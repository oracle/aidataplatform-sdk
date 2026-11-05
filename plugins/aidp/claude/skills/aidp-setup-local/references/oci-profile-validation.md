# OCI security-token profile reuse validation

Use this procedure only before starting `security_token` authentication. Run it at most once for the same profile and target region during a session. Do not use it for `api_key`.

If the profile was already accepted for the target region, or an AIDP request using that profile and region succeeded, reuse the retained session state without validating or asking again. Invalidate that state after a profile or target-region change, an explicit request for fresh authentication, or an authentication-related failure. A later HTTP `401 NotAuthenticated` always invalidates the retained result even when this helper or an earlier AIDP request succeeded; rerun the helper immediately before diagnosing the endpoint, instance, command, roles, or permissions.

## Run the bundled helper

Resolve `../scripts/validate_oci_security_token.py` relative to this reference's directory and invoke it with Python:

```bash
python3 <skill_directory>/scripts/validate_oci_security_token.py \
  --profile <profile_name> \
  --target-region <target_region>
```

When the authentication selection has a custom config path, preserve setup's scoped `OCI_CLI_CONFIG_FILE` on this invocation so every internal OCI command reads the same config. Do not fall back to the default config under the same profile name.

The helper executes only fixed, read-only OCI commands. It captures OCI debug output in memory, never prints credentials, authorization headers, tenancy OCIDs, or raw debug data, and emits one sanitized JSON object. For `expired`, `invalid`, and `profile_missing`, the object also includes `detail`: OCI's own error line, as one line of at most 300 characters. `expired` means OCI reported that the CLI session has expired; any other validation failure, including one that merely mentions an expired certificate, is `invalid`.

The helper needs access to the OCI profile and OCI network. Request narrowly scoped permission for this exact helper invocation before running it when the runtime sandbox would otherwise block that access. Do not first run it in a restricted network and then repeat it. Do not grant broad access to Python, `oci`, `aidp`, the shell, or the entire skill.

Do not replace the helper with shell pipelines. Its internal timeouts make the outcome bounded and its argument-array subprocess calls avoid shell injection.

## Interpret the result

When this validation supports a pending read-only AIDP resource operation, an `active` or `active_details_unavailable` result is sufficient authorization to use that profile for the requested reads. Retain the profile and continue without displaying the reuse prompt below. Return the selected profile and `security_token` mode to `aidp-cli`, which names them once in the final operation result. This automatic reuse does not apply to standalone setup or a pending mutation; those flows use the prompts below unless the profile was already accepted earlier in the session.

| Status | Action |
| --- | --- |
| `active` | For a pending read-only resource operation, continue automatically. Otherwise show the profile, target region, tenancy name, and `validUntil` when returned, then ask whether to continue. |
| `active_details_unavailable` | For a pending read-only resource operation, continue automatically. Otherwise show `validUntil` when returned, omit unavailable region or tenancy details, and ask whether to continue with the profile for the target region. |
| `region_mismatch` | Explain the confirmed region mismatch. In the assisted flow, continue to authentication; otherwise wait for the user to choose another profile or request authentication. |
| `expired`, `invalid`, or `profile_missing` | Report that the profile cannot be reused, and show `detail` so the user sees OCI's actual reason. In the assisted flow, continue to authentication; otherwise wait for the user. |
| `validation_unavailable` or `oci_unavailable` | Report that validation could not run. Do not classify the credential as invalid and do not start authentication without the user's direction. |
| `invalid_input` | Correct the profile or region input before continuing. |

Outside a pending read-only resource operation, for `active`, show:

```text
OCI profile <profile_name> is valid for target region <target_region>.
Tenancy: <tenancy_name>
Valid until: <valid_until_when_available>
Would you like to continue with this profile?
```

Outside a pending read-only resource operation, for `active_details_unavailable`, show:

```text
OCI profile <profile_name> is active.
Valid until: <valid_until_when_available>
Would you like to continue with this profile for target region <target_region>?
```

Omit the `Valid until` line when the helper did not return it. It describes only the validation instant and never suppresses the mandatory recheck after a later `401 NotAuthenticated`.

For automatic read-only reuse, or when the user agrees in another flow, retain the exact profile with `security_token`, skip authentication, and continue to the read-only AIDP validation. If the user declines a prompt, ask whether they want another profile or authentication. Honor an explicit request for fresh login even when the profile is reusable.
