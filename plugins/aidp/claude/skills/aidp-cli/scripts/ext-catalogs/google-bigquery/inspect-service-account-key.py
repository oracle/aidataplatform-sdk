#!/usr/bin/env python3
# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
"""Expose only project ID and service-account email from a local JSON key."""
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
        try:
            key = json.loads(read_file(args.key_path, 1024 * 1024))
        except (ValueError, UnicodeError):
            raise ProtectedError("KEY_METADATA_UNAVAILABLE", "Public metadata could not be derived from a service-account JSON key; provide the project ID and email separately without disclosing key contents.") from None
        if not isinstance(key, dict) or key.get("type") != "service_account":
            raise ProtectedError("INVALID_KEY_FORMAT", "Select a Google service-account JSON key; other authentication formats need separate contract verification.")
        project, email = key.get("project_id"), key.get("client_email")
        if (not isinstance(project, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", project)
                or not isinstance(email, str) or not re.fullmatch(r"[A-Za-z0-9_.+-]{1,128}@[A-Za-z0-9.-]{1,128}\.[A-Za-z]{2,24}", email)):
            raise ProtectedError("KEY_METADATA_UNAVAILABLE", "The JSON key has no usable public project ID or service-account email; ask only for those missing public fields.")
        print(json.dumps({"ok": True, "projectId": project, "serviceAccountEmail": email}))
        return 0
    except ProtectedError as error:
        print(json.dumps({"ok": False, "errorCode": error.code, "error": str(error)}))
    except Exception:
        print('{"ok":false,"errorCode":"KEY_METADATA_UNAVAILABLE","error":"Public key metadata could not be inspected; private diagnostics are suppressed."}')
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
