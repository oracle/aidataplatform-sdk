#!/usr/bin/env python3
"""Resolve protected JSON values in a private copy, invoke the CLI, then dispose of the copy."""
from __future__ import annotations

import base64
import getpass
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import uuid
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parent))
from platform_support import private_open, private_directory, readonly_open

MAX_TEMPLATE = 4 * 1024 * 1024
MAX_ATTACHMENT = 64 * 1024 * 1024
KINDS = ("visible_prompt_input", "invisible_prompt_input", "base64of", "textof")
PLACEHOLDER = re.compile(r"\{(" + "|".join(KINDS) + r"):([^\r\n]+)\}")
PROMPT_MARKER = re.compile(r"\{[A-Za-z_]*prompt_input:")


class ProtectedError(Exception):
    """Messages/codes are fixed diagnostics and must never include private values."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def read_file(path, limit):
    try:
        fd = readonly_open(os.path.expanduser(os.fspath(path)))
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ProtectedError("NOT_REGULAR_FILE", "Select a regular readable file, not a folder or special file.")
            data = stream.read(limit + 1)
            if len(data) > limit:
                raise ProtectedError("INPUT_TOO_LARGE", "The selected file exceeds the supported size limit.")
            return data
    except FileNotFoundError:
        raise ProtectedError("FILE_NOT_FOUND", "A referenced file was not found; correct the template path locally.") from None
    except PermissionError:
        raise ProtectedError("FILE_ACCESS_DENIED", "A referenced file is inaccessible to this process; check filesystem and host privacy/sandbox access.") from None
    except OSError:
        raise ProtectedError("FILE_READ_FAILED", "A referenced file could not be read; symlinks are not supported.") from None


def read_body_template(path):
    """Load a bounded object/array template without exposing parser excerpts."""
    raw = read_file(path, MAX_TEMPLATE)
    try:
        template = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ProtectedError("INVALID_JSON", "The template is not valid JSON; parser excerpts are suppressed.") from None
    if not isinstance(template, (dict, list)):
        raise ProtectedError("INVALID_JSON", "The body template must be a JSON object or array.")
    return raw, template


def write_body_template(path, body):
    """Create a fresh owner-only unresolved JSON template; never overwrite."""
    encoded = json.dumps(body, indent=2) + "\n"
    fd = private_open(Path(path).expanduser(), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(encoded)


def prompt_spec(kind, argument):
    """Parse generic visibility/requirement metadata without requesting input."""
    if kind not in ("visible_prompt_input", "invisible_prompt_input") or ":" not in argument:
        raise ProtectedError("INVALID_PROMPT_MODE", "Use prompt_input:required:TEXT or prompt_input:optional:TEXT with visible or invisible input.")
    mode, label = argument.split(":", 1)
    if mode not in ("required", "optional"):
        raise ProtectedError("INVALID_PROMPT_MODE", "Use prompt_input:required:TEXT or prompt_input:optional:TEXT with visible or invisible input.")
    required = mode == "required"
    if not label.strip() or any(ord(char) < 32 or ord(char) == 127 for char in label) or len(label) > 512:
        raise ProtectedError("INVALID_PROMPT", "Prompt labels must be short plain text.")
    return label, "invisible" in kind, required


def prompt(label, hidden, required):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ProtectedError("INTERACTIVE_TERMINAL_REQUIRED", "Run the wrapper yourself in an interactive user-controlled terminal; do not pipe credentials.")
    if not label.strip() or any(ord(char) < 32 or ord(char) == 127 for char in label) or len(label) > 512:
        raise ProtectedError("INVALID_PROMPT", "Prompt labels must be short plain text.")
    suffix = ": " if required else " (optional): "
    while True:
        if hidden:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", getpass.GetPassWarning)
                    value = getpass.getpass(label + suffix)
            except getpass.GetPassWarning:
                raise ProtectedError("HIDDEN_INPUT_UNAVAILABLE", "Hidden password input is unavailable; no echoed fallback is permitted.") from None
        else:
            value = input(label + suffix)
        if required and not value.strip():
            print("A value is required; please try again.")
            continue
        return value


def resolve(value, cache=None):
    if cache is None:
        cache = {}
    if isinstance(value, dict):
        if any(any("{" + kind + ":" in key for kind in KINDS) or PROMPT_MARKER.search(key)
               or "{aidp-secret-input" in key for key in value):
            raise ProtectedError("PLACEHOLDER_IN_KEY", "Placeholders belong in whole JSON values, not keys.")
        return {key: resolve(item, cache) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve(item, cache) for item in value]
    if not isinstance(value, str):
        return value
    match = PLACEHOLDER.fullmatch(value)
    if not match:
        if any("{" + kind + ":" in value for kind in KINDS) or PROMPT_MARKER.search(value):
            raise ProtectedError("INVALID_PLACEHOLDER", "Placeholders must occupy the entire JSON string value.")
        if "{aidp-secret-input" in value:
            raise ProtectedError("LEGACY_PLACEHOLDER", "Replace old draft placeholders with protected prompt/file placeholders.")
        return value
    if value in cache:
        return cache[value]
    kind, argument = match.groups()
    if kind in ("base64of", "textof"):
        raw = read_file(argument, MAX_ATTACHMENT)
        if not raw:
            raise ProtectedError("EMPTY_FILE", "The referenced attachment is empty.")
        if kind == "base64of":
            result = base64.b64encode(raw).decode("ascii")
        else:
            try:
                result = raw.decode("utf-8")
            except UnicodeError:
                raise ProtectedError("INVALID_TEXT_ENCODING", "textof requires a UTF-8 text file.") from None
    else:
        label, hidden, required = prompt_spec(kind, argument)
        result = prompt(label, hidden, required)
    cache[value] = result
    return result


def body_argument(command):
    locations = []
    for index, argument in enumerate(command):
        if argument == "--body":
            if index + 1 >= len(command):
                raise ProtectedError("BODY_ARGUMENT_REQUIRED", "Supply --body @body.json.")
            locations.append((index + 1, command[index + 1], False))
        elif argument.startswith("--body="):
            locations.append((index, argument[len("--body="):], True))
    if len(locations) != 1:
        raise ProtectedError("BODY_ARGUMENT_REQUIRED", "Supply exactly one --body @body.json argument to the existing CLI command.")
    index, reference, joined = locations[0]
    if not reference.startswith("@") or len(reference) == 1:
        raise ProtectedError("BODY_FILE_REQUIRED", "The body must reference a template using @filename; inline bodies are not supported.")
    return index, reference[1:], joined


def preflight(value, cache):
    """Validate file references/template syntax before collecting any credentials."""
    if isinstance(value, dict):
        if any(any("{" + kind + ":" in key for kind in KINDS) or PROMPT_MARKER.search(key)
               or "{aidp-secret-input" in key for key in value):
            raise ProtectedError("PLACEHOLDER_IN_KEY", "Placeholders belong in whole JSON values, not keys.")
        for item in value.values():
            preflight(item, cache)
    elif isinstance(value, list):
        for item in value:
            preflight(item, cache)
    elif isinstance(value, str):
        match = PLACEHOLDER.fullmatch(value)
        if match and match.group(1) in ("base64of", "textof"):
            resolve(value, cache)
        elif match:
            prompt_spec(*match.groups())
        else:
            resolve(value, cache)  # Reject malformed/legacy markers without prompting.


def execute(command, capture):
    if not command:
        raise ProtectedError("COMMAND_REQUIRED", "Usage: python3 protected_aidp.py --output-file RESULT.json -- aidp <existing arguments> --body @body.json")
    if any(argument.split("=", 1)[0] in ("--debug", "--verbose") for argument in command):
        raise ProtectedError("DEBUG_NOT_ALLOWED", "Disable debug/verbose output for protected requests.")
    index, template_path, joined = body_argument(command)
    raw_template, template = read_body_template(template_path)
    # The user template is never overwritten; only the resolved copy is private.
    with private_directory(prefix="aidp-protected-") as directory:
        actual = Path(directory) / ("actual_body_" + uuid.uuid4().hex + ".json")
        fd = private_open(actual, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw_template)
        cache = {}
        preflight(template, cache)
        resolved = resolve(template, cache)
        with actual.open("w", encoding="utf-8") as stream:
            json.dump(resolved, stream, ensure_ascii=True)
            stream.write("\n")
        args = list(command)
        reference = "@" + str(actual)
        args[index] = "--body=" + reference if joined else reference
        try:
            # Preserve complete CLI output privately for the agent handoff.
            streams = {"stdout": capture[0], "stderr": capture[1]}
            result = subprocess.run(args, check=False,
                                    env=dict(os.environ, AIDP_CLI_STRICT_URL_ENCODING="true",
                                             PYTHONIOENCODING="utf-8", PYTHONUTF8="1"), **streams)
        finally:
            # Cleanup also covers command failure, launch errors and cancellation.
            try:
                actual.unlink(missing_ok=True)
            except OSError:
                raise ProtectedError("BODY_DELETE_FAILED", "The command ended but temporary body deletion failed; do not retry the operation as a cleanup attempt.") from None
    return result.returncode if result.returncode >= 0 else 128 - result.returncode


def run_command(command, capture):
    def diagnostic(value):
        capture[0].write((json.dumps(value) + "\n").encode())
    try:
        return execute(command, capture)
    except ProtectedError as error:
        diagnostic({"ok": False, "errorCode": error.code, "error": str(error)})
    except (EOFError, KeyboardInterrupt):
        diagnostic({"ok": False, "errorCode": "CANCELLED", "error": "Cancelled; no automatic retry was performed."})
    except Exception:
        diagnostic({"ok": False, "errorCode": "PROTECTED_REQUEST_FAILED", "error": "The protected request could not complete. Private diagnostics are suppressed; do not retry a mutation blindly."})
    return 1


def main(argv=None):
    command = list(sys.argv[1:] if argv is None else argv)
    if len(command) < 4 or command[:1] != ["--output-file"] or command[2] != "--":
        print('{"ok":false,"errorCode":"OUTPUT_ARGUMENT_REQUIRED","error":"Use --output-file PATH -- aidp <arguments>."}')
        return 1
    target = Path(command[1]).expanduser().absolute()
    partial = target.with_name("." + target.name + "." + uuid.uuid4().hex + ".part")
    try:
        # Never replace an existing result, template or symlink. Publish the final
        # filename only after command completion AND temporary-body cleanup.
        if target.exists() or target.is_symlink():
            raise ProtectedError("OUTPUT_EXISTS", "Choose a fresh unique output filename; existing files are never overwritten.")
        fd = private_open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        with os.fdopen(fd, "w", encoding="utf-8") as result_file:
            with private_directory(prefix="aidp-output-") as capture_dir, \
                    tempfile.TemporaryFile(dir=capture_dir) as stdout, tempfile.TemporaryFile(dir=capture_dir) as stderr:
                code = run_command(command[3:], (stdout, stderr))
                stdout.seek(0); stderr.seek(0)
                json.dump({"complete": True, "exitCode": code,
                           "stdout": stdout.read().decode("utf-8", errors="replace"),
                           "stderr": stderr.read().decode("utf-8", errors="replace")}, result_file)
                result_file.write("\n")
            result_file.flush()
            os.fsync(result_file.fileno())
        os.link(partial, target)  # Atomic publication, fails rather than overwriting.
        print("Operation output handed off to AI agent. Ask it to continue.")
        return code
    except ProtectedError as error:
        print(json.dumps({"ok": False, "errorCode": error.code, "error": str(error)}))
    except (EOFError, KeyboardInterrupt):
        print('{"ok":false,"errorCode":"CANCELLED","error":"Cancelled; no automatic retry was performed."}')
    except Exception:
        print('{"ok":false,"errorCode":"OUTPUT_HANDOFF_FAILED","error":"Output handoff failed; do not repeat the operation blindly."}')
    finally:
        partial.unlink(missing_ok=True)
    return 1


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    raise SystemExit(main())
