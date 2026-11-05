# Create an agent

Check the exact installed CLI version's reference documentation and the
[shared Additional properties guidance](common.md#additional-properties)
for fields introduced or removed since the plugin release.

Read [common](common.md). Resolve workspace and target, then derive or ask only
missing display name and workspace destination (`pathInfo`). Choose canvas/code
and reuse intended compute/code/graph metadata. `type` is optional in this SDK;
use `CANVAS` or `CODE` when the installed flow requires a selection. Remote
`entryFilePath` / `dependenciesFilePath` identify workspace code; they are not
local attachments to Base64-encode. Do not upload, provision or deploy without
that action being part of the user's task.

Prepare a complete valid request graph from the installed contract. For each
selected HTTP/MCP raw-auth tool, include non-sensitive `authType` and OAuth
client/issuer/scope metadata; leave token/clientSecret absent so the helper can
insert prompts. Reuse supported credential references when intended instead.
For example, an auth object within an existing valid tool config can be:

```json
{"auth":{"authType":"OAUTH","clientId":"chosen-client","issuerIdpEndpoint":"https://idp.example.com","scopes":["chosen-scope"]}}
```

This fragment is not a complete agent graph. Do not invent node IDs or omit
required graph fields just to use it.

```bash
python3 <skill_dir>/scripts/agents/prepare-body.py --operation create \
  --metadata @/tmp/agent-metadata-<unique>.json --output /tmp/body-agent-<unique>.json
```

Validate referenced local paths separately and ask the user to execute the exact
installed command wrapped as:

```bash
python3 <skill_dir>/scripts/protected_aidp.py \
  --output-file /tmp/aidp-result-agent-<unique>.json -- \
  aidp --auth <auth-mode> --profile <profile> --endpoint <endpoint> \
  --instance-id <instance-ocid> agent create <workspace-key> --body @/tmp/body-agent-<unique>.json
```

Consume/delete the result, retain the agent key and report create status.
Creation is not deployment or proof of successful downstream tool authentication.
