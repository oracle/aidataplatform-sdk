# Update an agent

Check the exact installed CLI version's reference documentation and the
[shared Additional properties guidance](common.md#additional-properties)
for fields introduced or removed since the plugin release.

Read [common](common.md). Resolve workspace and stable agent key, then discover
only non-sensitive fields and ETag needed for the intended edit. Do not clone
masked authentication or unfiltered response data into the request.

For metadata-only changes, prepare only changed fields and run:

```bash
python3 <skill_dir>/scripts/agents/prepare-body.py --operation update \
  --metadata @/tmp/agent-metadata-<unique>.json --output /tmp/body-agent-<unique>.json
```

No token prompt is introduced. For intended tool authentication rotation, add
`--replace-secrets` and include only relevant tool/auth configurations. Preserve
all required graph content and version-specific change bookkeeping such as
`addedNodes`, `updatedNodes`, `deletedNodes`; verify installed graph replacement
versus patch semantics. If a full graph is required, protect all required secret
inputs locally and resolve the replacement scope before execution; do not assume
omission or an empty string preserves authentication.

Supported existing credential-store reference updates are non-sensitive and
remain references. A raw bearer or OAuth auth object without explicit replacement
is rejected by the helper. A changed public client ID or issuer can require a
new local client secret under the selected full-auth update contract.

Use `agent update <workspace-key> <agent-key>` from installed help and include
`--if-match <etag>` when appropriate. Wrap it with `protected_aidp.py
--output-file /tmp/aidp-result-agent-<unique>.json -- ... --body @<template>`.
Resolve any required credential-impact confirmation first, validate paths, then
consume/delete the result. Do not redeploy automatically or retry an uncertain
update without inspecting current state.
