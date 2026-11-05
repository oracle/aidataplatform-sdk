---
name: aidp-setup-local
description: Validate prerequisites, install the Python AIDP SDK and CLI, configure OCI authentication, or diagnose local AIDP access. Use for Python, pip, OCI CLI, AIDP CLI, OCI profiles, regions, security tokens, API keys, and setup validation.
---

# AIDP Local Setup

Prepare and validate a local Python AIDP CLI environment. Preserve existing OCI configuration and never display credentials, private keys, or security-token contents.

**User-facing messages:** never mention, quote, cite, or link these skill files or their rules, and never explain a question or action by saying an instruction requires it. When a reference gives an exact prompt, send that prompt as the whole message, word for word, with nothing added before or after it, except status the reference asks to show first, such as the list of missing prerequisites, and setup’s VPN reminder line placed before it. If the user asks why, answer in one plain sentence about the reason itself, such as "Reading your OCID from your token needs your OK."

## Responsibility boundary

This skill owns local prerequisite installation, OCI authentication, AIDP instance selection, region resolution, and one initial read-only workspace-list validation per session target, or the remembered-target fast path for read-only requests on a remembered instance. It does not manage AIDP resources such as clusters, notebooks, workflows, catalogs, or workspaces after setup; route those requests to `aidp-cli` only after initial validation and any required zero-workspace decision are complete.

For a request that only shows, forgets, or clears remembered AIDP context, run the matching `scripts/aidp_context.py` command from [the context command reference](references/context-cli.md) directly; skip prerequisite checks, authentication, and AIDP validation.

## Interaction rules

- Inspect before changing anything.
- Write every command out in full. Never store a command, executable, or options in a shell variable and expand it, such as `A="aidp ..."; $A workspace list`: zsh does not split an unquoted variable into words, so the command fails, and the variable also hides what runs from permission prompts.
- The AIDP CLI reads the environment variable `AIDP_CLI_STRICT_URL_ENCODING`. Always have it set to `true` for every AIDP API command, including the workspace-list validation, and pass path arguments raw, never pre-encoded. How to set it depends on the OS and shell; the bash examples below prefix the command with `AIDP_CLI_STRICT_URL_ENCODING=true`.
- Run plugin helpers only with the commands documented in these skills and their references. Do not list script folders or run a helper with `--help` to work out how to call it; the documented usage is complete. If a documented invocation fails validation, fix the arguments from the documentation instead of exploring.
- Finish all planned installations and pass final prerequisite checks before asking for an AIDP instance OCID, endpoint, or authentication help. Retain details the user volunteers without asking for them again; do not collect setup choices while an installer is running.
- Only after all planned installations, upgrades, and download recovery finish and final prerequisite checks pass, include this informational line in the next message that asks the user something, such as the AIDP instance choice, OCID, or authentication question: "If your company requires VPN for AIDP access, make sure you’re connected." Put it on its own line, directly before the question. If the request needs no further question, include it in the first user-visible message and continue with the request. Never send it as a message of its own, end the turn for it, or ask for VPN confirmation. Do not give it during package lookup, downloads, installation, or recovery.
- Keep responses short. Report status and the next required decision, not the reasoning behind it. Do not narrate commands before running them or restate a command that succeeded. On an error, give the status code, the most likely cause, and the one action that resolves it.
- Be helpful, not only diagnostic. Whenever you report a problem, such as a missing prerequisite, a version mismatch, or an outdated package, offer in the same message the specific action you can take to fix it, show the command, and ask whether the user wants you to do it.
- Request network access up front in a network-restricted environment. When the host's environment or sandbox policy says network access is restricted or disabled, do not run a network-dependent command inside the restriction first and wait for it to fail. On its first run, request the host's narrowly scoped approval to run it with network access: AIDP CLI commands, OCI CLI commands, the instance-name and security-token helpers, and the folder-transfer helper (including its CLI calls and Object Storage PUT/GET). The prerequisite script needs the network only when the latest-version check is due, as described in its section; request approval only for that run. Scope each request to that command, so a host's "always allow" option covers only that command, never all commands. When the environment does not say whether network is restricted, run commands normally and rely on the failure-recovery rules below. If the user declines, run the command inside the restriction and accept the result. For the prerequisite script, run it with `--skip-latest` instead, so a lookup that cannot reach the index does not wait for its timeout; the latest version is then reported as unknown, and the check time is not recorded. Network approval never replaces the confirmation required for a mutation.
- Group related missing values into one prompt instead of asking for them one at a time. Do not request values that the user already supplied.
- Do not infer or describe an environment category from its OCID resource type or endpoint hostname. Preserve the exact selected AIDP instance OCID as immutable session state. An endpoint URL is routing input only: never replace the selected instance OCID with an OCID or other identifier found in its path, query, fragment, or response.
- After validating all prerequisites, summarize their status before asking the user to install anything.
- Keep the prerequisite summary focused on the version checks and whether each command works. Always report the AIDP CLI and Python client version match and the latest-version result from the prerequisite check. Do not surface other pip dependency-resolver warnings unless an observed OCI or AIDP command failure makes them actionable.
- For missing prerequisites, ask once whether the user will install them or wants the agent to install them. A response such as `help install`, `install them`, or equivalent authorizes agent-managed installation of every missing prerequisite listed in that summary. Do not ask again before each package or command.
- When a required installation is declined, explain that setup cannot continue and stop.
- Do not use `sudo`, install a package manager, edit shell startup files, or replace an existing OCI configuration unless the user separately approves that action.
- Run final prerequisite verification once after all planned installations/upgrades finish; run earlier checks only when needed to bootstrap the remaining installation commands.
- Treat a remembered non-null `configFilePath` as part of its authentication selection. If the path exists and is readable and `OCI_CLI_CONFIG_FILE` is unset, apply it as a scoped `OCI_CLI_CONFIG_FILE` value to every `aidp`, `oci`, identity-helper, profile-validation-helper, and name-resolution-helper invocation that uses that selection; do not export it globally. If `OCI_CLI_CONFIG_FILE` is already set to the same path, keep it. If it is set to a different path, or the remembered path is missing or unreadable, do not fall back to `~/.oci/config` under the remembered profile name; treat that remembered authentication selection as unusable and enter the regular authentication flow. When remembered `configFilePath` is null, respect an existing `OCI_CLI_CONFIG_FILE`; otherwise use the normal OCI default config.
- Authentication is session state. Retain the selected authentication mode and profile after they are configured, and reuse them for later AIDP operations. For `security_token`, also retain the validated target region and tenancy name when available. A pending read-only AIDP resource request authorizes direct use of a retained or remembered authentication selection without a separate profile-validation call: use the workspace-list request, or the first request on the remembered-target fast path, as the live check, do not ask whether to use the profile, and let `aidp-cli` identify the profile and authentication mode in the final result. Validate authentication before a mutation. Do not repeat profile-reuse validation or confirmation during the same session when that profile is already known to work for that target region. Invalidate the retained result when the user changes the profile or target region, explicitly requests fresh authentication, or an authentication-related error shows that the credential no longer works.

## Native Windows execution

On native Windows, read [Windows execution](references/windows.md) before running
setup or resource commands. It defines the PowerShell invocation, executable
paths and temporary-file conventions that override POSIX examples below.

## Remembered context

Use the context helper for every cross-session context read or write (`python <setup_skill_dir>/scripts/aidp_context.py` for agent calls, its `get all` interface inside the prerequisite script), as described in [the context command reference](references/context-cli.md); read it before a new context operation. Never open, parse, create, or edit `~/.config/aidp/context.json` directly.

- The prerequisite script calls the context helper’s `get all` interface internally. Reuse its returned `context` for `pythonCli`, `recentlyUsedAIDP`, `lastUsedAuth`, `endpoints`, and `latestVersionCheck`; do not issue a separate initial context read. A failed read is nonfatal and triggers uncached discovery. Re-read only after a write that the session depends on. Context-only show/forget/clear requests still use the context helper directly and skip prerequisites.
- Treat remembered authentication, endpoints, instances, and names as default guesses that require the live validation defined by this skill. Never persist a user OCID, IAM name, email address, or other resolved user identity; retain identity only for the current session.
- Persist eligible validated connection defaults automatically without asking for consent. A context-helper failure is nonfatal and must not block setup or a pending operation.
- Write a context value only when it is new or differs from the prerequisite script’s returned `context`. Compare `pythonCli` by its CLI and Python interpreter paths; save a newly verified selection with the context helper before AIDP operations, independently of authentication or target validation. Compare before each `set`: `lastUsedAuth` by authentication mode, profile, and config path; a recent instance by instance OCID, region, endpoint, and name, where a newly resolved name for an unnamed entry counts as a change, and so does using an instance that is not already first in `recentlyUsedAIDP`, so the list stays ordered by last use; an endpoint template by whether it is already in its `<realm>:<resource_type>` group. Skip every other unchanged value, including an instance already first in the list, even though the write would only refresh its timestamp; each write can cost a separate permission review.
- When no target was supplied in the current session, read `recentlyUsedAIDP`. If entries exist, show each known name first, followed by that entry's `displayOcid` verbatim and then the full region, in MRU order. Do not independently abbreviate `instanceOcid` or shorten `displayOcid`. The helper preserves the OCID prefix through its embedded region key and shortens only its unique suffix, for example `nik_delta_uuid_DND — ocid1.aidataplatformqa.oc1.phx.…jane5hgq (us-phoenix-1)`. Ask the user to select one or provide another OCID. Mark an entry without a stored name as `Name not resolved` rather than presenting its OCID as though it were the instance name. Resolve that name against the validated endpoint before saving the instance.
- When no authentication was established in the current session, read `lastUsedAuth`. If it exists, use it directly for the first required read-only workspace-list request without the general authentication-choice question. A success establishes working session authentication; a `401 NotAuthenticated` follows the authentication checkpoint. If remembered authentication is absent, use the regular authentication flow.
- Record `lastUsedAuth` after live OCI validation or a successful AIDP workspace-list request establishes that the selection works, subject to the write-only-when-changed rule above.
- For each new AIDP instance OCID supplied or selected in the session, save the target through `aidp_context.py` after its first successful HTTP 2xx response, whether from workspace-list validation or a direct resource operation. Save the exact request OCID, its resolved region and validated endpoint in `recentlyUsedAIDP`, plus a safely generalized endpoint template when applicable. If the name is known, save it with the target; otherwise fetch the name once with the bounded helper, then save. Do not ask another persistence question. Check the save receipt; a save failure is nonfatal. Skip unchanged records and respect explicit user restrictions on persistence.
- Attempt an unknown instance-name lookup before saving and include a successful result verbatim. A failed name lookup does not block target saving or the requested operation; do not repeat the lookup for the same OCID during the session.

## Workflow

### 1. Validate and summarize prerequisites

Run this check once per session, before the first AIDP operation. This applies both when setup is invoked directly and when `aidp-cli` needs a working environment. Reuse the result for the rest of the session. Rerun it only after an installation, upgrade, or pip restore, for the one network-permission rerun, for the one `--check-latest` rerun that obtains a verified command, for the `--aidp` verification of a new installation, or when the user asks.

Run the existing prerequisite script once; it owns the context read, saved-CLI check, bounded nonrecursive Python CLI discovery, and weekly update decision. Never discover executables or run separate version checks outside it.

```bash
# Normal resource request: the script applies the weekly latest-version policy
python3 <skill_dir>/scripts/check_prerequisites.py
# Explicit setup, /aidp:doctor, or a user-requested update check
python3 <skill_dir>/scripts/check_prerequisites.py --check-latest
# User declines lookup network access or requests local-only checks
python3 <skill_dir>/scripts/check_prerequisites.py --skip-latest
```

The script gets context through the helper's `get all` interface. A missing or invalid context, absent saved entry, or unusable saved executable triggers discovery inside the same invocation. A remembered CLI is checked with `--version` only, without Python ownership detection; its saved interpreter supplies package checks. Newly discovered candidates must have a Python interpreter and pass `--version`. Discovery checks direct `aidp` entries in each `PATH` directory first, then `~/.aidp-venv/bin/aidp`, then the selected Python environment's script directories. It deduplicates executable targets, skips non-Python/non-executable candidates without running them, stops at the first working Python CLI, and shares one timeout across fallback discovery. It never scans recursively.

Reuse the returned `context` as the session’s initial context read. When both latest package versions are returned, record `latestVersionCheck` with the context helper, once per successful lookup. If a skipped lookup returns an install/upgrade action without a verified command, rerun once with `--check-latest` to obtain one. Explicit setup and doctor use `--check-latest`; normal requests let the script decide. Network permission rules above still apply: a normal lookup may be due, so request narrowly scoped network access for that invocation; if declined, use `--skip-latest`.

Do not run the individual version commands yourself while the script can run, and do not wrap the script in `timeout` or discard its stderr. It runs its checks in parallel and prints one JSON summary:

- `context` and `context_error`: the helper’s context snapshot, or a nonfatal read-failure summary. Reuse the snapshot for later target and authentication selection.
- `prerequisites.aidp_cli` includes selected absolute `path`, `source`, `validated`, `current_path_aidp`, and `path_adjustment_required` alongside status/version. The interpreter is `aidp_python.path`; the session PATH prefix (one or more directories) is the existing `add_to_path` action’s `path_hint`. Only when `validated` is true, save the working selection with `aidp_context.py set pythonCli --path <prerequisites.aidp_cli.path> --python-path <aidp_python.path>` if it differs from `context.pythonCli`. Do not save a below-minimum/invalid CLI or failed package probe. Do not claim persistence without a successful write receipt. A context write failure does not block current-session use.
- `environment`: operating system, release, and CPU architecture.
- `prerequisites`: `python` (3.9 or later required), `pip`, `oci_cli`, `aidp_cli` (5.1.0 or later required), and `aidp_python_client`, each with `status` (`installed`, `missing`, `invalid`, or `unknown`), `version`, and a `detail` reason when not installed.
- `prerequisites.oci_cli` reports its validated absolute `path` and whether a session PATH adjustment is needed. The checker keeps a working OCI CLI found on PATH; when absent there, it checks beside the selected AIDP executable, its resolved target and the selected Python interpreter, without scanning directories recursively. An installed but off-PATH OCI CLI is reused, not offered for reinstallation. Retain its verified path and apply the returned `add_to_path` prefix on every tool invocation when either CLI needs it.
- `aidp_python`: the interpreter that owns the `aidp` command, and whether it has `pip`. Package versions and upgrade commands use this interpreter, so a CLI installed with pipx or in another environment is not mistaken for a missing one.
- `versions`: `match` (whether `aidp-cli` and `aidp-python-client` versions are identical, or null when either is missing), the `latest` published version of each package from the configured package index, `aidp_cli_update` (`up to date`, `update available`, or `unknown`), and `target_version`, the version both packages should be upgraded to: the latest `aidp-cli` when it is also published for `aidp-python-client`, otherwise the highest version published for both, or null when no such version is verified: the index could not be read, the lookup was skipped, or no version is published for both packages.
- `actions`: fixes, each with its `reasons` and the exact `command`. Use the returned `command_shell`: PowerShell on Windows, a POSIX shell elsewhere. Run commands exactly as returned.
  - `install_aidp_packages` appears when an AIDP package is missing; `upgrade_aidp_packages` appears when both are installed but mismatched or outdated; never both. Their commands install both packages in one pip call pinned to `target_version`, a version verified to exist for both, so pip either installs the matching pair or changes nothing. When no such version is verified, the action has `command: null` and a `blocked` reason: the index could not be read, the lookup was skipped, or the index publishes no version for both packages (`versions.no_shared_release` is true).
  - `install_method` is `pip` for a regular pip install, including `--user` when the existing installation is user-scoped. When the interpreter that owns `aidp` has no pip, the script queries the index with the Python running the script instead (`versions.index_python`), and the `pip` command first restores pip with `ensurepip`.
  - `install_method` is `virtualenv` when no Python CLI was found, whenever the interpreter is externally managed (PEP 668) and rejects pip installs, including when `aidp` is already installed there, and when the interpreter that owns `aidp` has neither pip nor `ensurepip`, in which case the environment is built from the Python running the script. The command creates `~/.aidp-venv` and installs both packages there; `path_hint` names the folder that must be first on `PATH`, `verify_aidp` is the new CLI's full path, and `alternative_command` offers pipx only when pipx is already installed.
  - `in_place_command` appears when `aidp` is already installed in an externally managed interpreter; it upgrades it there with `--break-system-packages`. Offer it only as an explicit alternative, with one sentence warning that it modifies a Python managed by the operating system or Homebrew, and run it only when the user chooses it.
  - `restore_pip` appears when no Python with pip is available to run a lookup that was not skipped. It restores pip with `ensurepip` without touching any AIDP package, so a rerun can verify a matching release.
  - `add_to_path` is a session-scoped execution adjustment, not a shell-configuration change. It appears only when the selected CLI is not the executable current `PATH` resolves; comparison resolves symlinks. Use its `path_hint` as described below. No approval question or shell startup edit is needed.
- `ok` and `blocking`: whether every required prerequisite is installed, and which ones are not. The script exits `0` when `ok` is true and `1` otherwise; mismatches or available updates alone do not make it fail, but an invalid or below-minimum AIDP CLI version or an unknown required prerequisite blocks setup. If the Python package probe fails, report validation as incomplete with `prerequisites.aidp_python_client.detail` and stop the pending AIDP operation. Do not report success or infer that packages are missing and offer installation from a failed probe. An unknown latest-published version remains nonblocking.

If the script cannot start because no Python 3 interpreter is available, try `python` when `python3` is not found, and use it only when `python --version` reports Python 3. If neither starts the script, bootstrap the summary without Python: report Python and pip as missing, run `oci --version` and `aidp --version` directly for their rows, mark the AIDP Python client and the version results as unknown, and continue with the installation question below. Run the script once Python is installed.

The minimum check compares only the first three numeric components (`major.minor.patch`). Extra build numbers and suffixes do not affect eligibility: `5.1.0`, `5.1.0.36.45595`, and `5.1.0rc1` all satisfy the `5.1.0` minimum. SDK/CLI matching still uses the full version, and upgrade selection compares all numeric components.

Normal use needs no CLI-path argument. Retain `--aidp <path>` only for explicit selection or fresh-install verification; this is a new candidate and must pass Python ownership detection. `--python <interpreter>` selects the fallback Python environment for discovery and installation. If the package index cannot be reached, the latest versions are null and the update status is `unknown`; this alone does not invalidate an installed CLI. Each lookup waits at most 20 seconds. When the restriction was not known up front and `latest_detail` reports a timeout or connection failure in a restricted execution environment that may block network access, request narrowly scoped network permission once, when the host supports it, and rerun the script once outside the restriction. If host network access is unavailable or declined, keep the `unknown` result and do not diagnose the user’s VPN from a sandbox failure. If the lookup still times out with host network access, follow [package download timeouts](references/troubleshooting.md#package-download-timeouts) and wait for the user’s choice before another retry. Do not keep probing or retrying automatically. Pass `--skip-latest` when the latest-version check is not due, when the user asks to avoid network access, or when the user declines network access for the script in a restricted environment.

When setup is invoked directly, or from `/aidp:doctor`, present the result in this shape. Never describe the operating system or architecture as a prerequisite. Do not start installation or upgrade while presenting this status.

```text
Environment:
- Operating system: <operating_system>
- Architecture: <architecture>

Prerequisites:
- Python <version>: <status>
- pip <version>: <status>
- OCI CLI <version>: <status>
- AIDP CLI <version>: <status>
- AIDP Python client <version>: <status>

Versions:
- AIDP CLI and Python client: <matching | mismatch: CLI <cli_version>, Python client <client_version>>
- AIDP CLI latest published: <latest_version> (<up to date | update available | unknown>)
```

When `aidp-cli` triggers the check for a resource request and `ok` is true with no actions, include the VPN reminder above, then continue with the request. Do not show the summary or ask the `Installation is complete` question in that path. Show only problems, each with its offer to fix it.

#### Upgrade prompt: stop and wait

When an `upgrade_aidp_packages` or `install_aidp_packages` action has `command: null`, there is nothing safe to run yet. Never build an install or upgrade command yourself in that case. If `actions` also contains `restore_pip`, offer to run its command first, because no matching release can be verified without pip; after the user agrees and it succeeds, rerun the script. If the index could not be read, first apply the network-permission rerun described above; a rerun that verifies a version returns a command. Otherwise report its `reasons` and `blocked` text in a user-visible reply and do not ask the upgrade question or stop. Continue with the pending request using the installed CLI when it works; when a package is missing or `aidp_cli` is below its required version, setup cannot complete until a matching release can be verified.

When `actions` contains `upgrade_aidp_packages` with a command, this is a stopping point. Do not run the pending AIDP request, including a read-only one, until the user has answered.

1. In a user-visible reply, report its `reasons`, show its `command`, and ask:

   ```text
   Would you like me to upgrade aidp-cli and aidp-python-client to <target_version>?
   ```

   For `install_method` `virtualenv`, explain briefly that the packages go into a dedicated environment to keep installations separate. Offer `alternative_command` only when present.
2. End the turn and wait for the answer. A progress or status update that mentions the problem and then continues does not count as asking, because those updates may be collapsed or skimmed. Use the host's question tool when one is available.
3. Keep this prompt about the upgrade; defer instance, endpoint, and authentication questions until all planned installations and final prerequisite checks finish.
4. If the user declines, keep the reported status and continue with the pending request without asking again this session. If the user agrees, run that exact command, rerun the script, report the updated versions, and then continue with the pending request. For `install_method` `virtualenv`, rerun the script with `--aidp <verify_aidp>` to verify the new CLI, then save its changed selection and apply its session command environment. This explicit verification overrides a still-working old context path.

The mismatch or update itself does not make the AIDP CLI unusable; it only requires this question before continuing.


If anything is missing or invalid, list exactly what is required and ask:

```text
Would you like to install the missing prerequisites yourself, or would you like me to install them for you?
```

- If the user chooses self-installation, provide relevant guidance from [references/installation.md](references/installation.md), wait for confirmation that installation is complete, then validate every missing item again. Do not proceed while a required prerequisite still fails.
- If the user asks the agent to install them, treat that response as approval for all missing prerequisites already listed and begin installation without another conversational confirmation. Briefly state what is being installed, but do not ask `May I run these commands?` or pause between packages. Then follow [references/installation.md](references/installation.md):
  - Install Python 3.9 or later and pip with an established installer for the detected operating system.
  - For Windows OCI CLI installation, follow the virtual-environment command in [installation guidance](references/installation.md#windows-oci-cli-installation). Elsewhere use the active Python environment or official OCI installer; omit `--user` inside a virtual environment.
  - Install the AIDP Python client and CLI together in a dedicated virtual environment when no working Python CLI exists; keep any TypeScript installation intact. Use the configured Python package index. When the prerequisite script returned `install_aidp_packages`, run its `command`; this install question replaces the upgrade prompt for that action. Otherwise follow [references/installation.md](references/installation.md).
- Follow [installation process handling](references/installation.md#installation-process): retain and poll the original installer session to completion before the next package or verification step; avoid repeated CPU/process checks. For failed downloads, stalled installers, or Windows path/script errors, use [setup troubleshooting](references/troubleshooting.md), also used by `/aidp:doctor`. Normal setup may recover directly without asking the user to run doctor.
- Rerun `scripts/check_prerequisites.py` once after all planned installations/upgrades finish (use `--aidp <verify_aidp>` when the action supplies it, so a working old saved CLI cannot override the new installation), save the verified selection if changed, and present the updated summary. If a required check still fails, apply the matching [troubleshooting](references/troubleshooting.md) fix once and verify again; stop with corrective guidance only if it still fails.

Ask again only if installation requires a materially different action that was not covered by the summary, such as installing a package manager, using elevated privileges, replacing existing configuration, or modifying files outside the active environment. System- or tool-generated permission prompts may still appear and are separate from the skill's conversational approval.

Do not query GitHub releases or download release archives during setup. Use the configured Python package index for latest-version checks and upgrades as described in [references/installation.md](references/installation.md). Describe an older installed version as having an update available, never as unsupported; only report an explicit minimum-version requirement from an authoritative AIDP source.

### Session command environment

Retain `prerequisites.aidp_cli` and `aidp_python.path` for the session. If neither `prerequisites.aidp_cli.path_adjustment_required` nor `prerequisites.oci_cli.path_adjustment_required` is true, use the existing `PATH` without adding a prefix. Otherwise prepend the `add_to_path` action’s `path_hint` for every AIDP or OCI command, help/discovery call, protected wrapper, transfer helper, and retry; child processes must inherit the same environment. Apply the scoped environment on every tool invocation because an earlier export may not persist. Use a safely quoted prefix such as `env PATH='<selected_bin>':"$PATH" AIDP_CLI_STRICT_URL_ENCODING=true aidp ...`; helper calls receive the same prefix. Never modify shell startup files as part of this flow. Preserve the selected interpreter path for package operations and documentation generation; do not assume changing `PATH` selects the correct `python3`. Preserve the originally validated OCI CLI path when a prepended directory would shadow it. Rerun prerequisites only after the existing installation/upgrade/repair triggers or an explicit user request, not before each command.


### 2. Choose an AIDP instance for validation

Only after all planned installations, upgrades, and download recovery finish, final prerequisite checks pass, and any upgrade decision is complete, ask:

```text
Prerequisites are ready.
If your company requires VPN for AIDP access, make sure you’re connected.
Would you like to validate it with any AIDP instance?
```

The VPN line is informational and needs no separate reply. When a target and validation request are already supplied, do not ask for them again; include the reminder in the next message and continue with validation.

- If the user declines, report the installed versions and conclude the flow; do not ask about authentication or an AIDP instance.
- If the user agrees and no AIDP instance was supplied, first use the remembered-context selection above. Ask for an existing AIDP instance OCID only when the user chooses a different instance or no remembered instance is available.
- Validate that the OCID resembles `ocid1.<resource-type>.<realm>.<region>.<unique-id>`. Resolve its embedded region key case-insensitively through [the bundled region-key cache](references/oci-region-keys.json), show the resolved full region, and retain it for authentication and AIDP validation. Do not ask for the region again.
- The bundled cache is refreshed only as part of plugin maintenance. If the cache does not contain the OCID's region key, ask the user to provide the full OCI region identifier, for example `us-phoenix-1`; do not guess.
- Extract the OCID resource type before authentication. If it is not exactly `aidataplatform` and no endpoint decision is retained for that instance, follow the remembered-endpoint discovery in [AIDP target selection](references/aidp-target-selection.md). When it finds no remembered candidate, stop and ask its regular endpoint-selection question. When candidates exist, use that reference's fast read-only validation path and try them sequentially.
- Before authentication or validation, follow [AIDP target selection](references/aidp-target-selection.md). It owns endpoint choice, normalization, OCID-region consistency, confirmation, and session reuse.
- Use the exact selected AIDP instance OCID for the name lookup, every AIDP `--instance-id`, and every `aidp_context.py set recentlyUsedAIDP --instance-ocid` call. If those values differ, do not write context; retain the validated command target and correct the pending context record.
- After the first successful HTTP 2xx response from workspace validation or a direct operation, use the known instance name or fetch it once according to that reference, then save the validated target automatically.
- If the user does not have an instance, recommend creating one in the OCI Console; do not create it on their behalf. Provide the generic [OCI Console sign-in link](https://cloud.oracle.com/) and the official [getting-started guide](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/get-started-oracle-ai-data-platform.html), then give these short steps:
  1. Sign in through the OCI Console link, then open **Analytics & AI** > **AI Data Platform Workbenches**.
  2. Select the target compartment and choose **Create AI Data Platform Workbench**.
  3. Enter the requested instance details, review the configuration, and create it.
  4. Wait until the instance is active, then copy its OCID and provide it for CLI validation.
  Mention that creating an instance requires the appropriate IAM permission, and pause until the user supplies an active instance OCID.

### 3. Configure authentication

This skill owns OCI authentication for AIDP operations. If the session already has an authentication mode and profile that the user accepted after successful validation in this workflow, reuse them and proceed to AIDP validation without asking the user to configure authentication again.

When no remembered authentication is available or reusable, do not start authentication automatically. Ask:

```text
Would you like to configure OCI authentication yourself, or would you like me to help you authenticate?
```

Use the CLI authentication values `security_token` (recommended) and `api_key`. If the user says `auth_key`, clarify that the valid CLI value is `api_key`.

When a pending read-only AIDP request has a retained session authentication selection or a remembered `lastUsedAuth`, use the workspace-list request, or the first request on the remembered-target fast path, as the live authentication and endpoint check instead of running the reuse helper first. A successful response establishes working authentication state for that profile and target region. A `401 NotAuthenticated` triggers the authentication checkpoint, which runs the helper then. This removes one full helper round trip from the common successful path. If no authentication selection is available, complete the normal authentication choice before any AIDP request. Run the helper before the request when the operation can mutate state or the user explicitly asked to verify or change authentication. When the helper does run, follow [the OCI security-token profile reuse validation](references/oci-profile-validation.md) at most once per profile and target region during the session. Use its bundled helper as one scoped, read-only invocation; do not reproduce its OCI calls as shell pipelines. If the profile was already validated and accepted, or has since completed a successful AIDP request with that target region, treat it as working session state: skip both the reuse checks and the confirmation prompt. Repeat the checks after that state is invalidated by a profile or target-region change, an explicit request for fresh authentication, or an authentication-related failure. The once-per-session limit never applies after a later `401 NotAuthenticated`: invalidate the retained result and rerun the helper immediately. Do not use this reuse-validation workflow for `api_key` authentication; for a remembered `api_key` selection, the successful workspace-list request is the fast-path validation and its `401` follows the API-key checkpoint.

When this validation confirms that a previously used security token is expired or invalid, do not merely tell the user to refresh it. Say which profile needs attention and ask one clear question:

```text
The OCI security-token session for profile <profile_name> is <expired_or_invalid>. Would you like to refresh it yourself, or would you like me to help you refresh it?
```

If the user asks for help, enter the assisted security-token flow directly; do not repeat the general authentication-choice question. If the user chooses to refresh it, provide the exact authentication command for the retained profile and OCID-resolved region, wait for completion, and validate it before retrying the AIDP request.

Retain the selected authentication mode and profile as session state. Record the selection after either live OCI validation or a successful AIDP workspace-list request establishes that it works. A persistence failure is nonfatal and must not repeat authentication or the AIDP request.

#### Customer configures authentication

1. Wait for the customer to complete authentication or profile configuration.
2. Ask which authentication method they configured—`security_token` or `api_key`—and which profile name they used. Offer `DEFAULT` only as a convenience; do not assume it was used.
3. For a pending read-only AIDP resource request using `security_token`, retain the supplied profile and proceed directly to workspace-list validation without running the profile helper or showing a reuse question; `aidp-cli` reports what it used with the final result. For a mutation, explicit authentication check, or standalone authentication setup, run the profile reuse validation first. Show the tenancy name and ask whether to continue, or omit unavailable details and ask whether to continue with the active profile. If that validation fails, wait for the customer to repair or replace the profile; do not authenticate on their behalf unless they explicitly change to the assisted flow.
4. For `api_key`, do not run the security-token reuse validation. Retain the exact profile the customer supplied and proceed to AIDP validation; validate it only if the AIDP request returns an authentication-related error.

#### Agent helps with authentication

Only enter this flow after the user explicitly asks for help. Select `security_token` with the `DEFAULT` profile without asking. Never ask the user which authentication method or which OCI profile to use, and never present the available profiles for them to pick from, even when several exist or some have expired tokens. Use a different method or profile only when the user explicitly requests it.

For a pending read-only AIDP resource request, retain the selected `DEFAULT` profile and proceed directly to workspace-list validation without running the profile helper or showing a reuse question; `aidp-cli` reports the profile and authentication mode with the final result. If that request returns `401 NotAuthenticated`, follow the authentication checkpoint and continue into the already authorized assisted flow when the profile is invalid or expired. For a mutation or standalone authentication setup, run profile reuse validation before starting browser authentication. When it is valid, show its tenancy name and ask whether to continue, or omit unavailable details and ask whether to continue with the active profile. If the profile is missing, invalid, expired, or confirmed active in a different region, explain the result and continue to the security-token authentication steps because the user's request for assisted authentication already authorized that flow.

#### Security token

1. Use the resolved region from the AIDP instance OCID; do not request the region again. Tell the user:

   ```text
   I’ll use OCI security-token authentication with the DEFAULT profile and region <resolved_region> from the AIDP instance OCID.

   I will run:
   oci session authenticate --region <resolved_region> --profile-name DEFAULT
   ```

   OCI sign-in lets the user select their tenancy in the browser, so do not ask for a tenancy name.
2. Use `DEFAULT` as the OCI profile name unless the user explicitly requested another profile.
3. Select the OCI config and token locations:
   - If `OCI_CLI_CONFIG_FILE` is set, use it as `<config_file>` and use a `sessions` directory beside it as `<token_directory>`.
   - Otherwise use the normal OCI config and session locations.
4. Start browser-based authentication:
   - Explain that authentication opens a browser or prints a login link.
   - Check whether TCP port `8181` is already in use. If the authentication process started by this flow owns it, keep that process running and continue reading its terminal output; do not start a second authentication attempt. Never terminate an unrelated process without user approval.
   - Ensure the parent directories for `<config_file>` and `<token_directory>` exist. Do not create an empty config file before authentication.
   - Run the following command in a foreground pseudo-terminal that provides a persistent session handle. Keep polling that same session while it waits for the browser callback; do not replace it with another process because output is temporarily idle.

   ```bash
     env OCI_CLI_CONFIG_FILE="<config_file>" oci session authenticate \
     --region <resolved_region> \
     --profile-name <profile_name> \
     --config-location <config_file> \
     --token-location <token_directory>
   ```

   Never add `--no-browser` in this assisted security-token flow. In a fresh environment it requires another authentication method, can invoke API-key bootstrap, and can produce a misleading missing-user-OCID error.
5. Watch the running process. When it prints `You can also open the following URL in a web browser window to continue:`, immediately send the complete clickable URL while keeping the process alive. If an attempt is restarted, clearly identify the new URL as the only one to use.
   - Keep the active task and the same pseudo-terminal session open while authentication waits for the browser callback. Do not finish the response or release the authentication process merely because its output is temporarily idle. If the user must act after an interruption or a progress message may no longer be visible, repeat the complete URL for the currently running attempt. Never repeat or recommend a URL from an earlier attempt.
6. Ask the user to complete sign-in and MFA. Browser success alone is not CLI completion: continue polling the same process until it exits successfully and prints `Config written to: <config_file>`.
7. If the browser reports success but the process exits early, its output is lost, or completion is otherwise uncertain, do not request another login yet. First run this bounded local check against the same config:

   ```bash
   env OCI_CLI_CONFIG_FILE="<config_file>" \
     oci session validate --profile <profile_name> --auth security_token
   ```

   - If valid, retain the profile and continue to AIDP validation without another login.
   - If invalid and the original process is still running, keep polling it. Ask before stopping that exact process if it is genuinely stuck.
   - If invalid after the process has exited, report its final error or exit status, verify port `8181` is free, and restart the same browser command at most once. Relay its fresh URL and tell the user not to reuse an older link.
8. Only after that retry also fails may the user be asked to run authentication locally. Provide the exact command above, including the selected config and token paths. After the user says it completed, run the same `oci session validate` check before any AIDP request.
9. Proceed to the AIDP workspace-list command after confirmed CLI success or successful session validation. Otherwise stop with the actual authentication error. Do not switch to `--no-browser` or API-key authentication.

#### API key

Explain that API-key configuration requires the customer to manage their private key and OCI profile. Provide the OCI CLI setup guidance, but do not create, upload, overwrite, or expose keys. Wait for the user to confirm that configuration is complete and provide the profile name. Reuse it for the AIDP request and validate it only if that request returns an authentication-related error.

### 4. Validate AIDP access

Run the read-only workspace-list command once after the session target and authentication selection are established, except on the remembered-target fast path below.

**Remembered-target fast path.** A `recentlyUsedAIDP` entry exists only because that instance and endpoint passed this validation in an earlier session. Skip the separate validation when all of these hold:

- the user selected that remembered instance, or supplied an OCID that matches it;
- its remembered endpoint is used unchanged;
- the authentication selection is the remembered `lastUsedAuth`, or one that already worked in this session, rather than a newly chosen profile or mode;
- the pending request is read-only.

Then run the requested read directly. If it needs a workspace key, its workspace-list call is the first real step, not an extra check. The first successful AIDP response counts as this validation for the session, including the instance-name lookup for an unnamed entry and the write-only-when-changed context rule. If that response is a workspace list with zero workspaces, apply the zero-workspace handling below. If the first request fails, fall back to the full flow before retrying: a `401 NotAuthenticated` follows the authentication checkpoint; a `404`, `NotAuthorizedOrNotFound`, DNS error, connection error, or timeout runs this workspace-list validation once and follows its normal classification. Keep the separate validation for mutations, for a new or changed instance, endpoint, or authentication selection, and when setup or `/aidp:doctor` runs validation as its purpose. On the optimistic read path, this request itself establishes whether the authentication works. Retain its result and do not repeat this validation for later operations against the same instance, endpoint, authentication mode, and profile. A change to any of those values establishes a new session target and requires one new validation.

Use the region or endpoint retained by [AIDP target selection](references/aidp-target-selection.md). For the standard regional route:

```bash
AIDP_CLI_STRICT_URL_ENCODING=true aidp \
  --auth <security_token_or_api_key> \
  --profile <profile_name> \
  --region <region> \
  --instance-id <aidp_instance_ocid> \
  workspace list
```

For an explicit endpoint, replace `--region <region>` with `--endpoint <normalized_endpoint>`; never pass both. The OCID-resolved region still governs OCI authentication and profile validation.

Setup is successful when the command returns a valid workspace list containing zero or more items. Do not treat an empty list as a connectivity or authentication failure. When it contains one or more workspaces, report only that validation passed and the number returned. When it contains zero workspaces, route directly to the read-only role-assignment check in `aidp-cli` with the retained session state. If identity is needed, present its compact user-OCID-or-local-helper prompt immediately; do not first ask whether the user wants roles checked. After the diagnostic reports every discoverable role as `Assigned` or `Not assigned`, or explains why assignment status is unavailable, name any pending AIDP operation and ask whether the user still wants to proceed despite zero visible workspaces. Do not continue that operation until the user answers. Never infer that the instance has no clusters or other resources solely from an empty workspace list. Keep the versions, profile, authentication mode, resolved region, and instance OCID as session state; state them only when validation fails or the user asks.

Apply the first-success target-save rule above before returning the validation result. Store an endpoint template only when the full resolved region can safely be replaced by `{region}` in the hostname. Never save a target from a failed response or substitute an OCID embedded in an endpoint URL.

Request network access for this validation up front when the environment is known to restrict it, as described in the interaction rules. If it still fails with DNS resolution, connection timeout, or connection refusal inside a restricted execution environment, treat that restriction as a possible cause before diagnosing the user's machine, network, VPN, profile, region, or endpoint. When the host supports scoped execution approval, request narrowly scoped permission and retry the exact validation command once outside the restricted environment with the same confirmed settings. Do not repeat variants inside the same restricted environment. If a host-level retry is unavailable or declined, report that connectivity could not be verified from the restricted environment and provide the exact command for the user to run locally. Suggest network, VPN, DNS, or endpoint changes only when the host-level retry also fails.

For the first HTTP `401`, HTTP `404`, or `NotAuthorizedOrNotFound`, follow the failure workflow in [AIDP target selection](references/aidp-target-selection.md). It covers security-token validation, one-time endpoint disclosure, and a single alternative-endpoint retry.

For the expected conversation, read [references/setup-example.md](references/setup-example.md).
