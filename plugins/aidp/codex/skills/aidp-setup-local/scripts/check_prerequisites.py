#!/usr/bin/env python3
"""Check local AIDP prerequisites in one read-only pass and print a JSON summary."""

import argparse
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

MIN_PYTHON = (3, 9)
MIN_AIDP_CLI = "5.1.0"
CLI_PACKAGE = "aidp-cli"
CLIENT_PACKAGE = "aidp-python-client"
PACKAGES = (CLI_PACKAGE, CLIENT_PACKAGE)
VERSION_TIMEOUT_SECONDS = 20
# Network access is requested up front in restricted environments, so the
# lookup normally has real network access; this leaves room for slow
# networks and package-index mirrors.
DEFAULT_INDEX_TIMEOUT_SECONDS = 20
WINDOWS = os.name == "nt"
VENV_BIN = "Scripts" if WINDOWS else "bin"
AIDP_EXE = "aidp.exe" if WINDOWS else "aidp"
OCI_EXE = "oci.exe" if WINDOWS else "oci"
PYTHON_EXE = "python.exe" if WINDOWS else "python"
VENV_DIR = os.path.join(os.path.expanduser("~"), ".aidp-venv")

VERSION_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)+[A-Za-z0-9.+-]*)")
RELEASE_RE = re.compile(r"^(\d+(?:\.\d+)*)")
INDEX_LATEST_RE = re.compile(r"^\S+ \(([^)]+)\)", re.MULTILINE)
INDEX_AVAILABLE_RE = re.compile(r"^Available versions:\s*(.+)$", re.MULTILINE)
SH_EXEC_RE = re.compile(r"^'''exec' \"?([^\"]+?)\"? \"\$0\"", re.MULTILINE)

# Runs inside the interpreter that owns the `aidp` command, so package versions
# come from the environment the CLI actually imports from.
PACKAGE_PROBE = """
import json, sys
try:
    from importlib import metadata
except ImportError:
    metadata = None
try:
    import site
    user_base = site.getuserbase()
except Exception:
    user_base = None
try:
    import os, sysconfig
    marker = os.path.join(sysconfig.get_path("stdlib"), "EXTERNALLY-MANAGED")
    externally_managed = os.path.isfile(marker)
except Exception:
    externally_managed = False
script_dir = None
candidates = []
try:
    candidates = [sysconfig.get_path("scripts")]
    if user_base:
        candidates.append(sysconfig.get_path("scripts", scheme="nt_user" if os.name == "nt" else os.name + "_user"))
    for directory in candidates:
        if directory and os.path.isfile(os.path.join(directory, "aidp.exe" if os.name == "nt" else "aidp")):
            script_dir = directory
            break
except Exception:
    script_dir = None
try:
    import importlib.util
    has_pip = importlib.util.find_spec("pip") is not None
    has_ensurepip = importlib.util.find_spec("ensurepip") is not None
except Exception:
    has_pip = has_ensurepip = None
packages = {}
for name in %r:
    version = None
    if metadata is not None:
        try:
            version = metadata.version(name)
        except metadata.PackageNotFoundError:
            version = None
    packages[name] = version
print(json.dumps({
    "python": "%%d.%%d.%%d" %% tuple(sys.version_info[:3]),
    "virtualenv": sys.prefix != getattr(sys, "base_prefix", sys.prefix),
    "user_base": user_base,
    "externally_managed": externally_managed,
    "script_dir": script_dir,
    "script_dirs": candidates,
    "pip": has_pip,
    "ensurepip": has_ensurepip,
    "packages": packages,
}))
""" % (PACKAGES,)


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-latest",
        action="store_true",
        default=None,
        help="Do not query the package index for the latest published versions.",
    )
    parser.add_argument("--check-latest", action="store_true",
                        help="Force the published-version lookup, regardless of the weekly cache.")
    parser.add_argument(
        "--index-timeout",
        type=int,
        default=DEFAULT_INDEX_TIMEOUT_SECONDS,
        help="Seconds to wait for each package-index lookup.",
    )
    parser.add_argument(
        "--aidp",
        help="Check this aidp command instead of the one PATH resolves, for example "
        "to verify a fresh installation by its full path.",
    )
    parser.add_argument(
        "--python",
        help="Python interpreter to check when the aidp command is not on PATH "
        "(default: the interpreter running this script).",
    )
    return parser


def _run(command, timeout):
    environment = os.environ.copy()
    environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    environment["PIP_NO_INPUT"] = "1"
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=environment,
        )
    except FileNotFoundError:
        return None, "", "command not found"
    except subprocess.TimeoutExpired:
        return None, "", "timed out after %ss" % timeout
    except OSError as exc:
        return None, "", str(exc)
    return result.returncode, result.stdout, result.stderr


def _first_line(text):
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return None


def _parse_version(text):
    match = VERSION_RE.search(text or "")
    return match.group(1) if match else None


def _release(version):
    if not isinstance(version, str):
        return None
    match = RELEASE_RE.match(version)
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def _is_older(installed, latest, components=None):
    left, right = _release(installed), _release(latest)
    if left is None or right is None:
        return None
    if components is not None:
        left, right = left[:components], right[:components]
    width = max(len(left), len(right))
    left += (0,) * (width - len(left))
    right += (0,) * (width - len(right))
    return left < right


def _tool(name, arguments, path=None, timeout=VERSION_TIMEOUT_SECONDS):
    path = path or shutil.which(name)
    if not path:
        return {"status": "missing"}
    returncode, stdout, stderr = _run([path] + list(arguments), timeout)
    version = _parse_version(stdout) or _parse_version(stderr)
    if returncode == 0 and version:
        return {"status": "installed", "version": version, "path": path}
    return {
        "status": "invalid",
        "path": path,
        "detail": _first_line(stderr) or _first_line(stdout) or "exit status %s" % returncode,
    }


def _oci_cli(path_result, aidp_path, interpreter):
    """Reuse OCI from the selected environment before declaring it missing."""
    if path_result["status"] != "missing":
        return dict(path_result, path_adjustment_required=False)
    directories = []
    for executable in (aidp_path, os.path.realpath(aidp_path) if aidp_path else None, interpreter):
        if executable:
            directory = os.path.dirname(os.path.abspath(executable))
            if directory not in directories:
                directories.append(directory)
    for directory in directories:
        candidate = os.path.join(directory, OCI_EXE)
        if _executable_file(candidate):
            result = _tool("oci", ["--version"], path=candidate)
            return dict(result, path_adjustment_required=result["status"] == "installed")
    return path_result


def _python():
    version = "%d.%d.%d" % tuple(sys.version_info[:3])
    result = {"status": "installed", "version": version, "path": sys.executable}
    if tuple(sys.version_info[:2]) < MIN_PYTHON:
        result["status"] = "invalid"
        result["detail"] = "Python %d.%d or later is required" % MIN_PYTHON
    return result


def _pip():
    returncode, stdout, stderr = _run(
        [sys.executable, "-m", "pip", "--version"], VERSION_TIMEOUT_SECONDS
    )
    version = _parse_version(stdout)
    if returncode == 0 and version:
        return {"status": "installed", "version": version}
    return {"status": "missing", "detail": _first_line(stderr) or "pip is not available"}


def interpreter_from_script(script_path):
    """Return the Python interpreter named by a console script, if any."""
    try:
        if WINDOWS and str(script_path).lower().endswith(".exe"):
            # pip/distlib console launchers are PE files with an embedded
            # interpreter shebang and a ZIP __main__.py. Never execute unknown
            # native/TypeScript executables to discover Python ownership.
            with zipfile.ZipFile(script_path) as archive:
                entry = archive.getinfo("__main__.py")
                if entry.file_size > 65536 or b"aidp_cli" not in archive.read(entry):
                    return None
            with open(script_path, "rb") as handle:
                raw = handle.read(4 * 1024 * 1024)
            headers = re.findall(rb"#!([^\r\n]+)[\r\n]", raw)
            if not raw.startswith(b"MZ") or not headers:
                return None
            candidate = headers[-1].decode("utf-8").strip().strip('"')
            return os.path.abspath(candidate) if _executable_file(candidate) else None
        with open(os.path.realpath(script_path), "rb") as handle:
            head = handle.read(1024).decode("utf-8", "replace")
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, UnicodeError):
        return None
    if not head.startswith("#!"):
        return None
    lines = head.splitlines()
    parts = lines[0][2:].strip().split()
    if not parts:
        return None
    candidate = parts[0]
    if os.path.basename(candidate) == "env":
        names = [part for part in parts[1:] if not part.startswith("-")]
        candidate = shutil.which(names[0]) if names else None
    elif os.path.basename(candidate) == "sh":
        # pip writes this form when the interpreter path is long or has spaces.
        match = SH_EXEC_RE.search(head)
        candidate = match.group(1) if match else None
    if (
        candidate
        and "python" in os.path.basename(candidate).lower()
        and os.path.isfile(candidate)
        and os.access(candidate, os.X_OK)
    ):
        return os.path.abspath(candidate)
    return None


def _probe_packages(interpreter, timeout=VERSION_TIMEOUT_SECONDS):
    returncode, stdout, stderr = _run(
        [interpreter, "-c", PACKAGE_PROBE], timeout
    )
    if returncode != 0:
        return None, _first_line(stderr) or "package probe failed"
    try:
        return json.loads(stdout), None
    except ValueError:
        return None, "package probe returned unreadable output"


def _index_versions(interpreter, package, timeout):
    returncode, stdout, stderr = _run(
        [interpreter, "-m", "pip", "index", "versions", package], timeout
    )
    latest = INDEX_LATEST_RE.search(stdout or "") if returncode == 0 else None
    if not latest:
        detail = _first_line(stderr) if returncode is not None else stderr
        return {"latest": None, "available": [], "detail": detail or "index lookup failed"}
    available = INDEX_AVAILABLE_RE.search(stdout)
    versions = [v.strip() for v in available.group(1).split(",")] if available else []
    return {"latest": latest.group(1).strip(), "available": versions}


def _update_status(installed, latest):
    older = _is_older(installed, latest)
    if older is None:
        return "unknown"
    return "update available" if older else "up to date"


def _shell(command):
    if WINDOWS:
        return "& " + " ".join("'" + part.replace("'", "''") + "'" for part in command)
    return " ".join(shlex.quote(part) for part in command)


def _chain(first, second):
    if WINDOWS:
        return first + "; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; " + second
    return first + " && " + second


def _pip_install(python, target, flags=()):
    # Both packages in one pip call, pinned to a version verified to exist for
    # both, so pip either installs the matching pair or changes nothing.
    base = [python, "-m", "pip", "install", "--upgrade"] + list(flags)
    return _shell(base + ["%s==%s" % (CLIENT_PACKAGE, target), "%s==%s" % (CLI_PACKAGE, target)])


def _upgrade_command(interpreter, target, user_install, break_system_packages=False, bootstrap_pip=False):
    flags = []
    if user_install:
        flags.append("--user")
    if break_system_packages:
        flags.append("--break-system-packages")
    command = _pip_install(interpreter, target, flags)
    if bootstrap_pip:
        # The environment that owns aidp has no pip; ensurepip restores it first.
        command = _chain(
            _shell([interpreter, "-m", "ensurepip", "--upgrade"] + (["--user"] if user_install else [])),
            command,
        )
    return command


def _venv_command(interpreter, target):
    # Externally managed interpreters (PEP 668) reject pip installs, including
    # --user, so install into a dedicated virtual environment instead.
    venv_python = os.path.join(VENV_DIR, VENV_BIN, PYTHON_EXE)
    return _chain(
        _shell([interpreter, "-m", "venv", VENV_DIR]),
        _pip_install(venv_python, target),
    )


def _pipx_command(target):
    return _chain(
        _shell(["pipx", "install", "--force", "%s==%s" % (CLI_PACKAGE, target)]),
        _shell(["pipx", "inject", "aidp-cli", "%s==%s" % (CLIENT_PACKAGE, target)]),
    )


def _common_target(index):
    """Highest version published for both packages, preferring the CLI's latest."""
    cli = index.get(CLI_PACKAGE, {})
    client = index.get(CLIENT_PACKAGE, {})
    latest_cli = cli.get("latest")
    client_versions = set(client.get("available", [])) | {client.get("latest")}
    if latest_cli and _release(latest_cli) is not None and latest_cli in client_versions:
        return latest_cli
    shared = [v for v in set(cli.get("available", [])) & client_versions if v and _release(v)]
    return max(shared, key=_release) if shared else None


def _executable_file(path):
    return os.path.isfile(path) and os.access(path, os.X_OK)


def _read_context():
    # Use the context helper's get interface; never parse context.json here.
    helper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aidp_context.py")
    code, stdout, stderr = _run([sys.executable, helper, "get", "all"], VERSION_TIMEOUT_SECONDS)
    if code == 0:
        try:
            value = json.loads(stdout)
            if isinstance(value, dict) and value.get("schemaVersion") == 2:
                return value, None
        except ValueError:
            pass
    return None, "AIDP context could not be read; using local CLI discovery."


def _latest_due(context):
    try:
        checked = context["latestVersionCheck"]["checkedAt"]
        checked = datetime.fromisoformat(checked.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - checked > timedelta(days=7)
    except (KeyError, TypeError, ValueError):
        return True


def _select_cli(context, python=None, aidp=None):
    """Bounded, nonrecursive discovery, with one version check per executable.

    Remembered selections are trusted as Python installations. Inspect ownership
    only for new candidates. Preserve interpreter symlinks: resolving a venv's
    Python to its base executable would lose the owning environment.
    """
    deadline = time.monotonic() + VERSION_TIMEOUT_SECONDS
    versions = {}
    seen = set()
    probes = {}
    failures = []
    fallback = os.path.abspath(python or sys.executable)

    def remaining():
        return max(0.001, deadline - time.monotonic())

    def version(path):
        key = os.path.realpath(path)
        if key not in versions:
            versions[key] = _tool("aidp", ["--version"], path, remaining())
        return versions[key]

    def candidate(path):
        path = os.path.abspath(path)
        key = os.path.realpath(path)
        if key in seen or time.monotonic() >= deadline or not _executable_file(path):
            return None
        seen.add(key)
        owner = interpreter_from_script(path)
        if owner:
            result = version(path)
            if result["status"] == "installed":
                return result, owner, "aidp", probes
            failures.append((result, owner))
        return None

    if aidp:
        path = os.path.abspath(aidp)
        owner = interpreter_from_script(path)
        result = version(path) if owner else {
            "status": "invalid", "path": path,
            "detail": "the selected aidp command is not a Python CLI",
        }
        return result, owner or fallback, "aidp" if owner else "option", probes

    saved = (context or {}).get("pythonCli")
    if saved and _executable_file(saved["path"]):
        result = version(saved["path"])
        if result["status"] == "installed" and _executable_file(saved["pythonPath"]):
            return result, saved["pythonPath"], "context", probes

    # A timed-out remembered executable must not consume fallback discovery's budget.
    deadline = time.monotonic() + VERSION_TIMEOUT_SECONDS
    paths = [os.path.join(directory, AIDP_EXE) for directory in os.get_exec_path()]
    paths.append(os.path.join(VENV_DIR, VENV_BIN, AIDP_EXE))
    for path in paths:
        selected = candidate(path)
        if selected:
            return selected

    if time.monotonic() < deadline:
        probes[fallback] = _probe_packages(fallback, remaining())
        facts = probes[fallback][0] or {}
        directories = facts.get("script_dirs") or [facts.get("script_dir")]
        for directory in directories:
            if directory:
                selected = candidate(os.path.join(directory, AIDP_EXE))
                if selected:
                    return selected
    detail = "No working Python aidp CLI was found."
    if time.monotonic() >= deadline:
        detail += " Discovery reached its time limit."
    if failures:
        result, owner = failures[-1]
        result = dict(result, detail=detail)
        return result, owner, "aidp", probes
    return {"status": "missing", "detail": detail}, fallback, "option" if python else "python3", probes


def check(skip_latest, index_timeout, python=None, aidp=None):
    context, context_error = _read_context()
    if skip_latest is None:
        skip_latest = not _latest_due(context)
    path_aidp = shutil.which("aidp")
    off_path_dir = None
    with ThreadPoolExecutor(max_workers=6) as pool:
        pip_future = pool.submit(_pip)
        oci_future = pool.submit(_tool, "oci", ["--version"])
        selection_future = pool.submit(_select_cli, context, python, aidp)
        aidp_cli, interpreter, source, probes = selection_future.result()
        owner = interpreter if source in ("aidp", "context") else None
        aidp_path = aidp_cli.get("path")
        if aidp_path and (not path_aidp or os.path.realpath(path_aidp) != os.path.realpath(aidp_path)):
            off_path_dir = os.path.dirname(aidp_path)
        probe_future = None if interpreter in probes else pool.submit(_probe_packages, interpreter)
        # The probe is fast and decides which pip can query the index, so the
        # lookups start only after it returns.
        probe, probe_error = probes[interpreter] if probe_future is None else probe_future.result()
        # Probe results, or an empty mapping when the probe failed; `probe`
        # itself still marks that failure for the client's "unknown" status.
        facts = probe or {}
        owner_has_pip = facts.get("pip") is not False
        owner_has_ensurepip = facts.get("ensurepip") is not False
        checker_pip = pip_future.result()
        index_python = interpreter
        if not owner_has_pip:
            # The environment that owns aidp has no pip; any Python with pip
            # reads the same package index.
            index_python = sys.executable if checker_pip["status"] == "installed" else None
        index_futures = {}
        if not skip_latest and index_python:
            for package in PACKAGES:
                index_futures[package] = pool.submit(
                    _index_versions, index_python, package, index_timeout
                )
        index = {package: future.result() for package, future in index_futures.items()}
        if not skip_latest and not index_python:
            index = {
                package: {"latest": None, "available": [], "detail": "no Python with pip is available to query the package index"}
                for package in PACKAGES
            }
        prerequisites = {
            "python": _python(),
            "pip": checker_pip,
            "oci_cli": _oci_cli(oci_future.result(), aidp_path, interpreter),
        }

    installed = facts.get("packages", {})
    cli_version = installed.get(CLI_PACKAGE)
    client_version = installed.get(CLIENT_PACKAGE)

    if aidp_cli["status"] == "invalid" and cli_version:
        aidp_cli.setdefault("version", cli_version)
    if aidp_cli["status"] == "missing" and cli_version and _release(cli_version) is None:
        aidp_cli = {"status": "invalid", "version": cli_version,
                    "detail": "the installed aidp-cli package has an invalid version"}
    if aidp_cli["status"] == "installed":
        aidp_cli["on_path"] = off_path_dir is None
    below_minimum = bool(
        aidp_cli["status"] == "installed" and _is_older(aidp_cli.get("version"), MIN_AIDP_CLI, components=3)
    )
    invalid_cli_version = (
        aidp_cli["status"] in ("installed", "invalid")
        and aidp_cli.get("version") is not None
        and _release(aidp_cli.get("version")) is None
    )
    if below_minimum:
        aidp_cli["status"] = "invalid"
        aidp_cli["detail"] = "aidp-cli %s or later is required" % MIN_AIDP_CLI
    elif invalid_cli_version:
        aidp_cli["status"] = "invalid"
        aidp_cli["detail"] = "the installed aidp-cli version is invalid; its required minimum cannot be verified"
    prerequisites["aidp_cli"] = aidp_cli

    if probe is None:
        prerequisites["aidp_python_client"] = {"status": "unknown", "detail": probe_error}
    elif client_version:
        prerequisites["aidp_python_client"] = {"status": "installed", "version": client_version}
    else:
        prerequisites["aidp_python_client"] = {"status": "missing"}

    cli_installed_version = aidp_cli.get("version")
    match = None
    if cli_installed_version and client_version:
        match = cli_installed_version == client_version

    latest_cli = index.get(CLI_PACKAGE, {}).get("latest")
    latest_client = index.get(CLIENT_PACKAGE, {}).get("latest")
    target = _common_target(index)
    # Both version lists were read and share no release.
    no_shared_release = bool(
        target is None
        and all(index.get(package, {}).get("latest") for package in PACKAGES)
    )

    versions = {
        "match": match,
        "latest": {CLI_PACKAGE: latest_cli, CLIENT_PACKAGE: latest_client},
        "aidp_cli_update": _update_status(cli_installed_version, latest_cli),
        "aidp_python_client_update": _update_status(client_version, latest_client),
        "target_version": target,
        "no_shared_release": no_shared_release,
        "index_python": None if skip_latest else index_python,
    }
    if skip_latest:
        versions["latest_detail"] = "skipped"
    else:
        details = [index[p]["detail"] for p in PACKAGES if index[p].get("detail")]
        if details:
            versions["latest_detail"] = details[0]

    user_base = facts.get("user_base")
    user_install = bool(
        aidp_path
        and user_base
        and not facts.get("virtualenv")
        and os.path.realpath(aidp_path).startswith(os.path.realpath(user_base) + os.sep)
    )

    missing = [
        package
        for key, package in (("aidp_cli", CLI_PACKAGE), ("aidp_python_client", CLIENT_PACKAGE))
        if prerequisites[key]["status"] == "missing"
    ]
    reasons = ["%s is not installed" % package for package in missing]
    failed_cli = aidp_cli["status"] == "invalid"
    if failed_cli and not (below_minimum or invalid_cli_version):
        reasons.append(aidp_cli.get("detail", "the Python aidp command failed validation"))
    if below_minimum:
        reasons.append(
            "aidp-cli %s or later is required; %s is installed"
            % (MIN_AIDP_CLI, cli_installed_version)
        )
    if invalid_cli_version:
        reasons.append("the installed aidp-cli version is invalid; install a verified supported release")
    if match is False:
        reasons.append(
            "aidp-cli %s and aidp-python-client %s do not match"
            % (cli_installed_version, client_version)
        )
    if versions["aidp_cli_update"] == "update available":
        reasons.append("aidp-cli %s is available" % latest_cli)

    externally_managed = bool(
        facts.get("externally_managed") and not facts.get("virtualenv")
    )
    # An existing `aidp` in an externally managed interpreter does not make
    # changing that interpreter safe, so the in-place override is only offered.
    managed_existing = bool(externally_managed and owner and cli_version)

    actions = []
    oci_off_path = prerequisites["oci_cli"].get("path_adjustment_required", False)
    if (off_path_dir or oci_off_path) and aidp_cli["status"] == "installed":
        # Keep the selected AIDP first even when only OCI needs the prefix.
        directories = [os.path.dirname(aidp_path)]
        path_reasons = []
        if off_path_dir:
            path_reasons.append(
                "PATH runs %s instead of %s" % (path_aidp, aidp_path) if path_aidp
                else "the aidp command is installed in %s, which is not on PATH" % off_path_dir)
        if oci_off_path:
            oci_path = prerequisites["oci_cli"]["path"]
            oci_directory = os.path.dirname(oci_path)
            if oci_directory not in directories:
                directories.append(oci_directory)
            path_reasons.append("the oci command is installed in %s, which is not on PATH" % oci_directory)
        path_hint = os.pathsep.join(directories)
        actions.append(
            {
                "kind": "add_to_path",
                "reasons": path_reasons,
                "path_hint": path_hint,
                "aidp_path": aidp_path,
                "command": ("$env:PATH = '" + path_hint.replace("'", "''") + "' + [IO.Path]::PathSeparator + $env:PATH")
                if WINDOWS else 'export PATH=%s"${PATH:+:$PATH}"' % shlex.quote(path_hint),
                "scope": "session",
            }
        )
    # Only when missing pip is what prevented the version lookup; a skipped
    # lookup stays unverified whether or not pip is restored.
    pip_blocked_lookup = not skip_latest and index_python is None
    if reasons and pip_blocked_lookup and not owner_has_pip and owner_has_ensurepip:
        # pip is needed before any matching release can be verified or
        # installed; restoring it changes no AIDP package.
        actions.append(
            {
                "kind": "restore_pip",
                "reasons": ["the Python that owns aidp has no pip"],
                "command": _shell(
                    [interpreter, "-m", "ensurepip", "--upgrade"]
                    + (["--user"] if user_install else [])
                ),
            }
        )
    if reasons:
        action = {
            # A missing or below-minimum package is a prerequisite installation,
            # not an upgrade, so setup asks its single install question instead
            # of the upgrade prompt.
            "kind": "install_aidp_packages" if missing or failed_cli else "upgrade_aidp_packages",
            "reasons": reasons,
            "target_version": target,
        }
        if target is not None and _is_older(target, MIN_AIDP_CLI, components=3):
            action["install_method"] = None
            action["command"] = None
            action["blocked"] = (
                "no release of aidp-cli %s or later is published for both packages" % MIN_AIDP_CLI
            )
        elif target is None:
            # Without a version verified for both packages, any command could
            # change one package and then fail on the other, so none is offered.
            action["install_method"] = None
            action["command"] = None
            if no_shared_release:
                action["blocked"] = (
                    "no release is published for both aidp-cli %s and aidp-python-client %s"
                    % (latest_cli, latest_client)
                )
            elif skip_latest:
                action["blocked"] = "the package-index lookup was skipped"
            else:
                action["blocked"] = "the package index could not be read to verify a matching release"
        elif not aidp_path or not owner or externally_managed or not (owner_has_pip or owner_has_ensurepip):
            # Without pip or ensurepip in the owning environment, an isolated
            # environment built from the checker's own Python is the reliable path.
            venv_base = interpreter if owner_has_ensurepip else sys.executable
            action["install_method"] = "virtualenv"
            action["command"] = _venv_command(venv_base, target)
            action["path_hint"] = os.path.join(VENV_DIR, VENV_BIN)
            action["verify_aidp"] = os.path.join(VENV_DIR, VENV_BIN, AIDP_EXE)
            alternative = _pipx_command(target) if shutil.which("pipx") else None
            if alternative:
                action["alternative_command"] = alternative
            if managed_existing and owner_has_pip:
                action["in_place_command"] = _upgrade_command(
                    interpreter, target, user_install, break_system_packages=True
                )
        else:
            action["install_method"] = "pip"
            action["command"] = _upgrade_command(
                interpreter, target, user_install, bootstrap_pip=not owner_has_pip
            )
        actions.append(action)

    required = ("python", "pip", "oci_cli", "aidp_cli", "aidp_python_client")
    blocking = [key for key in required if prerequisites[key]["status"] in ("missing", "invalid", "unknown")]

    aidp_cli.setdefault("path", aidp_path)
    aidp_cli.update({
        "source": source,
        "validated": aidp_cli["status"] == "installed" and probe is not None,
        "current_path_aidp": path_aidp,
        "path_adjustment_required": bool(off_path_dir),
    })

    return {
        "command_shell": "powershell" if WINDOWS else "posix",
        "context": context,
        "context_error": context_error,
        "ok": not blocking,
        "blocking": blocking,
        "environment": {
            "os": platform.system(),
            "os_release": platform.mac_ver()[0] or platform.release(),
            "architecture": platform.machine(),
        },
        "prerequisites": prerequisites,
        "aidp_python": {
            "path": interpreter,
            "source": source,
            "version": facts.get("python"),
            "virtualenv": facts.get("virtualenv"),
            "user_install": user_install,
            "externally_managed": externally_managed,
            "pip": facts.get("pip"),
        },
        "versions": versions,
        "actions": actions,
    }


def main():
    args = _parser().parse_args()
    if args.skip_latest and args.check_latest:
        print("--skip-latest and --check-latest cannot be combined", file=sys.stderr)
        return 2
    if args.index_timeout < 1:
        print("--index-timeout must be at least 1", file=sys.stderr)
        return 2
    if args.python and not _executable_file(args.python):
        print("--python must name an executable Python interpreter", file=sys.stderr)
        return 2
    if args.aidp and not _executable_file(args.aidp):
        print("--aidp must name an executable aidp command", file=sys.stderr)
        return 2
    summary = check(False if args.check_latest else args.skip_latest, args.index_timeout, args.python, args.aidp)
    print(json.dumps(summary, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
