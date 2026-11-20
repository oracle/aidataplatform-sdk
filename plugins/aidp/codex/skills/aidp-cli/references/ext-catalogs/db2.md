# IBM Db2 external catalog

Check the exact installed CLI version's reference documentation using the
[shared version guidance](common.md#cli-version-and-additional-properties).
For new source-specific fields, also read
[Additional properties](#additional-properties).

Use source type `DB2` and [the common protected workflow](common.md).

- Derive the endpoint, actual port and database from authorized source metadata
  or prior context; ask only missing non-sensitive values in chat. Do not assume
  a default port or derive an Oracle SID/service from the database name.
- Database name is mandatory. Username and password are required only in the
  local terminal immediately before execution; username visible, password hidden.
- No Oracle wallet, service alias, key file or wallet password is needed for the
  inspected branch. Preserve intended TLS through optional `sslEnabled`, and
  reuse selected workspace context only for applicable private connectivity.

DB2 API property names are lower-case/dotted, not `DB2_*`:

| Config | API property |
|---|---|
| `host` | `host` |
| `port` | `port` |
| `databaseName` | `database.name` |
| Local username prompt | `user.name` |
| Local password prompt | `password` |
| Optional `sslEnabled` | `ssl.enabled` |
| Optional `workspaceKey` | `WORKSPACE_KEY` |

The first five API properties are mandatory. Example non-sensitive config:

```json
{"host":"db2.example","port":"50001","databaseName":"SALES","sslEnabled":true}
```

The port is an example, not an inferred default, and must be a JSON string.
Add `displayName` only for creation. A stored-catalog replacement-password test
uses only `{"catalogKey":"<existing-key>"}` with `--operation test-connection`.
It emits the dotted contract's `password` property, not `DB2_PASSWORD`; stored
endpoint/account/TLS metadata is reused. Testing does not save the new password.

Evidence: `Db2ExternalCatalogHelper`, UI `buildDb2CatalogConnectionProperties`,
shared `CatalogServiceHandler.testConnection`.

## Prepare, test and create

```bash
python3 <skill_dir>/scripts/ext-catalogs/db2/prepare-body.py \
  --operation test-connection --config @/tmp/db2-config-<unique>.json \
  --output /tmp/body-db2-test-<unique>.json
```

Continue with the common workflow's [template helper contract](common.md#additional-source-template-helpers)
and [required output handoff](common.md#required-output-handoff-for-every-source).
Use this exact prepared body path for validation and execution, and the same
fresh result path for execution and consumption. For creation, use
`--operation create` with the chosen `displayName`, fresh filenames, and
`catalog create` as described there.

## Additional properties
