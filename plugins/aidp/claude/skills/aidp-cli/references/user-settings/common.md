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
The reviewed PAT branch uses `entityType: PERSONAL_ACCESS_TOKEN`. The inspected backend
also has linked-account flows; those are not PAT prompts. Do not pretend linked
sign-in can be completed with an empty token. Follow its installed flow instead.
SDK help labels Git username/PAT optional, but the inspected backend explicitly
requires both for PAT settings. Use required prompts for that branch.

For IAM settings, never substitute a credential key for `privateApiKey`. Use
public IAM/config metadata for the intended identity, not private key contents;
ask only missing metadata in chat. Private key paths are chat inputs when the
user considers them non-sensitive. The key is raw PEM text, not Base64.

`SettingData` is shared by user and admin endpoints. Its `OAUTH` variant maps
to `OAuthAdminSetting` and belongs to admin settings; it is not part of this user-setting workflow. Do not confuse it with agent tool OAuth client credentials.

## Template preparation

Compose the complete unresolved JSON using installed help, the field guidance
below, and [generic preparation](../protected-bodies.md#prepare-an-unresolved-template).

For PATs explicitly include the discriminator/entity type, required visible
username and hidden token placeholders. IAM uses the verified public metadata
and `data.privateApiKey: "{textof:/local/key.pem}"`. The resolver does not detect
inline secrets or merge current settings; never put raw/masked secrets in JSON.

For updates, compose the final request from verified current public state plus
only the intended edit. Retain type, name, boolean `isDefault`, Git `entityType`
or IAM `tenancy`/`region`, and other required/known public metadata. Do not send
a type-only body or guess an omitted default: the backend can clear omitted
public values and default `isDefault` to false. Metadata-only updates omit
private fields and reuse stored credentials, even where a shared create-oriented
SDK subtype marks those secrets required. Rotation must be explicit; retain
current public/default state unless its change is requested. Resolve missing
state before execution, without retrieving stored secrets.

Create needs `name`, `isDefault`, `data`. Updates may change only the requested
metadata or payload; preserve omitted fields by following installed update
semantics. Never resend masked credentials or use an optional empty prompt to
mean “keep the old value.” Changing the default affects later user integrations;
reuse the user's stated intent, otherwise resolve that choice in chat.

Validate with `scripts/validate-protected-paths.py @<template>` before execution.
IAM key-file create/replacement and metadata-only updates normally contain no
terminal prompts. Summarize the target, public settings, key-file path if used,
and intended default/credential changes, ask "Shall I proceed?", and wait for
approval before running the protected wrapper yourself. Git PAT create/rotation
still requires a user-run command for username/token input. Inspect the entire
template and follow the shared
[execution-mode rules](../protected-bodies.md#choose-execution-mode).
In both modes use `protected_aidp.py --output-file <unique-result> -- <exact-cli-command>`
and consume/delete only that result via `read-protected-result.py`. After direct
execution, report the outcome without a user continuation step. Automatic body
cleanup follows the shared workflow.

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
