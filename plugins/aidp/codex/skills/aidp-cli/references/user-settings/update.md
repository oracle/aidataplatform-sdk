# Update a user setting

Check the exact installed CLI version's reference documentation and the
[shared Additional properties guidance](common.md#additional-properties)
for fields introduced or removed since the plugin release.

Read [common](common.md). Resolve `settingKey` within the authenticated user's
settings, existing type, default state, and ETag if provided. Do not copy secret
fields from responses; never send redaction markers as credentials.

For a name/default change, obtain a current non-sensitive snapshot for the
resolved setting. Retain its type, name and default state, plus public connection
fields: Git `entityType` or IAM `tenancy`/`region`. Retain other already-known public data such as Git `providerName`/`username`
or IAM `userId`/`fingerprint` when available. Do not retrieve or copy secret values,
masked secrets, or an unfiltered GET response into this file.

Example `/tmp/setting-current-<unique>.json` for an IAM setting:

```json
{"name":"production","isDefault":true,"data":{"type":"IAM_USER_CREDENTIAL","tenancy":"ocid1.tenancy.example","region":"us-phoenix-1"}}
```

Compose the complete final request from the verified public snapshot, applying
only the requested edit. This merge is performed during request composition,
not by a script. Retain type, name, `isDefault` and required public connection
metadata; never silently default to false. Type-only or incomplete snapshots
are insufficient because omitted public values can become null.

For metadata-only updates, omit private fields and reuse stored credentials.
For an explicitly requested rotation, retain the same public/default state and
add placeholders only for the new private values: visible username/hidden PAT
for Git, or `textof` for an IAM key. Verify public fingerprint/identity metadata
for a different key file. Include complete replacement data when required by the
installed endpoint; do not assume a merge or send empty secrets to retain them.

Prepare the final unresolved JSON using [common template guidance](common.md#template-preparation).

After checking installed help, wrap `user-setting update <setting-key>` with
`protected_aidp.py --output-file /tmp/aidp-result-setting-<unique>.json -- ...
--body @<template>`. Include `--if-match <etag>` when available and appropriate.
Follow the common execution-mode rules. Metadata-only updates and IAM key-file
rotation normally have no prompts: summarize the intended edit/rotation, target,
public inputs, default impact and key-file path if used, ask "Shall I proceed?",
and wait for approval before running the wrapper yourself. Git PAT rotation
keeps the user-run username/token prompts after any required confirmation.
Consume/delete the result in both modes; direct execution does not require a
user continuation step. Metadata-only updates do not ask for tokens.
