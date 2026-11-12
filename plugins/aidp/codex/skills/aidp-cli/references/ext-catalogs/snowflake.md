# Snowflake external catalog

Check the exact installed CLI version's reference documentation using the
[shared version guidance](common.md#cli-version-and-additional-properties).
For new source-specific fields, also read
[Additional properties](#additional-properties).

Use source type `SNOWFLAKE` and [the common protected workflow](common.md).

- Derive the selected account/server hostname and actual port from authorized
  metadata or the user's non-sensitive connection details. Ask only unresolved
  endpoint, database, warehouse, optional role and authentication choices in chat.
  These are external Snowflake resources; the AIDP instance/OCI profile does not
  determine their values. Do not guess warehouse, database, role or a default port.
- Require `authenticationMethod: Basic` or `KeyPair` explicitly. The UI's Basic
  default is not evidence of the source's authentication policy. No Oracle wallet
  or TNS/service alias is needed for either branch.
- Both branches require a visible local username prompt. Basic additionally
  requires a hidden account password. KeyPair requires private-key content and
  only a hidden key passphrase where appropriate; never ask for an account password
  or send a dummy password for KeyPair. The backend owns any compatibility sentinel.

Required common API properties: `SNOWFLAKE_HOST`, `SNOWFLAKE_PORT`,
`SNOWFLAKE_DATABASE_NAME`, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_USERNAME`,
`SNOWFLAKE_AUTHENTICATION_METHOD`. `SNOWFLAKE_ROLE` and `WORKSPACE_KEY` are optional.
The backend requires database and warehouse even though the UI builder can omit
empty values. Follow that validation for new/full tests and creation.

## Basic authentication

Non-sensitive config example (not defaults):

```json
{"host":"chosen-account.snowflakecomputing.com","port":"443","databaseName":"SALES","warehouse":"QUERY_WH","authenticationMethod":"Basic"}
```

Add the selected `role` only when needed and `displayName` only for creation.
The helper adds required visible username and hidden `SNOWFLAKE_PASSWORD` prompts.
Port must be a JSON string. No private-key path or passphrase is requested.

## KeyPair authentication

Ask the local PEM path in chat when non-sensitive. Privately inspect only its
envelope using the precreated helper:

```bash
python3 <skill_dir>/scripts/ext-catalogs/snowflake/inspect-private-key.py --key-path /local/snowflake-key.pem
```

It exposes only `encrypted` and `format`; no key material. This verifies access
and recognizes PEM envelopes, not cryptographic validity, key registration,
account permissions or Snowflake JDBC compatibility. For a non-PKCS8 or unknown
format, obtain a locally prepared format compatible with the installed driver;
do not print or convert key contents ad hoc. Never infer encryption from a filename.

Use the returned boolean as `privateKeyEncrypted` in non-sensitive config:

```json
{"host":"chosen-account.snowflakecomputing.com","port":"443","databaseName":"SALES","warehouse":"QUERY_WH","authenticationMethod":"KeyPair","privateKeyFilePath":"/local/snowflake-key.pem","privateKeyEncrypted":true}
```

The helper maps the local path to `SNOWFLAKE_PRIVATE_KEY_CONTENT: {textof:PATH}`
(raw UTF-8 key text, not Base64). The API also accepts `SNOWFLAKE_PRIVATE_KEY_FILE`,
but a user's local Downloads path is not a path on the remote runtime: do not
send it as that property. Prefer the content placeholder matching the UI upload
flow, so only the protected wrapper opens the key during execution.
If `privateKeyEncrypted` is true, `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` uses a required
hidden prompt; false omits that property; unknown/omitted uses an optional hidden
prompt showing `(optional)`. No password field is added in this branch.

## Existing catalog tests

For a verified Basic-auth catalog, config may be only
`{"catalogKey":"<existing-key>","authenticationMethod":"Basic"}`. This uses the
shared stored-password test shortcut and does not save the new password.
KeyPair does not use this shortcut: the inspected stored-catalog test path
replaces only the password and ignores newly supplied key material. For KeyPair,
prepare a full test without `catalogKey`, reuse non-sensitive endpoint/database/
warehouse/role metadata and pass the local key via the protected content placeholder.
Do not fetch a stored private key or masked passphrase into model context.

Evidence: `SnowflakeExternalCatalogHelper` common/type-dependent validation and
compatibility-password handling, UI `buildSnowflakeCatalogConnectionProperties`,
shared `CatalogServiceHandler.testConnection`.

## Prepare, test and create

```bash
python3 <skill_dir>/scripts/ext-catalogs/snowflake/prepare-body.py \
  --operation test-connection --config @/tmp/snowflake-config-<unique>.json \
  --output /tmp/body-snowflake-test-<unique>.json
```

Continue with the common workflow's [template helper contract](common.md#additional-source-template-helpers)
and [required output handoff](common.md#required-output-handoff-for-every-source).
Use this exact prepared body path for validation and execution, and the same
fresh result path for execution and consumption. For creation, use
`--operation create` with the chosen `displayName`, fresh filenames, and
`catalog create` as described there.

## Additional properties
