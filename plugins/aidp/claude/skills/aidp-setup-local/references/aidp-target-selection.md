# AIDP target selection

Use when selecting or changing an AIDP instance or endpoint, and for the initial access failure.

## Select the target

1. Resolve the region from the instance OCID through `oci-region-keys.json`. If the key is absent, ask for the full region; never guess. This region always governs OCI authentication and profile validation.
2. Reuse the endpoint choice for the same session instance.
3. With resource type exactly `aidataplatform`, use only the standard regional route. Do not reuse or probe remembered custom endpoints. If inconsistent remembered context contains multiple standard candidates, ignore those candidates and use the regular endpoint flow.
4. For any other resource type with no session choice, find the exact instance in `recentlyUsedAIDP` from the prerequisite script’s returned `context` (its internal helper `get all` result) and place its endpoint first when present. Then take the templates for `<realm>:<resource_type>` from that result's `endpoints` and substitute the OCID-resolved full region for `{region}`. Accept only normalized HTTPS base endpoints whose hostname remains valid after substitution. Preserve MRU order, deduplicate the combined list, and truncate the entire list—including the exact instance endpoint—to at most five candidates.
5. When the selected instance has a remembered endpoint and setup's remembered-target fast path applies, use that endpoint directly for the requested read. If that read fails, follow setup's fast-path fallback before changing endpoints: a `401` follows the authentication checkpoint; a `404` or `NotAuthorizedOrNotFound` first runs the workspace-list validation on the same endpoint, and when that validation succeeds the failure is specific to the requested resource, so keep the endpoint and do not probe others; a DNS, connection, or timeout error first applies the restricted-environment handling. Probe the other candidates below only when the same-endpoint validation also fails with an access or routing error. Otherwise, when remembered candidates and a retained or remembered authentication selection exist, use read-only workspace-list requests as the fast live validation path; do not run a separate authentication helper first. Probe candidates sequentially in MRU order with a bounded timeout and stop at the first valid response containing zero or more items. That response validates both the endpoint and the authentication selection for the profile and target region. A `401 NotAuthenticated` pauses probing and follows the authentication checkpoint below; after authentication becomes valid, retry that same candidate once and then resume with the next candidate only if the retry fails. Every other candidate failure advances silently to the next candidate, including other `4xx`, `5xx`, DNS errors, connection errors, or timeouts. If no authentication selection is available, complete the normal authentication choice before probing. If all candidates fail, do not report every intermediate error; use the regular endpoint question below.
6. When no remembered candidate succeeds, do not characterize the environment; ask once:

  ```text
  Before I validate access, should I use the standard regional AIDP endpoint https://aidp.<resolved_region>.oci.oraclecloud.com, or would you like to provide a different HTTPS AIDP endpoint?
  ```

  Replace `<resolved_region>` before asking.
7. Require an explicit endpoint to be absolute HTTPS with a hostname and no credentials. Normalize it to scheme, hostname, and optional port. Discard its path, query, and fragment as routing noise. Never extract, compare, adopt, or persist an OCID or resource identifier found outside the hostname; it does not change the selected AIDP instance.
8. Compare its hostname labels case-insensitively with the full regions in `oci-region-keys.json`:
   - Matching OCID region: proceed.
   - Different known region: show the OCID region, endpoint, and endpoint region.
   - No known region: say consistency could not be verified.
9. For mismatch or unknown region, require explicit confirmation for that exact instance, region, and endpoint before any AIDP request. Reconfirm when one changes.

An endpoint controls only AIDP routing; it never overrides the selected instance OCID or its OCID-derived region. An endpoint is disclosed only when the user supplied its exact URL or the agent displayed it.

After the first successful HTTP 2xx response for a new session target, from workspace validation or a direct operation, use the known name or fetch it once before recording only the exact instance OCID passed as that request's `--instance-id`, its resolved name when available, and the safely generalized endpoint template through `aidp_context.py`. Verify that the planned context `--instance-ocid` is byte-for-byte identical to the successful command target; skip the write on mismatch. Never source the context OCID from an endpoint URL, record a failed candidate, persist user identity, or ask for persistence consent. Do not open or edit the context file directly.

## Resolve the instance name

After the first successful HTTP 2xx response from workspace validation or a direct operation, use the known instance name or resolve it once against the validated endpoint before saving the target. For resource type `aidataplatform`, derive the endpoint from the OCID-resolved region. For every other resource type, wait until remembered probing or the user has established the exact endpoint.

Run the bundled `scripts/resolve_aidp_instance_name.py` with the established authentication mode, profile, validated endpoint, exact selected instance OCID, and custom config file when applicable. Preserve the scoped `OCI_CLI_CONFIG_FILE` for remembered custom configurations. The helper performs one read-only `oci raw-request` with retries disabled, a 3-second connection timeout, a 10-second read timeout, and a 20-second process bound. It extracts only the response body's `displayName`; do not replace it with `name` or OCI CLI `--query`, and never display or retain the full response. The OCID must be the same immutable value later passed to AIDP `--instance-id`; never substitute an identifier from the user-provided endpoint URL. Track lookup attempts by exact AIDP instance OCID for the session. Do not repeat an attempt, whether it succeeded or failed, for the same OCID even when its endpoint changes. Only a different AIDP instance OCID permits another lookup during the session. A lookup failure is nonfatal: retain `Name not resolved` and continue with workspace validation and the requested operation. Do not query unselected remembered instances only to fill their names.

Invoke the helper directly so its exit status and diagnostics are its own:

```bash
python3 <skill_dir>/scripts/resolve_aidp_instance_name.py \
  --auth <auth_mode> \
  --profile <profile> \
  --endpoint <validated_endpoint> \
  --instance-ocid <aidp_instance_ocid> \
  [--config-file <custom_config_path>]
```

Do not wrap it in `timeout`, `gtimeout`, or another time-limiting command; the helper already bounds itself, and `timeout` is not installed on macOS by default. Do not redirect or discard its stderr (for example with `2>/dev/null`), and always check its exit status. The helper exits `0` with the name on stdout, `1` when the lookup failed, or `2` when its arguments were rejected. Any other status, such as `126` or `127`, means the helper never ran: this is an invocation error, not a lookup attempt. Fix the invocation and rerun it once; it does not consume the per-OCID attempt. On exit `1` or `2`, retain a one-line summary of its stderr for the session and state briefly that the instance name could not be resolved, with that reason, instead of omitting the name silently.

After the first successful HTTP 2xx response, save the target with its known name. If the name is unknown, attempt this lookup once against the validated endpoint before saving. A successful helper result must be passed verbatim to `aidp_context.py set recentlyUsedAIDP --name <display_name>`; do not run the lookup and then omit `--name`. This also backfills a previously unnamed remembered instance without creating a separate persistence path. If the helper exits unsuccessfully or returns no name, omit `--name` and continue saving the other validated context.

## Handle the first access failure

For HTTP `401 NotAuthenticated`, use an authentication checkpoint before endpoint diagnosis:

1. Invalidate any retained authentication-validation result immediately, even when the profile was valid earlier or another AIDP request already succeeded. Preserve the failed request, current endpoint, and position in the remembered-candidate list.
2. For `security_token`, immediately rerun the bundled profile-validation helper for the retained profile and OCID-resolved region. For `api_key`, run the fixed read-only `oci iam region list --profile <profile_name> --auth api_key --output json` check. Do not ask the user to request this check and do not advance to another endpoint first.
3. If authentication is invalid or expired, report that the earlier validation was a point-in-time result and ask whether the user wants to refresh or repair it themselves or wants help. Enter the already selected assistance flow directly when requested; do not repeat the general authentication-choice question.
4. After authentication becomes valid, retry the exact failed read-only AIDP request once with the same instance and endpoint. If this occurred during remembered endpoint probing, retry the same candidate and then resume with the remaining candidates only if that authenticated retry still fails. Do not restart candidates already attempted. Return mutating requests to `aidp-cli` for its state check and confirmation rules instead of retrying them here.
5. If authentication is still valid at the checkpoint, classify the `401` as AIDP endpoint, instance, or access related. During remembered probing, continue with the next candidate. Outside probing, state the exact attempted endpoint only if it has not already been shown or supplied, then use the regular endpoint question or access guidance.
6. If authentication cannot be restored or the user declines, stop with the current endpoint and pending operation retained. Do not claim that the endpoint or instance rejected a valid profile.

For the first HTTP `404` or `NotAuthorizedOrNotFound`:

1. Validate established OCI authentication unless the same profile and authentication mode still have valid session state and no authentication-related failure occurred.
2. When valid, report the AIDP status. Include the attempted endpoint only if not previously disclosed; repeat it only when it changes.
3. Offer one user-provided endpoint retry without characterizing the environment. Normalize it and apply the target checks above before retrying.
4. If declined, recommend IAM or OCID-visibility checks. If the retry fails, report it and stop.
