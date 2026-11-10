# Native Windows execution

Use native Windows Python with PowerShell; do not require WSL, Bash, awk or sed.
The other references show POSIX examples. Apply these Windows equivalents to
all setup, create/update, connection-test, transfer and status commands.

## Python and executable selection

Follow the [bootstrap workflow](../SKILL.md#1-validate-and-summarize-prerequisites).
On Windows, try `python` or `py -3`; do not assume `python3` exists. A Microsoft
Store alias or a missing launcher is not proof that Python is absent. Known
shared interpreter candidates, in order, are:

- `Join-Path $env:USERPROFILE '.aidp-venv\Scripts\python.exe'`
- `Join-Path $env:SystemDrive 'oci-cli\Scripts\python.exe'`

If no bootstrap interpreter is available and the user has a custom installation,
ask for its interpreter path before offering another Python installation. Do not
read context files manually or recursively scan assistant caches. Sharing applies
to the same OS user; another Windows account does not automatically share access.

After selection, use the exact `aidp_python.path` for helpers and AIDP package
commands. The OCI package command is documented in
[installation guidance](installation.md#windows-oci-cli-installation).
Use PowerShell's call operator for quoted executable paths:

```powershell
& 'C:\Users\User\.aidp-venv\Scripts\python.exe' '<skill_dir>\scripts\check_prerequisites.py'
```

Replace paths with actual selected paths. Windows virtual environments use
`Scripts\python.exe` and `Scripts\aidp.exe`, not `bin/python` or `bin/aidp`.
The prerequisite checker understands pip's Windows console launchers and emits
PowerShell install/upgrade commands (`command_shell: powershell`). Execute those
commands in PowerShell without translating them to cmd.exe or a POSIX shell.

When the command tool already runs PowerShell, pass the command text directly to that session. Do not nest another `pwsh.exe -Command` or `powershell.exe -Command`, or construct another layer of escaped/encoded command text. Let the host select the shell. Use `&` with the quoted executable path and pass arguments separately as shown above; apply environment assignments in the same invocation.

Only when the checker requires a PATH adjustment, prepend its `path_hint` for
each process invocation, with the Windows separator. Preserve the selected OCI
executable if this would shadow it. Do not modify shell startup files.

```powershell
$env:PATH = 'C:\Users\User\.aidp-venv\Scripts' + [IO.Path]::PathSeparator + $env:PATH
$env:AIDP_CLI_STRICT_URL_ENCODING = 'true'
& 'C:\Users\User\.aidp-venv\Scripts\aidp.exe' <existing arguments>
```

Environment assignments such as `VAR=value command`, `export`, and
`env PATH=...` are POSIX forms. Use `$env:NAME` assignments in PowerShell. Use
single-line commands rather than backslash continuations. Quote literal paths
with single quotes and double any embedded single quote; use `&` before a quoted
executable path. Use filesystem tools or the selected Python for reference-file
searches/extraction rather than requiring Unix utilities.

## Installation directory selection

Use these destinations for new Windows installations; reuse working existing
tools in their current locations. Other platforms keep their existing paths.

- OCI CLI and its dependencies: `Join-Path $env:SystemDrive 'oci-cli'`.
  Resolve the actual system drive; for example, Windows on `D:` uses
  `D:\oci-cli`. Do not assume `C:` or guess when `SystemDrive` is unavailable.
- AIDP CLI and its matched Python client: `Join-Path $env:USERPROFILE '.aidp-venv'`.
  The checker's `--venv-dir` overrides this AIDP destination only; never pass the
  OCI directory there. Using OCI's Python to bootstrap a check does not make
  that environment an AIDP installation destination.

Keep credentials/configuration, downloads and instance data outside both package
environments. Follow [installation guidance](installation.md#windows-oci-cli-installation)
for package commands, ordering, verification and independent context saves.

Before preparing each directory:

1. Inspect declared filesystem restrictions. If the directory is already known
   to be outside sandbox writable locations, request narrowly scoped host access
   upfront and run the create/write probe under the intended user's normal
   account. Otherwise probe normally; if an unexpected sandbox restriction
   appears, request host access and repeat that probe once. Host access does not
   authorize administrator elevation or ACL changes. Do not repeat a completed
   host probe merely to confirm it.
2. Create an absent directory and verify write access by creating and deleting
   a uniquely named file. Never overwrite a file, reuse an unrelated nonempty
   directory, or change permissions automatically. Verify and reuse a setup
   environment that already exists rather than recreating it.
3. Report failed, unavailable or declined host access. Route OCI directory
   preparation failures to the [MSI fallback](installation.md#windows-oci-msi-fallback).
   AIDP folder-access failures may use the user/IT preparation below.

For an AIDP folder-access failure, provide copyable user/IT commands scoped to the
selected AIDP directory. Resolve the intended Windows user's SID from the normal
host user context; a sandbox account or another administrator is not that user.
Substitute the verified SID and actual selected path; never send placeholders:

```powershell
# An administrator window may be needed if ordinary folder creation was denied.
$aidpInstallDirectory = Join-Path $env:USERPROFILE '.aidp-venv'
New-Item -ItemType Directory -Path $aidpInstallDirectory -Force
icacls $aidpInstallDirectory /grant '*<verified-user-SID>:(OI)(CI)M'
```

For an explicitly selected custom AIDP directory, use that exact path in both
commands. Explain that Modify grants that user access to read, create, change
and delete files in this directory and inheriting children. Never grant on a
parent directory or drive root, grant Everyone access, recursively reset ACLs,
or take ownership. Do not execute administrator commands unless the user asks.
Wait for user/IT completion, then verify write access before retrying. If declined
or still unwritable, report the error and stop that installation.

## Context and identity helpers

Call `scripts/aidp_context.py` directly using the selected Python interpreter.
The helper uses Windows file locking on Windows.

For local OCI identity discovery, follow the consent prompt in the identity
reference before invoking `scripts/oci-whoami.py`. Use its `--profile`,
`--config-file` and `--auth` options to preserve the established selection.
Request only required `--output` fields. `--tenancy-only` reads the profile's
public tenancy field without opening the security token. Never decode tokens
manually or use this helper to bypass identity-discovery consent.

## Paths and protected files

Use an existing writable directory under the system temporary location returned
by `[IO.Path]::GetTempPath()` or Python's `tempfile.gettempdir()`, not literal
`/tmp`. Generate unique names without overwriting existing files:

```powershell
$resultPath = Join-Path ([IO.Path]::GetTempPath()) ('aidp-result-' + [guid]::NewGuid().ToString('N') + '.json')
```

Substitute actual Windows paths in metadata, templates and placeholders. In JSON
use forward slashes (`C:/Users/User/file.pem`) or escaped backslashes. Quote
`@` file arguments as a whole in PowerShell, for example
`--body '@C:\Users\User\AppData\Local\Temp\body.json'`, to avoid splatting.
The wrapper still receives a normal `@filename` argument.

Use the existing protected wrappers for secrets and attachments. Their platform
helper creates owner-only Windows DACLs, checks owner SIDs and allowed access
entries when consuming results, and rejects reparse points. Do not replace
these protections with `chmod` or disable permission checks. A filesystem that
cannot enforce this protection must fail closed; choose a local filesystem with
Windows security-descriptor support.

## Cluster feature checks

Use the same retained authentication, OCI profile and validated endpoint. Build
the full target URI as one quoted argument; do not translate the wrapper API's
`/20240831/dataLakes` route to the public SDK version. For example:

```powershell
oci raw-request --profile '<profile>' --auth security_token --http-method GET --target-uri 'https://<validated-host>/20240831/dataLakes/<instance-ocid>/featureStatuses?featureNames=CLUSTER_AUTOSCALE&featureNames=AI_COMPUTE_AUTOSCALE_ENABLED'
```

Use the established auth mode, not necessarily `security_token`. Request narrowly
scoped network execution approval before the first call when the host restricts
network access, just as on other platforms. Configuration confirmation and the
stop-after-acceptance behavior for cluster creation remain unchanged.
