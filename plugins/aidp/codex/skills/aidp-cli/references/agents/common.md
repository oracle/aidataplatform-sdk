# Agents: secrets depend on tool authentication

For `create_agent` / `update_agent`, read [create](create.md) or [update](update.md)
and [protected bodies](../protected-bodies.md). The agent's top-level metadata
itself does not require a password. Inspect the exact selected tool/auth contract
before requesting any private input.

| Selected branch | Non-sensitive discovery/chat | Private input |
|---|---|---|
| Code agent or graph with no secret-bearing tools | Workspace, destination, name, code paths, compute and requested settings | None by default |
| HTTP/MCP `authType: NO_AUTH` | Tool endpoint/configuration | None |
| HTTP/MCP `OCI_RESOURCE_PRINCIPAL` | Intended resource access and tool configuration | None; do not request an OCI private key |
| HTTP/MCP `BEARER_TOKEN` with raw-token contract | Endpoint, tool identity and auth mode | Required hidden `auth.token` |
| HTTP/MCP `OAUTH` | `clientId`, `issuerIdpEndpoint`, scopes and endpoint | Required hidden `auth.clientSecret` |
| Supported credential-store reference | Existing credential identity/key, required secret-key label | None; never fetch its secret value |

`HttpToolConfiguration` has `url`, `method`, `headers`, `params`, `body`, `auth`;
`McpToolConfiguration` has `endpoint`, `customHeaders`, `allowedTools`, `auth`.
Auth can appear under tool configs in `diagram.toolsMap`, HTTP/MCP tool nodes,
and inline tools in agent/supervisor nodes.
Tool-specific headers, params and body may also contain secrets; mark the exact
whole values as required/optional hidden placeholders using the installed tool
contract. A complete Authorization header must be entered locally as one value
if required: embedded `Bearer {placeholder}` substitution is unsupported.

A bearer credential-store reference is encoded in `auth.token` as a JSON string
containing non-empty `displayName` and `secretKey`. Those values identify a
stored credential; do not turn them into password prompts or retrieve the secret.
The helper preserves this reference shape unchanged.

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

## Model configuration and availability

The `BaseLlmConfig` variants are `OCI_GEN_AI` and `THIRD_PARTY`.
A third-party model requires a supported `provider` (`openai`, `anthropic` or
`gemini`) and a typed `apiKeyCredstoreRef` containing the credential's
`displayName` and optional `secretKey`. These identify a stored credential;
do not request or fetch its API key. Preserve the user's provider, model,
endpoint, compartment and supported connection settings; do not infer them from
the AIDP instance. OCI model configurations do not need a third-party API key.

Before creating or updating an agent whose effective graph uses a third-party
model, verify `AI_AGENTS_3P_LLMS_ENABLED` for the selected AIDP instance. A
metadata-only update may retain a stored third-party model, so omission of a new
diagram does not establish that this check is unnecessary. Inspect only the
non-sensitive model-type metadata needed to determine the effective configuration;
do not copy a stored graph or authentication into an update body.

Use `oci raw-request` for an authenticated read of the bulk wrapper route
`GET /20240831/dataLakes/{instanceOcid}/featureStatuses?featureNames=AI_AGENTS_3P_LLMS_ENABLED`,
following the [feature-status request conventions](../clusters/create.md#check-autoscaling-before-suggesting-limits).
Preserve setup's validated endpoint, instance, authentication, region, profile
and custom OCI config. This wrapper route is separate from the public SDK API;
use the wrapper route and API version shown above.

- A matching item in the response's `data.items` with string `value` equal to
  `true` (case-insensitive) and no item error establishes availability.
- Explicit `false` means third-party models are disabled for this instance.
- A missing item, item error, invalid value or failed request leaves availability
  unverified. Follow the main skill's read-only authentication/network recovery;
  do not describe a failed lookup as a disabled feature.

Only submit the third-party configuration after availability is established.
Otherwise explain the result and resolve access or ask whether the user wants a
supported alternative. Do not silently remove the model, switch providers or
submit a trial mutation. OCI-only graphs do not require this third-party check.

## Session settings and response metadata

Copy supported session summarization, long-term memory and retention settings
only when requested, preserving explicit `false` values. The reviewed fields are
`automaticSummarizationConfig`, `longTermMemoryConfig` and
`sessionRetentionConfig`. Retention can include `isRetentionPolicyEnabled` and
`breachAction: DELETE_FIFO`; do not enable deletion or change retention policy on
the user's behalf. Long-term memory's `llmConfig` uses the OCI model contract;
do not substitute a third-party configuration into that field.

`a2aEndpointUrl` and `deploymentState` are response metadata. Do not copy them
into create/update requests or treat their presence as authorization to deploy
or invoke an agent. SDK redaction metadata does not replace protected-input
handling or make an unfiltered response safe to display.

## Helper contract

`scripts/agents/prepare-body.py --operation create|update --metadata @<metadata>
--output <fresh-template>` takes the intended non-sensitive request/graph only.
It does not discover a complete graph, create tools, deploy, or invoke AIDP.
Preserve the installed graph discriminator, keys, edges, tool/node associations
and requested configuration. Do not paste a full unfiltered agent GET response
into metadata; build the intended request from non-sensitive fields.

For create, the helper inserts required hidden bearer-token / OAuth-client-secret
prompts only at reviewed HTTP/MCP authentication locations: `diagram.toolsMap`
tool `toolConfig.auth`, HTTP/MCP node `configuration.auth` or
`configuration.toolConfig.auth`, and agent/supervisor inline `tools[].toolConfig.auth`.
Distinct tool paths produce distinct prompts. OAuth requires public `clientId` and `issuerIdpEndpoint` first;
scopes are copied from the user's integration requirements, never guessed.
Reference-only, NO_AUTH and resource-principal configs are preserved unchanged.
For secret rotation on update, add `--replace-secrets`; only include the intended
changed authentication/tool configurations. The helper treats every raw bearer/
OAuth auth object included with that flag as a replacement, so do not include
unrelated tools. Without the flag, omit raw-auth objects entirely to avoid silent
clearing; metadata-only and supported reference-only updates need no prompts.

Checks are specific to the selected payload and authentication type:

- `BEARER_TOKEN`: protect `auth.token`, preserving a supported credential reference.
- `OAUTH`: protect `auth.clientSecret`; client ID, issuer and scopes remain public.
- `NO_AUTH` and `OCI_RESOURCE_PRINCIPAL`: no private input is added.

There is no global secret-name blacklist or `--public-field` option. Tool names,
JSON schemas, public field definitions and arbitrary metadata are copied without
classifying their contents from names such as `api_key`, `password` or `auth`.
The helper does not traverse an HTTP request body or schema looking for auth objects.

For each custom tool payload, inspect that endpoint's actual input contract and
mark only its credential values with whole-value protected placeholders. For example:

| Exact tool contract | Protected template field |
|---|---|
| HTTP header `x-api-key` contains an API key | `headers["x-api-key"] = "{invisible_prompt_input:required:Enter API key for the selected tool}"` |
| HTTP query parameter `api_key` contains an API key | `params.api_key = "{invisible_prompt_input:required:Enter API key for the selected tool}"` |
| HTTP request body `client_secret` contains a secret | `body.client_secret = "{invisible_prompt_input:required:Enter client secret for the selected tool}"` |
| MCP custom `Authorization` header contains credentials | `customHeaders.Authorization = "{invisible_prompt_input:required:Enter complete Authorization header for the selected MCP tool}"` |
| HTTP body defines a schema with properties named `auth` or `api_key` | Keep the public schema unchanged; do not request credentials for field definitions. |

These are examples, not a list of names that always contain secrets. Use the
actual endpoint's field path and requirement; preserve any public values or
supported references. Replace the example prompt labels with the actual tool
name and field path so distinct credentials have distinct placeholders; identical
placeholders intentionally reuse one value. A custom secret is not automatically detected or rejected
by the helper. Never paste raw secrets into metadata, and never read local key
or wallet contents. Use `textof`/`base64of` only when that tool API expects it.

Validate paths separately. Execute using `protected_aidp.py --output-file
<unique-result> -- <exact-cli-command>`, then consume/delete the agreed result.
The terminal shows prompts and `Operation output handed off to AI agent. Ask it
to continue.` The wrapper deletes the actual request body on completion/error/
Ctrl+C; do not separately persist credentials or print request bodies.

## Local evidence

SDK models: `CreateAgentDetails`, `UpdateAgentDetails`, `AgentDiagram`,
`HttpTool`, `McpTool`, HTTP/MCP tool-node detail models, `HttpToolConfiguration`,
`McpToolConfiguration`, `Auth`, `BearerTokenAuth`, `OAuth`.
Reference detection also checked in the supplied backend's
`AgentFlowPersistenceService.isCredentialStoreReference`. The helper prepares
protected inputs; validate the complete graph with the CLI reference before
execution.

## Additional properties
