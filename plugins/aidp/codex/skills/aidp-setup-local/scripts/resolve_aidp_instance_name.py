#!/usr/bin/env python3
# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
"""Resolve one AIDP display name without exposing the raw service response."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from urllib.parse import quote, urlsplit


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth", choices=("security_token", "api_key"), required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--instance-ocid", required=True)
    parser.add_argument("--config-file")
    return parser


def _target_uri(endpoint: str, instance_ocid: str) -> str:
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("endpoint must be an HTTPS base endpoint")
    if not instance_ocid.startswith("ocid1.") or any(
        character.isspace() for character in instance_ocid
    ):
        raise ValueError("instance OCID is invalid")
    base = endpoint.rstrip("/")
    return f"{base}/20240831/aiDataPlatforms/{quote(instance_ocid, safe='.-_')}"


def main() -> int:
    args = _parser().parse_args()
    try:
        target_uri = _target_uri(args.endpoint, args.instance_ocid)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    command = [
        "oci",
        "raw-request",
        "--auth",
        args.auth,
        "--profile",
        args.profile,
        "--no-retry",
        "--connection-timeout",
        "3",
        "--read-timeout",
        "10",
        "--http-method",
        "GET",
        "--target-uri",
        target_uri,
        "--output",
        "json",
    ]
    if args.config_file:
        command.extend(("--config-file", args.config_file))

    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"instance-name lookup failed: {exc}", file=sys.stderr)
        return 1

    if result.returncode != 0:
        detail = result.stderr.strip() or "OCI raw request failed"
        print(detail, file=sys.stderr)
        return 1

    try:
        display_name = json.loads(result.stdout).get("data", {}).get("displayName")
    except (AttributeError, json.JSONDecodeError):
        display_name = None
    if not isinstance(display_name, str) or not display_name.strip():
        print("AIDP response did not contain displayName", file=sys.stderr)
        return 1

    print(display_name.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
