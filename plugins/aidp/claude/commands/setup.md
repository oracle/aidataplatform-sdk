---
description: Set up the local AIDP CLI environment, authenticate to OCI, and optionally validate an AIDP instance.
argument-hint: "[aidp-instance-ocid]"
disable-model-invocation: true
---

# AIDP Setup

Guide the user through local AIDP setup. This command is the explicit step-by-step wrapper around the `aidp-setup-local` skill; that skill is authoritative for prerequisite checks, OCI authentication, region resolution, and the initial read-only validation.

Follow the skill's responsibility boundary, interaction rules, and setup workflow exactly. If an AIDP instance OCID is supplied below, retain it for the validation stage; otherwise follow the skill's normal instance-selection flow. Do not request information already provided.

$ARGUMENTS
