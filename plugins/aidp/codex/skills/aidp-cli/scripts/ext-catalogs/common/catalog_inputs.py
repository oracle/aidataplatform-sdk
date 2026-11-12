# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
"""Private-file primitives shared by external catalog helpers (standard library only)."""
from __future__ import annotations

import json
import errno
import os
import re
import stat
import zipfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from platform_support import private_open, readonly_open

MAX_JSON = 1024 * 1024
MAX_WALLET = 32 * 1024 * 1024


class InputError(Exception):
    """Only fixed, non-sensitive messages may be placed in this exception."""

    def __init__(self, message, code="INVALID_INPUT", stage="validation"):
        super().__init__(message)
        self.code = code
        self.stage = stage


def read_bytes(path, limit, stage="input"):
    path = os.path.expanduser(os.fspath(path))
    try:
        fd = readonly_open(path)
    except FileNotFoundError:
        raise InputError("The input file was not found. Correct its location locally.", "FILE_NOT_FOUND", stage) from None
    except PermissionError:
        raise InputError("The process cannot read this input. Check filesystem permissions and host privacy/sandbox access; an existing file may still be inaccessible.", "FILE_ACCESS_DENIED", stage) from None
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise InputError("This input is a symbolic link. Select the regular source file locally.", "SYMLINK_NOT_ALLOWED", stage) from None
        raise InputError("The input could not be opened. Check the selected file locally.", "FILE_OPEN_FAILED", stage) from None
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise InputError("Input must be a regular file.", "NOT_REGULAR_FILE", stage)
        try:
            data = stream.read(limit + 1)
        except PermissionError:
            raise InputError("The process cannot read this input. Check filesystem and host privacy/sandbox access.", "FILE_ACCESS_DENIED", stage) from None
        except OSError:
            raise InputError("The input could not be read. Check local file access.", "FILE_READ_FAILED", stage) from None
        if len(data) > limit:
            raise InputError("Input exceeds the supported size limit.", "INPUT_TOO_LARGE", stage)
        return data


def write_private(path, value):
    """Exclusive creation: never follow symlinks or overwrite an existing artifact."""
    data = json.dumps(value, indent=2, ensure_ascii=True).encode() + b"\n"
    fd = private_open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)


def wallet_services(wallet_path):
    import io

    wallet_path = os.path.expanduser(wallet_path)
    content = read_bytes(wallet_path, MAX_WALLET, stage="wallet_file")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = [e for e in archive.infolist() if Path(e.filename).name.lower() == "tnsnames.ora"]
            if not entries:
                raise InputError("ZIP contains no tnsnames.ora file.", "TNS_FILE_MISSING", "wallet_zip")
            if len(entries) != 1:
                raise InputError("ZIP contains multiple tnsnames.ora files; select an unambiguous database wallet.", "TNS_FILE_AMBIGUOUS", "wallet_zip")
            if entries[0].file_size > MAX_JSON:
                raise InputError("Wallet service file is too large.", "TNS_FILE_TOO_LARGE", "wallet_zip")
            if entries[0].flag_bits & 1:
                raise InputError("The ZIP entry itself is encrypted; this helper supports ordinary wallet ZIPs. This is separate from the wallet protection password.", "ENCRYPTED_ZIP_UNSUPPORTED", "wallet_zip")
            with archive.open(entries[0]) as stream:
                raw = stream.read(MAX_JSON + 1)
            if len(raw) > MAX_JSON:
                raise InputError("Wallet service file is too large.", "TNS_FILE_TOO_LARGE", "wallet_zip")
    except zipfile.BadZipFile:
        raise InputError("Wallet file is not a readable ZIP or failed its integrity check.", "INVALID_WALLET_ZIP", "wallet_zip") from None
    except NotImplementedError:
        raise InputError("The ZIP uses an unsupported compression method.", "ZIP_COMPRESSION_UNSUPPORTED", "wallet_zip") from None
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError:
        raise InputError("Wallet service file is not valid UTF-8 text.", "TNS_ENCODING_UNSUPPORTED", "tns_parse") from None
    aliases = []
    depth = 0
    quote = None
    for line in text.splitlines():
        # Extract aliases only at top level; never print descriptors/hosts or ZIP paths.
        clean = line.strip()
        if depth == 0 and quote is None and not clean.startswith("#") and "=" in clean:
            names, descriptor = clean.split("=", 1)
            candidates = [name.strip() for name in names.split(",")]
            if (not descriptor.strip() or descriptor.lstrip().startswith("(")) and all(re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", n) for n in candidates):
                aliases.extend(candidates)
        escaped = False
        for char in clean:
            if quote is not None:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
            elif char in ('"', "'"):
                quote = char
            elif char == "#":
                break
            else:
                if char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
        if depth < 0:
            raise InputError("Wallet service configuration is malformed.", "INVALID_TNS_SYNTAX", "tns_parse")
    if depth or quote is not None or not aliases or len(aliases) > 256:
        raise InputError("Wallet contains no supported service list or is malformed.", "INVALID_TNS_SYNTAX", "tns_parse")
    return sorted(set(aliases))


def guarded(action):
    try:
        return action() or 0
    except InputError as error:
        print(json.dumps({"ok": False, "errorCode": error.code, "stage": error.stage, "error": str(error)}))
    except Exception:
        # JSON/ZIP/OS/subprocess errors can contain input contents and private paths.
        print(json.dumps({"ok": False, "errorCode": "HELPER_FAILED", "stage": "unknown", "error": "Catalog helper failed; the cause is not classified. Do not assume a bad path or damaged ZIP, and do not display private files."}))
    return 1
