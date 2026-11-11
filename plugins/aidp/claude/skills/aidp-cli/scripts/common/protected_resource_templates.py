# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
"""Build unresolved templates only; prompting and API execution stay in protected_aidp."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protected_aidp import MAX_TEMPLATE, PLACEHOLDER, ProtectedError, read_file, write_body_template


def required(mapping, *fields):
    if any(field not in mapping or mapping[field] is None or
           isinstance(mapping[field], str) and not mapping[field].strip() for field in fields):
        raise ProtectedError("MISSING_METADATA", "Supply the required non-sensitive metadata for the selected type.")


def prompt(label, visible=False):
    kind = "visible" if visible else "invisible"
    return "{" + kind + "_prompt_input:required:" + label + "}"


def private_key(path):
    if not path or any(char in path for char in "\r\n}"):
        raise ProtectedError("KEY_PATH_REQUIRED", "Supply --private-key-path; file contents are read only by the protected wrapper.")
    return "{textof:" + path + "}"


def protected_field(mapping, field):
    """Check an exact sensitive field from the selected payload contract."""
    if field in mapping and (not isinstance(mapping[field], str) or not PLACEHOLDER.fullmatch(mapping[field])):
        raise ProtectedError("INLINE_SECRET", "Use whole-value protected placeholders for this payload's sensitive fields; never include raw or masked secret values.")


def credentials(body, args):
    replacing = args.operation == "create" or args.replace_secrets
    if args.operation == "create":
        required(body, "displayName")
    if not replacing:
        if "credentialDetails" in body or "type" in body or args.type or args.secret_key or args.private_key_path:
            raise ProtectedError("REPLACEMENT_NOT_SELECTED", "Use --replace-secrets for a credential payload change; metadata-only updates must omit credentialDetails and type options.")
        return body
    if args.type not in ("SECRET_TOKEN", "SERVICE_ACCOUNT", "VAULT_REFERENCE"):
        raise ProtectedError("UNSUPPORTED_TYPE", "Select SECRET_TOKEN, SERVICE_ACCOUNT or VAULT_REFERENCE from the installed contract.")
    if body.get("type", args.type) != args.type:
        raise ProtectedError("TYPE_MISMATCH", "The metadata and selected credential type must agree.")
    details = body.setdefault("credentialDetails", {})
    if not isinstance(details, dict):
        raise ProtectedError("INVALID_METADATA", "credentialDetails must be an object.")
    if details.get("credentialType", args.type) != args.type:
        raise ProtectedError("TYPE_MISMATCH", "Both credential type discriminators must agree.")
    body["type"] = details["credentialType"] = args.type
    if args.type == "SECRET_TOKEN":
        for pair in details.get("secretTokenPair", []):
            protected_field(pair, "secretValue")
        keys = args.secret_key or [pair["secretKey"] for pair in details.get("secretTokenPair", [])]
        if not keys or len(set(keys)) != len(keys) or any(not isinstance(key, str) or not key.strip() for key in keys):
            raise ProtectedError("SECRET_KEYS_REQUIRED", "Supply one or more distinct non-empty --secret-key names.")
        details["secretTokenPair"] = [{"secretKey": key, "secretValue": prompt("Enter secret value `" + key + "`")}
                                     for key in keys]
    elif args.type == "SERVICE_ACCOUNT":
        protected_field(details, "privateKey")
        required(details, "userId", "tenancy", "region", "fingerprint")
        details["privateKey"] = private_key(args.private_key_path)
    else:
        required(details, "secretId")
    return body


SETTING_PUBLIC_FIELDS = {
    "GIT_ACCOUNT": {"type", "entityType", "providerName", "username"},
    "IAM_USER_CREDENTIAL": {"type", "tenancy", "region", "userId", "fingerprint"},
}
SETTING_REQUIRED_PUBLIC_FIELDS = {
    "GIT_ACCOUNT": ("entityType",),
    "IAM_USER_CREDENTIAL": ("tenancy", "region"),
}


def metadata_only_setting(body, args):
    current = copy.deepcopy(getattr(args, "current_setting", None) or {})
    if set(body) - {"name", "isDefault", "data"} or set(current) - {"name", "isDefault", "data"}:
        raise ProtectedError("INVALID_METADATA", "Supply only public setting name, default state and documented data fields; do not copy an unfiltered GET response.")
    data, current_data = body.get("data", {}), current.get("data", {})
    if not isinstance(data, dict) or not isinstance(current_data, dict) or args.private_key_path or args.secret_key:
        raise ProtectedError("REPLACEMENT_NOT_SELECTED", "Metadata-only updates cannot include credential inputs; select --replace-secrets for credential changes.")
    setting_type = args.type or data.get("type") or current_data.get("type")
    if setting_type not in SETTING_PUBLIC_FIELDS:
        raise ProtectedError("SETTING_TYPE_REQUIRED", "Supply the verified existing setting type through --type or public data.type; never guess it.")
    if any(item.get("type", setting_type) != setting_type for item in (data, current_data)):
        raise ProtectedError("TYPE_MISMATCH", "The current setting, data.type and --type must agree; metadata-only updates cannot change types.")
    allowed = SETTING_PUBLIC_FIELDS[setting_type]
    if set(data) - allowed or set(current_data) - allowed:
        raise ProtectedError("REPLACEMENT_NOT_SELECTED", "Supply only the selected type's public fields; secrets must not be included in metadata-only updates.")
    if current and any(key != "type" and current_data.get(key) != value for key, value in data.items()):
        raise ProtectedError("PUBLIC_SETTING_CHANGED", "Metadata-only updates preserve current connection data; select the intended credential-data update flow to change it.")
    merged = {**current, **body}
    merged_data = {**current_data, **data, "type": setting_type}
    required(merged, "isDefault")
    if type(merged["isDefault"]) is not bool:
        raise ProtectedError("INVALID_METADATA", "Retain the existing default state or explicitly choose a JSON boolean.")
    required(merged_data, *SETTING_REQUIRED_PUBLIC_FIELDS[setting_type])
    if any(not isinstance(value, str) or not value.strip() or PLACEHOLDER.fullmatch(value)
           for value in merged_data.values()):
        raise ProtectedError("INVALID_METADATA", "Public setting data must contain verified non-empty text values, not secret placeholders.")
    if "name" in merged:
        required(merged, "name")
    merged["data"] = merged_data
    return merged


def user_settings(body, args):
    if args.operation == "create":
        required(body, "name", "isDefault")
    if args.operation == "update" and not args.replace_secrets:
        return metadata_only_setting(body, args)
    if args.operation == "update":
        current = copy.deepcopy(getattr(args, "current_setting", None) or {})
        current_data, data = current.get("data", {}), body.get("data", {})
        if not isinstance(current_data, dict) or not isinstance(data, dict):
            raise ProtectedError("INVALID_METADATA", "Current and replacement setting data must be objects.")
        setting_type = args.type or data.get("type") or current_data.get("type")
        if setting_type not in SETTING_PUBLIC_FIELDS:
            raise ProtectedError("SETTING_TYPE_REQUIRED", "Supply the verified setting type through --type or data.type.")
        if any(item.get("type", setting_type) != setting_type for item in (data, current_data)):
            raise ProtectedError("TYPE_MISMATCH", "The current setting, replacement data and --type must agree.")
        if (set(current) - {"name", "isDefault", "data"}
                or set(current_data) - SETTING_PUBLIC_FIELDS[setting_type]):
            raise ProtectedError("INVALID_METADATA", "The current-setting snapshot must contain only documented public metadata.")
        if any(not isinstance(value, str) or not value.strip() or PLACEHOLDER.fullmatch(value)
               for value in current_data.values()):
            raise ProtectedError("INVALID_METADATA", "Current public data must contain verified text, not credentials or placeholders.")
        body = {**current, **body, "data": {**current_data, **data, "type": setting_type}}
        # The backend converts an omitted isDefault into false. Never guess:
        # use the snapshot's value unless the caller explicitly supplies one.
        if "isDefault" not in body:
            raise ProtectedError("DEFAULT_STATE_REQUIRED", "Supply the existing default state through --existing-metadata or explicitly retain it as isDefault in metadata.")
        if type(body["isDefault"]) is not bool:
            raise ProtectedError("INVALID_METADATA", "The retained or explicitly chosen default state must be a JSON boolean.")
        args.type = setting_type
    if args.type not in SETTING_PUBLIC_FIELDS:
        raise ProtectedError("UNSUPPORTED_TYPE", "Select GIT_ACCOUNT or IAM_USER_CREDENTIAL; OAUTH is an admin setting.")
    data = body.setdefault("data", {})
    if not isinstance(data, dict):
        raise ProtectedError("INVALID_METADATA", "Setting data must be an object.")
    if data.get("type", args.type) != args.type:
        raise ProtectedError("TYPE_MISMATCH", "The metadata and selected setting type must agree.")
    data["type"] = args.type
    if args.type == "GIT_ACCOUNT":
        protected_field(data, "personalAccessToken")
        required(data, "providerName")
        if data.get("entityType", "PERSONAL_ACCESS_TOKEN") != "PERSONAL_ACCESS_TOKEN":
            raise ProtectedError("UNSUPPORTED_ENTITY", "This helper supports PAT settings; discover linked-account flows separately.")
        data["entityType"] = "PERSONAL_ACCESS_TOKEN"
        data["username"] = prompt("Enter Git account username", visible=True)
        data["personalAccessToken"] = prompt("Enter Git personal access token")
    elif args.type == "IAM_USER_CREDENTIAL":
        protected_field(data, "privateApiKey")
        required(data, "userId", "tenancy", "region", "fingerprint")
        data["privateApiKey"] = private_key(args.private_key_path)
    return body


def agents(body, args):
    if args.operation == "create":
        required(body, "displayName", "pathInfo")
    if args.type or args.private_key_path or args.secret_key:
        raise ProtectedError("INVALID_OPTIONS", "Agent types and graph metadata belong in the input body; credential helper options do not apply.")

    for config, path in agent_auth_configs(body):
        auth = config.get("auth")
        if not isinstance(auth, dict) or auth.get("authType") not in ("BEARER_TOKEN", "OAUTH"):
            continue
        if auth["authType"] == "BEARER_TOKEN" and credential_reference(auth.get("token")):
            continue
        field = "token" if auth["authType"] == "BEARER_TOKEN" else "clientSecret"
        protected_field(auth, field)
        if args.operation != "create" and not args.replace_secrets:
            raise ProtectedError("REPLACEMENT_NOT_SELECTED", "Omit unchanged authentication from update bodies or select --replace-secrets for intended rotation.")
        if auth["authType"] == "BEARER_TOKEN":
            auth["token"] = prompt("Enter bearer token for " + pointer(path))
        else:
            required(auth, "clientId", "issuerIdpEndpoint")
            auth["clientSecret"] = prompt("Enter OAuth client secret for " + pointer(path))
    return body


def agent_auth_configs(body):
    """Visit reviewed HTTP/MCP payload locations, never arbitrary body/schema data."""
    diagram = body.get("diagram", {})
    if diagram is None:
        return
    if not isinstance(diagram, dict):
        raise ProtectedError("INVALID_METADATA", "Agent diagram must be an object.")

    def entries(name):
        registry = diagram.get(name)
        if registry is None:
            return ()
        if not isinstance(registry, dict):
            raise ProtectedError("INVALID_METADATA", "Agent tool and node registries must be objects when supplied.")
        return registry.items()

    def tool_config(tool, path):
        if not isinstance(tool, dict):
            raise ProtectedError("INVALID_METADATA", "Agent tools must be object definitions.")
        if tool.get("toolType") in (None, "HTTP", "MCP") and isinstance(tool.get("toolConfig"), dict):
            yield tool["toolConfig"], path + ("toolConfig",)

    for name, tool in entries("toolsMap"):
        yield from tool_config(tool, ("diagram", "toolsMap", name))
    for name, node in entries("nodes"):
        if not isinstance(node, dict):
            raise ProtectedError("INVALID_METADATA", "Agent nodes must be object definitions.")
        path = ("diagram", "nodes", name)
        if node.get("type") in (None, "HTTP_TOOL", "MCP_TOOL"):
            config = node.get("configuration")
            if isinstance(config, dict):
                yield config, path + ("configuration",)
                if isinstance(config.get("toolConfig"), dict):
                    yield config["toolConfig"], path + ("configuration", "toolConfig")
        if node.get("type") in (None, "AGENT", "SUPERVISOR_AGENT"):
            tools = node.get("tools")
            if tools is None:
                continue
            if not isinstance(tools, list):
                raise ProtectedError("INVALID_METADATA", "Inline agent tools must be an array when supplied.")
            for index, tool in enumerate(tools):
                yield from tool_config(tool, path + ("tools", str(index)))


def credential_reference(value):
    if not isinstance(value, str):
        return False
    try:
        reference = json.loads(value)
        return (isinstance(reference, dict) and set(reference) == {"displayName", "secretKey"}
                and all(isinstance(item, str) and item.strip() for item in reference.values()))
    except ValueError:
        return False


def pointer(path):
    return "".join("/" + part.replace("~", "~0").replace("/", "~1") for part in path)


def main(family, argv=None):
    parser = argparse.ArgumentParser(description="Prepare an unresolved protected body; no API or secret-file reads.")
    parser.add_argument("--operation", choices=("create", "update"), required=True)
    parser.add_argument("--metadata", required=True, help="Non-sensitive JSON body file, optionally prefixed by @")
    parser.add_argument("--output", required=True, help="Fresh unresolved JSON template path")
    parser.add_argument("--type")
    parser.add_argument("--replace-secrets", action="store_true")
    parser.add_argument("--secret-key", action="append", default=[])
    parser.add_argument("--private-key-path")
    parser.add_argument("--existing-metadata", help="Verified non-sensitive current user-setting snapshot; never an unfiltered GET response")
    args = parser.parse_args(argv)
    try:
        body = json.loads(read_file(args.metadata.removeprefix("@"), MAX_TEMPLATE))
        if not isinstance(body, dict) or not body:
            raise ProtectedError("INVALID_METADATA", "Supply a non-empty JSON body object.")
        args.current_setting = None
        if args.existing_metadata:
            if family != "user-settings" or args.operation != "update":
                raise ProtectedError("INVALID_OPTIONS", "--existing-metadata is only for user-setting updates.")
            current = json.loads(read_file(args.existing_metadata.removeprefix("@"), MAX_TEMPLATE))
            if not isinstance(current, dict) or not current:
                raise ProtectedError("INVALID_METADATA", "Supply a non-empty public current-setting snapshot.")
            args.current_setting = current
        # Each payload handler checks only its documented sensitive fields.
        body = {"credentials": credentials, "user-settings": user_settings, "agents": agents}[family](copy.deepcopy(body), args)
        # Validate placeholder syntax, but intentionally do not open attachments.
        def check(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if "{" in key:
                        raise ProtectedError("INVALID_METADATA", "JSON keys must not contain placeholders.")
                    check(item)
            elif isinstance(value, list):
                for item in value:
                    check(item)
            elif isinstance(value, str) and "_prompt_input:" in value:
                from protected_aidp import prompt_spec
                match = PLACEHOLDER.fullmatch(value)
                if not match:
                    raise ProtectedError("INVALID_PROMPT", "Use a whole-value protected prompt placeholder.")
                prompt_spec(*match.groups())
        check(body)
        output = Path(args.output).expanduser()
        write_body_template(output, body)
        print(json.dumps({"ok": True, "templatePath": str(output)}))
        return 0
    except ProtectedError as error:
        print(json.dumps({"ok": False, "errorCode": error.code, "error": str(error)}))
    except FileExistsError:
        print('{"ok":false,"errorCode":"OUTPUT_EXISTS","error":"Choose a fresh template filename; existing files are never overwritten."}')
    except Exception:
        print('{"ok":false,"errorCode":"TEMPLATE_FAILED","error":"Could not prepare the template; input excerpts are suppressed."}')
    return 1
