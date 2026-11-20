# ADW external catalog

Check the exact installed CLI version's reference documentation using the
[shared version guidance](common.md#cli-version-and-additional-properties).
For new source-specific fields, also read
[Additional properties](#additional-properties).

Use [the common workflow](common.md) and the generic protected-body wrapper
for creation and connection testing with source type `ADW`. ADW and ALH have separate API prefixes even where the UI labels the
Autonomous source as Lakehouse; do not silently substitute one for the other.

- Derive target tenancy/region/compartment from established source context.
  Discover authorized Autonomous instances in the selected compartment (the UI's
  ADW/ALH listing uses workload `DW` and `AVAILABLE`; newer APIs also expose `LH`,
  so verify live metadata). Ask for the intended instance only when ambiguous.
- Given a selected instance and wallet-generation permissions, use the common
  wallet-download helper, then list services with the private-input helper.
  Otherwise ask for the wallet ZIP path in chat and use `--wallet` helpers. Cross-region
  or cross-tenancy UI flows use wallet upload; do not assume the current profile
  can download a wallet from another tenancy.
- Ask the service/alias choice in chat using only helper-produced options. Use a
  database-specific wallet; do not select the first alias automatically.
- Collect `accountUserName` and hidden `accountPassword` in the terminal only
  immediately before execution. No default `ADMIN` account. Wallet paths may be
  supplied in chat; contents stay private. Use optional hidden wallet-password
  placeholders when optional and required hidden placeholders for FIPS. Follow common.md for validation and automatic body disposal.

Non-sensitive values to discover (map these to the API body fields below):

```json
{"displayName":"sales_adw","serviceAlias":"sales_low"}
```

`workspaceKey` is optional unless the selected private-network flow needs it.
Creation materializes `ADW_USERNAME`, `ADW_PASSWORD`, `ADW_TNS_ALIAS`,
`ADW_WALLET_CONTENT_BASE64`, and `ADW_WALLET_PASSWORD`. Required fields are the
first four; a wallet is required even if the database itself supports walletless
TLS. Do not request host/port separately. Staging properties are not mandatory
creation inputs; discuss a staging destination only for a flow that needs one.

For a new connection test, prepare the API body without `displayName` or
`catalogType` and run `catalog test-connection`; no catalog is created. For a replacement-password
test against a stored catalog, use the common stored-catalog shortcut: only the
catalog key/type and a privately entered replacement password are needed.

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
