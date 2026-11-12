# Create a credential

Check the exact installed CLI version's reference documentation and the
[shared Additional properties guidance](common.md#additional-properties)
for fields introduced or removed since the plugin release.

Read [common](common.md). Discover the intended type and target first. Ask in
chat only for unresolved display name, key names, source identity, Vault secret
choice and optional description. Do not prompt for secrets in chat.

Example non-sensitive metadata for two secret-token entries:

```json
{"displayName":"integration_keys","credentialDescription":"Integration access"}
```

```bash
python3 <skill_dir>/scripts/credentials/prepare-body.py --operation create \
  --type SECRET_TOKEN --secret-key api_token --secret-key client_secret \
  --metadata @/tmp/credential-metadata-<unique>.json --output /tmp/body-credential-<unique>.json
```

Each generated pair has a required hidden prompt identifying its exact `secretKey`,
for example, "Enter secret value `api_token`"; values are not reused across pairs.
Service-account metadata instead includes `credentialDetails`
with `userId`, `tenancy`, `region`, `fingerprint`, and `isReadOnly` when needed;
use `--type SERVICE_ACCOUNT --private-key-path /local/key.pem`.
Vault metadata includes `credentialDetails.secretId`; use `--type VAULT_REFERENCE`
and request no password or token.

Validate paths separately. After the concrete requested credential change has
any required confirmation, provide the exact installed CLI command wrapped as:

```bash
python3 <skill_dir>/scripts/protected_aidp.py \
  --output-file /tmp/aidp-result-credential-<unique>.json -- \
  aidp --auth <auth-mode> --profile <profile> --endpoint <endpoint> \
  --instance-id <instance-ocid> credentials create --body @/tmp/body-credential-<unique>.json
```

`--instance-id` is global in current CLI versions; older generated docs show a
positional instance. Follow installed help. Do not create resources merely to
validate this workflow. Consume the result once; retain the returned credential
key for authorized follow-up. A conflict requires state inspection, not a blind retry.
