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

Put only the requested edit in `/tmp/setting-metadata-<unique>.json`, for example
`{"name":"production-renamed"}` or `{"isDefault":false}`. Then run:

```bash
python3 <skill_dir>/scripts/user-settings/prepare-body.py --operation update \
  --existing-metadata @/tmp/setting-current-<unique>.json \
  --metadata @/tmp/setting-metadata-<unique>.json --output /tmp/body-setting-<unique>.json
```

The helper merges the edit with the snapshot, preserving public data and an
unchanged default flag. It adds no secret prompts or private-key placeholders;
the backend reuses the stored credentials. Snapshot and patch types must agree,
and the patch cannot change connection data in metadata-only mode. A type-only
snapshot is insufficient: the backend maps omitted public fields to null, and
an omitted default flag becomes false.

Without `--existing-metadata`, `--metadata` must already contain the complete
verified public state with the requested edit applied, including a boolean
`isDefault` and all type-specific public fields listed above. `--type` may supply
the verified discriminator but never substitutes for those existing values.

For intended PAT or IAM credential rotation, use the same public snapshot with
`--existing-metadata` and add `--replace-secrets` (plus `--private-key-path` for IAM).
The helper retains the snapshot's `isDefault` automatically; do not set it to
false merely because the request changes a credential. An explicit `isDefault`
in the edit overrides the snapshot only when that default change is requested.
Without a snapshot, include the verified current boolean in `--metadata`; the
helper rejects omitted/invalid default state instead of letting the backend
silently demote the setting. The type can come from `--type` or the verified
snapshot, and their values must agree.

For example, rotate a Git PAT using the existing public snapshot and an edit
containing `{"data":{}}` (or other explicitly requested replacement metadata):

```bash
python3 <skill_dir>/scripts/user-settings/prepare-body.py --operation update \
  --replace-secrets --existing-metadata @/tmp/setting-current-<unique>.json \
  --metadata @/tmp/setting-metadata-<unique>.json --output /tmp/body-setting-<unique>.json
```

No existing secret values belong in the snapshot. The helper merges public
configuration, then adds only the new credential's protected inputs. Reuse only non-sensitive data fields
required for the selected branch. Git rotation prompts for username visibly and
PAT invisibly; IAM uses the key file privately. When the replacement key changes
its public fingerprint or account identity, include those verified new values in
the edit; do not assume the snapshot fingerprint matches a different key file. Include the complete replacement
data object if required by the installed endpoint; do not assume a merge.

After checking installed help, wrap `user-setting update <setting-key>` with
`protected_aidp.py --output-file /tmp/aidp-result-setting-<unique>.json -- ...
--body @<template>`. Include `--if-match <etag>` when available and appropriate.
Resolve any required credential/default-impact confirmation before the user runs
it; then consume/delete the result. Metadata-only updates do not ask for tokens.
