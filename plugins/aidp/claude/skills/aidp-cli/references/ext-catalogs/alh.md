# ALH external catalog

Check the exact installed CLI version's reference documentation using the
[shared version guidance](common.md#cli-version-and-additional-properties).
For new source-specific fields, also read
[Additional properties](#additional-properties).

Use [the common workflow](common.md) with source type `ALH` in the protected body.
The API uses `ALH_*` properties. Its downstream helper treats ALH as ADW; that
does not mean callers should replace the public source type or property prefix.

- Reuse source tenancy/region/compartment where known. Discover authorized
  Autonomous databases in that scope. The UI's Lakehouse listing uses `DW`;
  newer OCI metadata also exposes `LH`. Do not identify an arbitrary `DW`
  resource as the user's intended Lakehouse without context.
- Ask which database only when selection is unresolved. Download its instance
  wallet with the common helper if authorized and accessible; otherwise ask the
  user for the wallet ZIP path in chat; use the direct `--wallet` helpers. The UI falls back to wallet upload
  for a different tenancy or region.
- Use the service-list helper and ask for the intended alias in chat. Do not
  print the connection descriptors or assume an alias solely from its suffix.
- Collect `accountUserName` and hidden `accountPassword` in the terminal only
  immediately before execution. For the wallet password,
  optional hidden placeholders allow Enter; FIPS uses required placeholders.
  Do not collect account credentials during instance/service discovery.

Non-sensitive values to discover (map these to the API body fields below):

```json
{"displayName":"sales_lakehouse","serviceAlias":"sales_low"}
```

Add a discovered/selected `workspaceKey` if the private-network flow requires
one. Required API properties: `ALH_USERNAME`, `ALH_PASSWORD`,
`ALH_WALLET_CONTENT_BASE64`, `ALH_TNS_ALIAS`. `ALH_WALLET_PASSWORD` is supported
but absent from the mandatory list. Host, port, Base64 encoding, staging
properties, and internal catalog flags are not additional mandatory user inputs.
Use a database-specific wallet rather than a regional multi-database wallet.

For a full test, omit `displayName` and use `catalog test-connection`.
For a stored-catalog replacement-password test, use the common shortcut and do
not request username, wallet, or service again. A test does not save a new password.

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
