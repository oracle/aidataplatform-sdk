---
name: aidp-cli
description: Operate Oracle AI Data Platform resources with the AIDP CLI. Use after local setup for command discovery, read operations, payload construction, troubleshooting, and confirmed changes; do not use for initial installation or OCI authentication.
---

# AIDP CLI

Use the installed AIDP CLI to operate any AIDP command group after `aidp-setup-local` has established a working local environment. This is the general resource-operations skill; it covers workspaces as well as command groups such as clusters, notebooks, workflows, catalogs, credentials, and volumes.

**User-facing messages:** never mention, quote, cite, or link these skill files or their rules, and never explain a question or action by saying an instruction requires it. When a reference gives an exact prompt, send that prompt as the whole message, word for word, with nothing added before or after it, except status the reference asks to show first, such as the list of missing prerequisites, and setup’s VPN reminder line placed before it. If the user asks why, answer in one plain sentence about the reason itself, such as "Reading your OCID from your token needs your OK."

## Native Windows execution

On native Windows, read [Windows execution](references/windows.md) before running
setup or resource commands. It defines the PowerShell invocation, executable
paths and temporary-file conventions that override POSIX examples below.

## Responsibility boundary

This skill owns AIDP resource operations after setup: command discovery, reads, mutations, payload construction, and command troubleshooting. It does not install prerequisites, configure or recover OCI authentication, choose an initial AIDP instance, or perform initial connectivity validation; route those concerns to `aidp-setup-local`.

## Remembered context

Use `../aidp-setup-local/scripts/aidp_context.py` for every cross-session context read or write, as described in [the context command reference](../aidp-setup-local/references/context-cli.md); read it before a new context operation. Never open, parse, create, or edit `~/.config/aidp/context.json` directly. Remembered values are default guesses; let `aidp-setup-local` validate authentication, instance, region, and endpoint before the requested operation. Automatically save eligible validated connection defaults without asking for consent. Never persist a user OCID, IAM name, email address, or other user identity; retain those only for the current session. If context is missing, invalid, or unavailable, continue with the regular uncached flow.

## Scope and routing

- Use `aidp-setup-local` for prerequisite installation, OCI authentication, choosing an instance, and initial validation.
- Use this skill once the user asks to inspect, list, get, create, update, delete, troubleshoot, or otherwise operate an AIDP resource.
- When an environment was not established during the current conversation and the user did not supply an AIDP instance OCID, take `recentlyUsedAIDP` from the prerequisite script’s returned `context`, running setup’s prerequisite script first and reusing its returned `context` if the context has not been read in this session. If entries exist, show each known name first, followed by that entry's `displayOcid` verbatim and then the full region, in MRU order. Do not independently abbreviate `instanceOcid` or shorten `displayOcid`. The helper preserves the OCID prefix through its embedded region key and shortens only its unique suffix, for example `nik_delta_uuid_DND — ocid1.aidataplatformqa.oc1.phx.…jane5hgq (us-phoenix-1)`. Ask the user to select one or provide another OCID. Label an entry without a stored name as `Name not resolved`; after the user selects it, let `aidp-setup-local` resolve the name against the final validated endpoint. Do not probe every unselected remembered instance merely to populate the selection list. If no entry exists, ask only for the AIDP instance OCID. Retain the selected OCID, resolved name when available, its resolved region, and any validated endpoint for the rest of the session. Do not ask for the OCID again unless the user explicitly asks to change the AIDP instance. Resolve its embedded region key case-insensitively through [the bundled region-key cache](../aidp-setup-local/references/oci-region-keys.json). Do not ask the user for a region when the cache resolves the key.
- If the cache does not contain the OCID's region key, ask for the full OCI region identifier, for example `us-phoenix-1`; do not guess.
- Authentication is owned by `aidp-setup-local`. Continue with whichever authentication mechanism it established for the session, including `security_token` or `api_key`, and use its exact OCI profile. For a read-only request, let setup optimistically validate a retained or remembered authentication selection with its workspace-list request, or with the first request on its remembered-target fast path. If no authentication selection is available, invoke setup's authentication workflow; do not independently ask for, assume, or configure an authentication mode or OCI profile in this skill. Mutations require setup to validate authentication first.
- Before the first resource operation for a session target, let `aidp-setup-local` complete its one-time workspace-list validation, or apply its remembered-target fast path: for a read-only request on a remembered instance with its remembered endpoint and authentication, run the request directly and let its first response serve as the validation, falling back to the full validation only if it fails. If it returns zero workspaces, proceed directly to the read-only role-assignment check below; do not ask whether the user wants roles checked. Let setup obtain the user's decision about the pending operation only after the diagnostic. Continue only when the user agrees. Do not translate zero visible workspaces into a claim that no clusters or other resources exist; resolve any workspace key required by the requested command normally, including accepting a user-supplied key.
- Before authentication or any AIDP command for a new or changed instance, extract the OCID resource type. If it is not exactly `aidataplatform` and no endpoint decision is retained for that instance, follow remembered-endpoint discovery in [AIDP target selection](../aidp-setup-local/references/aidp-target-selection.md). Ask its regular endpoint question only when no remembered candidate succeeds. When a retained or remembered authentication selection exists, let setup's read-only workspace-list request validate the authentication and endpoint together; when none exists, complete the normal authentication choice first.
- Follow [AIDP target selection](../aidp-setup-local/references/aidp-target-selection.md) before using a new or changed instance or endpoint. Preserve the selected AIDP instance OCID exactly across name lookup, validation, resource commands, and context persistence. Always retain the OCID-resolved region; an explicit endpoint changes only AIDP data-plane routing and no identifier embedded in its path or query may replace the selected instance.
- Do not infer, name, or describe an environment category from an OCID resource type, an endpoint hostname, or any other identifier. Preserve exact OCIDs and user-provided endpoint hostnames when displaying or using them, and never explain a routing or access outcome in terms of which environment an instance belongs to.

## Discover the command contract

Use the CLI command reference generated for the installed `aidp-cli` version, looked up directly in `~/.config/aidp/docs/aidp-cli-<installed_version>.md`, as the primary discovery source. It provides the command index, documented arguments, options, and request-body fields for exactly that version, without requiring broad interactive CLI discovery.

1. Before the first operation in a session, make sure the `aidp-setup-local` prerequisite script has run once, with or without `--skip-latest` as its weekly latest-version rule requires. It covers `aidp --version`, the AIDP CLI and Python client version match, and the latest-version check in one call. Only after all planned installations, upgrades, and download recovery finish and final prerequisite checks pass, include setup’s VPN reminder on its own line, directly before the question in the next message that asks the user something, such as the instance choice. If no question is needed, include it in the first user-visible message and continue with the request. Never send it alone or end the turn for it. If prerequisite checks report problems, show only those problems and offer to apply the documented remediation through `aidp-setup-local`. Carry out approved fixes yourself; ask the user to act only when a step requires their direct participation or they choose self-installation. Do not hand off ad hoc repair commands to the user. When `actions` contains `upgrade_aidp_packages` with a command, follow setup's "Upgrade prompt: stop and wait": ask the upgrade question in a user-visible reply, then end the turn. Defer instance, endpoint, and authentication questions until all planned installations and final prerequisite checks finish. Do not run the requested operation, even a read-only one, until the user answers. Mentioning the mismatch in a progress update and continuing is not enough. Continue with the request after the user declines, or after the upgrade and a rerun of the script. When the action has `command: null`, follow setup's handling for that case instead: report its `blocked` reason without stopping, and never build an install or upgrade command yourself. Reuse setup’s selected Python CLI and session command environment. Only when `prerequisites.aidp_cli.path_adjustment_required` is true, prepend the `add_to_path` action’s `path_hint` to `PATH` for every AIDP command, helper, protected wrapper, and retry; child processes inherit it. Otherwise do not adjust `PATH`. No shell-configuration question is required. Never run a separate CLI discovery/version check or initial context read. Keep the explicitly selected `aidp_python.path` for documentation generation, and retain the originally validated OCI CLI path if the prefix would shadow it. Rerun it later in the same session only in the cases setup allows: after an installation, upgrade, or pip restore, the one network-permission rerun, the one `--check-latest` rerun that obtains a verified command, the `--aidp` verification of a new installation, or when the user asks.
2. Look up commands in the version-specific reference, after the prerequisite script has run. The reference is large, about 160,000 tokens, so never read it whole:
   - Take the installed version from the prerequisite output, `prerequisites.aidp_cli.version`. The reference is `~/.config/aidp/docs/aidp-cli-<version>.md`.
   - Each command has its own heading in the form `` #### `aidp <command-group> <command>` ``. Use the file directly; do not check for it separately first. When the command is known, extract exactly its section in one read-only call; the range ends at the next heading:

     ```bash
     sed -n '/^#### `aidp <command-group> <command>`/,/^##/p' ~/.config/aidp/docs/aidp-cli-<version>.md
     ```

     When the command is not known, or the extraction prints nothing, search only the `####` headings for a keyword from the request with the host's file-search tool or a read-only search such as `rg -n '^#### .*<keyword>'`, then extract the one matching section the same way. Read a whole command-group section only when the user asks for an overview of that group.
   - Only when the extraction or search shows that the file does not exist, generate it with the Python that owns `aidp`, reported as `aidp_python.path`, because the generator documents the CLI installed in the Python that runs it:

     ```bash
     <aidp_python.path> <skill_dir>/scripts/GenerateAIDPCLIDoc.py --outputDir ~/.config/aidp/docs
     ```

     It needs no network, writes only that one file, and does nothing when the file already exists. Do not wrap it in `timeout` or discard its stderr. If the host restricts writes outside the workspace, request narrowly scoped permission for this exact command.
   - Then use the file at the exact path the generator prints, after `Generated:` or `Doc already exists:`, rather than the name you derived; the two can differ for unusual version formats. Keep using that file for the rest of the session; a new one is generated only when the installed `aidp-cli` version changes, such as after an upgrade, because the new version's file is missing.
   - If anything goes wrong, such as generation failing, the installed CLI shipping no command manifest, or the file being unreadable, discover commands with `aidp command-groups` and `aidp search <term>`, then confirm each command with installed `aidp <command-group> <command> --help`.
3. Map the user's request to the command group and operation from the sections you found. Use `aidp command-groups` or `aidp search <term>` only when the documentation does not make the intended operation clear.
4. Immediately before executing a new, ambiguous, changed, or mutating operation, verify its exact installed command contract:

   ```bash
   aidp <command-group> --help
   aidp <command-group> <command> --help
   ```

   Installed CLI help is authoritative when it differs from the reference or prior examples. Update the planned command and payload to match the installed CLI; do not execute a documented command shape that its installed help rejects.
5. Identify required path arguments, options, request-body fields, pagination, and retry behavior. Ask only for values that are required and not already known.
6. For known simple read operations, use the documented command shape directly. If it fails validation, refresh the command contract from installed help before retrying.

## Cluster creation

For Spark cluster or AI compute creation, read [cluster creation guidance](references/clusters/create.md).
Obtain the cluster name and type, then present accessible workspaces for the
user to select. Reuse explicit choices already supplied for this creation.
Check both autoscaling flags in one signed bulk request; include scaling limits
only when the relevant flag is confirmed enabled. Show the picked defaults and
user overrides together as Configuration, without calling them recommended.
Ask whether to change anything or create with that configuration, and wait for
explicit confirmation of the displayed configuration before creating.
Once creation is accepted, report that it was triggered and offer a status
check. Do not wait for ACTIVE or start status polling unless the user asks.

## Protected request bodies (all sensitive operations)

For protected commands, present the complete command directly. Do not create or search for generated launcher scripts unless the user explicitly requests one; invoke the bundled protected wrapper directly with the selected interpreter and current session settings.

For any AIDP operation whose JSON body needs credentials, tokens, passwords,
private keys or file contents, follow [protected request bodies](references/protected-bodies.md).
Prepare a JSON template from chat with whole-value prompt/file placeholders and
ask the user to run `scripts/protected_aidp.py` with the exact existing CLI command
and `--body @<template>`. Do not collect secret values in chat, read source key or
wallet contents, or construct resolved secret bodies yourself. The generic
wrapper prompts locally, substitutes in a private copy, executes once and deletes
that copy on completion/error. Wallet ZIP paths are non-secret chat inputs.
For every agent-guided protected request, include `--output-file <fresh-result> --`
before the CLI executable. This applies to all source types and create/test/update
operations. Follow `read-protected-result.py` in the same reference to wait for,
read and delete only the agreed result; continue within the authorized task.
`--output-file` is required; the wrapper refuses commands without it.

## Credentials, user settings and agents

For create/update with protected input, read only the relevant family reference:

- [Credentials](references/credentials/common.md): secret-token pairs, service-account PEM, or Vault references; helpers in `scripts/credentials/`.
- [User settings](references/user-settings/common.md): Git PAT or IAM private key; helpers in `scripts/user-settings/`.
- [Agents](references/agents/common.md): HTTP/MCP bearer/OAuth secrets, custom sensitive fields, or supported credential references; helpers in `scripts/agents/`.

Each family has separate create/update references. Discover non-sensitive values
first, ask only unresolved choices in chat, then prepare whole-value placeholders.
Metadata-only edits do not prompt for secrets. Do not turn a credential reference
into a plaintext-secret request. Use the shared wrapper with `--output-file` and
consume/delete the exact result file before continuing.

## External catalogs and connection testing

Read the selected source reference plus [the catalog workflow](references/ext-catalogs/common.md):
[ADW](references/ext-catalogs/adw.md), [ALH](references/ext-catalogs/alh.md),
[ATP](references/ext-catalogs/atp.md), [Kafka](references/ext-catalogs/kafka.md),
[Oracle Database](references/ext-catalogs/oracle.md),
[Exadata](references/ext-catalogs/exadata.md),
[MySQL](references/ext-catalogs/mysql.md), [DB2](references/ext-catalogs/db2.md),
[Azure SQL Server](references/ext-catalogs/azure-sqlserver.md),
[Snowflake](references/ext-catalogs/snowflake.md),
[Google BigQuery](references/ext-catalogs/google-bigquery.md), or
[Oracle Analytics](references/ext-catalogs/oracle-analytics.md).
When a connection-test source is unspecified, use the complete 12-source prompt
in the common workflow; do not offer a partial example list or “another source”.
Discover non-sensitive values and ask only unresolved choices in chat. Use the
wallet helpers for readability/service discovery without printing contents, then
prepare the protected body template. Keep direct OAC catalog creation distinct
from control-plane OAC association. No separate credential draft is required.
Always use the common workflow’s `--output-file` handoff for every catalog source,
including Oracle Database, MySQL, DB2, Azure SQL Server and both Snowflake auth
branches, and Google BigQuery service-account keys; consume/delete that exact result before continuing. Use the new sources’
documented `prepare-body.py` helpers.

## Folder transfers

For folder upload/download or explicitly requested archive extraction, use
[the folder-transfer reference](references/folder-transfer.md). The helper can ZIP
local folders automatically. For a ZIP upload with unspecified extraction intent,
ask whether to upload and extract or upload the ZIP as a file only. Upload-only
uses the existing single-file API; do not load the folder reference for it.

## Build and run operations

- Write every command out in full. Never store a command, executable, or options in a shell variable and expand it, such as `A="aidp ..."; $A workspace list`: zsh does not split an unquoted variable into words, so the command fails, and the variable also hides what runs from permission prompts.
- Run plugin helpers only with the commands documented in these skills and their references. Do not list script folders or run a helper with `--help` to work out how to call it; the documented usage is complete. If a documented invocation fails validation, fix the arguments from the documentation instead of exploring.
- Every AIDP API command, meaning a resource operation such as `workspace list` or `catalog list`, prints a `Response:` line followed by a JSON object; there is no option to omit that line. Utility commands such as `aidp --version`, `aidp search`, and `--help` print plain text instead. A success contains `data`, `headers`, and `status`; an error contains `status`, `code`, `message`, and `opc-request-id`. Read the output as text, or parse the JSON starting at the first `{`; never pipe the raw output straight into a JSON parser.
- Take field names from the command's response or its section in the generated reference; never guess them. If a field you expected is absent or `null`, check the actual response keys before reporting or omitting it.
- The AIDP CLI reads the environment variable `AIDP_CLI_STRICT_URL_ENCODING`; when it is `true`, the CLI encodes every path argument strictly. Always have it set to `true` for every AIDP API command, in every command group. Pass path arguments raw, with literal `/` and `%`; never pre-encode them as `%2F` or `%25`. How to set an environment variable for a command depends on the OS and shell; in bash or zsh, prefix the command:

  ```bash
  AIDP_CLI_STRICT_URL_ENCODING=true aidp --auth <auth_mode> --profile <profile> --endpoint <endpoint> --instance-id <aidp_instance_ocid> workspace-object head <workspace_key> /Workspace/Shared/example1/input.csv --should-include-metadata true --should-update-recent false
  ```
- Whenever an operation needs the current user's OCI user OCID, OCI IAM name, or email, follow [Resolve the current OCI user](references/oci-whoami.md). Reuse retained identity details and request or discover only the fields required for the operation.
- In a network-restricted environment, follow setup's rule to request network access up front: when the host's environment or sandbox policy says network access is restricted, request narrowly scoped approval with network access on the first run of each AIDP or OCI command or folder-transfer helper (including its CLI calls and Object Storage PUT/GET) instead of letting it fail inside the restriction first. Scope the approval to that command. This does not replace the confirmation a mutation requires.
- Pass the exact `--auth` mechanism and `--profile` established by `aidp-setup-local` on every AIDP command in the session. When that authentication selection includes a custom config path, preserve setup's scoped `OCI_CLI_CONFIG_FILE` value on every command; never silently use the same profile name from the default config. Never print or request private keys, security-token contents, or other credentials.
- Supply the selected AIDP target as global CLI options. Use either `--region <region>` or `--endpoint <endpoint>`, never both.

  ```bash
  AIDP_CLI_STRICT_URL_ENCODING=true aidp \
    --auth <auth_mode> \
    --profile <profile> \
    --region <region> \
    --instance-id <aidp_instance_ocid> \
    <command-group> <command>
  ```

- Build JSON passed through `--body` from live help and the user's confirmed input. Validate generated JSON before a mutating request. Do not reuse an example payload unless the fields match the current operation.
- Resolve a stable resource key or OCID before updating, deleting, changing permissions, or acting on a similarly named resource. Refresh its live state if staleness could affect the result.
- Preserve useful resource keys, operation IDs, request IDs, and pagination tokens in the conversation for follow-up requests. Reduce long command output to the fields the request needs; do not reproduce every returned field. Offer raw output in one short line rather than printing it unasked.

## Inspect roles and assignments

For `what roles do I have`, another role-assignment question, or setup validation that returned zero workspaces:

1. Resolve the current OCI user once by following [Resolve the current OCI user](references/oci-whoami.md). For zero-workspace validation, use its compact role-assignment prompt immediately when identity is not retained. That prompt is the only question before identity resolution; do not separately ask whether to check roles. Send it word for word as the whole message, then wait for the user's choice before running the helper.
2. List all AIDP roles with `role list`, following pagination. For each distinct role key, run `role get <role_key>` with the retained target and authentication options.
3. Mark a role `Assigned` only when the exact resolved user OCID appears in its `assignees` array; otherwise mark it `Not assigned`. Never use `isAssigned` to determine membership.
4. Run `role list-permissions <role_key>` for assigned roles and show each assigned role's permission count. Show individual permission names only when requested.
5. Present every discoverable role and its assignment state. If identity, role listing, or role details are unavailable, report that assignment status could not be determined; never report zero assigned roles from missing information.

When invoked after zero-workspace setup validation, begin with `AIDP validation succeeded but returned 0 workspaces.` Return the result to setup for the continuation question. Run this diagnostic at most once for the same profile, user, instance, and endpoint during the session unless the user asks to refresh it.

## Response style

Default to the shortest response that answers the request. The user wants the result, not the process.

- Lead with the result. For a read operation, the table or value is the first thing in the response; no preamble describing what was run.
- Show the fields the user asked for plus the resource name, key, and state. Omit creator, timestamps, sizing, versions, and nested resources unless the user asked for them or an error makes them relevant. Offer them in one line instead, for example `Say the word for sizing and creation details.`
- Do not narrate a command before running it, name the reference files consulted, explain flag choices, or restate a command that succeeded.
- Follow installed `--help` silently. Never report that it disagrees with the bundled reference.
- Limit explanation on a success path to one sentence, and only when the user must act on it.
- When a read-only operation automatically reused a profile that `aidp-setup-local` confirmed valid—whether restored from context or found during assisted validation—add one short final note naming the OCI profile and authentication mode used. Do not call it prevalidated; live validation belongs to `aidp-setup-local`.
- Failures are the exception: on an error, give the status code, the single most likely cause, and the one action or question that resolves it. Keep that explanation, it is what unblocks the user. State the cause in terms of the request that failed, never in terms of an environment category.

### Automatic context persistence

For each new AIDP instance OCID in the session, save the validated target through setup's context helper after its first successful HTTP 2xx response, whether from workspace validation or a direct operation. If the name is known, save it with the target; otherwise fetch the name once with setup's bounded helper, then save. Authentication retains its existing separate save rule. After a later successful AIDP operation, call `aidp_context.py` only when a validated value changed or became newly available; do not rewrite unchanged values merely to refresh timestamps. Record the instance you used when it is not already first in `recentlyUsedAIDP`, so the list stays ordered by last use; skip that write when it is already first. Do not initiate another name lookup when setup already attempted one for the same AIDP instance OCID, even when that attempt failed or the endpoint changed. Only a different AIDP instance OCID permits another lookup during the session. Do not ask a persistence question or record user identity. A name-lookup or context-helper failure is nonfatal and must not change the successful operation result.

## Confirmation and safety

The user's direct request authorizes a straightforward requested operation, but ask for an explicit confirmation immediately before an operation that can delete or purge data, change permissions or credentials, create or provision chargeable resources, alter lifecycle or availability, overwrite local files, or change OCI authentication, profile, endpoint, or region settings.

For a confirmation, state the exact command intent, target resource key or OCID, and important impact. Do not perform such an operation based only on a display name when a stable identifier is available.

## Errors

- On a CLI validation error, inspect the relevant live help and request body before retrying. For protected requests, inspect only the unresolved template; never inspect the temporary resolved copy or source secret files.
- If a read-only AIDP command still fails with DNS resolution, connection timeout, or connection refusal inside a restricted execution environment, including when network access was not requested up front, treat that restriction as a possible cause before diagnosing the user's machine, network, VPN, profile, region, or endpoint. When the host supports scoped execution approval, request narrowly scoped permission and retry the exact command once outside the restricted environment, preserving the confirmed OCID, authentication mode, profile, region, and endpoint. Do not vary flags or repeat the command inside the same restricted environment. If a host-level retry is unavailable or declined, report that connectivity could not be verified from the restricted environment and provide the exact command for the user to run locally. Suggest network, VPN, DNS, or endpoint changes only when the host-level retry also fails. Apply this recovery only to read-only commands; never use it to retry a mutation.
- On HTTP `401 NotAuthenticated`, immediately pause the current operation and follow the authentication checkpoint in [AIDP target selection](../aidp-setup-local/references/aidp-target-selection.md). A prior profile-validation result or successful AIDP request does not bypass this check because a security token can expire during the session. Preserve the exact command, instance, endpoint, and endpoint-candidate position. After authentication becomes valid, retry the failed read-only request once and continue from that point. For a mutation, inspect live state first and obtain any still-required confirmation instead of retrying automatically.
- On HTTP `404` or `NotAuthorizedOrNotFound`, do not immediately assume an endpoint or instance-routing problem:
  - If an AIDP request has already succeeded during this session for the same instance and endpoint and no authentication failure occurred, handle the failure as command-, resource-, or permission-specific.
  - Otherwise, run the standard read-only workspace-list validation once using the same instance, endpoint, profile, and authentication mode.
  - Follow the `404`/`NotAuthorizedOrNotFound` workflow in [AIDP target selection](../aidp-setup-local/references/aidp-target-selection.md) only when that validation request returns the same access failure.
  - Preserve known session values, and do not retry the original command until the failure is classified.
- On an async response, report the operation key and offer to poll it with the installed CLI.
- Do not retry a failed mutation blindly. First inspect the resulting state to avoid duplicate creation or unintended changes.
