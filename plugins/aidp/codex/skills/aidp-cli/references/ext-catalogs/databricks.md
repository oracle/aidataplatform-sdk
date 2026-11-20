# Databricks Unity Catalog

Check the exact installed CLI version's reference documentation using the
[shared version guidance](common.md#cli-version-and-additional-properties).
For new source-specific fields, also read
[Additional properties](#additional-properties).

Use source type `DATABRICKS_UNITY_CATALOG` and [the common workflow](common.md),
including the installed connector and
[availability check](common.md#connector-availability). "Databricks" maps to
this source; no extra connector-type question is needed.

## Four fields, fixed authentication

Match the UI: collect the HTTPS workspace base URL, OAuth client ID, and remote
Unity Catalog name together, plus a catalog display name for create if missing.
Reuse details already given. The fourth connection field, the client secret,
is requested once, privately in the user's terminal just before execution.
Authentication is fixed to `oauth-m2m`; do not ask the user to choose a grant,
provide a PAT, log in through a browser, or supply a database username/password,
port, warehouse, HTTP path, wallet or OCI credential-store record.

The workspace URL is a base URL such as `https://workspace.example.com`, not a
SQL warehouse or browser page URL. Client ID and catalog name are public metadata;
do not fetch, read or copy the client secret into chat or the public config.
The helper does not add private-network keys to the five-property UI payload.

The assistant creates the non-sensitive config from the user's answers:

```json
{"displayName":"lakehouse","workspaceUrl":"https://workspace.example.com","clientId":"chosen-client-id","remoteCatalog":"main"}
```

```bash
python3 <skill_dir>/scripts/ext-catalogs/databricks/prepare-body.py \
  --operation create --config @/tmp/databricks-config-<unique>.json \
  --output /tmp/body-databricks-<unique>.json
```

Create-only optional fields are `description`, `properties`, and
`isTestConnectionEnabled`; omit unrequested options. A full connection test uses
`--operation test-connection` with only the three public connection fields.
For an existing catalog, use only `{"catalogKey":"<existing-key>"}`. The helper
prompts for a replacement client secret; the backend reuses the saved workspace,
client ID and remote catalog. Testing does not save the replacement secret.

The five connection properties are:

- `DATABRICKS_UNITY_CATALOG_WORKSPACE_URL`
- `DATABRICKS_UNITY_CATALOG_AUTH_TYPE` = `oauth-m2m`
- `DATABRICKS_UNITY_CATALOG_OAUTH_CLIENT_ID`
- `DATABRICKS_UNITY_CATALOG_OAUTH_CLIENT_SECRET` = required hidden placeholder
- `DATABRICKS_UNITY_CATALOG_REMOTE_CATALOG`

Continue with common template validation and one protected-command/result handoff.
The backend owns internal credential storage; never add its compatibility dummy
password or wallet fields to a user request. Creation may include harvesting;
report accepted/pending versus completed accurately and retain the operation key.

## Evidence and version differences

Reviewed against `DatabricksUnityCatalogExternalCatalogHelper`, the public
catalog definitions, UI `databrickscatalog.tsx`, and
`createDatabricksCatalog.cy.ts`. Installed help must advertise the source.
`DATABRICKS_REMOTE_CATALOG` and internal dotted names are legacy response keys,
not keys for a new create/test request.

## Additional properties
