# MySQL external catalog

Check the exact installed CLI version's reference documentation using the
[shared version guidance](common.md#cli-version-and-additional-properties).
For new source-specific fields, also read
[Additional properties](#additional-properties).

Use source type `MYSQL` and [the common protected workflow](common.md).

- Discover the actual database endpoint, port and intended network path from
  accessible source metadata or retained context. Otherwise ask those missing
  non-sensitive values in chat. Do not assume port 3306 from a UI default.
- Database name is optional in the inspected backend. Omit it unless the user
  intends a particular database; do not ask for a required Oracle service/SID.
- Ask for username visibly and password invisibly in the terminal immediately
  before execution. No wallet, wallet password, private key or service alias is
  needed for the inspected username/password branch.
- TLS is an optional `MYSQL_SSL_ENABLED` property. Preserve the actual required
  `sslEnabled` choice; absence does not prove TLS is disabled. Reuse an intended
  `workspaceKey` for private connectivity when applicable; do not provision networking.

Required API connection properties: `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USERNAME`,
`MYSQL_PASSWORD`. Optional: `MYSQL_DATABASE_NAME`, `MYSQL_SSL_ENABLED`, `WORKSPACE_KEY`.

Example non-sensitive config (not connection defaults):

```json
{"host":"mysql.example","port":"3306","sslEnabled":true}
```

Add `databaseName` only when selected, `displayName` only for create, and
`workspaceKey` only for the intended private-network route. Port must be a JSON string.
For a stored-catalog replacement-password test, config is only
`{"catalogKey":"<existing-key>"}` with `--operation test-connection`.
The helper sends `key`, `sourceType: MYSQL` and a required hidden replacement
`MYSQL_PASSWORD`; the inspected backend reuses stored connection details. This
tests the password without updating the catalog. Never resend masked passwords.

Evidence: `MysqlExternalCatalogHelper` required/mapping definitions, shared
`CatalogServiceHandler.testConnection`, UI `buildMysqlCatalogConnectionProperties`.

## Prepare, test and create

```bash
python3 <skill_dir>/scripts/ext-catalogs/mysql/prepare-body.py \
  --operation test-connection --config @/tmp/mysql-config-<unique>.json \
  --output /tmp/body-mysql-test-<unique>.json
```

Continue with the common workflow's [template helper contract](common.md#additional-source-template-helpers)
and [required output handoff](common.md#required-output-handoff-for-every-source).
Use this exact prepared body path for validation and execution, and the same
fresh result path for execution and consumption. For creation, use
`--operation create` with the chosen `displayName`, fresh filenames, and
`catalog create` as described there.

## Additional properties
