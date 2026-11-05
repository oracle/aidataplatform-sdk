# Create a user setting

Check the exact installed CLI version's reference documentation and the
[shared Additional properties guidance](common.md#additional-properties)
for fields introduced or removed since the plugin release.

Read [common](common.md). Reuse authenticated-user/target context and discover
existing setting names/defaults when needed to avoid duplicates. Ask only the
unresolved provider, name and default intent in chat. Account username and token
are entered locally immediately before the AIDP call.

Example PAT metadata:

```json
{"name":"work_git","isDefault":false,"data":{"providerName":"GITHUB"}}
```

```bash
python3 <skill_dir>/scripts/user-settings/prepare-body.py --operation create \
  --type GIT_ACCOUNT --metadata @/tmp/setting-metadata-<unique>.json \
  --output /tmp/body-setting-<unique>.json
```

For IAM, use `--type IAM_USER_CREDENTIAL --private-key-path /local/key.pem` and
include public `userId`, `tenancy`, `region`, `fingerprint` in metadata's `data`.
`OAUTH` belongs to admin settings and is not accepted by this helper.

Check paths separately, settle any required credential/default-change confirmation,
then ask the user to run:

```bash
python3 <skill_dir>/scripts/protected_aidp.py \
  --output-file /tmp/aidp-result-setting-<unique>.json -- \
  aidp --auth <auth-mode> --profile <profile> --endpoint <endpoint> \
  --instance-id <instance-ocid> user-setting create --body @/tmp/body-setting-<unique>.json
```

Use installed help to resolve CLI-version differences. Consume/delete the agreed
result. Retain the setting key for authorized follow-up and do not print its data
if the response contains credentials.
