# Microsoft SQL Server external catalog

Check the exact installed CLI version's reference documentation using the
[shared version guidance](common.md#cli-version-and-additional-properties).
For new source-specific fields, also read
[Additional properties](#additional-properties).

Use source type `SQLSERVER`, distinct from Azure SQL Server's `AZURE_SQLSERVER`.
Follow [the common workflow](common.md), including the installed connector and
[availability check](common.md#connector-availability).

## Collect only missing connection details

Reuse the intended host and existing session choices. Ask for the catalog name
(for create) and host together when both are missing. Use port `1433`, matching
the UI default, unless the user or connection settings specify another port;
show the selected port in the operation summary without an extra confirmation
question. Database name is optional: omit it to use the login's default database.
Do not assume `master` or ask for a database unless needed for the user's task.

The final local command prompts for the account username and hides the password.
Do not ask for either in chat or request a wallet, Azure tenant ID, or OAuth
configuration. This source has no reviewed SSL-toggle property; do not invent one.
Retain a confirmed `workspaceKey` only for the intended private-network route.

The assistant writes the public config and runs the bundled preparation helper;
the user supplies connection details in ordinary language, not JSON or API keys.
Minimal create config, using the default port and login database:

```json
{"displayName":"sales_sql","host":"sql.example.com"}
```

```bash
python3 <skill_dir>/scripts/ext-catalogs/sqlserver/prepare-body.py \
  --operation create --config @/tmp/sqlserver-config-<unique>.json \
  --output /tmp/body-sqlserver-<unique>.json
```

Optional public fields: `port` (string), `databaseName`, `workspaceKey`, and
create-only `description`, `properties`, `isTestConnectionEnabled`.
Keep an explicitly supplied non-default port. For a full connection test, omit
create-only fields and use `--operation test-connection`.
For an existing catalog, resolve its stable key/source and pass only
`{"catalogKey":"<existing-key>"}`; the local prompt requests just a replacement
password and the server reuses saved connection details. Testing does not save it.

The helper emits exactly `SQLSERVER_HOST`, `SQLSERVER_PORT`, `SQLSERVER_USERNAME`,
`SQLSERVER_PASSWORD`, optional `SQLSERVER_DATABASE_NAME`, and the shared
`WORKSPACE_KEY` when selected. Continue with common validation and the single
protected-command/result handoff; a 202 remains pending until its job completes.

## Evidence and version differences

Reviewed against `SqlServerExternalCatalogHelper`, public catalog definitions,
UI `sqlservercatalog.ts` / `catalogCreationOptions.ts`, and
`createSQLServerCatalog.cy.ts`. Installed CLI help must support `SQLSERVER`;
older repository SDKs may predate it. Never change source to
`AZURE_SQLSERVER` as a fallback.

## Additional properties
