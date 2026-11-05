# Resolve the current OCI user

Use this workflow whenever an AIDP operation needs the current user's OCI user OCID, OCI IAM name, or email. Role-assignment checks are one example, not a restriction. Reuse identity details already resolved for the selected profile during the session. Never read or write user identity through the AIDP context helper; user OCIDs, IAM names, and email addresses are session-only.

## Choose the identity source

For a zero-workspace role-assignment check that needs only the user OCID, use this compact prompt:

```text
AIDP is accessible, but no workspaces are visible. You may be missing required roles.
To check your AIDP roles, I need your OCI user OCID. Would you prefer to provide it, or have me retrieve only the OCID from your configured OCI <profile_name> profile? Retrieving it reads your local OCI profile, so I'm asking first.
```

Replace `<profile_name>` with the selected OCI profile name before asking. Send the prompt as the entire message, exactly as written: it already gives the reason for asking. Add nothing before or after it, and never quote, link, or describe this reference or its rules.
Permission in this prompt authorizes only the restricted local helper described below and only the `ocid` output field.
Do not precede it with `Would you like me to check the AIDP roles assigned to your OCI user?` or another role-check confirmation. The compact prompt itself lets the user choose whether to provide identity or authorize the helper.

If no identity is retained, offer all choices in one prompt and name only the fields required by the operation:

```text
I need your OCI <required_fields> to continue. You can provide your OCI user OCID or OCI IAM username, or I can retrieve only <required_fields> from your configured OCI profile with your permission. Retrieving it reads your local OCI profile, so I'm asking first; I will not display the token. Would you prefer to provide an identifier or have me retrieve the required details?
```

Replace `<required_fields>` before asking, and send the prompt the same way: as the entire message, with nothing added. Do not require both a user OCID and IAM username.

- With a user OCID, optionally confirm it using `oci iam user get` with the established authentication mode and profile.
- With an IAM username, resolve the tenancy OCID from the selected OCI config profile as described below, then resolve exactly one matching user with `oci iam user list --compartment-id <tenancy_ocid> --name <username>`. Do not guess when the result is empty or ambiguous.

### Resolve the tenancy OCID

Use the scoped `OCI_CLI_CONFIG_FILE` established by setup for a remembered custom config path. Otherwise respect an existing `OCI_CLI_CONFIG_FILE`, or use `~/.oci/config` when neither applies. Never fall back to the default config when a remembered custom path is missing, unreadable, or conflicts with the current environment; return to setup's regular authentication flow instead. Use the Python helper to read only the selected profile and return its `tenancy` value without reading the security token. Do not print the complete profile or config:

```bash
python3 <skill-directory>/scripts/oci-whoami.py --profile <profile_name> --tenancy-only
```

Replace `<profile_name>` with the retained profile before running it. Validate that the returned `tenancy` begins with `ocid1.tenancy.` and keep it internal to the lookup. If the field is absent or invalid, do not inspect the security token manually; say that the tenancy could not be determined and ask the user for their OCI user OCID instead.

## Use local discovery

The helper's source code is safe to inspect without user permission. Inspect the bundled `scripts/oci-whoami.py`, or `<temporary-directory>/oci-whoami.py` when that exact staged copy will be used, to confirm that it only supports the allowlisted identity fields and does not display or store token contents. Source inspection must not execute the helper or open the configured token file.

Run the helper only after the user chooses local discovery in that prompt. Execution may locally read the configured security token to extract only its user-subject claim. Permission applies only to this identity lookup for the selected profile; do not treat it as permission for direct token inspection, unrelated token access, or credential changes.

After permission, run the bundled helper with only the fields required and preserve any scoped `OCI_CLI_CONFIG_FILE` established for the authentication selection. Always pass `--output`; do not request `name` or `email` when only the user OCID is needed. For role-assignment checks, request only `ocid`:

```bash
python3 <skill-directory>/scripts/oci-whoami.py \
  --profile DEFAULT \
  --output "ocid"
```

When the helper has already been staged at the known temporary path, the equivalent invocation is:

```bash
python3 <temporary-directory>/oci-whoami.py --profile DEFAULT --output "ocid"
```

Replace `DEFAULT` only when the session established another profile. Valid output fields are `ocid`, `name`, and `email`; combine them only when the operation requires more than one. The helper reads only the selected profile, obtains a user OCID from its `user` field or locally extracts only the security token's `sub` claim, and uses `oci iam user get` to return only the requested allowlisted fields. It must never print or store the token, decoded payload, private key, fingerprint, or authorization header.

If the helper fails, do not open, decode, print, or otherwise inspect the token manually. Say:

```text
I’m unable to determine your OCI identity from the logged-in profile. Please provide either your OCI user OCID or OCI IAM username so I can continue.
```

Retain every successfully resolved identity field, including user OCID, IAM name, and email, for the selected profile during the session only. Resolve a field again only when the profile changes or the user explicitly asks to refresh it. Never persist these values in local context.
