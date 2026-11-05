# Oracle Database external catalog

Check the exact installed CLI version's reference documentation using the
[shared version guidance](common.md#cli-version-and-additional-properties).
For new source-specific fields, also read
[Additional properties](#additional-properties).

Use [the common workflow](common.md) with source type `ORACLE` in the protected body.

- Discover an OCI-managed database/PDB's connection metadata when accessible.
  Otherwise ask for a non-sensitive connection string or host, actual listener
  port, and service name/SID in chat. Never request a credential-bearing URL in
  chat; ask the user to provide only its address/service portion.
- Choose service-name or SID mode from known connection metadata; ask only when
  unresolved. The UI's initial service-name/basic selection is a form default,
  not proof of the server's service or security requirements. Do not guess 1521.
- Collect `accountUserName` and hidden `accountPassword` in the terminal only
  just before execution. For wallet mode, request the ZIP path in chat and verify
  it through `--wallet` helpers; never open its contents in model context. Prompt
  locally for a hidden wallet password, allowing Enter only when optional.
- Oracle host/port still need public values in wallet mode. Unlike the Autonomous
  workflow, this helper does not derive a generic Oracle endpoint from arbitrary
  wallet contents. If only the wallet identifies an endpoint, add a reviewed
  helper exposing only the necessary choices before proceeding; never unzip or
  inspect it ad hoc in model-visible output.

Non-sensitive values to discover (map these to the API body fields below) (basic):

```json
{"displayName":"erp","host":"db.example","port":"1521","serviceName":"erp.example"}
```

For SID mode, replace `serviceName` with `sid`; supply exactly one. For wallet
mode add `"useWallet":true` and the actual `"sslEnabled":true/false` setting.
For private networking add the established `workspaceKey`.
The generated properties are `ORACLE_HOST`, `ORACLE_PORT`, `ORACLE_USERNAME`,
`ORACLE_PASSWORD`, and `ORACLE_DATABASE_NAME` or `ORACLE_DATABASE_SID`, plus
wallet/SSL properties when requested. Staging fields are not mandatory for
creation. Do not request a wallet for a basic connection.

For a full test, omit `displayName` and use `catalog test-connection`.
For an existing catalog's replacement-password test, use the common shortcut;
the server reuses stored endpoint/account/wallet details.

Prepare actual API field names with whole-value `visible_prompt_input`,
`invisible_prompt_input`, optional hidden prompt, and `base64of`/`textof` values
as documented in [protected bodies](../protected-bodies.md). Do not use a
separate credential draft, collector or build command. The wrapper owns prompt
validation, execution and automatic disposal of its private request copy.

For both creation and connection tests, use the common workflow’s required
`protected_aidp.py --output-file <fresh-result-path> -- aidp ... --body @<template>`
handoff. Then wait for and consume/delete that exact result with
`read-protected-result.py`.

## Additional properties
