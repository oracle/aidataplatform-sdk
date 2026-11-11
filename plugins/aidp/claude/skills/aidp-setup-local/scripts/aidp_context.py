#!/usr/bin/env python3
# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
"""Safely read and update non-identity cross-session AIDP context."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from platform_support import private_open, restrict_directory, exclusive_lock, readonly_open


SCHEMA_VERSION = 2
MAX_ENDPOINTS = 5
MAX_RECENT_INSTANCES = 10
STANDARD_ENDPOINT_TEMPLATE = "https://aidp.{region}.oci.oraclecloud.com"

PROFILE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
RESOURCE_TYPE_RE = re.compile(r"^[a-z][a-z0-9-]{0,127}$")
REALM_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
REGION_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+-\d+$")
HOST_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
INSTANCE_OCID_RE = re.compile(
    r"^ocid1\.([a-z][a-z0-9-]*)\.([a-z0-9-]+)\.([a-z0-9-]+)\.([A-Za-z0-9._-]+)$"
)
ALLOWED_FIELDS = {
    "schemaVersion",
    "lastUsedAuth",
    "endpoints",
    "recentlyUsedAIDP",
    "latestVersionCheck",
    "pythonCli",
    "ociCli",
}
LEGACY_FIELDS = {"consent", "userOcids"}


class ContextError(Exception):
    def __init__(self, code: str, message: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code


def _context_path() -> Path:
    override = os.environ.get("AIDP_CONTEXT_FILE")
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute():
            raise ContextError(
                "invalid_context_path",
                "AIDP_CONTEXT_FILE must be an absolute path.",
            )
        return path
    return Path.home() / ".config" / "aidp" / "context.json"


def _empty_context() -> dict[str, Any]:
    return {"schemaVersion": SCHEMA_VERSION}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _emit(value: Any) -> None:
    json.dump(value, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def _emit_error(error: ContextError) -> None:
    json.dump(
        {"error": {"code": error.code, "message": error.message}},
        sys.stderr,
        ensure_ascii=False,
    )
    sys.stderr.write("\n")


def _require_dict(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContextError("invalid_context", f"{field} must be a JSON object.")
    return value


def _validate_timestamp(value: Any, field: str) -> None:
    if not isinstance(value, str):
        raise ContextError("invalid_context", f"{field} must be a timestamp.")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ContextError(
            "invalid_context", f"{field} must be an ISO-8601 timestamp."
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContextError(
            "invalid_context", f"{field} must include a timezone."
        )


def _validate_document(document: Any) -> dict[str, Any]:
    data = _require_dict(document, "context")
    version = data.get("schemaVersion")
    if version != SCHEMA_VERSION:
        raise ContextError(
            "unsupported_schema",
            f"Unsupported AIDP context schema version: {version!r}.",
        )

    unexpected = set(data) - ALLOWED_FIELDS
    if unexpected:
        raise ContextError(
            "invalid_context",
            "Context contains unsupported fields: " + ", ".join(sorted(unexpected)),
        )

    auth = data.get("lastUsedAuth")
    if auth is not None:
        auth_obj = _require_dict(auth, "lastUsedAuth")
        if auth_obj.get("authType") not in {"security_token", "api_key"}:
            raise ContextError(
                "invalid_context", "lastUsedAuth.authType is invalid."
            )
        if not isinstance(auth_obj.get("profile"), str):
            raise ContextError(
                "invalid_context", "lastUsedAuth.profile must be a string."
            )
        _validate_profile(auth_obj["profile"])
        config_path = auth_obj.get("configFilePath")
        if config_path is not None and not isinstance(config_path, str):
            raise ContextError(
                "invalid_context",
                "lastUsedAuth.configFilePath must be a string or null.",
            )
        if config_path is not None and not Path(config_path).is_absolute():
            raise ContextError(
                "invalid_context",
                "lastUsedAuth.configFilePath must be absolute.",
            )
        _validate_timestamp(
            auth_obj.get("lastValidatedAt"), "lastUsedAuth.lastValidatedAt"
        )

    endpoints = data.get("endpoints")
    if endpoints is not None:
        endpoint_obj = _require_dict(endpoints, "endpoints")
        for key, entries in endpoint_obj.items():
            if not isinstance(key, str) or not isinstance(entries, list):
                raise ContextError(
                    "invalid_context", "Each endpoints entry must be an array."
                )
            if not all(isinstance(entry, dict) for entry in entries):
                raise ContextError(
                    "invalid_context", "Endpoint records must be JSON objects."
                )
            parts = key.split(":")
            if len(parts) != 2:
                raise ContextError(
                    "invalid_context", "Endpoint group keys must be realm:resourceType."
                )
            realm = _validate_realm(parts[0])
            resource_type = _validate_resource_type(parts[1])
            if key != f"{realm}:{resource_type}":
                raise ContextError(
                    "invalid_context", "Endpoint group keys must be normalized."
                )
            limit = 1 if resource_type == "aidataplatform" else MAX_ENDPOINTS
            if len(entries) > limit:
                raise ContextError(
                    "invalid_context", "An endpoint group exceeds its MRU limit."
                )
            seen_templates: set[str] = set()
            for index, entry in enumerate(entries):
                template = entry.get("template")
                if not isinstance(template, str):
                    raise ContextError(
                        "invalid_context", "Endpoint template must be a string."
                    )
                normalized = _normalize_https_url(template, True)
                if normalized != template:
                    raise ContextError(
                        "invalid_context", "Endpoint templates must be normalized."
                    )
                if (
                    resource_type == "aidataplatform"
                    and template != STANDARD_ENDPOINT_TEMPLATE
                ):
                    raise ContextError(
                        "invalid_context",
                        "The standard endpoint group must use its canonical template.",
                    )
                if template in seen_templates:
                    raise ContextError(
                        "invalid_context", "Endpoint templates must be unique."
                    )
                seen_templates.add(template)
                _validate_timestamp(
                    entry.get("lastValidatedAt"),
                    f"endpoints.{key}[{index}].lastValidatedAt",
                )

    recent = data.get("recentlyUsedAIDP")
    if recent is not None and (
        not isinstance(recent, list)
        or not all(isinstance(entry, dict) for entry in recent)
    ):
        raise ContextError(
            "invalid_context", "recentlyUsedAIDP must be an array of objects."
        )
    if isinstance(recent, list):
        if len(recent) > MAX_RECENT_INSTANCES:
            raise ContextError(
                "invalid_context", "recentlyUsedAIDP exceeds its MRU limit."
            )
        seen_instances: set[str] = set()
        for index, entry in enumerate(recent):
            instance_ocid = entry.get("instanceOcid")
            if not isinstance(instance_ocid, str):
                raise ContextError(
                    "invalid_context", "Recent instance OCID must be a string."
                )
            resource_type, realm = _parse_instance_ocid(instance_ocid)
            if entry.get("resourceType") != resource_type or entry.get("realm") != realm:
                raise ContextError(
                    "invalid_context",
                    "Recent instance resource type and realm must match its OCID.",
                )
            region = entry.get("region")
            if not isinstance(region, str) or _validate_region(region) != region:
                raise ContextError(
                    "invalid_context", "Recent instance region must be normalized."
                )
            endpoint = entry.get("endpoint")
            if not isinstance(endpoint, str):
                raise ContextError(
                    "invalid_context", "Recent instance endpoint must be a string."
                )
            if _normalize_https_url(endpoint, False) != endpoint:
                raise ContextError(
                    "invalid_context", "Recent instance endpoint must be normalized."
                )
            name = entry.get("name")
            if name is not None and (
                not isinstance(name, str)
                or not name.strip()
                or name != name.strip()
                or len(name) > 512
            ):
                raise ContextError(
                    "invalid_context", "Recent instance name is invalid."
                )
            _validate_timestamp(
                entry.get("lastUsedAt"),
                f"recentlyUsedAIDP[{index}].lastUsedAt",
            )
            if instance_ocid in seen_instances:
                raise ContextError(
                    "invalid_context", "Recent instance OCIDs must be unique."
                )
            seen_instances.add(instance_ocid)

    python_cli = data.get("pythonCli")
    if python_cli is not None:
        cli_obj = _require_dict(python_cli, "pythonCli")
        if set(cli_obj) != {"path", "pythonPath"}:
            raise ContextError("invalid_context", "pythonCli must contain path and pythonPath.")
        for key in ("path", "pythonPath"):
            value = cli_obj[key]
            if not isinstance(value, str) or "\x00" in value or not Path(value).is_absolute():
                raise ContextError("invalid_context", f"pythonCli.{key} must be an absolute path.")

    oci_cli = data.get("ociCli")
    if oci_cli is not None:
        cli_obj = _require_dict(oci_cli, "ociCli")
        if set(cli_obj) != {"path"}:
            raise ContextError("invalid_context", "ociCli must contain only path.")
        value = cli_obj["path"]
        if not isinstance(value, str) or "\x00" in value or not Path(value).is_absolute():
            raise ContextError("invalid_context", "ociCli.path must be an absolute path.")

    version_check = data.get("latestVersionCheck")
    if version_check is not None:
        check_obj = _require_dict(version_check, "latestVersionCheck")
        if set(check_obj) != {"checkedAt"}:
            raise ContextError(
                "invalid_context", "latestVersionCheck must contain only checkedAt."
            )
        _validate_timestamp(check_obj["checkedAt"], "latestVersionCheck.checkedAt")

    return data


def _migrate_document(document: Any) -> dict[str, Any]:
    data = _require_dict(document, "context")
    version = data.get("schemaVersion")
    if version == SCHEMA_VERSION:
        return _validate_document(data)
    if version != 1:
        raise ContextError(
            "unsupported_schema",
            f"Unsupported AIDP context schema version: {version!r}.",
        )
    unexpected = set(data) - ALLOWED_FIELDS - LEGACY_FIELDS
    if unexpected:
        raise ContextError(
            "invalid_context",
            "Context contains unsupported fields: " + ", ".join(sorted(unexpected)),
        )
    migrated = {"schemaVersion": SCHEMA_VERSION}
    for field in ("lastUsedAuth", "endpoints", "recentlyUsedAIDP"):
        if field in data:
            migrated[field] = data[field]
    return _validate_document(migrated)


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_context()
    if path.is_symlink():
        raise ContextError(
            "unsafe_context_path", "The AIDP context file must not be a symlink."
        )
    try:
        # Keep reads free of filesystem mutations. Windows must allow the
        # writer to replace/unlink this name while this handle reads its snapshot.
        descriptor = readonly_open(path, share_delete=True)
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            return _migrate_document(json.load(stream))
    except FileNotFoundError:
        # A concurrent clear may remove the name after the existence check.
        return _empty_context()
    except json.JSONDecodeError as exc:
        raise ContextError(
            "invalid_json",
            f"The AIDP context file is not valid JSON at line {exc.lineno}.",
        ) from exc
    except OSError as exc:
        raise ContextError(
            "context_read_failed", f"Unable to read the AIDP context: {exc.strerror}."
        ) from exc


def _prepare_directory(path: Path) -> None:
    parent = path.parent
    if parent.exists() and parent.is_symlink():
        raise ContextError(
            "unsafe_context_path", "The AIDP context directory must not be a symlink."
        )
    try:
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        restrict_directory(parent)
    except OSError as exc:
        raise ContextError(
            "context_directory_failed",
            f"Unable to prepare the AIDP context directory: {exc.strerror}.",
        ) from exc


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    _prepare_directory(path)
    lock_path = path.with_name(path.name + ".lock")
    if lock_path.exists() and lock_path.is_symlink():
        raise ContextError(
            "unsafe_context_path", "The AIDP context lock must not be a symlink."
        )
    try:
        descriptor = private_open(lock_path, os.O_RDWR | os.O_CREAT)
        with os.fdopen(descriptor, "r+", encoding="utf-8") as lock_stream:
            with exclusive_lock(lock_stream):
                yield
    except OSError as exc:
        raise ContextError(
            "context_lock_failed", f"Unable to lock the AIDP context: {exc.strerror}."
        ) from exc


def _write_atomic(path: Path, document: dict[str, Any]) -> None:
    _validate_document(document)
    if path.exists() and path.is_symlink():
        raise ContextError(
            "unsafe_context_path", "The AIDP context file must not be a symlink."
        )
    file_descriptor: int | None = None
    temporary_name: str | None = None
    try:
        temporary_name = str(path.parent / (".context." + uuid.uuid4().hex + ".tmp"))
        file_descriptor = private_open(temporary_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
            file_descriptor = None
            json.dump(document, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
    except OSError as exc:
        raise ContextError(
            "context_write_failed", f"Unable to write the AIDP context: {exc.strerror}."
        ) from exc
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def _mutate(
    path: Path,
    operation: Callable[[dict[str, Any]], tuple[dict[str, Any], Any]],
) -> Any:
    with _exclusive_lock(path):
        current = _load(path)
        updated, result = operation(current)
        _write_atomic(path, updated)
        return result


def _validate_profile(profile: str) -> str:
    if not PROFILE_RE.fullmatch(profile):
        raise ContextError("invalid_profile", "OCI profile name is invalid.")
    return profile


def _validate_realm(realm: str) -> str:
    normalized = realm.lower()
    if not REALM_RE.fullmatch(normalized):
        raise ContextError("invalid_realm", "OCI realm is invalid.")
    return normalized


def _validate_resource_type(resource_type: str) -> str:
    normalized = resource_type.lower()
    if not RESOURCE_TYPE_RE.fullmatch(normalized):
        raise ContextError(
            "invalid_resource_type", "AIDP OCID resource type is invalid."
        )
    return normalized


def _validate_region(region: str) -> str:
    normalized = region.lower()
    if not REGION_RE.fullmatch(normalized):
        raise ContextError("invalid_region", "OCI region identifier is invalid.")
    return normalized


def _normalize_https_url(value: str, require_region_template: bool) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ContextError("invalid_endpoint", "Endpoint URL is invalid.") from exc
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ContextError(
            "invalid_endpoint", "Endpoint must be an absolute HTTPS URL."
        )
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ContextError(
            "invalid_endpoint",
            "Endpoint must not contain credentials, a query, or a fragment.",
        )
    if parsed.path not in {"", "/"}:
        raise ContextError(
            "invalid_endpoint", "Endpoint must not contain an API path."
        )

    hostname = parsed.hostname.lower()
    placeholder_count = hostname.count("{region}")
    if require_region_template and placeholder_count != 1:
        raise ContextError(
            "invalid_endpoint_template",
            "Endpoint template must contain exactly one {region} hostname placeholder.",
        )
    if not require_region_template and placeholder_count:
        raise ContextError(
            "invalid_endpoint", "Exact endpoint must not contain {region}."
        )
    test_hostname = hostname.replace("{region}", "us-phoenix-1")
    labels = test_hostname.split(".")
    if len(labels) < 2 or any(not HOST_LABEL_RE.fullmatch(label) for label in labels):
        raise ContextError("invalid_endpoint", "Endpoint hostname is invalid.")

    authority = hostname if port is None else f"{hostname}:{port}"
    return f"https://{authority}"


def _parse_instance_ocid(value: str) -> tuple[str, str]:
    match = INSTANCE_OCID_RE.fullmatch(value)
    if not match:
        raise ContextError("invalid_instance_ocid", "AIDP instance OCID is invalid.")
    return match.group(1).lower(), match.group(2).lower()


def _with_display_ocid(entry: dict[str, Any]) -> dict[str, Any]:
    result = dict(entry)
    instance_ocid = entry["instanceOcid"]
    prefix, unique_suffix = instance_ocid.rsplit(".", 1)
    result["displayOcid"] = f"{prefix}.…{unique_suffix[-8:]}"
    return result


def _get_value(data: dict[str, Any], args: argparse.Namespace) -> Any:
    if args.field == "all":
        # Same derived display field as `get recentlyUsedAIDP`; never stored.
        result = dict(data)
        if isinstance(data.get("recentlyUsedAIDP"), list):
            result["recentlyUsedAIDP"] = [
                _with_display_ocid(entry) for entry in data["recentlyUsedAIDP"]
            ]
        return result
    if args.field in ("lastUsedAuth", "latestVersionCheck", "pythonCli", "ociCli"):
        return data.get(args.field)
    if args.field == "endpoints":
        endpoints = data.get("endpoints")
        if args.realm is None and args.resource_type is None:
            return endpoints
        if args.realm is None or args.resource_type is None:
            raise ContextError(
                "missing_selector",
                "Both --realm and --resource-type are required for one endpoint group.",
            )
        if not isinstance(endpoints, dict):
            return None
        key = f"{_validate_realm(args.realm)}:{_validate_resource_type(args.resource_type)}"
        return endpoints.get(key)
    if args.field == "recentlyUsedAIDP":
        recent = data.get("recentlyUsedAIDP")
        if not isinstance(recent, list):
            return None
        display_entries = [_with_display_ocid(entry) for entry in recent]
        if args.instance_ocid is None:
            return display_entries
        _parse_instance_ocid(args.instance_ocid)
        return next(
            (
                entry
                for entry in display_entries
                if entry.get("instanceOcid") == args.instance_ocid
            ),
            None,
        )
    raise ContextError("invalid_field", "Unsupported context field.")


def _set_value(path: Path, args: argparse.Namespace) -> Any:
    def operation(data: dict[str, Any]) -> tuple[dict[str, Any], Any]:
        timestamp = _now()
        if args.field == "ociCli":
            value = {"path": args.path}
            data["ociCli"] = value
            return data, value
        if args.field == "pythonCli":
            value = {"path": args.path, "pythonPath": args.python_path}
            data["pythonCli"] = value
            return data, value
        if args.field == "lastUsedAuth":
            profile = _validate_profile(args.profile)
            config_path: str | None = None
            if args.config_file_path:
                candidate = Path(args.config_file_path).expanduser()
                if not candidate.is_absolute():
                    raise ContextError(
                        "invalid_config_path",
                        "OCI config file path must be absolute.",
                    )
                config_path = str(candidate)
            value = {
                "authType": args.auth_type,
                "profile": profile,
                "configFilePath": config_path,
                "lastValidatedAt": timestamp,
            }
            data["lastUsedAuth"] = value
            return data, value

        if args.field == "endpoints":
            realm = _validate_realm(args.realm)
            resource_type = _validate_resource_type(args.resource_type)
            template = _normalize_https_url(args.template, True)
            if (
                resource_type == "aidataplatform"
                and template != STANDARD_ENDPOINT_TEMPLATE
            ):
                raise ContextError(
                    "invalid_standard_endpoint",
                    "The standard aidataplatform resource type accepts only its canonical regional endpoint template.",
                )
            key = f"{realm}:{resource_type}"
            endpoints = data.setdefault("endpoints", {})
            if not isinstance(endpoints, dict):
                raise ContextError("invalid_context", "endpoints must be an object.")
            current = endpoints.get(key, [])
            current = [
                entry
                for entry in current
                if isinstance(entry, dict) and entry.get("template") != template
            ]
            record = {"template": template, "lastValidatedAt": timestamp}
            limit = 1 if resource_type == "aidataplatform" else MAX_ENDPOINTS
            endpoints[key] = [record, *current][:limit]
            return data, endpoints[key]

        if args.field == "recentlyUsedAIDP":
            resource_type, realm = _parse_instance_ocid(args.instance_ocid)
            region = _validate_region(args.region)
            endpoint = _normalize_https_url(args.endpoint, False)
            recent = data.setdefault("recentlyUsedAIDP", [])
            if not isinstance(recent, list):
                raise ContextError(
                    "invalid_context", "recentlyUsedAIDP must be an array."
                )
            previous = next(
                (
                    entry
                    for entry in recent
                    if isinstance(entry, dict)
                    and entry.get("instanceOcid") == args.instance_ocid
                ),
                None,
            )
            name = args.name if args.name is not None else (
                previous.get("name") if isinstance(previous, dict) else None
            )
            if name is not None:
                name = name.strip()
                if not name or len(name) > 512:
                    raise ContextError(
                        "invalid_instance_name", "AIDP instance name is invalid."
                    )
            record: dict[str, Any] = {
                "instanceOcid": args.instance_ocid,
                "resourceType": resource_type,
                "realm": realm,
                "region": region,
                "endpoint": endpoint,
                "lastUsedAt": timestamp,
            }
            if name is not None:
                record["name"] = name
            remaining = [
                entry
                for entry in recent
                if isinstance(entry, dict)
                and entry.get("instanceOcid") != args.instance_ocid
            ]
            data["recentlyUsedAIDP"] = [record, *remaining][
                :MAX_RECENT_INSTANCES
            ]
            return data, record

        if args.field == "latestVersionCheck":
            value = {"checkedAt": timestamp}
            data["latestVersionCheck"] = value
            return data, value

        raise ContextError("invalid_field", "Unsupported context field.")

    return _mutate(path, operation)


def _remove_value(path: Path, args: argparse.Namespace) -> Any:
    def operation(data: dict[str, Any]) -> tuple[dict[str, Any], Any]:
        removed = False
        if args.field in ("lastUsedAuth", "latestVersionCheck", "pythonCli", "ociCli"):
            removed = data.pop(args.field, None) is not None
        elif args.field == "endpoints":
            realm = _validate_realm(args.realm)
            resource_type = _validate_resource_type(args.resource_type)
            template = _normalize_https_url(args.template, True)
            endpoints = data.get("endpoints")
            if isinstance(endpoints, dict):
                key = f"{realm}:{resource_type}"
                current = endpoints.get(key)
                if isinstance(current, list):
                    updated = [
                        entry
                        for entry in current
                        if not isinstance(entry, dict)
                        or entry.get("template") != template
                    ]
                    removed = len(updated) != len(current)
                    if updated:
                        endpoints[key] = updated
                    else:
                        endpoints.pop(key, None)
                if not endpoints:
                    data.pop("endpoints", None)
        elif args.field == "recentlyUsedAIDP":
            _parse_instance_ocid(args.instance_ocid)
            recent = data.get("recentlyUsedAIDP")
            if isinstance(recent, list):
                updated = [
                    entry
                    for entry in recent
                    if not isinstance(entry, dict)
                    or entry.get("instanceOcid") != args.instance_ocid
                ]
                removed = len(updated) != len(recent)
                if updated:
                    data["recentlyUsedAIDP"] = updated
                else:
                    data.pop("recentlyUsedAIDP", None)
        else:
            raise ContextError("invalid_field", "Unsupported context field.")
        return data, {"removed": removed}

    return _mutate(path, operation)


def _clear(path: Path) -> dict[str, bool]:
    with _exclusive_lock(path):
        if path.exists() and path.is_symlink():
            raise ContextError(
                "unsafe_context_path", "The AIDP context file must not be a symlink."
            )
        existed = path.exists()
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise ContextError(
                "context_clear_failed",
                f"Unable to clear the AIDP context: {exc.strerror}.",
            ) from exc
        return {"cleared": existed}


def _migrate(path: Path) -> dict[str, int]:
    def operation(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
        return data, {"schemaVersion": SCHEMA_VERSION}

    return _mutate(path, operation)


def _add_common_selectors(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--realm", "--relm")
    parser.add_argument("--resource-type", "--resourceType", dest="resource_type")
    parser.add_argument("--instance-ocid", "--instanceOcid", dest="instance_ocid")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read and update non-identity cross-session AIDP context."
    )
    actions = parser.add_subparsers(dest="action", required=True)

    get_parser = actions.add_parser("get", help="Read context without modifying it.")
    get_parser.add_argument(
        "field",
        choices=[
            "all",
            "lastUsedAuth",
            "endpoints",
            "recentlyUsedAIDP",
            "latestVersionCheck",
            "pythonCli",
            "ociCli",
        ],
    )
    _add_common_selectors(get_parser)

    set_parser = actions.add_parser("set", help="Record validated context.")
    set_fields = set_parser.add_subparsers(dest="field", required=True)

    oci_parser = set_fields.add_parser("ociCli")
    oci_parser.add_argument("--path", required=True)

    cli_parser = set_fields.add_parser("pythonCli")
    cli_parser.add_argument("--path", required=True)
    cli_parser.add_argument("--python-path", required=True)

    auth_parser = set_fields.add_parser("lastUsedAuth")
    auth_parser.add_argument(
        "--auth-type", "--authType", dest="auth_type", required=True,
        choices=["security_token", "api_key"]
    )
    auth_parser.add_argument("--profile", required=True)
    auth_parser.add_argument(
        "--config-file-path", "--configFilePath", dest="config_file_path"
    )

    endpoint_parser = set_fields.add_parser("endpoints")
    endpoint_parser.add_argument("--realm", "--relm", required=True)
    endpoint_parser.add_argument(
        "--resource-type", "--resourceType", dest="resource_type", required=True
    )
    endpoint_parser.add_argument("--template", required=True)

    recent_parser = set_fields.add_parser("recentlyUsedAIDP")
    recent_parser.add_argument(
        "--instance-ocid", "--instanceOcid", dest="instance_ocid", required=True
    )
    recent_parser.add_argument("--region", required=True)
    recent_parser.add_argument("--endpoint", required=True)
    recent_parser.add_argument("--name")

    set_fields.add_parser("latestVersionCheck")

    remove_parser = actions.add_parser("remove", help="Forget one context value.")
    remove_fields = remove_parser.add_subparsers(dest="field", required=True)
    remove_fields.add_parser("lastUsedAuth")
    remove_fields.add_parser("latestVersionCheck")
    remove_fields.add_parser("pythonCli")
    remove_fields.add_parser("ociCli")

    remove_endpoint = remove_fields.add_parser("endpoints")
    remove_endpoint.add_argument("--realm", "--relm", required=True)
    remove_endpoint.add_argument(
        "--resource-type", "--resourceType", dest="resource_type", required=True
    )
    remove_endpoint.add_argument("--template", required=True)

    remove_recent = remove_fields.add_parser("recentlyUsedAIDP")
    remove_recent.add_argument(
        "--instance-ocid", "--instanceOcid", dest="instance_ocid", required=True
    )

    actions.add_parser("migrate", help="Remove legacy identity and consent fields.")
    actions.add_parser("clear", help="Remove all remembered AIDP context.")
    return parser


def main() -> int:
    try:
        args = _build_parser().parse_args()
        path = _context_path()
        if args.action == "get":
            result = _get_value(_load(path), args)
        elif args.action == "set":
            saved_value = _set_value(path, args)
            result = {
                "saved": True,
                "field": args.field,
                "value": saved_value,
            }
        elif args.action == "remove":
            result = _remove_value(path, args)
        elif args.action == "migrate":
            result = _migrate(path)
        elif args.action == "clear":
            result = _clear(path)
        else:
            raise ContextError("invalid_action", "Unsupported context action.")
        _emit(result)
        return 0
    except ContextError as error:
        _emit_error(error)
        return error.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
