# Credentials: discovery and protected input

For `create_credential` / `update_credential`, the CLI group in this repository is
`credentials` (plural). Read [create](create.md) or [update](update.md), then
[protected bodies](../protected-bodies.md). Check installed group/operation help
before constructing the final command; preserve established auth and target.

| Type in this SDK | Non-sensitive values to derive or ask in chat | Private input just before execution |
|---|---|---|
| `SECRET_TOKEN` | Display name; secret-key names and number of pairs; optional description | One required hidden `secretValue` per pair |
| `SERVICE_ACCOUNT` | Intended OCI user OCID, tenancy, region, fingerprint; read-only intent; local PEM path | `privateKey` via `{textof:PATH}` |
| `VAULT_REFERENCE` | Selected Vault secret OCID as `secretId` | None; do not retrieve the secret value |

`credentialDetails.credentialType` must match top-level `type`. `secretKey` names
are labels, not secret values; a `credentialKey` identifies an existing resource,
not a substitute for creation's credential details. Do not use the current OCI
user automatically for a service account: it may be a different identity. Reuse
non-sensitive OCI metadata only for the intended identity. Never read or print
profile keys or a private PEM to derive values. Resolve fingerprint from public
IAM metadata or a public key, or ask in chat if unavailable. `isReadOnly` is
optional in the inspected backend but required by some generated SDK/help
versions: follow installed help and the intended access scope.

The inspected backend additionally supports Git credentials and uses different
enum spellings from this SDK. Do not translate or enable those payloads by guess.
The helper supports the three SDK types above; discover an installed Git
credential contract separately if needed. Git PAT user settings have their own
[reference](../user-settings/common.md).

For new names, the inspected backend accepts a letter followed by letters,
digits or underscores, up to 255 characters; description is at most 255. Verify
live validation when versions differ. Secret pairs must be non-empty with unique
non-empty keys. The backend limits secret values to 1 MiB; do not ask the agent
to inspect them for validation.

## Helper contract

`scripts/credentials/prepare-body.py` takes `--operation create|update`,
`--metadata @/tmp/credential-metadata-<unique>.json`, and
`--output /tmp/body-credential-<unique>.json`. Metadata contains only confirmed
non-sensitive request fields and unresolved placeholders. It never contains raw
or masked secrets, nor an unfiltered GET response. The helper checks `credentialDetails.secretTokenPair[].secretValue` for
`SECRET_TOKEN` and `credentialDetails.privateKey` for `SERVICE_ACCOUNT`, rejecting
raw or masked values at those exact fields. `VAULT_REFERENCE.secretId` remains a
public reference. It adds protected placeholders and never reads private keys.
It creates a fresh owner-only template and never overwrites an existing file.

Create or payload replacement additionally takes `--type SECRET_TOKEN|SERVICE_ACCOUNT|VAULT_REFERENCE`.
For secret tokens, repeat `--secret-key NAME` for each intended pair; for service
accounts supply `--private-key-path /local/key.pem`. Metadata-only updates omit
`--type`, `credentialDetails`, and secret options. Payload replacement on update
requires `--replace-secrets` even for changing a Vault reference.

Run `scripts/validate-protected-paths.py @/tmp/body-credential-<unique>.json`
before prompting. File paths may be discussed in chat; contents stay outside
model context. Use the generic protected wrapper with `--output-file` and consume
then delete the agreed result using `read-protected-result.py`. The terminal
shows prompts and `Operation output handed off to AI agent. Ask it to continue.`
Follow the shared reference for cancellation, cleanup and safe continuation.

## Local evidence

Field shapes: SDK `CreateDataLakeCredentialDetails`, `UpdateDataLakeCredentialDetails`,
`CredentialDetails`, `SecretTokenCredentialDetails`, `SecretPair`,
`ServiceAccountCredentialDetails`, `VaultReferenceCredentialDetails` in
`aidp-python-client/src/aidp_python_client/aidataplatform_dp/models/`.
Required/type validation also checked against `CredentialV2Validator.java` in
the supplied API-handler checkout. Installed CLI help takes precedence.

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
