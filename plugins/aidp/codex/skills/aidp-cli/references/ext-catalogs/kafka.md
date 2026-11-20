# Kafka external catalog

Check the exact installed CLI version's reference documentation using the
[shared version guidance](common.md#cli-version-and-additional-properties).
For new source-specific fields, also read
[Additional properties](#additional-properties).

Use [the common workflow](common.md) with source type `KAFKA` in the protected body.

- Identify whether this is OCI Streaming or another Kafka service; ask in chat
  only if context does not establish it. Discover the intended stream pool or
  cluster using authorized metadata/configuration. Do not assume every Kafka
  source is OCI Streaming.
- Bootstrap servers and TLS/SASL settings are non-sensitive chat inputs when not
  discoverable. OCI Streaming Kafka settings can be constructed from its actual
  endpoint, selected pool, tenancy/domain and identity; its password is an OCI
  auth token. Do not substitute the OCI API signing key or a login password.
- Collect `accountUserName` and hidden `accountPassword` in the terminal only
  immediately before execution, unless supplied by an authorized secret integration. The
  helper deliberately keeps the account name private too. Existing auth tokens
  cannot be reconstructed from token-list metadata; creating one is a separate
  credential operation, not a read-only derivation.

Non-sensitive values to discover (map these to the API body fields below):

```json
{"displayName":"events","bootstrapServers":"broker.example:9092","sslEnabled":true,"saslMode":"PLAIN"}
```

Use actual source settings; the example is not a universal default. Required API
properties: `BOOTSTRAP_SERVERS`, `USERNAME`, `PASSWORD`. `ENABLE_SSL`, `SASL_MODE`
and a selected `WORKSPACE_KEY` are supported. The inspected UI exposes bootstrap
servers, username/password and SSL, but does not expose a SASL selector. The API
helper requires credentials even for deployments where Kafka itself might allow
anonymous access; do not invent empty credentials.

For a full test, omit `displayName` and use `catalog test-connection`.
For an existing catalog's replacement-password test, use the common shortcut:
only the stable key/type and a hidden replacement-password placeholder in the body.

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
