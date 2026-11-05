# ATP external catalog

Check the exact installed CLI version's reference documentation using the
[shared version guidance](common.md#cli-version-and-additional-properties).
For new source-specific fields, also read
[Additional properties](#additional-properties).

Use [the common workflow](common.md) with source type `ATP` in the protected body.

- Reuse source tenancy/region/compartment and discover available Autonomous
  instances with workload `OLTP`. Ask the user to choose only when the intended
  instance is ambiguous.
- Download the selected instance's wallet through the common helper when
  authorized. Otherwise request the wallet ZIP path in chat and use `--wallet`. The UI
  switches to wallet upload for a different source tenancy or region.
- List aliases with the service helper. Ask the user for the service choice in
  chat; the E2E test's `_high`/first-option fallback is test behavior, not a
  production default to copy.
- Collect database `accountUserName` and hidden `accountPassword` in the terminal
  only just before execution. Wallet paths are non-secret chat inputs. The local
  wallet-password prompt allows Enter when optional; FIPS requires a value. A
  fresh wallet download prompts for its protection password separately.

Non-sensitive values to discover (map these to the API body fields below):

```json
{"displayName":"orders_atp","serviceAlias":"orders_tp"}
```

Add `workspaceKey` only when the selected private-network flow needs it.
Required properties are `ATP_USERNAME`, `ATP_PASSWORD`,
`ATP_WALLET_CONTENT_BASE64`, and `ATP_TNS_ALIAS`; `ATP_WALLET_PASSWORD` is also
supported. Do not request host/port or Base64 text. The inspected ATP connector
requires a wallet even when the underlying database supports walletless TLS.
Staging properties are not mandatory creation inputs.

For a new full connection test, omit `displayName` and use
`catalog test-connection`. Existing-catalog replacement-password tests use
only the common stored-catalog shortcut and privately supplied new password.

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
