# Prerequisite installation guidance

Use this reference when a prerequisite is missing and the user has approved its installation, or when the user has approved an AIDP CLI and Python client upgrade.

For failed or stalled installations and package-index lookups, follow [setup troubleshooting](troubleshooting.md).

## Python 3.9 or later and pip

First complete the bootstrap flow in `SKILL.md`: a compatible Python can run the checker and read saved context without pip. Validate the saved environment and finish existing-machine and assistant-runtime discovery before offering installation. Reuse a compatible interpreter with working pip; do not install another Python merely because it is absent from PATH. If Python or pip is missing, name the missing components and ask whether the user will install them or wants help. A general AIDP setup request is not confirmation to install Python/pip. Wait for explicit confirmation before running an installer or `ensurepip`, including a pip restore suggested by the checker.

After confirmation, detect the operating system and available package manager before proposing a command. Prefer an existing, trusted package manager:

- macOS: Homebrew, when already installed.
- Debian or Ubuntu Linux: `apt` packages for `python3` and `python3-pip`.
- Fedora or RHEL-compatible Linux: `dnf` packages for Python 3 and pip.
- Windows: `winget`, when available, or the official Python installer.

Show the exact command and explain whether it needs elevated privileges before running it. Do not install a package manager automatically. After installation, require both of these checks to pass:

```bash
python3 --version
python3 -m pip --version
```

### Windows installer recovery

When the official Windows installer fails with MSI error 2203 and `0x80070003`
(path not found), retain its logs and inspect the failing MSI path. This does
not establish a path-length problem or a corrupt download. A local installer
layout is not a guaranteed repair because installation still uses the MSI cache.
Do not keep retrying the same installer or change cache permissions or registry
settings without evidence and approval.

For a command-line environment, Python's official [NuGet distribution](https://docs.python.org/3.13/using/windows.html#the-nuget-org-packages)
is an alternative that does not use Windows Installer. Use it only after the
user has confirmed Python/pip installation. Download the architecture-appropriate
`python` package at a verified version from its official NuGet listing, and
extract the package archive into a fresh user-local directory. A NuGet package
manager installation is not required to extract the archive. Check the package
identity/version and validate the extracted `tools/python.exe` Authenticode
signature as Python Software Foundation before running it; fail closed if
validation fails. Do not substitute Python's embeddable ZIP, which does not
support ordinary pip management.

Verify the extracted interpreter with `--version`, `-m pip --version`, and a
temporary `-m venv <test-directory>` followed by that environment's
`Scripts/python.exe -m pip --version`. If pip is missing, report that fact and
bootstrap it only under the user's confirmed pip-installation scope. Keep the
absolute interpreter path for the prerequisite checker. This provides a local
CLI runtime without registering global commands or editing PATH. NuGet runtime
updates use a new versioned directory, rather than an in-place Python upgrade.

## Installation process

Run each installation in a foreground command session, retain its process/session handle, and poll that same session until it exits before starting another installer or final verification. Quiet output alone does not mean failure; keep waiting while progress continues, without an overall installation time limit. Do not start duplicate installers or retry blindly. Give brief updates for meaningful progress or an unusually long delay. For failure, prolonged inactivity, or a lost session, follow [installer troubleshooting](troubleshooting.md#stalled-or-interrupted-installation).

### Final verification

After all planned installations/upgrades finish, run the prerequisite checker
once. Earlier checks are only for bootstrapping remaining installation commands.
Pass the generated action's exact `--aidp <verify_aidp>` when supplied so a saved
old CLI cannot override the new installation. For a new OCI installation, pass
`--oci <absolute-oci-path>`: use the pip environment's `Scripts\oci.exe` or the
actual executable selected by the MSI wizard. Do not assume a changed PATH is
visible in an existing assistant process.

Save new or changed validated `pythonCli` and `ociCli` independently through the
[context helper](context-cli.md#record-successful-context), then present the
updated prerequisite summary. Do not save missing or failed selections.

Run `<environment-python> -m pip check` once per pip environment changed by setup;
skip it when no packages changed. Block completion only on missing/incompatible
requirements needed by OCI CLI/SDK, AIDP CLI/client or their dependencies.
Unrelated pre-existing conflicts must not trigger automatic repairs. The MSI's
bundled runtime does not require a separate pip check.

If a required check still fails, follow the relevant troubleshooting procedure,
repair once and verify again unless that procedure says to stop. For Windows OCI,
the MSI fallback's confirmation and stopping rules take priority.

## OCI CLI

The checker selects OCI in this order: explicit `--oci`, a working saved
`ociCli.path`, PATH, then bounded candidates beside the selected AIDP/Python and
installation environments, including `<SystemDrive>\oci-cli\Scripts` on Windows.
Saved paths are revalidated and stale paths fall back to discovery. Reuse a
working installation in place; do not relocate it to consolidate directories.

If OCI is missing but the user says it is installed elsewhere, ask for its full
executable path and validate it with `--oci <absolute-executable-path>`. If invalid,
report the error and offer repair instead of silently installing a duplicate.
Otherwise, follow the missing-prerequisite installation question in `SKILL.md`.

Keep the validated path for the session and save it when new or changed through
the [context helper](context-cli.md#record-successful-context). Apply the checker's
scoped PATH prefix on each invocation when required; an earlier chat or tool
call's PATH update is not assumed to persist. Preserve the validated OCI selection
if another prepended directory would shadow it. Never edit global PATH or shell
startup files, recursively scan drives, or guess custom installation folders.

On macOS/Linux, when Python and pip are available, installation into the active Python environment is acceptable:

```bash
python3 -m pip install oci-cli
```

Inside a virtual environment, do not add `--user`. Outside a virtual environment, prefer the official OCI CLI installer or a user-scoped installation to avoid modifying the system Python. The final prerequisite check verifies OCI CLI; use this command only for targeted OCI troubleshooting, not as an additional routine check:

```bash
oci --version
```

### Windows OCI CLI installation

After installation confirmation, use the separate destinations and access checks
in [Windows directory selection](windows.md#installation-directory-selection).
Create or reuse the OCI environment at its [Windows destination](windows.md#installation-directory-selection)
with the selected base Python, then run:

```powershell
& (Join-Path $env:SystemDrive 'oci-cli\Scripts\python.exe') -m pip install oci-cli
```

If directory preparation, environment creation, or pip installation fails, retain
the error and directly offer the MSI fallback below. Do not try another pip
directory, change ACLs or long-path settings, modify the wheel, disable
dependencies, or retry alternate/extended-length prefixes. Wait for the installer
to exit before entering recovery.

Then install the matched AIDP CLI/client pair with the checker's generated action
in its separate AIDP destination defined in the Windows reference. Reuse existing
working tools rather than relocating them. Preserve package-index, proxy and certificate
settings; omit `--user` inside virtual environments.

Finish with [final verification](#final-verification).


### Windows OCI MSI fallback

Offer this fallback immediately after the system-drive OCI directory cannot be
prepared, its virtual-environment creation fails, or its pip installation exits
with an error. Report the actual failure and ask whether the user wants the
official Oracle MSI installer. Explain that it may request Windows administrator
approval and Oracle warns it can overwrite existing OCI CLI installations. A
prior confirmation for the pip attempt is not confirmation to launch MSI; wait
for an explicit MSI choice. Do not offer registry changes or another pip folder
as intermediate recovery. If declined, report OCI setup as incomplete.

After the user chooses MSI:

1. Follow Oracle's [Windows MSI instructions](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm#Windows).
   Resolve the Windows MSI asset from Oracle's official `oracle/oci-cli` GitHub
   release linked there. Use a verified release/version; do not hard-code an
   expiring redirected URL. If the releases page fails, try the official direct
   asset URL for that verified version; stop and report unresolved download errors
   rather than using an unofficial mirror.
2. Download the MSI outside either package environment. Check its SHA-256 against
   the published release-asset digest and validate its Authenticode signature as
   Oracle. Do not launch it if either validation fails.
3. Launch the verified installer with logging:
   `msiexec.exe /i "<downloaded-msi>" /L*v "<installation-log>"`.
   Use actual full paths and appropriate scoped host access. The user completes
   the wizard and any Windows administrator prompt. Keep the MSI installation
   separate from the AIDP virtual environment; do not target a nonempty pip
   environment. Preserve existing OCI credentials/configuration.
4. After user completion, inspect the installation result/log and retain the
   actual `oci.exe` path from the selected destination or installer log. Check a
   relevant help command using that full path. Continue any remaining AIDP
   installation, then follow [final verification](#final-verification) to validate
   and save both selections in one checker run. An earlier checker run is only
   needed if it supplies commands required to finish installation.
5. If MSI fails, report the exit status and diagnostic error; leave setup
   incomplete and stop automated installation retries. Do not alter registry
   settings or delete partial installations without a separately chosen repair.

Validate the installed result rather than assuming future MSI versions avoid
every path issue.

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


Use the configured Python package index for normal pip installations, version discovery, and upgrades. The explicitly chosen Windows OCI MSI fallback is the sole exception for obtaining the official Oracle MSI asset and its verification metadata from GitHub; never use that exception for AIDP packages.
