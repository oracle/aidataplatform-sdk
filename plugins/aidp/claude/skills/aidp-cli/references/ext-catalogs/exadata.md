# Exadata external catalog

Check the exact installed CLI version's reference documentation using the
[shared version guidance](common.md#cli-version-and-additional-properties).
For new source-specific fields, also read
[Additional properties](#additional-properties).

Use [the common workflow](common.md) with source type `EXADATA` in the protected body.

- Discover the intended database/PDB and its connection string from accessible
  OCI metadata. Otherwise ask for the non-sensitive host, actual port and
  service name/SID in chat (or a connection string without credentials).
- Reuse the current workspace key when appropriate. If no workspace is selected,
  list authorized workspaces and ask which to use. `WORKSPACE_KEY` must appear
  inside connection properties; passing it only as CLI context is insufficient.
- Collect only database `accountUserName` and hidden `accountPassword` in the
  terminal immediately before execution; do not collect them during discovery. No default `ADMIN` identity and no password discovery from OCI metadata.
- Do not ask for or generate an Exadata wallet. The inspected API explicitly
  rejects wallet creation despite SDK wallet property names. Verify the installed
  service contract if support changes; do not bypass the rejection by dropping
  requested security requirements.

Non-sensitive values to discover (map these to the API body fields below):

```json
{"displayName":"finance_exadata","host":"scan.example","port":"1521","serviceName":"finance.example","workspaceKey":"selected-workspace"}
```

Replace `serviceName` with `sid` for SID mode; choose exactly one. The required
properties are `EXADATA_HOST`, `EXADATA_PORT`, `EXADATA_USERNAME`,
`EXADATA_PASSWORD`, `WORKSPACE_KEY`, and one of `EXADATA_DATABASE_NAME` or
`EXADATA_DATABASE_SID`. Host/port/service values must come from the actual source,
not this example. Staging properties are not mandatory creation inputs.

Full connection tests omit `displayName` and use `catalog test-connection`.
For a stored-catalog replacement-password test, use the common shortcut; do not
request a new wallet, endpoint or username.

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
