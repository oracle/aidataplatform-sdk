#!/usr/bin/env python3
"""Generate a CLI reference from the aidp-cli installed in this Python environment."""

from __future__ import annotations

import argparse
import errno
import json
import os
import sys
import tempfile
import time
from contextlib import contextmanager
from importlib import metadata
from pathlib import Path
from typing import Dict, Iterable, List

try:
    import fcntl
except ImportError:  # Windows uses msvcrt for the same file lock.
    fcntl = None


# Self-contained copy of the CLI renderer in tools/generate_release_docs.py.
def render_cli_doc(manifest: dict) -> str:
    lines: List[str] = ["<a id=\"top\"></a>",
                        "# AIDP CLI Command Reference",
                        "This guide summarizes the command groups, commands, options, and payload requirements exposed by the `aidp` command-line interface."]
    lines.extend([
        "## Security guidance",
        "- Treat PAR URLs and signed URLs returned by commands as bearer access material. Redact them from logs, tickets, and support bundles.",
        "- Do not commit OCI configuration files, private keys, session-token files, or request bodies containing credentials. Avoid `--debug` when command output could contain sensitive request or response data.",
        "- Use `--endpoint` only with a trusted, approved service endpoint. Prefer region-based endpoint resolution when an explicit endpoint is not required.",
        "- Use short-lived, workload-scoped OCI identities and least-privilege permissions where available. Review destructive commands carefully before running them.",
    ])
    lines.append("## Global Options")
    lines.extend([
        "- `--debug` — enable debug logging",
        "- `--profile` / `-p` — OCI config profile (default `DEFAULT`)",
        "- `--auth` — authentication mode (`api_key`, `security_token`, `instance_principal`, `resource_principal`; default `security_token`)",
        "- `--config-file` — path to OCI config file",
        "- `--region` — OCI region override",
        "- `--endpoint` — data plane endpoint override (default `https://aidp.<region>.oci.oraclecloud.com`)",
        "- `--instance-id` — AIDP instance OCID",
        "- `--timeout` — connection/read timeout in seconds",
    ])

    lines.append("## Utility Commands")
    lines.extend([
        "- `aidp command-groups` — list API command groups",
        "- `aidp search <term>` — fuzzy-search command names and descriptions",
        "- `aidp configure` — set default profile, instance OCID, and other settings",
        "- `aidp help [group|command]` — show contextual help",
        "- `aidp version` — print CLI version",
    ])

    groups = manifest.get("commandGroups", [])
    lines.append("## Command Index")
    for group in groups:
        display = format_group_display(group["name"])
        anchor = group_anchor(group["name"])
        lines.append(f"- [{display}](#{anchor})")

    for group in groups:
        display = format_group_display(group["name"])
        anchor = group_anchor(group["name"])
        lines.append(f"\n## <a id=\"{anchor}\"></a>{display}")
        if group.get("description"):
            lines.append(group["description"])
        lines.append("**Command Index:**")
        for command in group.get("commands", []):
            cmd_anchor = command_anchor(group["name"], command["name"])
            lines.append(f"- [{group['name']} {command['name']}](#{cmd_anchor})")
        lines.append("### Commands")
        for command in group.get("commands", []):
            lines.extend(render_cli_command(group["name"], command))
    return "\n".join(lines).strip() + "\n"


def render_cli_command(group: str, command: dict) -> List[str]:
    lines: List[str] = []
    anchor = command_anchor(group, command["name"])
    lines.append(f"\n#### `aidp {group} {command['name']}`")
    lines.append(f"<a id=\"{anchor}\"></a>")
    if command.get("summary"):
        lines.append(command["summary"])
    if command.get("description") and command["description"] != command.get("summary"):
        lines.append(command["description"])
    lines.append("\n**Usage:**\n")
    lines.append(f"`{build_cli_usage(group, command)}`\n")

    path_fields = cli_argument_fields(command)
    if path_fields:
        lines.append("**Path Arguments:**")
        lines.extend(format_cli_fields(path_fields))
    option_fields = cli_option_fields(command)
    if option_fields:
        lines.append("**Options:**")
        lines.extend(format_cli_fields(option_fields))
    if command.get("bodyModels"):
        lines.extend(render_cli_body_models(command["bodyModels"]))
    elif command.get("bodyFields"):
        lines.append("**Request Body:**")
        lines.extend(format_cli_fields(command["bodyFields"]))
    lines.append("---")
    lines.append(f"**Return:** [Back to {group.title()}](#{group}) • [Top](#top)")
    return lines


def cli_argument_fields(command: dict) -> List[dict]:
    return [
        field for field in command.get("fields", [])
        if field.get("in") == "path"
        and field.get("required")
        and field.get("name") != "ai_data_platform_id"
    ]


def cli_option_fields(command: dict) -> List[dict]:
    argument_names = {field["name"] for field in cli_argument_fields(command)}
    return [
        field for field in command.get("fields", [])
        if field.get("in") != "body"
        and field.get("name") != "ai_data_platform_id"
        and field.get("name") not in argument_names
    ]


def build_cli_usage(group: str, command: dict) -> str:
    parts = ["aidp", group, command["name"]]
    for field in cli_argument_fields(command):
        cli_name = field.get("cliName") or field.get("name")
        parts.append(f"<{cli_name.upper()}>")
    if any(
        field.get("name") == "ai_data_platform_id" and field.get("required")
        for field in command.get("fields", [])
    ):
        parts.append("--instance-id <AI-DATA-PLATFORM-ID>")
    for field in cli_option_fields(command):
        if field.get("required"):
            cli_name = field.get("cliName") or field.get("name").replace("_", "-")
            value_name = {"path": "target-path", "maven-search-query": "text"}.get(cli_name, cli_name)
            parts.append(f"--{cli_name} <{value_name}>")
    if any(field.get("in") == "body" for field in command.get("fields", [])):
        parts.append("--body @<local-file>" if cli_uses_raw_body(command) else "--body <JSON>")
    return " ".join(parts)


def cli_uses_raw_body(command: dict) -> bool:
    return (
        any(field.get("in") == "body" for field in command.get("fields", []))
        and not command.get("bodyModels")
        and not command.get("bodyFields")
    )


def format_cli_fields(fields: Iterable[dict]) -> List[str]:
    out: List[str] = []
    for field in fields:
        cli_name = field.get("cliName") or field.get("cli_name") or field.get("name")
        f_type = field.get("type", "string")
        required = "required" if field.get("required") else "optional"
        desc = field.get("description", "")
        out.append(f"- `{cli_name}` ({f_type}, {required}) — {desc}")
    return out


def render_cli_body_models(models: dict) -> List[str]:
    lines: List[str] = []
    selectors = variant_selectors(models)
    for model_name, details in models.items():
        fields = details.get("fields", [])
        if not fields:
            continue
        lines.append("")
        lines.append(f"**Request Body (`{model_name}`):**")
        enum_fields = {name: values for name, values in details.get("enumFields", {}).items()}
        selector = selectors.get(model_name)
        for field in fields:
            name = field.get("name")
            f_type = field.get("type", "string")
            required = "required" if field.get("required") else "optional"
            enum_values = field.get("enumValues") or enum_fields.get(name) or []
            description = describe_body_field(field.get("description") or "", enum_values)
            if selector and name == selector[0]:
                description = append_sentence(description, f"Must be `{selector[1]}` for this variant.")
            lines.append(f"- `{name}` ({f_type}, {required}) — {description}".strip())
        variants = details.get("variants", [])
        if variants:
            lines.append("")
            lines.append(f"**Variants** (selected by `{variants[0].get('discriminatorField')}`):")
            for variant in variants:
                lines.append(f"- `{variant.get('discriminatorValue')}` → `{variant.get('modelName')}`")
        fixed_values = {selector[0]: selector[1]} if selector else {}
        example = build_cli_body_example(model_name, fields, enum_fields, fixed_values)
        if example:
            lines.append("")
            lines.append("**Example:**")
            lines.append("```json")
            lines.append(example)
            lines.append("```")
    return lines


def variant_selectors(models: dict) -> Dict[str, tuple[str, object]]:
    # Maps each variant model to the discriminator field and value its parent selects it by.
    selectors: Dict[str, tuple[str, object]] = {}
    for details in models.values():
        for variant in details.get("variants", []):
            field = variant.get("discriminatorField")
            if field and variant.get("modelName"):
                selectors.setdefault(variant["modelName"], (field, variant.get("discriminatorValue")))
    return selectors


def describe_body_field(description: str, enum_values: List[object]) -> str:
    # The example shows only the first enum value, so list them all here unless the
    # description already does.
    if not enum_values or "allowed values" in description.lower():
        return description
    return append_sentence(description, f"Allowed values: {', '.join(str(value) for value in enum_values)}.")


def append_sentence(description: str, sentence: str) -> str:
    description = description.strip().rstrip(".")
    return f"{description}. {sentence}" if description else sentence


def build_cli_body_example(
    model_name: str,
    fields: List[dict],
    enum_fields: Dict[str, List[str]],
    fixed_values: Dict[str, object] | None = None,
) -> str:
    example: Dict[str, object] = {}
    enum_fields = enum_fields or {}
    fixed_values = fixed_values or {}
    for field in fields:
        name = field.get("name")
        f_type = field.get("type", "string")
        if name in fixed_values:
            example[name] = fixed_values[name]
            continue
        enum_values = field.get("enumValues") or enum_fields.get(name) or []
        example[name] = example_value_for_type(f_type, enum_values)
    if not example:
        return ""
    return json.dumps(example, indent=2)


def example_value_for_type(f_type: str, enum_values: List[str]) -> object:
    if f_type.lower() == "array":
        return [enum_values[0]] if enum_values else []
    if enum_values:
        return enum_values[0]
    mapping = {
        "string": "<string>",
        "str": "<string>",
        "int": 0,
        "integer": 0,
        "number": 0,
        "float": 0,
        "bool": True,
        "boolean": True,
        "array": [],
        "object": {}
    }
    return mapping.get(f_type.lower(), "<string>")


def format_group_display(name: str) -> str:
    cleaned = name.replace("-", " ").replace("_", " ")
    if cleaned.lower() == "mlops":
        return "ML Ops"
    words = cleaned.split()
    return " ".join(word.capitalize() for word in words)


def group_anchor(name: str) -> str:
    return name.replace(" ", "-")


def command_anchor(group: str, command: str) -> str:
    return f"{group}-{command}".replace(" ", "-")




MANIFEST_PATH = "aidp_cli/operation_manifest.json"
LOCK_PATH = (
    Path(tempfile.gettempdir()) / "GenerateAIDPCLIDoc.lock"
    if os.name == "nt"
    else Path(f"/tmp/GenerateAIDPCLIDoc-{os.getuid()}.lock")
)


@contextmanager
def generation_lock():
    with LOCK_PATH.open("a+b") as lock_file:
        if fcntl is not None:
            try:
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("Another CLI doc generation is running; waiting for it to finish.")
                fcntl.flock(lock_file, fcntl.LOCK_EX)
            yield
        else:
            import msvcrt

            lock_file.seek(0)
            waiting = False
            while True:
                try:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    busy = getattr(exc, "winerror", None) in (33, 36) or exc.errno in (
                        errno.EACCES, errno.EAGAIN
                    )
                    if not busy:
                        raise
                    if not waiting:
                        print("Another CLI doc generation is running; waiting for it to finish.")
                        waiting = True
                    time.sleep(0.1)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)


def installed_cli() -> tuple[str, dict]:
    try:
        distribution = metadata.distribution("aidp-cli")
    except metadata.PackageNotFoundError as exc:
        raise RuntimeError(
            f"aidp-cli is not installed for {sys.executable}"
        ) from exc

    version = distribution.version
    manifest_path = Path(distribution.locate_file(MANIFEST_PATH))
    if not manifest_path.is_file():
        raise RuntimeError(
            f"Installed aidp-cli {version} has no {MANIFEST_PATH}; "
            "cannot generate its CLI reference"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read installed CLI manifest: {exc}") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("commandGroups"), list):
        raise RuntimeError("Installed CLI manifest has an unsupported format")
    return version, manifest


def generate(output_dir: Path) -> Path | None:
    try:
        version = metadata.version("aidp-cli")
    except metadata.PackageNotFoundError as exc:
        raise RuntimeError(f"aidp-cli is not installed for {sys.executable}") from exc

    if not version or any(char in version for char in "/\\"):
        raise RuntimeError(f"Invalid installed aidp-cli version: {version!r}")
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"aidp-cli-{version}.md"
    if target.exists():
        print(f"Doc already exists: {target}")
        return None

    with generation_lock():
        # Recheck after locking: another process may have created this file.
        if target.exists():
            print(f"Doc already exists: {target}")
            return None
        installed_version, manifest = installed_cli()
        if installed_version != version:
            raise RuntimeError("Installed aidp-cli version changed during generation; retry")
        markdown = render_cli_doc(manifest)

        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=output_dir,
                prefix=f".{target.name}.", suffix=".tmp", delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(markdown)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.chmod(temporary_path, 0o644)
            # A hard link creates the final name only if it does not exist.
            os.link(temporary_path, target)
        except FileExistsError:
            print(f"Doc already exists: {target}")
            return None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    print(f"Generated: {target}")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputDir", required=True, type=Path, help="Directory for the versioned Markdown file")
    args = parser.parse_args()
    try:
        generate(args.outputDir.expanduser().resolve())
    except (OSError, RuntimeError, KeyError, TypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
