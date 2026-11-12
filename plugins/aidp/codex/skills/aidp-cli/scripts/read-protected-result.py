#!/usr/bin/env python3
# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
"""Wait for one completed result, read it privately, delete it, then emit it."""
import argparse
import json
import os
from pathlib import Path
import stat
import time

from protected_aidp import MAX_ATTACHMENT, ProtectedError
from platform_support import readonly_open


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result")
    parser.add_argument("--wait-seconds", type=float, default=0)
    args = parser.parse_args(argv)
    if not 0 <= args.wait_seconds <= 60:
        parser.error("--wait-seconds must be between 0 and 60")
    path = Path(args.result).expanduser()
    deadline = time.monotonic() + args.wait_seconds
    try:
        while True:
            try:
                info = path.lstat()
                break
            except FileNotFoundError:
                if time.monotonic() >= deadline:
                    print('{"ready":false}')
                    return 2
                time.sleep(min(0.2, max(0, deadline - time.monotonic())))
        if not stat.S_ISREG(info.st_mode):
            raise ProtectedError("UNSAFE_RESULT", "The result must be a regular owner-only file owned by this user.")
        try:
            fd = readonly_open(path, private=True)
        except PermissionError:
            raise ProtectedError("UNSAFE_RESULT", "The result must be a regular owner-only file owned by this user.") from None
        try:
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ProtectedError("UNSAFE_RESULT", "The result must be a regular owner-only file owned by this user.")
                raw = stream.read(MAX_ATTACHMENT + 1)
            if len(raw) > MAX_ATTACHMENT:
                raise ProtectedError("INPUT_TOO_LARGE", "The result exceeds the supported size limit.")
            result = json.loads(raw)
            if not isinstance(result, dict) or result.get("complete") is not True:
                raise ProtectedError("INVALID_RESULT", "The result is not a completed command handoff.")
        finally:
            # Delete before exposing contents, including on parse/read errors.
            path.unlink()
        print(json.dumps(result))
        return 0
    except ProtectedError as error:
        print(json.dumps({"ok": False, "errorCode": error.code, "error": str(error)}))
    except Exception:
        print('{"ok":false,"errorCode":"RESULT_READ_FAILED","error":"Could not consume the result; no automatic command retry was performed."}')
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
