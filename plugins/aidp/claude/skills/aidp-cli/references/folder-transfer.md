# Folder upload and download

Use for **folder** transfers or requested archive extraction. For an existing ZIP,
confirm extraction intent unless already explicit. Upload-only ZIP requests use
the single-file API, not this helper.

The helper keeps PAR URLs inside the process: CREATE → PUT → UPDATE → poll for
upload; create ZIP → poll → GET for download. It prints only progress, operation
key, final paths, and URL-redacted error diagnostics. It neither modifies the GA CLI nor retries failed transfers.
Use the session's validated authentication, profile, instance, and endpoint.
Use setup’s session command environment. When either `prerequisites.aidp_cli.path_adjustment_required` or `prerequisites.oci_cli.path_adjustment_required` is true, prepend the `add_to_path` action’s `path_hint` to the helper process’s `PATH`; its child `aidp` calls inherit the selection. No separate CLI-path argument is needed.
`<skill_dir>` is the aidp-cli skill directory containing SKILL.md. In a restricted
environment, obtain network access for the helper before running it; this covers
both its AIDP CLI calls and Object Storage transfer.
Pass `--region` instead of `--endpoint` when using regional routing; optional
`--config-file` and inherited OCI_CLI_CONFIG_FILE preserve custom OCI configuration.

```bash
# Workspace folder archive upload (.zip or .aidp)
python3 <skill_dir>/scripts/folder-transfer.py upload \
  --aidpOCID <instance-ocid> --workspaceKey <workspace-key> \
  --sourceZipPath /local/MyFolder.zip --destPath imports \
  --auth security_token --profile <profile> --endpoint <endpoint>

# Volume folder archive upload (.zip only)
python3 <skill_dir>/scripts/folder-transfer.py upload \
  --aidpOCID <instance-ocid> --volumeKey <catalog.schema.volume> \
  --sourceZipPath /local/MyFolder.zip --destPath imports \
  --auth security_token --profile <profile> --endpoint <endpoint>

# Workspace folder download
python3 <skill_dir>/scripts/folder-transfer.py download \
  --aidpOCID <instance-ocid> --workspaceKey <workspace-key> \
  --sourcePath imports/MyFolder --destPath /local/downloads \
  --auth security_token --profile <profile> --endpoint <endpoint>

# Volume folder download
python3 <skill_dir>/scripts/folder-transfer.py download \
  --aidpOCID <instance-ocid> --volumeKey <catalog.schema.volume> \
  --sourcePath imports/MyFolder --destPath /local/downloads \
  --auth security_token --profile <profile> --endpoint <endpoint>
```

For automatic folder packaging, replace `--sourceZipPath /local/MyFolder.zip`
with `--sourceFolderPath /local/MyFolder`. The helper ZIPs the folder's contents,
including hidden files and empty subdirectories, without adding the enclosing
folder. Temporary archives are removed after success or failure; symlinks are
rejected. Supply exactly one source option. Download continues to use `--sourcePath`;
the old upload `--sourcePath` remains an alias for an existing archive.

Upload `destPath` is the remote parent directory; `.` means root. Extraction adds
the archive basename without its extension. Existing remote files are preserved
unless `--overwrite` is explicitly authorized (workspace skips existing files;
volume fails on collisions). Both operations require active default workspace compute.

For download, `destPath` is a local directory or a `.zip` filename stem. The helper
creates `foldername-YYYYMMddHHmmss.zip` using local time (24-hour clock). An existing
14-digit timestamp suffix is preserved; existing files are never overwritten.
ZIP CRC integrity is checked before saving. An exclusive-copy fallback supports
filesystems without hard links. Standard HTTPS_PROXY/NO_PROXY settings are honored.
Backend folder exports currently omit empty directories, even though upload preserves them.
Wait limit defaults to 30 minutes (`--waitTimeout` seconds), with 5-second polling
(`--pollInterval`) and 120-second request timeout (`--requestTimeout`). On failure,
inspect the reported operation key before restarting; remote work may continue.

Prepare a ZIP of the folder's contents with `cd MyFolder` then
`zip -r ../MyFolder.zip *`. This places the archive beside the folder. Avoid Finder
Compress packaging such as `__MACOSX`; archive entry paths are preserved. `*` omits
root dotfiles, so include required hidden files explicitly. Use an existing valid
`.aidp` archive for workspace imports; renaming a ZIP does not convert its format.

## Transfer API contract

The helper uses these request and response fields; it supplies the transfer
metadata itself rather than asking the user to enter API fields:

- Upload CREATE: `action`, `zipFileName`, `destinationFolderPath` and
  `isOverwrite`. The response supplies `operationKey` and `uploadUrl`.
- Upload UPDATE: `action`, `operationKey`, `eTag` and `sizeInBytes`, using the
  completed upload's metadata.
- Download: `sourceFolderPath`. The response supplies `operationKey`,
  `downloadUrl` and `archiveName`.
- Polling: `async-operations get <operationKey>`, reading `status`.
  `IN_PROGRESS` continues waiting, `SUCCEEDED` completes, and `FAILED` or
  `CANCELED` stops with an error.

Keep transfer URLs inside the helper and preserve the established no-blind-retry
behavior. Contract drift requires review of both plugin variants and their
helper tests before a new baseline is accepted.

## CLI version and additional properties

Always check the CLI reference documentation for the exact installed CLI
version. Properties may have been introduced or removed after this plugin
release. If the CLI reference lists a new field, also consult
[Additional properties](#additional-properties) for handling details. Verify
field requirements and sensitive-input handling in the CLI reference rather
than guessing when no additional guidance is recorded.

Perform this check yourself. Preserve documented defaults and explicit user
choices, and omit unrequested optional fields, including newly introduced ones.
Ask only for required information that is still missing and has no documented
default or established session value. An empty Additional properties section
must not add a user-input step or block the existing flow.

## Additional properties
