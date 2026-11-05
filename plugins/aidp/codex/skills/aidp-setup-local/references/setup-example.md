# Setup example

User request:

```text
Set up the AIDP CLI on my machine.
```

The agent first runs the prerequisite script with `--check-latest` for explicit setup. It reads context internally, reuses a saved CLI after `--version` only, or discovers and verifies a Python CLI when needed. It checks Python 3.9+, pip, OCI CLI, AIDP CLI 5.1.0+, and the AIDP Python client, and reports every result before changing the machine. If a required tool is missing, it asks whether the user will install it or wants the agent to do so. If the AIDP CLI and Python client versions do not match, or the AIDP CLI is older than the latest published release, and the check returns an upgrade command, the agent offers that upgrade, which moves both packages to the same version, before validation. When the check returns no command, because no matching release could be verified, the agent reports why it cannot upgrade and continues without the upgrade prompt.

The agent finishes all planned installations and final prerequisite checks before asking for the instance OCID, endpoint, or authentication help. It retains volunteered details without asking again.

After successful verification, the agent saves a changed Python CLI/interpreter selection through the context helper and applies scoped `PATH` only if the script reports it is required. Existing TypeScript installations remain intact. Only after all planned installations, upgrades, and download recovery finish and final prerequisite checks pass, the agent asks:

```text
Prerequisites are ready.
If your company requires VPN for AIDP access, make sure you’re connected.
Would you like to validate it with any AIDP instance?
```

The VPN line is informational: it rides along with the validation question rather than being sent alone and needs no separate reply or VPN confirmation.

If the user declines, the agent reports the installed versions and ends the flow. It does not ask about authentication or an AIDP instance.

If the user agrees, the agent reuses recent instances from the prerequisite script’s returned `context`. When remembered entries exist, it shows each known name first, followed by that entry's derived `displayOcid` verbatim and the full region—for example `nik_delta_uuid_DND — ocid1.aidataplatformqa.oc1.phx.…jane5hgq (us-phoenix-1)`. It labels an unnamed entry `Name not resolved` and lets the user select one or provide another OCID. It does not query every unselected candidate. Otherwise it asks for an AIDP instance OCID. It validates the selected OCID, resolves the region embedded in it, and uses that region throughout the rest of the flow. It does not ask for a separate region or open the context JSON directly.

If the user does not have an instance, the agent recommends these OCI Console steps and waits for an active instance OCID:

1. Sign in through the generic [OCI Console](https://cloud.oracle.com/), then open **Analytics & AI** > **AI Data Platform Workbenches**.
2. Choose the compartment and select **Create AI Data Platform Workbench**.
3. Complete the requested details, review them, and create the instance.
4. When the instance is active, copy its OCID for CLI validation.

The agent also links to the official [Oracle AI Data Platform Workbench getting-started guide](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/get-started-oracle-ai-data-platform.html) and notes that appropriate IAM permission is required to create an instance.

Once it has the selected OCID, the agent reuses `lastUsedAuth` from the same returned `context` without another context read. For a pending read-only AIDP resource request, remembered authentication is used directly for the required workspace-list validation without a separate profile check or confirmation; the final resource result names the profile and authentication mode. A successful workspace-list response establishes working session authentication. A `401 NotAuthenticated` invokes the authentication checkpoint and retries the same request once after authentication is restored. If remembered authentication is absent, the agent asks who will handle authentication. If the user requests help for a pending read-only request, it selects `DEFAULT` and uses the workspace-list request as the first live check; for standalone setup or a pending mutation, it validates authentication first, resolves the tenancy name when available, and asks:

```text
OCI profile DEFAULT is valid for target region us-phoenix-1.
Tenancy: <tenancy_name>
Would you like to continue with this profile?
```

If region or tenancy discovery is incompatible with the operating system or unavailable tooling, the agent keeps the successful session-validation result and asks only:

```text
OCI profile DEFAULT is active.
Would you like to continue with this profile for target region us-phoenix-1?
```

After a successful read-only workspace validation, or when the user agrees to either reuse prompt in another flow, the agent retains the working profile and region and automatically records that validated authentication selection. The first successful HTTP 2xx response for a new instance OCID triggers target saving, whether it comes from workspace validation or a direct operation. If the name is already known, it saves with that name; otherwise it calls the bundled bounded name helper once, then saves with `--name` when successful. A failed lookup cannot block validation or the requested operation and is not repeated for the same OCID during the session, even if the endpoint changes. It retains any resolved instance name for the session and does not repeat the reuse checks or confirmation on later operations unless the profile or region changes, the user requests fresh authentication, or an authentication error occurs.

If the profile is missing, invalid, expired, or confirmed active in a different region, the agent explains the result and starts the already-requested assisted authentication flow:

```text
I’ll use OCI security-token authentication with the DEFAULT profile and region us-phoenix-1 from the AIDP instance OCID.

I will run:
oci session authenticate --region us-phoenix-1 --profile-name DEFAULT
```

The agent runs browser-based sign-in in a foreground terminal, leaves it running for the browser callback, and shares the printed URL if the browser does not open. It keeps the task active while awaiting the callback and repeats the full clickable URL in a final response if a user follow-up requires one, because progress updates may be collapsed. It waits for a successful `Config written to:` message, then proceeds directly to AIDP validation rather than separately validating the OCI profile.

The agent validates access with:

```bash
AIDP_CLI_STRICT_URL_ENCODING=true aidp \
  --auth security_token \
  --profile DEFAULT \
  --region us-phoenix-1 \
  --instance-id <aidp_instance_ocid> \
  workspace list
```

One or more returned workspaces confirm success and allow a pending operation to continue. Zero returned workspaces also confirm connectivity and route directly to the role-assignment diagnostic. When identity is unavailable, the agent immediately uses the compact user-OCID-or-local-helper prompt; it does not first ask whether the user wants roles checked. If setup was invoked for a pending operation, it names that operation after the diagnostic and asks whether the user still wants to proceed; it does not claim that the instance has no clusters or other resources. This workspace validation and any zero-workspace diagnostic run only once for the same session target.

Successful authentication selection, endpoint, instance name, and instance results are recorded automatically only through `aidp_context.py`; failures never become saved defaults. User OCIDs, IAM names, and email addresses remain session-only and are never written to context. The agent never asks a context-persistence consent question.

For HTTP 404, the agent accepts only an absolute HTTPS endpoint with a hostname and no embedded credentials, normalizes it to its base address, and offers one retry if the user has an alternative AIDP endpoint URL:

```text
AIDP access validation returned NotAuthorizedOrNotFound (HTTP 404). Your OCI user may not have access to this AIDP instance.

We used the https://aidp.us-phoenix-1.oci.oraclecloud.com/ endpoint for validation. If you have an alternative AIDP endpoint URL, we can retry using it. Would you like to provide one?
```

For HTTP `401 NotAuthenticated`, the agent invalidates the earlier point-in-time authentication result and immediately checks the configured OCI profile again, even if an earlier AIDP request succeeded. If the security token expired during the flow, it asks whether the user wants to refresh it themselves or wants the agent's help. A request for help enters the assisted browser-authentication flow directly, without repeating the general authentication-choice question. Once the profile is valid, the agent retries the same failed read-only request once with the same endpoint; during remembered endpoint discovery it resumes at that candidate instead of restarting or skipping ahead.
