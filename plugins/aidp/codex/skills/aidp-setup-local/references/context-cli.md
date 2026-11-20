# AIDP context command reference

Use `../scripts/aidp_context.py` relative to this file. The helper is the only supported interface to `~/.config/aidp/context.json`; never read or write that file directly.

The context stores validated connection defaults and verified local AIDP/Python and OCI executable selections. Persist them automatically without asking for consent. Never pass or store a user OCID, IAM name, email address, token, private key, fingerprint, password, or authorization header.

Treat every remembered value as a default guess that still needs the live validation this skill defines. Return stored values unchanged; never infer, name, or describe an environment category from a stored resource type, realm, endpoint hostname, or other remembered identifier. The helper validates inputs, applies MRU limits, locks concurrent writes, and replaces the file atomically. If a read or write fails, continue the requested AIDP operation with the regular uncached flow.

## Read

```bash
python3 <setup_skill_dir>/scripts/aidp_context.py get all
python3 <setup_skill_dir>/scripts/aidp_context.py get pythonCli
python3 <setup_skill_dir>/scripts/aidp_context.py get lastUsedAuth
python3 <setup_skill_dir>/scripts/aidp_context.py get endpoints
python3 <setup_skill_dir>/scripts/aidp_context.py get endpoints --realm oc1 --resource-type aidataplatformenv
python3 <setup_skill_dir>/scripts/aidp_context.py get recentlyUsedAIDP
python3 <setup_skill_dir>/scripts/aidp_context.py get recentlyUsedAIDP --instance-ocid <aidp_ocid>
```

For setup/resource requests, `check_prerequisites.py` invokes `aidp_context.py get all` internally with its own interpreter; reuse its returned `context` instead of issuing another initial read. For context-only requests, use `get all` directly; use the per-field reads only for a targeted re-read after a write. A missing field or entry returns JSON `null`. Reads never create or modify the context file. Each recent-instance object returned by `get all` or `get recentlyUsedAIDP` includes a derived `displayOcid` that preserves `ocid1.<resource-type>.<realm>.<region-key>.` and the final eight characters of the unique suffix. Use it verbatim in remembered-instance selection lists. It is output-only and is never stored in the context file.

## Record successful context

Verified local CLI, after the prerequisite script selects a working Python CLI and successfully probes its packages:

```bash
python3 <setup_skill_dir>/scripts/aidp_context.py set pythonCli --path <absolute_aidp_path> --python-path <absolute_python_path>
python3 <setup_skill_dir>/scripts/aidp_context.py get pythonCli
python3 <setup_skill_dir>/scripts/aidp_context.py remove pythonCli
```

Write only when either path differs. Store the interpreter path as selected, without resolving its virtual-environment symlink to a base Python. A remembered executable receives only `--version`, once per session, without ownership detection; package/version checks use `pythonPath`. A new candidate receives ownership detection before its version check. A failed remembered selection triggers script-owned discovery. Skill-managed upgrades verify and save the resulting selection. An external installation into another environment does not replace a still-working saved selection; remove `pythonCli` or explicitly select a new CLI to rediscover. Existing schema-2 files without `pythonCli` remain valid. Older plugin releases that reject unknown fields cannot read the added field: remove `pythonCli` with the updated helper before downgrading.

Verified OCI executable, after the prerequisite checker returns an installed OCI result:

```bash
python3 <setup_skill_dir>/scripts/aidp_context.py set ociCli --path <absolute_oci_path>
python3 <setup_skill_dir>/scripts/aidp_context.py get ociCli
python3 <setup_skill_dir>/scripts/aidp_context.py remove ociCli
```

Compare the validated path with `context.ociCli.path` and write only when new or
changed, independently of AIDP target/authentication validation. Save no version,
credentials or token contents. Each new session revalidates the saved executable
with `--version`; a working saved path skips OCI PATH discovery and other OCI
version probes. Use the returned session PATH adjustment for child commands,
preserving the validated OCI executable if another directory would shadow it. Stale or failing paths fall back to normal discovery. An
explicit prerequisite-checker `--oci <path>` overrides the saved selection.
Existing schema-2 contexts without `ociCli` remain valid. Codex and Claude share
this per-user context when configured with the same context path.

Authentication, after either live OCI validation or a successful AIDP workspace-list request establishes that the selection works:

```bash
python3 <setup_skill_dir>/scripts/aidp_context.py set lastUsedAuth \
  --auth-type security_token \
  --profile DEFAULT
```

Add `--config-file-path <absolute_path>` only when a custom OCI config file was explicitly selected. The calling skills treat this path as part of the remembered authentication selection and apply it as a scoped `OCI_CLI_CONFIG_FILE`; they never silently fall back to the default config when the remembered path is unavailable.

Endpoint template, after a successful AIDP workspace-list validation:

```bash
python3 <setup_skill_dir>/scripts/aidp_context.py set endpoints \
  --realm oc1 \
  --resource-type aidataplatformenv \
  --template 'https://aidpenv.{region}.example.com'
```

The camel-case alias `--resourceType` is also accepted. Entries are deduplicated and moved to the front. Nonstandard resource types retain at most five templates. The standard `aidataplatform` resource type accepts only `https://aidp.{region}.oci.oraclecloud.com` and retains at most one template.

Recent instance, after the first successful HTTP 2xx response for a new session target, using its known name or fetching the name once before saving:

```bash
python3 <setup_skill_dir>/scripts/aidp_context.py set recentlyUsedAIDP \
  --instance-ocid <aidp_ocid> \
  --region us-phoenix-1 \
  --endpoint https://aidpenv.us-phoenix-1.example.com \
  --name <optional_name>
```

The helper derives resource type and realm from the OCID. The caller must pass the exact AIDP instance OCID used as `--instance-id` by the successful AIDP request; never pass an OCID found in an endpoint URL path or query. Entries are deduplicated and moved to the front; at most ten are retained. Resolve the instance `displayName` with this skill's bounded helper and supply `--name` when successful. A name-lookup failure does not block recording the other validated context. During the session, do not retry it for the same AIDP instance OCID even when the endpoint changes; only a different OCID permits another lookup. Invoke the helper directly as documented in [the AIDP target selection reference](aidp-target-selection.md): no `timeout` or similar wrapper, no discarded stderr, and a checked exit status. An exit status other than `0`, `1`, or `2` means the helper did not run and does not count as an attempt.

Every successful `set` prints a write receipt only after the atomic replacement completes:

```json
{
  "saved": true,
  "field": "recentlyUsedAIDP",
  "value": {
    "instanceOcid": "<aidp_ocid>",
    "region": "us-phoenix-1",
    "endpoint": "https://aidpenv.us-phoenix-1.example.com"
  }
}
```

The `value` contains the complete value written for that field. Inspect this receipt instead of issuing a verification read. A nonzero exit prints an error rather than a receipt and must not be described as saved. When a restricted runtime blocks the mutation, request narrowly scoped permission for the same helper command and retry it once; do not add a separate `get` command. If it still fails or permission is unavailable, preserve the requested AIDP result and state briefly that its local context was not saved; never claim success without the receipt.

## Latest-version check time

`latestVersionCheck` records when this skill last looked up the latest published AIDP package versions, so that lookup runs at most once a week. It stores only the time; the helper sets `checkedAt` itself.

```bash
python3 <setup_skill_dir>/scripts/aidp_context.py get latestVersionCheck
python3 <setup_skill_dir>/scripts/aidp_context.py set latestVersionCheck
python3 <setup_skill_dir>/scripts/aidp_context.py remove latestVersionCheck
```

## Migrate, forget, or clear

```bash
python3 <setup_skill_dir>/scripts/aidp_context.py migrate
python3 <setup_skill_dir>/scripts/aidp_context.py remove lastUsedAuth
python3 <setup_skill_dir>/scripts/aidp_context.py remove endpoints --realm oc1 --resource-type aidataplatformenv --template '<template>'
python3 <setup_skill_dir>/scripts/aidp_context.py remove recentlyUsedAIDP --instance-ocid <aidp_ocid>
python3 <setup_skill_dir>/scripts/aidp_context.py remove latestVersionCheck
python3 <setup_skill_dir>/scripts/aidp_context.py clear
```

`migrate` preserves valid authentication, endpoint, and recent-instance values while removing legacy `consent` and `userOcids` fields. `clear` removes the entire context file. Neither command modifies OCI configuration, session tokens, or AIDP resources.

## Stored shape

```json
{
  "schemaVersion": 2,
  "pythonCli": {
    "path": "/home/example/.aidp-venv/bin/aidp",
    "pythonPath": "/home/example/.aidp-venv/bin/python"
  },
  "ociCli": {"path": "/home/example/.aidp-venv/bin/oci"},
  "lastUsedAuth": {
    "authType": "security_token",
    "profile": "DEFAULT",
    "configFilePath": null,
    "lastValidatedAt": "2026-09-28T10:00:00Z"
  },
  "endpoints": {
    "oc1:aidataplatformenv": [
      {
        "template": "https://aidpenv.{region}.example.com",
        "lastValidatedAt": "2026-09-28T10:00:00Z"
      }
    ]
  },
  "recentlyUsedAIDP": [],
  "latestVersionCheck": {
    "checkedAt": "2026-10-08T05:00:00Z"
  }
}
```
