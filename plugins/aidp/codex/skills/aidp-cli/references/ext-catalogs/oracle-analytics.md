# Oracle Analytics external catalog

Use [the common workflow](common.md) with source type `ORACLE_ANALYTICS` for a direct
external catalog creation or full connection test. This flow uses a registered
application certificate/private key, not a database password or client secret.

Always check the CLI reference documentation for the exact installed CLI
version. Properties may have been introduced or removed after this plugin release. If the
CLI reference lists a new field, also consult
[Additional properties](#additional-properties) for handling details. An empty
section does not establish support or handling for a new field; verify its
requirements in the CLI reference before using it, including any sensitive-input
handling, rather than guessing.

Perform this reference check yourself; do not ask users to supply API field
names or values for every optional property. Preserve the documented defaults
and explicit user choices. Omit unrequested optional fields, including newly
introduced ones. Ask only for required information that is still missing and
has no documented default or established session value. An empty Additional
properties section does not add a user-input step or block the existing flow.

## Choose the intended operation first

This reference covers direct external catalog creation and full connection tests.
For a request to associate an Oracle Analytics instance, clarify that outcome
rather than substituting direct catalog creation or requesting catalog secrets.

## Direct catalog requirements

- Discover/select the OAC instance; use its service URL. Resolve its actual
  identity-domain URL rather than constructing one from the AIDP region (domain
  home region may differ). Discover the intended registered application's client
  ID, authorized scope and registered certificate where permitted. Ask unresolved
  application/domain/endpoint/scope selections in chat. Do not invent the scope.
- Prepare `base64of` placeholders pointing to matching certificate/private-key
  PEM files for the registered application. The generic wrapper privately reads
  and Base64-wraps the complete PEM documents. Do not request
  key text, Base64 content or a client secret in chat. If file paths themselves
  are private, the user can fill those placeholders locally; do not reread them. Existing private
  keys cannot be derived from a public certificate. A new key pair must also be
  registered and granted access; generation is not equivalent to discovery.
- Reuse an authorized existing key/certificate source where available. Any
  mechanism that retrieves private material must keep it inside a reviewed helper
  or secret integration, not a model-visible command output.

Non-sensitive values to discover (map these to the API body fields below):

```json
{"displayName":"sales_analytics","oacEndpointUrl":"https://analytics.example","idcsEndpointUrl":"https://identity.example","clientId":"selected-client-id","scope":"selected-authorized-scope"}
```

The API requires `OAC_ENDPOINT_URL`, `OAC_IDCS_ENDPOINT_URL`,
`OAC_IDCS_CLIENT_ID`, `OAC_IDCS_CLIENT_SCOPE`, `OAC_IDCS_CERTIFICATE`, and
`OAC_IDCS_PRIVATE_KEY`. The backend fills missing or blank `OAC_DISCOVERY_USER`
with a compatibility placeholder; do not ask users to supply that internal default.

For a full test, omit `displayName` and use `catalog test-connection`; this
does not create a catalog. Never use the existing-catalog password-replacement
shortcut for OAC. HTTP 202 is pending, not connection success.

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
