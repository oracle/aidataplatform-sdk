# Google BigQuery external catalog

Check the exact installed CLI version's reference documentation using the
[shared version guidance](common.md#cli-version-and-additional-properties).
For new source-specific fields, also read
[Additional properties](#additional-properties).

Use source type `GOOGLE_BIGQUERY` and [the common protected workflow](common.md).
Installed Python SDK/CLI `5.1.0.36.45595` includes this source in catalog create
and test-connection models/help. Some repository SDK checkouts omit it; always
check the installed CLI contract before concluding the connector is unsupported.
The UI shows this connector only when its connector availability flag allows it.

## Minimum inputs and discovery

- Reuse the chosen catalog name/description for creation, or existing catalog key
  for a stored-catalog key replacement test. A full new-connection test needs no
  display name. Preserve authenticated AIDP target context.
- Ask for a non-sensitive local path to the Google service-account JSON key.
  Do not ask the user to paste the JSON, private key, password or access token.
  Do not read the file into model context. Use the precreated inspector to derive
  only `projectId` and `serviceAccountEmail`:

  ```bash
  python3 <skill_dir>/scripts/ext-catalogs/google-bigquery/inspect-service-account-key.py \
    --key-path /local/google-service-account.json
  ```

  It opens a bounded regular file privately, rejects symlinks, and prints only
  those public fields. It does not prove key validity, IAM grants or connectivity.
  If public metadata cannot be derived, obtain only the missing public fields in
  chat. Do not open the file yourself to diagnose it. Use an accessible local path.
- Derive the BigQuery endpoint and port from authorized existing source settings,
  or ask for the actual values in chat. They are not determined by the OCI region.
  `https://www.googleapis.com/bigquery/v2` and `443` appear in UI examples, but do
  not override a configured endpoint/proxy or silently assume its network policy.
- Authentication is the reviewed service-account flow: derive
  `GOOGLE_BIGQUERY_OAUTH_TYPE: service_account`; do not ask for that fixed value.
  No Oracle wallet, TNS alias, account username/password, warehouse, or separate
  dataset/database name is required by this reviewed catalog contract. If another
  authentication method is requested, verify it separately before inventing fields.
- Reuse an established `workspaceKey` only when private networking requires it.

## Protected request

Public config example (values are examples, not defaults):

```json
{"host":"https://www.googleapis.com/bigquery/v2","port":"443","projectId":"example-project","serviceAccountEmail":"reader@example-project.iam.gserviceaccount.com","privateKeyFilePath":"/local/google-service-account.json"}
```

```bash
python3 <skill_dir>/scripts/ext-catalogs/google-bigquery/prepare-body.py \
  --operation test-connection --config @/tmp/google-bigquery-config-<unique>.json \
  --output /tmp/body-google-bigquery-test-<unique>.json
```

The helper maps public fields to `GOOGLE_BIGQUERY_HOST`, `GOOGLE_BIGQUERY_PORT`,
`GOOGLE_BIGQUERY_PROJECT_ID`, `GOOGLE_BIGQUERY_OAUTH_SERVICE_ACCT_EMAIL` and
`GOOGLE_BIGQUERY_OAUTH_TYPE`. `GOOGLE_BIGQUERY_OAUTH_PVT_KEY` is
`{textof:/local/google-service-account.json}`: the selected file's complete raw
UTF-8 contents, matching UI upload behavior. Do not extract just its `private_key`
field, Base64-encode it, or send a path to the remote runtime. Only the protected
wrapper reads the content into its temporary request during execution.

For creation use `--operation create`, add the chosen `displayName` and requested
optional `description`/`properties`, use fresh filenames, and execute
`catalog create`. No dummy password or wallet properties belong in this request;
compatibility sentinels are owned by the backend.

## Existing catalog test

For a verified stored BigQuery catalog, config can be just
`{"catalogKey":"<existing-key>","privateKeyFilePath":"/local/replacement-key.json"}`.
The helper sends `key`, `sourceType` and only a protected replacement
`GOOGLE_BIGQUERY_OAUTH_PVT_KEY`. The backend reloads stored public metadata and
uses its BigQuery key-replacement branch; testing does not save the replacement.
Never retrieve a stored private key or masked key into model context. Replacing
the account/project identity instead requires a full test with its intended public
metadata, rather than a stored-key shortcut.

Validate the unresolved body with `scripts/validate-protected-paths.py`, then
follow the common [required output handoff](common.md#required-output-handoff-for-every-source)
using `protected_aidp.py --output-file <fresh-result> -- aidp ... --body @<template>`.
Consume/delete only that result with `read-protected-result.py`. The actual body
is deleted on success, failure or Ctrl+C, and the original key file is retained.

Reviewed evidence: installed SDK/CLI catalog models/help; UI
`buildGoogleBigQueryCatalogConnectionProperties` and private-key test dialog;
backend `GoogleBigqueryExternalCatalogHelper` and `CatalogServiceHandler.testConnection`.

## Additional properties
