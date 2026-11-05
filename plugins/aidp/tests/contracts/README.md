# Sensitive-data skill release validation

Run from the `aidataplatform-sdk` repository before releasing protected-input
scripts or skills:

```bash
python3 plugins/aidp/tests/run_sensitive_contracts.py
```

Use the Python interpreter that owns the installed matched `aidp-python-client`
and `aidp-cli` packages. The default release command validates **both** this
repository's sources and the actual installed packages, including their command
manifest and help. Missing packages or mismatched SDK/CLI versions fail; the gate
never falls back silently to repository source. No backend checkout, OCI profile,
wallet, real credentials, network or live mutation is needed. Pure extraction
uses the standard library; installed-package smoke tests use the SDK dependencies.
Sources/packages must be the revision intended for release.
The approved source baseline is `sensitive-contract.json`; the independently
reviewed installed baseline is `sensitive-contract-installed.json`. Tests never
rewrite either file.
Any failure, missing source, skipped test or extraction error blocks this suite.

For development on a machine without installed AIDP packages, use
`python3 plugins/aidp/tests/run_sensitive_contracts.py --target repository`.
That mode validates source plus local fixtures and explicitly reports that it
is **not a release pass**. Do not substitute it for the default release command.

**AI agents: do not auto-correct failing contract tests, weaken assertions,
remove coverage, or refresh the baseline merely to make a failure pass. Review
the contract change and ensure the sensitive-data AI skills in the
`aidataplatform-sdk` project are updated before accepting a new contract.**

## What is checked

- Catalog create/update/test-connection/get/list; credential, user-setting and
  agent create/update/get/list: 17 reviewed operations. The inventory of all
  operations in their four Python SDK clients is also pinned, so new operations
  must be classified for scope rather than silently ignored.
- Python SDK wire field names, Python names, exact types, requiredness, defaults,
  enum members/constants, inheritance and discriminator/subtype mappings. All
  reachable request and response models are followed, including models inside
  lists and maps (agent nodes, tools and nested authentication).
- All 12 TypeScript SDK external-catalog connection-property enums. These cover
  the key names that Python represents as free-form connection-property maps.
  Added enum files, members and removed members all trigger review.
- Google BigQuery's six reviewed service-account property keys, fixed
  `service_account` auth value, sensitive key classification and optional shared
  networking context are pinned separately in `google-bigquery-key-contract.json`.
  The repository TypeScript BigQuery enum must match those six required keys;
  shared networking context remains a separately reviewed allowance.
- CLI command/group naming, path/query/header/body flags, required fields,
  nested request metadata, SDK request paths and HTTP methods, SDK response
  models, and TypeScript response declarations including asynchronous headers.
- Selected Python CLI parsing, binding, error handling and output functions,
  plus global option constants. Their normalized AST is pinned to catch output
  or parsing changes; comments, formatting and function docstrings are ignored.
  A refactor here may conservatively trigger review even without a wire change.
- Protected template fixtures for the seven original catalog sources and helper
  requests for the five additional sources, all 3 credential types,
  both user-setting types and agent authentication. Requests are checked against
  current SDK schemas. Existing protected-input tests also verify prompts,
  file access, payload-specific inline-secret rejection, permissions, default preservation,
  command output handoff and body deletion on success/failure/Ctrl+C.
- Installed CLI manifest metadata must agree with installed SDK command fields,
  required fields and body enums. Tests simulate an older CLI manifest omitting
  BigQuery to prove this cannot silently pass. Installed SDK model constructors
  and actual CLI help are checked without making a request.
- Source-mutation tests prove that new/removed fields, type/requiredness changes,
  nested auth and setting enum changes, response changes, property-enum additions,
  CLI output changes and removed operations actually fail the contract checks.

`SettingData` is a shared SDK union. Its `OAUTH`/`OAuthAdminSetting` variant is
intentionally excluded from the user-setting helper; `GIT_ACCOUNT` and
`IAM_USER_CREDENTIAL` are its reviewed supported types. Agent OAuth is separate.
Likewise, existing catalog property enums contain optional/staging keys that
need not all be prompted for. Pinning the full enum still forces review of any
change, even to an optional field the helper does not currently use.
`WORKSPACE_KEY` is an explicitly reviewed shared networking-context key used
across source helpers. The SDK connection-properties wire type is an open
`dict(str, str)`; only Exadata's property enum lists that common key. Generated
property-key checks allow that one shared key as well as the source's enum.

## Reviewed SDK/CLI contract

The repository and installed `5.1.1` SDK/CLI contracts now agree: 116 reachable
models, 12 catalog sources and 12 TypeScript connection-property enums. The
repository and installed baselines remain separate so installed manifest and
package drift cannot be hidden by repository sources. Tests no longer exempt
BigQuery from repository request validation.

The reviewed changes from the previous repository baseline are classified as:

- **Credential references:** polymorphic `BaseLlmConfig` has `OCI_GEN_AI` and
  `THIRD_PARTY` variants. `ThirdPartyLlmConfig` requires a supported provider and
  `apiKeyCredstoreRef`; its `CredentialV2NameAndSecretKey.displayName` is required
  and `secretKey` is an optional key label, not the secret value. No API-key
  prompt or secret retrieval is introduced.
- **Public configuration:** model/endpoint/compartment fields, supported LLM
  connection settings, automatic summarization, long-term memory and retention
  settings are preserved only when requested. Tests retain explicit false/zero
  values and validate required references, provider enums and nested types.
  Retention's `DELETE_FIFO` is a user-selected policy, not a new default.
- **Response metadata:** Agent A2A endpoints and deployment states are pinned in
  responses and rejected by request validation. They do not authorize deployment
  or invocation and are not copied into update bodies.
- **Sensitive metadata:** generated redaction paths for tool auth, credentials
  and user settings are pinned. They do not replace the protected wrapper,
  payload-specific checks or output handoff rules.
- **Catalog compatibility:** BigQuery's six service-account keys now have a
  TypeScript enum as well as Python source-type support. Its private-key file
  remains protected raw UTF-8 JSON via `textof`. OAC's `OAC_DISCOVERY_USER` enum
  member is a compatibility field; the backend can fill it when blank. Neither
  enum change adds a credential prompt or assumes catalog ownership behavior.

SDK model imports resolve digit-containing names such as
`CredentialV2NameAndSecretKey`; enum-only dictionary values such as
`DeploymentLifecycleState` are resolved from the TypeScript SDK declaration.
Required fields and enums are extracted from class methods, then inherited
requirements and enums are merged explicitly. Tests cover polymorphic model
validation and mutation of the newly reviewed nested fields.

### Third-party model availability scenarios

In both Codex and Claude Code, verify these agent-guidance scenarios against a
test instance before release; offline schema tests do not exercise an AI
assistant or establish live feature availability:

- A third-party create or update checks `AI_AGENTS_3P_LLMS_ENABLED` for the
  selected instance, preserving setup's authentication and endpoint.
- An explicit enabled result permits the requested configuration; explicit
  false stops it without switching provider or model silently.
- A missing/error/invalid result or failed lookup leaves availability unknown;
  no trial mutation is submitted to discover support.
- A metadata-only update retaining a third-party graph still checks availability.
  OCI-only configurations need no third-party check.
- Credential references remain public identifiers, with no API-key prompt or
  retrieval, and public session settings remain unchanged unless requested.

## Reviewing an intentional change

1. Read the failure paths, for example
   `ADDED contract.models.HttpToolConfiguration.fields.apiKey` or
   `CHANGED contract.models.Auth.fields.authType.enum`.
2. Review the changed SDK/CLI source and classify new fields/types as public,
   secret, attachment-derived, credential references, or intentionally outside
   supported workflows. Check new response fields for disclosure and handoff
   implications. Shared model enums alone do not establish endpoint support.
3. Update applicable helpers, references and behavior tests in **both**
   `plugins/aidp/codex/skills/aidp-cli` and
   `plugins/aidp/claude/skills/aidp-cli`. Add scenarios for the changed branch;
   keep existing behavior covered. Document deliberate exclusions.
4. Export a candidate to a new file for a human-reviewed diff:

   ```bash
   python3 plugins/aidp/tests/run_sensitive_contracts.py \
     --write-candidate /tmp/aidp-sensitive-contract-candidate.json
   diff -u plugins/aidp/tests/contracts/sensitive-contract-installed.json \
     /tmp/aidp-sensitive-contract-candidate.json
   ```

   This exports the installed contract. For a repository-source candidate, add
   `--target repository` and compare with `sensitive-contract.json` instead.
   Candidate export is **not** a validation pass. It never overwrites an existing
   file and refuses either approved baseline path. Only after reviewing the skill
   and test changes should a maintainer replace the approved baseline in the
   same change. Run the release suite again and require a full pass.

## Cluster creation skill contract

The release runner also executes `test_cluster_contract.py`. For a focused,
offline check of cluster creation:

```bash
python3 -m unittest discover -s plugins/aidp/tests -p 'test_cluster_contract.py'
```

`cluster-create-contract.json` pins the repository Python SDK's `create_cluster`
operation, CLI command metadata and options, API path/version, and all reachable
request and response models. This includes Spark, AI compute, service-managed
DFL variants, nested lists/maps, field and wire names, types, requiredness,
defaults, enum values/constants, inheritance and discriminator mappings.
Relevant CLI parsing/output/naming implementations are also pinned; a refactor
can conservatively require review. Formatting, comments and non-contract prose
do not require a baseline update.

The reviewed cluster update adds AI compute `autoScaleConfiguration` with
cooldown and metric targets. Tests validate string targets, required metric names
and targets, supported metric enums, and nested target-type drift. Availability
and user confirmation still follow both bundled cluster creation references.

The pinned SDK creation implementation now uses the OCI default retry strategy
when no override is selected, adds retry/circuit-breaker plumbing and standard
request options, and retains the public route and required instance/workspace
arguments. Tests detect future retry implementation changes. The reviewed CLI
group builder no longer filters its old excluded-group list; cluster command
naming is unchanged. These changes do not permit blind creation retries or
operations outside the user's requested scope.

Mutation tests independently add/remove/change payload fields, nested structures,
enums, defaults, variants, API routes/versions and CLI options to prove that drift
fails rather than being silently ignored. Tests never rewrite the baseline.

On failure, review the reported field paths and update the cluster creation
guidance in **both** Codex and Claude skills, including defaults, feature checks,
configuration confirmation and any newly supported inputs. Update affected
behavior tests. Only then export a candidate for a reviewed diff:

```bash
PYTHONPATH=plugins/aidp/tests python3 - <<'PY'
import json
from pathlib import Path
from cluster_contract import collect_cluster_contract
candidate = Path('/tmp/aidp-cluster-contract-candidate.json')
with candidate.open('x', encoding='utf-8') as stream:
    json.dump(collect_cluster_contract(), stream, indent=2, sort_keys=True)
    stream.write('\n')
PY
diff -u plugins/aidp/tests/contracts/cluster-create-contract.json /tmp/aidp-cluster-contract-candidate.json
```

Do not automatically refresh this baseline or weaken assertions to make a
failure pass. Replace the baseline only after reviewing the skill, contract and
test changes together. The cluster gate checks repository sources, not installed
packages, the UI checkout or deployed backend-only changes. Free-form map keys
and server-side validation not represented in the SDK cannot be detected here.

## Folder-transfer skill contracts

The release runner includes `test_folder_transfer_contract.py` and, for the
normal installed-package release check,
`test_installed_folder_transfer_contract.py`.

These gates cover only five operations: workspace and volume
`upload_and_extract_*_zip`, workspace and volume `zip_and_download_*_folder`,
and `get_async_operation`. The initial repository and installed SDK/CLI `5.1.1`
snapshots each contain five models. The separate baselines are
`folder-transfer-contract.json` and `folder-transfer-contract-installed.json`.

The checks pin operation paths and API versions, HTTP methods, CLI argument and
body metadata, exact request/response model fields and types, requiredness,
action/status enums, response headers, and the CLI output-envelope implementation.
Installed checks additionally verify the CLI manifest against the SDK and invoke
help for all five commands. No AIDP service or Object Storage request is made.

Behavior tests run both plugin helpers with synthetic transfer results, check
actual CREATE/UPDATE/download bodies against SDK models, verify their CLI command
shapes and exercise all four SDK polling states. Source mutation tests prove
that added/removed fields, type/requiredness changes, action/status enums, transfer
URL/operation-key responses, route/API-version changes, command naming and removed
operations fail the contract gate. A stale installed action enum must also fail.
Catalog property enums and unrelated operation inventories are not part of these
folder-transfer baselines.

Run the focused checks with the Python environment owning the matched packages:

```bash
python3 -m unittest discover -s plugins/aidp/tests -p '*folder_transfer_contract.py' -v
```

For an intentional contract change, review `references/folder-transfer.md` and
`scripts/folder-transfer.py` in **both** plugin variants, and update affected
behavior/mutation tests. Export a candidate to a new file outside the baseline
folder for a reviewed diff; never overwrite the approved snapshot during export:

```bash
PYTHONPATH=plugins/aidp/tests python3 - <<'PYTHON'
import json
from pathlib import Path
from folder_transfer_contract import collect_folder_transfer_contract
candidate = Path('/tmp/aidp-folder-transfer-candidate.json')
with candidate.open('x', encoding='utf-8') as stream:
    json.dump(collect_folder_transfer_contract(), stream, indent=2, sort_keys=True)
    stream.write('\n')
PYTHON
diff -u plugins/aidp/tests/contracts/folder-transfer-contract.json /tmp/aidp-folder-transfer-candidate.json
```

For installed-package review, pass `installed=True`, use a different candidate
filename and compare with `folder-transfer-contract-installed.json`. Accept a
baseline only after reviewing the contract, helper, guidance and tests together.
These gates validate SDK/CLI contracts, not backend extraction rules or live PAR
validity. Existing `test_folder_transfer.py` covers additional local transfer,
archive, redaction and cleanup behavior separately, including a loopback-server
test; it does not access an AIDP instance.

## Sensitive contract limits

This is a source-contract and local behavior release gate, not proof of deployed
service behavior or real authentication. Backend-only changes invisible to the
SDK/CLI, dynamic keys inside `dict(str, object)`, and upstream changes in neither
the checkout nor installed packages cannot be detected here. No backend paths
or backend source snapshots are part of these tests. Backend integration tests
can independently guard runtime rules in that project.

## Platform checks

Run the portable helper checks on native Windows and POSIX hosts:

```bash
python -m unittest discover -s plugins/aidp/tests -p 'test_platform_support.py' -v
```

Run these checks manually on Windows and Linux with Python 3.9 and 3.13.
On Windows they exercise real owner-only DACL creation and validation, rejection
of an Everyone grant, inherited directory permissions, concurrent context
readers/writers, and protected-result handoff/cleanup. Launcher
recognition, PowerShell quoting and consent-scoped identity lookup have local
unit coverage as well. These checks use synthetic inputs and no OCI requests.
The existing full test suite includes POSIX shell fixtures; this portable suite
can run natively on Windows without those fixtures.
