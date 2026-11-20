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
client/issuer/scope metadata and explicitly add required hidden token/clientSecret
placeholders at the selected private values. Reuse supported credential references when intended instead.
For example, an auth object within an existing valid tool config can be:

```json
{"auth":{"authType":"OAUTH","clientId":"chosen-client","issuerIdpEndpoint":"https://idp.example.com","scopes":["chosen-scope"],"clientSecret":"{invisible_prompt_input:required:Enter client secret for selected tool}"}}
```

This fragment is not a complete agent graph. Do not invent node IDs or omit
required graph fields just to use it.

Prepare the complete unresolved JSON template using the [common template guidance](common.md#template-preparation).

Validate referenced local paths separately and follow the common execution-mode
rules. If no prompts remain, summarize the target, workspace, public agent inputs,
authentication references/file paths and intended creation, ask "Shall I proceed?",
and wait for approval before running the wrapper yourself. If any raw-secret or
other prompt remains, give the complete command to the user for local input.
Both modes use the exact installed command wrapped as:

```bash
python3 <skill_dir>/scripts/protected_aidp.py \
  --output-file /tmp/aidp-result-agent-<unique>.json -- \
  aidp --auth <auth-mode> --profile <profile> --endpoint <endpoint> \
  --instance-id <instance-ocid> agent create <workspace-key> --body @/tmp/body-agent-<unique>.json
```

Consume/delete the result, retain the agent key and report create status.
Creation is not deployment or proof of successful downstream tool authentication.
