---
description: Diagnose local AIDP CLI readiness and provide targeted recovery guidance.
argument-hint: "[aidp-instance-ocid]"
disable-model-invocation: true
---

# AIDP Doctor

Run a read-only local AIDP diagnostic using the validation rules and safety boundaries in `aidp-setup-local`.

Check the operating system and architecture, then run the setup skill's `scripts/check_prerequisites.py` once, without `--skip-latest`, to check Python, pip, OCI CLI, AIDP CLI, and AIDP Python client availability and versions, whether the AIDP CLI and Python client versions match, and whether the AIDP CLI is at the latest version published to the configured package index. If an AIDP instance OCID is supplied below, resolve its region using the setup skill's region-key cache. If the session has an established authentication mode and OCI profile, run one read-only AIDP workspace-list validation using that state and the supplied or retained instance OCID. Do not prompt for an instance or authentication merely to run this diagnostic, and do not install, upgrade, authenticate, edit configuration, or create resources.

For package timeouts, interrupted installations, or Windows path/script errors, use [setup troubleshooting](../skills/aidp-setup-local/references/troubleshooting.md) for targeted diagnosis and recovery proposals. Keep this diagnostic read-only; apply repairs only after the user chooses the setup remediation flow.

Report a compact status table: **check | status | detail**. Continue with independent checks after a failure and mark unavailable checks as unknown. End with the single smallest corrective next step. If a change is required, such as a version mismatch or available update, offer to make it and show the command, and offer `/oracle-aidp:setup` as the guided remediation path.

$ARGUMENTS
