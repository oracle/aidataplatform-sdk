# PostgreSQL external catalog

Check the exact installed CLI version's reference documentation using the
[shared version guidance](common.md#cli-version-and-additional-properties).
For new source-specific fields, also read
[Additional properties](#additional-properties).

Use source type `POSTGRESQL` and [the common workflow](common.md), including the
installed connector and [availability check](common.md#connector-availability).
Treat "Postgres" and "PostgreSQL" as the same source without asking again.

## Collect only missing connection details

Reuse connection details already supplied. Ask for the host, listener port and
database name together, plus catalog name for create if missing. Unlike SQL
Server, the reviewed UI has no PostgreSQL port default: retain the supplied
port or ask for it with the other missing fields. Database name is required;
do not infer it from the username or silently use `postgres`.

The final local command prompts visibly for username and invisibly for password.
Do not ask for credentials in chat, a wallet, or an authentication-method choice.
The public contract has five source-specific properties and no SSL-toggle key;
do not copy MySQL or Azure SQL Server SSL options into this payload.
Use a confirmed `workspaceKey` only for the intended private-network route.

The assistant writes public config and prepares the command, rather than asking
the user to create a config file. Example config:

```json
{"displayName":"sales_pg","host":"pg.example.com","port":"5432","databaseName":"sales"}
```

Here `5432` is an example chosen listener port, not an assumed UI default.

```bash
python3 <skill_dir>/scripts/ext-catalogs/postgresql/prepare-body.py \
  --operation create --config @/tmp/postgresql-config-<unique>.json \
  --output /tmp/body-postgresql-<unique>.json
```

Optional public fields: `workspaceKey`, and create-only `description`,
`properties`, `isTestConnectionEnabled`. For a full connection test, omit the
create-only fields and use `--operation test-connection`.
For an existing catalog use only `{"catalogKey":"<existing-key>"}`; the server
reuses stored metadata and the local prompt requests just the replacement
password. Testing does not save it.

The helper emits `POSTGRESQL_HOST`, `POSTGRESQL_PORT`,
`POSTGRESQL_DATABASE_NAME`, `POSTGRESQL_USERNAME`, `POSTGRESQL_PASSWORD`, and
shared `WORKSPACE_KEY` when selected. Continue with common validation and the
single protected-command/result handoff. Treat an accepted 202 as pending.

## Evidence and version differences

Reviewed against `PostgresqlExternalCatalogHelper`, public catalog definitions,
and UI `postgresqlcatalog.ts` / its unit tests. Installed CLI help must support
`POSTGRESQL`; older repository SDKs may predate it.

## Additional properties
