#!/usr/bin/env python3
"""Resolve only requested OCI identity fields after local-discovery consent."""
from __future__ import annotations

import argparse
import base64
import configparser
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def resolve(args):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", args.profile):
        raise ValueError("Invalid OCI profile name")
    path = Path(args.config_file or os.environ.get("OCI_CLI_CONFIG_FILE") or Path.home() / ".oci/config").expanduser()
    parser = configparser.ConfigParser(interpolation=None)
    with path.open(encoding="utf-8") as stream:
        parser.read_file(stream)
    if args.profile != "DEFAULT" and not parser.has_section(args.profile):
        raise ValueError("The selected OCI profile does not exist")
    profile = parser[args.profile]
    if args.tenancy_only:
        tenancy = profile.get("tenancy", "").strip()
        if not tenancy.startswith("ocid1.tenancy."):
            raise ValueError("The selected profile has no valid tenancy OCID")
        return {"tenancy": tenancy}
    fields = [value.strip() for value in (args.output or "").split(",") if value.strip()]
    if not fields or set(fields) - {"ocid", "name", "email"}:
        raise ValueError("Request only ocid, name, or email")
    token_file = profile.get("security_token_file", "").strip()
    user = profile.get("user", "").strip()
    auth = args.auth or ("security_token" if token_file else "api_key")
    if not user and token_file and auth == "security_token":
        # No token contents, claims other than sub, or parser excerpts escape.
        token = Path(token_file).expanduser().read_text(encoding="utf-8").strip()
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Cannot resolve OCI identity")
        payload = parts[1]
        user = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))).get("sub")
    if not isinstance(user, str) or not user.startswith("ocid1.user."):
        raise ValueError("Cannot resolve OCI identity")
    remote = [name for name in fields if name != "ocid"]
    fetched = {}
    if remote:
        query = "data.{" + ",".join(name + ":" + name for name in dict.fromkeys(remote)) + "}"
        command = [args.oci, "iam", "user", "get", "--auth", auth, "--profile", args.profile,
                   "--config-file", str(path), "--user-id", user, "--query", query, "--output", "json"]
        response = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
        if response.returncode:
            raise ValueError("OCI identity lookup failed")
        fetched = json.loads(response.stdout)
    return {field: user if field == "ocid" else fetched.get(field) for field in fields}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="DEFAULT")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output")
    mode.add_argument("--tenancy-only", action="store_true")
    parser.add_argument("--auth", choices=("security_token", "api_key"))
    parser.add_argument("--config-file")
    parser.add_argument("--oci", default="oci")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(resolve(args), indent=2))
        return 0
    except Exception:
        print("Unable to resolve the requested OCI identity fields from the selected profile.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
