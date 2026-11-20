# Azure SQL Server external catalog

Check the exact installed CLI version's reference documentation using the
[shared version guidance](common.md#cli-version-and-additional-properties).
For new source-specific fields, also read
[Additional properties](#additional-properties).

Use source type `AZURE_SQLSERVER` and [the common protected workflow](common.md).

- Resolve server hostname, actual listener port and database from authorized
  metadata/context; ask missing values in chat. Database name is mandatory in
  the inspected backend even though the UI payload builder can omit an empty
  value. Do not infer the database from the account name or use a guessed port.
- This inspected contract uses database username/password authentication. Prompt
  username visibly and password invisibly locally just before execution.
  Do not ask for an Azure client secret, tenant ID, OAuth token or OCI wallet:
  no Entra/OAuth branch is established by this payload contract. If requested,
  discover actual support before changing the authentication mode.
- Preserve the intended optional `sslEnabled` value; do not disable encryption
  to work around connection failures. Reuse `workspaceKey` only where the private
  connectivity flow requires it. Account credentials cannot be derived from the endpoint.

Required API properties: `AZURE_SQLSERVER_HOST`, `AZURE_SQLSERVER_PORT`,
`AZURE_SQLSERVER_DATABASE_NAME`, `AZURE_SQLSERVER_USERNAME`, `AZURE_SQLSERVER_PASSWORD`.
Optional: `AZURE_SQLSERVER_SSL_ENABLED`, `WORKSPACE_KEY`.

Example non-sensitive config (values are not connection defaults):

```json
{"host":"chosen-server.database.windows.net","port":"1433","databaseName":"sales","sslEnabled":true}
```

Port must be a JSON string. Add `displayName` only for create. A stored-catalog
replacement-password test needs only `{"catalogKey":"<existing-key>"}` with
`--operation test-connection`; the helper prompts for a replacement
`AZURE_SQLSERVER_PASSWORD` and reuses stored connection metadata. It does not
persist the replacement password.

Evidence: `SqlServerOnAzureExternalCatalogHelper` mandatory/mapping definitions,
UI `buildAzureSqlCatalogConnectionProperties`, shared `CatalogServiceHandler.testConnection`.

## Prepare, test and create

```bash
python3 <skill_dir>/scripts/ext-catalogs/azure-sqlserver/prepare-body.py \
  --operation test-connection --config @/tmp/azure-sqlserver-config-<unique>.json \
  --output /tmp/body-azure-sqlserver-test-<unique>.json
```

Continue with the common workflow's [template helper contract](common.md#additional-source-template-helpers)
and [required output handoff](common.md#required-output-handoff-for-every-source).
Use this exact prepared body path for validation and execution, and the same
fresh result path for execution and consumption. For creation, use
`--operation create` with the chosen `displayName`, fresh filenames, and
`catalog create` as described there.

## Additional properties
