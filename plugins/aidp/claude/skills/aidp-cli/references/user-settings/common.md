# User settings: discovery and protected input

For `create_user_setting` / `update_user_setting`, use CLI `user-setting`.
Read [create](create.md) or [update](update.md) and
[protected bodies](../protected-bodies.md). Settings belong to the authenticated
user; do not infer another user's setting from a matching display name.

| `data.type` | Derive/discuss in chat | Local private input |
|---|---|---|
| `GIT_ACCOUNT` | Provider, name, default intent; PAT entity type | Required visible username, required hidden `personalAccessToken` |
| `IAM_USER_CREDENTIAL` | Intended user OCID, tenancy, region, fingerprint, local PEM path, name/default intent | `privateApiKey` from `{textof:PATH}` |

Git providers in this SDK are `GITHUB`, `BITBUCKET`, `GITLAB`, `OCI_DEVOPS`.
The helper supports `entityType: PERSONAL_ACCESS_TOKEN`. The inspected backend
also has linked-account flows; those are not PAT prompts. Do not pretend linked
sign-in can be completed with an empty token. Follow its installed flow instead.
SDK help labels Git username/PAT optional, but the inspected backend explicitly
requires both for PAT settings. Use required prompts for that branch.

For IAM settings, never substitute a credential key for `privateApiKey`. Use
public IAM/config metadata for the intended identity, not private key contents;
ask only missing metadata in chat. Private key paths are chat inputs when the
user considers them non-sensitive. The key is raw PEM text, not Base64.

`SettingData` is shared by user and admin endpoints. Its `OAUTH` variant maps
to `OAuthAdminSetting` and belongs to admin settings; it is rejected by this
user-setting helper. Do not confuse it with agent tool OAuth client credentials.

## Helper contract

`scripts/user-settings/prepare-body.py` accepts `--operation create|update`,
`--metadata @/tmp/setting-metadata-<unique>.json`, and
`--output /tmp/body-setting-<unique>.json`. Metadata is a non-sensitive request
object with `name`, `isDefault`, and the chosen `data` metadata as appropriate.
The helper adds prompts or a `textof` placeholder; it never reads private files
or executes AIDP. Fresh output files only. For `GIT_ACCOUNT`, it rejects inline
values in `data.personalAccessToken`; for `IAM_USER_CREDENTIAL`, it rejects inline
values in `data.privateApiKey`. Public fields are not classified by name.

Create/payload replacement uses `--type GIT_ACCOUNT|IAM_USER_CREDENTIAL`.
IAM additionally uses `--private-key-path /local/key.pem`. For metadata-only
updates, use `--existing-metadata @<public-current-setting.json>` and a minimal
edit in `--metadata`; see [update](update.md). This snapshot must retain the
verified type and current `isDefault`, plus Git `entityType` or IAM `tenancy`/`region`. Other known public fields are preserved.
Alternatively supply the complete verified public state in `--metadata`.
Type-only bodies and omitted default flags are rejected rather than clearing
existing configuration. No credential prompt is added for metadata-only edits; stored secrets are reused.
Credential rotation also accepts the public snapshot and retains its default state
unless the user explicitly changes it. Without a snapshot, every update must
include the verified boolean `isDefault`; never assume false or omit it.
Public connection-data changes require an explicitly selected data-update flow.
Changing credential data on update requires `--replace-secrets`.

Create needs `name`, `isDefault`, `data`. Updates may change only the requested
metadata or payload; preserve omitted fields by following installed update
semantics. Never resend masked credentials or use an optional empty prompt to
mean “keep the old value.” Changing the default affects later user integrations;
reuse the user's stated intent, otherwise resolve that choice in chat.

Validate with `scripts/validate-protected-paths.py @<template>` before prompting;
execute with `protected_aidp.py --output-file <unique-result> -- <exact-cli-command>`.
Consume/delete only that agreed result via `read-protected-result.py`.
Automatic body cleanup and the terminal handoff message follow the shared workflow.

## Local evidence

SDK models: `CreateUserSettingDetails`, `UpdateUserSettingDetails`, `SettingData`,
`GitAccountUserSetting`, `IamUserCredentialUserSetting`, `OAuthAdminSetting`.
Also checked the supplied backend's `UserSettingsResource.java`,
`GitAccountUserSettingMapper.java`, `IamUserCredentialUserSettingMapper.java`.

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
