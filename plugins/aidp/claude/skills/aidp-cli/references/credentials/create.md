# Create a credential

Check the exact installed CLI version's reference documentation and the
[shared Additional properties guidance](common.md#additional-properties)
for fields introduced or removed since the plugin release.

Read [common](common.md). Discover the intended type and target first. Ask in
chat only for unresolved display name, key names, source identity, Vault secret
choice and optional description. Do not prompt for secrets in chat.

For type `OAUTH`, follow [OAuth credential creation](oauth.md) instead of the
template guidance below. It covers authorization-code provider discovery,
private client input, PKCE and the direct protected-template execution branch.

Example public metadata for a two-pair secret-token request (add the explicit credential details below):

```json
{"displayName":"integration_keys","credentialDescription":"Integration access"}
```

Prepare the complete unresolved JSON template using the [common template guidance](common.md#template-preparation).

Include `type: SECRET_TOKEN`, matching `credentialDetails.credentialType`, and
`secretTokenPair` entries with a required hidden placeholder at each `secretValue`.
Each placeholder identifies its exact `secretKey`,
for example, "Enter secret value `api_token`"; values are not reused across pairs.
Service-account metadata instead includes `credentialDetails`
with `userId`, `tenancy`, `region`, `fingerprint`, and `isReadOnly` when needed;
include `type: SERVICE_ACCOUNT`, the matching detail discriminator, and
`privateKey: "{textof:/local/key.pem}"`.
Vault metadata includes `credentialDetails.secretId`
and matching `VAULT_REFERENCE` discriminators; request no password or token.

Validate paths separately and follow the common execution-mode rules.
For `SERVICE_ACCOUNT` and `VAULT_REFERENCE` with no prompts, summarize the public
inputs, target, file path/reference and intended credential creation, ask
"Shall I proceed?", and wait for approval before executing the wrapper yourself.
For `SECRET_TOKEN`, obtain any required confirmation and give the command to the
user for private input. Both modes use the exact installed CLI command wrapped as:

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
