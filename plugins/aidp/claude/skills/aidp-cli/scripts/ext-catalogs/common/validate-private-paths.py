#!/usr/bin/env python3
# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
"""Check wallet access and optionally ZIP/TNS format without exposing contents."""
import argparse
import json

from catalog_inputs import MAX_WALLET, InputError, guarded, read_bytes, wallet_services


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wallet", required=True, help="Non-secret wallet ZIP path.")
    parser.add_argument("--check-wallet", action="store_true", help="Also validate ZIP/TNS parsing without displaying services or contents.")
    args = parser.parse_args()
    try:
        content = read_bytes(args.wallet, MAX_WALLET, stage="wallet_file")
        if not content:
            raise InputError("The selected attachment is empty.", "EMPTY_FILE", "wallet_file")
        check = {"field": "walletFilePath", "ready": True, "readable": True}
        if args.check_wallet:
            wallet_services(args.wallet)
            check["walletServicesParseable"] = True
    except InputError as error:
        check = {"field": "walletFilePath", "ready": False, "errorCode": error.code,
                 "stage": error.stage, "error": str(error)}
    ready = check["ready"]
    print(json.dumps({"ok": ready, "checks": [check],
                      "message": "Inputs validated in this helper process; later calls need the same host and access permissions."
                      if ready else "Correct only the reported input/access issue locally. Private paths and contents are not displayed."}))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(guarded(main))
