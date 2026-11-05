#!/usr/bin/env python3
"""Privately inspect PEM envelope metadata; never emit key material."""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from protected_aidp import ProtectedError, read_file


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-path", required=True)
    args = parser.parse_args(argv)
    try:
        raw = read_file(args.key_path, 1024 * 1024)
        match = re.search(rb"-----BEGIN (ENCRYPTED PRIVATE KEY|PRIVATE KEY|RSA PRIVATE KEY|EC PRIVATE KEY)-----", raw)
        if not match:
            raise ProtectedError("UNRECOGNIZED_KEY_ENVELOPE", "Select a PEM private-key file; key material is not shown. This helper does not convert or validate cryptographic keys.")
        label = match.group(1)
        if b"-----END " + label + b"-----" not in raw:
            raise ProtectedError("UNRECOGNIZED_KEY_ENVELOPE", "The selected PEM envelope is incomplete; inspect the source file locally.")
        encrypted = label == b"ENCRYPTED PRIVATE KEY" or bool(re.search(rb"Proc-Type:\s*4\s*,\s*ENCRYPTED", raw, re.I))
        print(json.dumps({"ok": True, "encrypted": encrypted,
                          "format": "PKCS8" if label in (b"PRIVATE KEY", b"ENCRYPTED PRIVATE KEY") else "LEGACY_PEM"}))
        return 0
    except ProtectedError as error:
        print(json.dumps({"ok": False, "errorCode": error.code, "error": str(error)}))
    except Exception:
        print('{"ok":false,"errorCode":"KEY_CHECK_FAILED","error":"Could not inspect the key envelope; private diagnostics are suppressed."}')
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
