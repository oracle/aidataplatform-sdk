# Update a credential

Check the exact installed CLI version's reference documentation and the
[shared Additional properties guidance](common.md#additional-properties)
for fields introduced or removed since the plugin release.

Read [common](common.md). Resolve a stable credential key and retrieve only
non-sensitive identity/type metadata. Never copy masked `secretValue` or private
key fields back into an update. Resolve any name ambiguity in chat.

For a description/name change, metadata contains only changed top-level fields:

```bash
python3 <skill_dir>/scripts/credentials/prepare-body.py --operation update \
  --metadata @/tmp/credential-metadata-<unique>.json --output /tmp/body-credential-<unique>.json
```

No secret prompt is added. For intended rotation, add `--replace-secrets`, the
existing `--type`, and the relevant `--secret-key` or `--private-key-path` options
from common.md. Discover whether the endpoint merges or replaces details before
building a multi-key replacement; include the intended complete key set when
required. Do not silently change the credential type or remove other keys. If
preserving required existing secret values is impossible through the contract,
ask for the replacement values locally rather than retrieving them into chat.

Use the existing key in `credentials update <credential-key>` after checking
installed help. Use `--if-match` only if that installed operation supports it;
never invent an option. Wrap the exact command with `protected_aidp.py
--output-file /tmp/aidp-result-credential-<unique>.json -- ... --body @<template>`.
Confirm the concrete credential impact where required, validate referenced
paths before prompting, consume/delete the result, and verify state without
retrieving secret contents if the outcome is uncertain.
