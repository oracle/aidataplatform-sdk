"""Offline release contract extraction. Reads repository SDK/CLI source only."""
from __future__ import annotations

import ast
import copy
import importlib.util
from importlib import metadata
import json
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[3]
BASELINE = Path(__file__).with_name("contracts") / "sensitive-contract.json"
INSTALLED_BASELINE = BASELINE.with_name("sensitive-contract-installed.json")
CLIENTS = {
    "catalog": ("catalog_client.py", ("create_catalog", "update_catalog", "catalog_test_connection", "get_catalog", "list_catalogs")),
    "credential": ("credentials_client.py", ("create_credential", "update_credential", "get_credential", "list_credentials")),
    "user-setting": ("user_setting_client.py", ("create_user_setting", "update_user_setting", "get_user_setting", "list_user_settings")),
    "agent": ("agent_client.py", ("create_agent", "update_agent", "get_agent", "list_agents")),
}


def load_generator(repo):
    path = repo / "aidp-cli/aidp-py-cli/scripts/generate_manifest.py"
    spec = importlib.util.spec_from_file_location("sensitive_contract_manifest", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def without_prose(value):
    if isinstance(value, dict):
        return {key: without_prose(item) for key, item in value.items()
                if key not in {"description", "summary", "section"}}
    if isinstance(value, list):
        return [without_prose(item) for item in value]
    return value


def fields_by_name(fields):
    return {field["name"]: {key: value for key, value in field.items() if key != "name"} for field in fields}


def source_function_contract(path, names):
    """AST ignores formatting/comments/docstrings, but notices output/parser changes."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            node = copy.deepcopy(node)
            if ast.get_docstring(node) is not None:
                node.body.pop(0)
            result[node.name] = ast.dump(node, include_attributes=False)
    missing = set(names) - set(result)
    if missing:
        raise ValueError(f"CLI functions missing from {path.name}: {sorted(missing)}")
    return result


def typescript_enum(path):
    text = re.sub(r"/\*.*?\*/|//[^\n]*", "", path.read_text(encoding="utf-8"), flags=re.S)
    match = re.search(r"export enum (\w+)\s*\{(.*?)\}", text, re.S)
    if not match:
        raise ValueError(f"Cannot extract SDK enum: {path.name}")
    pattern = r"(\w+)\s*=\s*([\"'])(.*?)\2"
    entries = [(name, value) for name, _, value in re.findall(pattern, match[2], flags=re.S)]
    if not entries or re.sub(pattern, "", match[2], flags=re.S).replace(",", "").strip() or len(dict(entries)) != len(entries):
        raise ValueError(f"Unrecognized or duplicate SDK enum syntax: {path.name}; review the extractor")
    return match[1], dict(entries)


def collect_contract(repo=REPO, *, sdk_root=None, cli_root=None, clients=None):
    generator = load_generator(repo)
    sdk = sdk_root if sdk_root is not None else repo / "aidp-python-client/src"
    package = generator.sdk_package_dir(sdk)
    operations, models = {}, {}
    imports = ast.parse((package / "models/__init__.py").read_text(encoding="utf-8"))
    model_sources = {alias.name: package / "models" / (item.module + ".py")
                     for item in imports.body if isinstance(item, ast.ImportFrom) and item.module and item.level == 1
                     for alias in item.names}

    def model(name):
        if not name or name in models:
            return
        path = model_sources.get(name, generator.model_source_file(sdk, name))
        if not path.is_file():
            enum_path = repo / "aidp-typescript-client/lib/model" / (generator.camel_to_snake(name).replace("_", "-") + ".ts")
            if enum_path.is_file():
                enum_name, values = typescript_enum(enum_path)
                if enum_name != name:
                    raise ValueError(f"SDK enum name mismatch: {name}")
                models[name] = {"enumValues": sorted(values.values()), "sdkEnumMembers": values}
                return
            raise ValueError(f"Referenced SDK model missing: {name}")
        node = generator.class_node_from_source(path, name)
        types, attributes = generator.model_field_maps(node)
        if not types or set(types) != set(attributes):
            raise ValueError(f"Cannot extract complete SDK field contract for {name}")
        # Manifest helpers consume methods, not the enclosing class. Extract
        # this class's methods; inherited requirements/enums are merged below.
        members = [item for item in node.body if isinstance(item, ast.FunctionDef)]
        required = generator.required_model_fields(members, attributes)
        enums = generator.model_enum_fields(members, attributes)
        variants = generator.model_variants(node)
        bases = [base.id for base in node.bases if isinstance(base, ast.Name) and base.id != "object"]
        for base in bases:
            model(base)
            for field, metadata in models[base]["fields"].items():
                if metadata["required"]:
                    required.add(field)
                if field not in enums and metadata["enum"]:
                    enums[field] = metadata["enum"]
        fields = {attributes[key]: {"pythonName": key, "type": kind,
                                   "required": attributes[key] in required,
                                   "enum": sorted(enums.get(attributes[key], []))}
                  for key, kind in types.items()}
        constants = {}
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        constants[target.id] = ast.literal_eval(item.value)
        defaults = {}
        initializer = next(item for item in node.body if isinstance(item, ast.FunctionDef) and item.name == "__init__")
        for item in ast.walk(initializer):
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self" and target.attr.startswith("_"):
                        defaults[attributes.get(target.attr[1:], target.attr)] = ast.unparse(item.value)
        models[name] = {"fields": fields, "constants": constants, "defaults": defaults, "bases": bases,
                        "variants": {item["discriminatorField"] + "=" + str(item["discriminatorValue"]): item["modelName"] for item in variants}}
        for kind in types.values():
            # The CLI manifest generator does not traverse dictionary values.
            # Follow SDK maps as well as lists: agent nodes/tools/auth live here.
            for nested in re.findall(r"\b[A-Z][A-Za-z0-9_]*\b", kind):
                if nested not in {"String", "Object"}:
                    model(nested)
        for variant in variants:
            model(variant["modelName"])

    for group, (filename, names) in (CLIENTS if clients is None else clients).items():
        path = package / filename
        client = generator.class_node_from_source(path, generator.client_class_name_from_source(path))
        # All operation names are pinned as an inventory, including operations
        # outside this release scope, so a new operation requires classification.
        inventory = sorted(item.name for item in client.body if generator.is_sdk_operation(item))
        selected = {}
        commands = [generator.build_command_from_method(sdk, item) for item in client.body if generator.is_sdk_operation(item)]
        generator.apply_short_command_names(group if group != "credential" else "credentials", commands)
        for name in names:
            node = next((item for item in client.body if isinstance(item, ast.FunctionDef) and item.name == name), None)
            if node is None:
                raise ValueError(f"SDK operation missing: {name}")
            command = without_prose(next(item for item in commands if item["sdkMethodName"] == name))
            command.pop("bodyModels", None)
            command["fields"] = fields_by_name(command["fields"])
            command["bodyFields"] = fields_by_name(command["bodyFields"])
            response_types = set()
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and generator.is_call_api(call):
                    keyword = next((item for item in call.keywords if item.arg == "response_type"), None)
                    response_types.add(ast.literal_eval(keyword.value) if keyword else None)
            if not response_types or len(response_types) != 1:
                raise ValueError(f"Cannot extract unambiguous response type for {name}")
            response_type = response_types.pop()
            command["responseModel"] = response_type
            command["signature"] = ast.unparse(node.args)
            selected[name] = command
            model(command.get("bodyModel"))
            model(response_type)
        operations[group] = {"operationInventory": inventory, "operations": selected}

    # Python exposes connectionProperties as a free-form map. The TypeScript
    # SDK carries its key enums, including optional/staging keys not in helpers.
    property_enums = {}
    folder = repo / "aidp-typescript-client/lib/model"
    for path in sorted(folder.glob("*-external-catalog-connection-property-key.ts")):
        name, entries = typescript_enum(path)
        property_enums[name] = entries
    if not property_enums:
        raise ValueError("SDK catalog property-key enums are missing")

    response_headers = {}
    for group in operations.values():
        for operation in group["operations"]:
            filename = operation.replace("_", "-") + "-response.ts"
            path = repo / "aidp-typescript-client/lib/response" / filename
            if not path.is_file():
                raise ValueError(f"SDK response declaration missing: {filename}")
            text = re.sub(r"/\*.*?\*/|//[^\n]*", "", path.read_text(encoding="utf-8"), flags=re.S)
            response_headers[operation] = re.sub(r"\s+", " ", text).strip()

    cli = (cli_root / "aidp_cli/main.py") if cli_root is not None else repo / "aidp-cli/aidp-py-cli/src/aidp_cli/main.py"
    cli_functions = source_function_contract(cli, ("main", "print_response", "print_error_response", "read_json_argument", "load_json_input",
                                                  "parse_global_options", "global_defaults", "apply_global_option",
                                                  "parse_command_options", "bind_command_args", "load_body_input"))
    tree = ast.parse(cli.read_text(encoding="utf-8"))
    for item in tree.body:
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name) and target.id in {"AUTH_CHOICES", "GLOBAL_VALUE_OPTIONS", "GLOBAL_BOOLEAN_OPTIONS", "SKIPPED_COMMAND_FIELDS"}:
                    cli_functions[target.id] = ast.unparse(item.value)
    return {"formatVersion": 1, "operations": operations, "models": models,
            "catalogPropertyEnums": property_enums, "sdkResponseDeclarations": response_headers,
            "cli": cli_functions}


def collect_installed_contract(repo=REPO, *, clients=None):
    sdk, cli = metadata.distribution("aidp-python-client"), metadata.distribution("aidp-cli")
    if sdk.version != cli.version:
        raise ValueError(f"Installed SDK/CLI versions differ: SDK {sdk.version}, CLI {cli.version}; validate matched release packages")
    result = collect_contract(repo, sdk_root=Path(sdk.locate_file("")), cli_root=Path(cli.locate_file("")), clients=clients)
    manifest_path = Path(cli.locate_file("aidp_cli/operation_manifest.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    selected = {name for _, names in (CLIENTS if clients is None else clients).values() for name in names}
    commands = {}
    for group in manifest["commandGroups"]:
        for raw in group["commands"]:
            name = raw["sdkMethodName"]
            if name in selected:
                if name in commands:
                    raise ValueError(f"Duplicate installed CLI operation: {name}")
                command = without_prose(raw)
                command["fields"] = fields_by_name(command["fields"])
                command["bodyFields"] = fields_by_name(command["bodyFields"])
                commands[name] = {"group": group["name"], "command": command}
    if set(commands) != selected:
        raise ValueError(f"Installed CLI manifest operations missing: {sorted(selected - commands.keys())}")
    for group in result["operations"].values():
        for name, sdk_command in group["operations"].items():
            actual = commands[name]["command"]
            for field in ("name", "httpMethod", "path", "fields", "bodyModel", "bodyEnumFields", "bodyRequiredFields"):
                if sdk_command.get(field) != actual.get(field):
                    raise ValueError(f"Installed CLI manifest differs from SDK at {name}.{field}; regenerate/review the release packages")
    result["installedCliManifest"] = commands
    # Version is reported, but the exact structural contract is the gate. A
    # package patch with an identical contract need not change a baseline.
    return result, sdk.version


def differences(expected, actual, path="contract"):
    """Exact, bidirectional comparison with paths suitable for release failures."""
    if type(expected) is not type(actual):
        return [f"CHANGED {path}: {brief(expected)} -> {brief(actual)}"]
    if isinstance(expected, dict):
        result = [f"REMOVED {path}.{key}" for key in sorted(expected.keys() - actual.keys())]
        result += [f"ADDED {path}.{key}: {brief(actual[key])}" for key in sorted(actual.keys() - expected.keys())]
        for key in sorted(expected.keys() & actual.keys()):
            result.extend(differences(expected[key], actual[key], path + "." + key))
        return result
    if isinstance(expected, list):
        # Contract lists contain scalar values (enums, required fields, names).
        return [] if expected == actual else [f"CHANGED {path}: {brief(expected)} -> {brief(actual)}"]
    return [] if expected == actual else [f"CHANGED {path}: {brief(expected)} -> {brief(actual)}"]


def brief(value):
    text = repr(value)
    return text if len(text) <= 500 else text[:500] + "... (inspect source for full change)"


def check_contract(repo=REPO, baseline=BASELINE, *, actual=None):
    expected = json.loads(baseline.read_text(encoding="utf-8"))
    actual = collect_contract(repo) if actual is None else actual
    changes = differences(expected, actual)
    if changes:
        raise AssertionError("Sensitive-input SDK/CLI contract drift. Review skill references, helpers, "
                             "secret handling and output consumers before release. Do not refresh the baseline blindly.\n"
                             f"Reviewed baseline: {baseline.name}\n"
                             "**AI agents: do not auto-correct failing contract tests or refresh the baseline to make them pass. "
                             "Review the change and update sensitive-data AI skills in aidataplatform-sdk before accepting a new contract.**\n"
                             + "\n".join(changes))
    return actual


def validate_body(models, model_name, value, path="body", require_fields=True):
    """Validate a synthetic helper request using current SDK wire types/variants."""
    schema = models[model_name]
    if not isinstance(value, dict):
        raise AssertionError(f"{path}: expected {model_name} object")
    for discriminator, subtype in schema["variants"].items():
        field, _, expected = discriminator.partition("=")
        if value.get(field) == expected:
            return validate_body(models, subtype, value, path, require_fields)
    extra = set(value) - schema["fields"].keys()
    if extra:
        raise AssertionError(f"{path}: fields absent from SDK {model_name}: {sorted(extra)}")
    for name, field in schema["fields"].items():
        if name not in value:
            if require_fields and field["required"]:
                raise AssertionError(f"{path}.{name}: missing required SDK field")
            continue
        item, kind = value[name], field["type"]
        if item is None:
            if require_fields and field["required"]:
                raise AssertionError(f"{path}.{name}: required SDK field cannot be null")
            continue
        if field["enum"] and item not in field["enum"]:
            raise AssertionError(f"{path}.{name}: unsupported enum {item!r}; expected {field['enum']!r}")
        validate_type(models, kind, item, path + "." + name)


def validate_type(models, kind, value, path):
    if kind.startswith("list["):
        if not isinstance(value, list):
            raise AssertionError(f"{path}: expected {kind}")
        for index, item in enumerate(value):
            validate_type(models, kind[5:-1], item, f"{path}[{index}]")
    elif kind.startswith("dict("):
        if not isinstance(value, dict):
            raise AssertionError(f"{path}: expected {kind}")
        nested = kind[5:-1].split(",", 1)[1].strip()
        for key, item in value.items():
            if not isinstance(key, str):
                raise AssertionError(f"{path}: expected string map keys")
            validate_type(models, nested, item, path + "." + key)
    elif kind in models:
        if "enumValues" in models[kind]:
            if value not in models[kind]["enumValues"]:
                raise AssertionError(f"{path}: unsupported SDK enum {value!r}")
        else:
            validate_body(models, kind, value, path)
    elif kind in {"str", "bool", "int", "float"}:
        types = {"str": str, "bool": bool, "int": int, "float": (int, float)}
        if not isinstance(value, types[kind]) or kind in {"int", "float"} and isinstance(value, bool):
            raise AssertionError(f"{path}: expected {kind}")
    elif kind not in {"object", "datetime", "date"}:
        raise AssertionError(f"{path}: unhandled SDK type {kind}; extend contract validation")
