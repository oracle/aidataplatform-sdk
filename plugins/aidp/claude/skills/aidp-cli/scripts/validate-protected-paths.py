#!/usr/bin/env python3
# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
"""Check protected-template paths and syntax without prompting or invoking AIDP."""
from __future__ import annotations

import argparse
import json

from protected_aidp import ProtectedError, preflight, read_body_template


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", help="Unresolved JSON template path, optionally prefixed with @")
    args = parser.parse_args(argv)
    try:
        _, template = read_body_template(args.template.removeprefix("@"))
        cache = {}
        preflight(template, cache)
        print(json.dumps({"ok": True, "fileReferences": len(cache)}))
        return 0
    except ProtectedError as error:
        print(json.dumps({"ok": False, "errorCode": error.code, "error": str(error)}))
    except Exception:
        print('{"ok":false,"errorCode":"PATH_CHECK_FAILED","error":"Template path checks could not complete; private diagnostics are suppressed."}')
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
