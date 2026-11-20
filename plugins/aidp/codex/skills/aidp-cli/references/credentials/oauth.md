# OAuth credentials: authorization-code providers

Read [credential discovery](common.md) and [protected bodies](../protected-bodies.md).
This is credential type `OAUTH`, not the agent tool's inline `authType: OAUTH`,
not OAuth admin user settings, and not Databricks catalog `oauth-m2m`.

## Supported scope and discovery

Confirm that the installed `credentials create` / `credentials update` help and
request schema support `OAUTH` with `credentialDetails.flowConfigDetails`.
The reviewed backend supports **only `AUTHORIZATION_CODE`**. Generated SDK enums
also contain `CLIENT_CREDENTIALS` and `DEVICE_CODE`, but the backend rejects both
with `NotAllowed`; do not offer them as working choices or substitute another
grant. If the user needs either reserved grant, explain the limitation.

OAuth credentials can be created only in the `DEFAULT` namespace. Omit a
namespace field when it is not exposed by the installed public CLI; do not use
internal `AGENT_HUB` namespaces or create a second provider to bypass access.
Creating provider configuration does not sign a user in or acquire a token.
The credential token API in the backend is internal-only, not a public CLI
workflow: do not invoke it, request tokens/codes in chat, or fabricate represented
user/principal headers.

Reuse the chosen provider's registered application settings. Ask together only
for missing public values: credential display name, issuer (or authorization and
token endpoints when issuer is unavailable), and registered redirect URL(s).
Reuse the registration's client-protection choice; if unknown, ask whether it
requires a client secret or is a public client using PKCE. Do not ask the user to
choose a grant from the three SDK enum values.

Prefer the configured issuer: the backend discovers its authorization/token
endpoints and verifies issuer and authorization-code support. Do not invent
endpoints by appending paths to an issuer. Without issuer, both `authorizationUrl`
and `tokenUrl` are required on create. If supplied with issuer, they must match
provider discovery. Issuer is HTTPS with no userinfo/query/fragment and no port
other than default/443. Provider endpoints must be absolute HTTPS without
userinfo/fragments. Keep provider-required query parameters when permitted.

Redirect URLs must be registered for this application and absolute, without
userinfo or fragments. HTTPS is required except HTTP loopback callbacks
(`localhost`, `127.0.0.1` or IPv6 loopback). Require at least one on create; do not
invent a callback from the AIDP endpoint. `scopes`, if requested, is a map of scope
names to descriptions, not an array. Do not expand scopes automatically.

## Private input and client protection

The backend treats both `clientId` and `clientSecret` as encrypted client values.
Use a required hidden prompt for a new/replaced client ID and for a confidential
client's secret. Do not retrieve them from a credential GET or copy masked values
into metadata. List summaries have null client values; that is not evidence that
the provider has no secret. This classification is specific to OAuth credential
configuration; follow the separate contracts for agent inline OAuth and Databricks.

For a public client without a secret, omit `clientSecret` and set
`isPkceRequired: true` (S256). For a confidential client, preserve its registered
PKCE requirement and use a required hidden secret prompt. With a nonblank secret,
omitting PKCE on create defaults to false; do not silently disable a requested
PKCE setting. A blank/absent effective secret requires PKCE true. Do not use an
optional empty secret prompt to mean “keep existing”.

## Prepare and execute

Prepare the complete unresolved JSON using the installed schema and the
[generic template workflow](../protected-bodies.md#prepare-an-unresolved-template).
Do not invent grant flags or include actual client values. Example create template for an explicitly selected public client:

```json
{
  "displayName": "registered_provider",
  "type": "OAUTH",
  "credentialDetails": {
    "credentialType": "OAUTH",
    "flowConfigDetails": {
      "grantType": "AUTHORIZATION_CODE",
      "issuer": "https://identity.example.com",
      "clientId": "{invisible_prompt_input:required:Enter registered OAuth client ID}",
      "redirectUrls": ["https://application.example.com/oauth/callback"],
      "isPkceRequired": true
    }
  }
}
```

The URLs are examples, not defaults. For an explicitly selected confidential
client add `clientSecret` with
`{invisible_prompt_input:required:Enter registered OAuth client secret}` and retain
the intended PKCE choice. Do not add a secret-token pair or a private PEM.

Validate the unresolved template with `scripts/validate-protected-paths.py`.
Follow the shared confirmation and execution-mode rules. Because create/replacement
includes hidden prompts, give the user the complete command to run locally:

```bash
python3 <skill_dir>/scripts/protected_aidp.py \
  --output-file /tmp/aidp-result-oauth-<unique>.json -- \
  aidp --auth <auth-mode> --profile <profile> --endpoint <endpoint> \
  --instance-id <instance-ocid> credentials create --body @/tmp/body-oauth-<unique>.json
```

Preserve setup's exact executables, authentication, config and target. Consume and
delete only that result with `read-protected-result.py`; report the credential key
and outcome, not client values or an unfiltered credential response. Browser user
authorization is a separate action; do not claim the provider is connected after
configuration creation alone.

## Update without accidental rotation

Resolve the existing stable key and type using non-sensitive metadata. A name or
description edit uses a metadata-only template and omits `type` and
`credentialDetails`. It needs no new client input.

For an intended OAuth provider edit, use the installed update schema and the
wrapper with `credentials update <credential-key>`. Keep `credentialType: OAUTH`
and `grantType: AUTHORIZATION_CODE` when including flow details. Send only intended
changes. Omitted/null provider fields preserve stored values in the reviewed
backend; prefer omission for unchanged fields. In particular, omit unchanged
client ID/secret and redirect URLs, and never copy a masked GET response.
Prompt only for client values the user intends to replace. A public-field-only
edit may have no prompts and follows the shared direct-execution rules.

Validate the effective provider configuration: removing a secret requires PKCE
true, and changing issuer/endpoints or redirects can affect future sign-ins.
Do not change credential type, revoke grants, delete tokens, or test a token
exchange as an implicit validation step. Express intended rotation through the selected replacement fields and
placeholders; no `--replace-secrets` flag is passed to the CLI.

## Evidence and limits

Reviewed against backend `credentialStore/definitions.cond.yaml`,
`CredentialV2Validator`, `OAuthCredentialModels` and the installed `5.2.0.2` SDK
OAuth model hierarchy. SDK presence does not establish deployment availability.
This reference does not accept a new release baseline or enable reserved grants.
