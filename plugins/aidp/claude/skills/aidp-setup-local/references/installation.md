# Prerequisite installation guidance

Use this reference when a prerequisite is missing and the user has approved its installation, or when the user has approved an AIDP CLI and Python client upgrade.

For failed or stalled installations and package-index lookups, follow [setup troubleshooting](troubleshooting.md).

## Python 3.9 or later and pip

Detect the operating system and available package manager before proposing a command. Prefer an existing, trusted package manager:

- macOS: Homebrew, when already installed.
- Debian or Ubuntu Linux: `apt` packages for `python3` and `python3-pip`.
- Fedora or RHEL-compatible Linux: `dnf` packages for Python 3 and pip.
- Windows: `winget`, when available, or the official Python installer.

Show the exact command and explain whether it needs elevated privileges before running it. Do not install a package manager automatically. After installation, require both of these checks to pass:

```bash
python3 --version
python3 -m pip --version
```

## Installation process

Run each installation in a foreground command session, retain its process/session handle, and poll that same session until it exits before starting another installer or final verification. Quiet output alone does not mean failure; keep waiting while progress continues, without an overall installation time limit. Do not start duplicate installers or retry blindly. Give brief updates for meaningful progress or an unusually long delay. For failure, prolonged inactivity, or a lost session, follow [installer troubleshooting](troubleshooting.md#stalled-or-interrupted-installation).

Run final prerequisite verification once after all planned installations/upgrades finish, not after each individual package. Retain bootstrap checks needed to obtain the remaining installation commands. Run `<environment-python> -m pip check` once per Python environment changed by this setup. Skip it when prerequisites already pass and no packages were installed or upgraded. Block completion only on missing or incompatible requirements needed by OCI CLI, the OCI SDK, AIDP CLI, the AIDP Python client, or their dependencies. Unrelated pre-existing package conflicts do not block AIDP setup and must not trigger automatic repairs.

## OCI CLI

The prerequisite checker reuses an existing OCI CLI from PATH or the selected
AIDP/Python environment. When it reports an installed OCI CLI outside PATH, apply
the returned session PATH prefix for each invocation; do not reinstall it. Keep
the verified OCI executable path for the session. A prefix applied in an earlier
chat or tool call is not assumed to persist, and no shell startup changes are
needed.

On macOS/Linux, when Python and pip are available, installation into the active Python environment is acceptable:

```bash
python3 -m pip install oci-cli
```

Inside a virtual environment, do not add `--user`. Outside a virtual environment, prefer the official OCI CLI installer or a user-scoped installation to avoid modifying the system Python. The final prerequisite check verifies OCI CLI; use this command only for targeted OCI troubleshooting, not as an additional routine check:

```bash
oci --version
```

### Windows OCI CLI installation

For pip-based Windows installation, use the selected approved virtual environment with ordinary Windows paths. If the returned AIDP installation command creates that environment, run it to completion first, then install OCI CLI there. Otherwise create the environment with the selected Python only if it does not exist; do not recreate an existing environment.

Invoke pip with that environment’s own `Scripts\python.exe`, replacing the sample path with the selected interpreter:

```powershell
& 'C:\Users\User\.aidp-venv\Scripts\python.exe' -m pip install oci-cli
```

Do not add an extended-length `--prefix` (`\\?\...`), which can fail with error 22 while creating dependency scripts. A virtual environment already selects pip’s destination. Keep dependencies enabled; do not add `--no-deps`, `--force-reinstall` or `--user` as a general repair.

For installation errors, follow [Windows path and script errors](troubleshooting.md#windows-path-and-script-errors).

Preserve the configured package index, proxy and certificates. Use the environment’s `Scripts` directory for command discovery and apply the final verification rules under Installation process once all planned packages are installed. Do not report success solely from downloaded files or an active process.

## AIDP Python SDK and CLI

Install the AIDP Python client and CLI together from the configured Python package index. The two packages must have identical installed versions, and `aidp-cli` accepts any recent client, so an unpinned install can leave them on different versions. Pin both to one version published for both: the latest `aidp-cli` when it is also published for `aidp-python-client`, otherwise the highest version published for both. Always install or upgrade both in one pip call, so pip either installs the matching pair or changes nothing; never upgrade one package first and the other afterwards. If no version is published for both, or the index cannot be read to verify one, do not install or upgrade either package; wait until a matching release can be verified.

`scripts/check_prerequisites.py` reads the installed and published versions and returns the exact command in its `actions` entry. Prefer that command, because it uses the interpreter that owns `aidp` and keeps a user-scoped installation user-scoped. When no working Python CLI exists, its command uses a dedicated environment, including when TypeScript already supplies `aidp`. Existing Python installations are reused. Its in-place upgrade forms are:

```bash
# Fresh installation
python3 -m pip install "aidp-python-client==<version>" "aidp-cli==<version>"
# Upgrade
python3 -m pip install --upgrade "aidp-python-client==<version>" "aidp-cli==<version>"
```

Run upgrades with the Python that owns `aidp`, which the prerequisite script reports. If that Python has no pip, restore it first with `<python> -m ensurepip --upgrade`; version lookups can use any Python with pip, because they read the same package index. If `ensurepip` is unavailable too, install into a dedicated virtual environment as described below.

When no virtual environment is active and a user-scoped installation is appropriate, add `--user` after `install`. Do not add `--user` inside a virtual environment. Confirm with:

```bash
python3 <skill_dir>/scripts/check_prerequisites.py
```

### Externally managed Python

Some Python installations, such as Homebrew Python and recent Debian, Ubuntu, and Fedora system Python, are marked externally managed (PEP 668). pip refuses to install into them, including with `--user`, and fails with `externally-managed-environment`. For a new installation, do not work around this with `--break-system-packages`. Install into a dedicated virtual environment instead; it needs nothing beyond Python itself:

```bash
python3 -m venv ~/.aidp-venv
~/.aidp-venv/bin/python -m pip install --upgrade "aidp-python-client==<version>" "aidp-cli==<version>"
```

The `aidp` command is then `~/.aidp-venv/bin/aidp`. Verify it through the prerequisite script with `--aidp ~/.aidp-venv/bin/aidp`; do not add a separate version call. Save the returned selection through the context helper. Apply the script’s scoped PATH adjustment only when required, for the session’s skill commands without editing shell startup files. On Debian or Ubuntu, if creating the environment fails because `ensurepip` is unavailable, the `python3-venv` package is required first.

When pipx is already installed, it is an equivalent alternative that manages the environment and `PATH` itself:

```bash
pipx install --force "aidp-cli==<version>"
pipx inject aidp-cli "aidp-python-client==<version>"
```

Do not install pipx only for this purpose.

This also applies when AIDP is already installed in an externally managed interpreter: an existing installation does not make changing that interpreter safe. Default to `~/.aidp-venv` and put its `bin` folder first on `PATH`. Upgrading in place with that interpreter and `--break-system-packages`, the prerequisite script's `in_place_command`, is an explicit alternative the user must choose.


Do not download GitHub release archives or use GitHub release metadata for normal installation, version discovery, or upgrades.
