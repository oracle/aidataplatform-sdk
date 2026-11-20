# Create a user setting

Check the exact installed CLI version's reference documentation and the
[shared Additional properties guidance](common.md#additional-properties)
for fields introduced or removed since the plugin release.

Read [common](common.md). Reuse authenticated-user/target context and discover
existing setting names/defaults when needed to avoid duplicates. Ask only the
unresolved provider, name and default intent in chat. For Git PAT settings,
account username and token are entered locally immediately before the AIDP call.
IAM settings use the supplied private-key file without a terminal prompt.

Example PAT metadata:

```json
{"name":"work_git","isDefault":false,"data":{"providerName":"GITHUB"}}
```

Prepare the complete unresolved JSON template using the [common template guidance](common.md#template-preparation).

For IAM, include `data.type: IAM_USER_CREDENTIAL`, public `userId`, `tenancy`,
`region`, `fingerprint`, and `privateApiKey: "{textof:/local/key.pem}"`.
For Git PAT, include `data.type: GIT_ACCOUNT`, `entityType: PERSONAL_ACCESS_TOKEN`,
a required visible `username` placeholder and hidden `personalAccessToken`
placeholder. Both branches require the intended name and boolean `isDefault`.
`OAUTH` belongs to admin settings, not this user-setting workflow.

Check paths separately and follow the common execution-mode rules. For IAM
settings with no prompts, summarize the public inputs, target, key-file path and
default intent, ask "Shall I proceed?", and wait for approval before running the
wrapper yourself. For Git PAT settings, settle any required confirmation and ask
the user to run the command for private input. Both modes use:

```bash
python3 <skill_dir>/scripts/protected_aidp.py \
  --output-file /tmp/aidp-result-setting-<unique>.json -- \
  aidp --auth <auth-mode> --profile <profile> --endpoint <endpoint> \
  --instance-id <instance-ocid> user-setting create --body @/tmp/body-setting-<unique>.json
```

Use installed help to resolve CLI-version differences. Consume/delete the agreed
result. Retain the setting key for authorized follow-up and do not print its data
if the response contains credentials.
