#!/usr/bin/env python3
# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
"""Download a wallet using a locally prompted protection password."""
import argparse
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import warnings

from catalog_inputs import MAX_WALLET, InputError, guarded, read_bytes, write_private
from platform_support import private_open, private_directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wallet-output", required=True, help="Standalone output ZIP path; protection password is prompted locally.")
    parser.add_argument("--database-id", required=True)
    parser.add_argument("--auth", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--config-file")
    parser.add_argument("--dedicated", action="store_true", help="Use when OCI metadata identifies dedicated Autonomous infrastructure.")
    parser.add_argument("--oci", default="oci")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    destination = Path(args.wallet_output).expanduser()
    if destination.exists() or destination.is_symlink():
        raise InputError("Generated wallet already exists; choose a fresh output path.")
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise InputError("Run wallet download in a user-controlled interactive terminal.", "INTERACTIVE_TERMINAL_REQUIRED", "terminal")
    password = ""
    while not password.strip():
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                password = getpass.getpass("Enter protection password for the downloaded wallet (required): ")
        except getpass.GetPassWarning:
            raise InputError("Hidden input is unavailable; no echoed password fallback is permitted.", "HIDDEN_INPUT_UNAVAILABLE", "terminal") from None
    with private_directory(prefix="aidp-wallet-download-") as directory:
        request = Path(directory) / "request.json"
        wallet = Path(directory) / "wallet.zip"
        details = {"password": password}
        if not args.dedicated:
            details["generateType"] = "SINGLE"
        write_private(request, details)
        command = [args.oci, "db", "autonomous-database", "generate-wallet",
                   "--autonomous-database-id", args.database_id, "--from-json", "file://" + str(request),
                   "--file", str(wallet), "--auth", args.auth, "--profile", args.profile, "--region", args.region]
        if args.config_file:
            command.extend(["--config-file", args.config_file])
        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=args.timeout, check=False)
        if result.returncode:
            raise InputError("Wallet download failed; verify database access and OCI authentication. Raw diagnostics were suppressed.")
        content = read_bytes(wallet, MAX_WALLET)
        fd = private_open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(content)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
    print(json.dumps({"ok": True, "walletFilePath": str(destination), "message": "Wallet downloaded. Its protection password was not retained in a draft."}))
    return 0


if __name__ == "__main__":
    raise SystemExit(guarded(main))
