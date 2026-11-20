# Cluster creation

Use this reference for compute inside an existing AIDP instance, not provisioning
a new AIDP instance. Discover the installed creation command and body contract
through the main skill before preparing a request. The values below are initial
suggestions based on UI defaults reviewed on 25 October 2026, not service defaults
or a substitute for installed help.

Always check the CLI reference documentation for the exact installed CLI
version. Properties may have been introduced or removed after this plugin release. If the
CLI reference lists a new field, also consult
[Additional properties](#additional-properties) for handling details. An empty
section does not establish support or handling for a new field; verify its
requirements in the CLI reference before using it, including any sensitive-input
handling, rather than guessing.

Perform this reference check yourself; do not ask users to supply API field
names or values for every optional property. Preserve the documented defaults
and explicit user choices. Omit unrequested optional fields, including newly
introduced ones. Ask only for required information that is still missing and
has no documented default or established session value. An empty Additional
properties section does not add a user-input step or block the existing flow.

## Collect the cluster choices

Reuse the instance, validated endpoint, region, and authentication established
in the session. For each creation, obtain these user choices before presenting
the configuration:

1. Ask for the cluster name. Do not pick a name on the user's behalf.
2. Ask for the cluster type: Spark (notebooks and Spark jobs) or AI compute
   (AI agents). Do not infer the type solely from the workload.
3. List the accessible workspaces for the selected instance, following
   pagination, and present their names and stable keys for the user to select.
   Ask which workspace should contain the cluster; do not silently select a
   remembered workspace. Resolve the selection to its exact key.

Do not repeat a question when the user has already explicitly supplied that
choice for this creation. A workspace explicitly selected for this creation
needs no second selection. If listing fails, report the failure and ask for a
workspace key rather than inventing a list or claiming no workspaces exist.
Follow the main skill's zero-workspace diagnostic when applicable.

Check for name conflicts in the selected workspace. Preserve explicit sizing
and scaling choices; use the initial values below for unspecified fields.
Do not ask separately about every optional field. Present the resulting
settings together as **Configuration**, never as a recommendation, and do not
use the word "recommended" in the cluster creation prompts.

## Check autoscaling before suggesting limits

After setup has validated access, fetch both flags in one read-only signed call:

- Spark: `CLUSTER_AUTOSCALE`.
- AI compute: `AI_COMPUTE_AUTOSCALE_ENABLED`.

The UI uses the bulk wrapper endpoint
`GET /20240831/dataLakes/{instanceOcid}/featureStatuses`. Read it with
`oci raw-request` using the command below.

Use the exact authentication mode, profile, custom config, and endpoint validated
by setup. This `/dataLakes` wrapper request uses `/20240831`, independently of
the public SDK's API version. Set `AIDP_ENDPOINT` to the validated HTTPS base
endpoint with no version path or trailing slash; the command adds `/20240831`
exactly once. Do not substitute the public SDK version or guess an alternate
host or version on failure.
In bash/zsh, after filling these non-secret variables from the retained session:

```bash
oci raw-request \
  --profile "$OCI_PROFILE" \
  --auth "$OCI_AUTH_MODE" \
  --http-method GET \
  --target-uri "${AIDP_ENDPOINT}/20240831/dataLakes/${AIDP_INSTANCE_OCID}/featureStatuses?featureNames=CLUSTER_AUTOSCALE&featureNames=AI_COMPUTE_AUTOSCALE_ENABLED"
```

`OCI_AUTH_MODE` is the established `security_token` or `api_key`, not a new
authentication choice. Preserve scoped `OCI_CLI_CONFIG_FILE` when applicable.
Apply the main skill's network-permission and authentication-error handling to
this OCI call as well. The array uses repeated `featureNames` query parameters
(`collectionFormat: multi`), not a comma-separated string.

Read the OCI response body's `data.items` and match each item by `featureName`.
Evaluate each flag independently; one successful item does not establish the
other flag's availability.

| Relevant flag result | Suggested settings |
| --- | --- |
| String `value` is `'true'`, with no item error | Offer autoscaling with initial limits of 1–10 workers for Spark or 1–10 replicas for AI compute. |
| String `value` is `'false'`, with no item error | Suggest 1 fixed worker or replica; omit autoscaling options and limits. |
| Request failed, item missing, item error, or invalid value | Availability is unknown. Suggest fixed capacity, briefly explain that availability could not be verified, and omit autoscaling limits. |

Do not treat absent or failed results as disabled. If the user explicitly
requested autoscaling and its availability cannot be established, explain the
result and resolve that choice rather than silently substituting fixed capacity.
For new AI compute, autoscaling remains off unless the user chooses it, even
when the feature flag is enabled.

## Initial compute values

| Setting | Spark | AI compute |
| --- | --- | --- |
| API type | `USER` | `AI_COMPUTE` |
| Driver sizing | AMD `amd.generic`, 2 OCPUs, 32 GB memory | 1 OCPU, 16 GB memory |
| Worker sizing | AMD `amd.generic`, 2 OCPUs, 32 GB memory per worker | Not applicable |
| Fixed capacity | 1 worker | 1 replica |
| Runtime | Spark 3.5.0 | No Spark runtime selection |
| Auto termination | 120 minutes | No termination setting proposed by this form |
| Description | Omit unless provided | Omit unless provided |
| Optional Spark configuration (advanced settings, environment variables, init scripts) | Omit unless requested | Not applicable |

Only offer scaling ranges after the corresponding successful feature check
above. With AI autoscaling chosen, initial UI values are 1–10 replicas, a target
of 10 API requests per second, 80 percent mean CPU utilization, and a 10 minute
cooldown. Use the configuration fields described below and preserve the user's
explicit scaling choices.

The Spark sizing matches the UI Quick start preset. Sizing alone does not
promise faster provisioning. When autoscaling is available, the initial Spark
limits are 1–10 workers; otherwise use 1 fixed worker. The skill may suggest
fixed capacity as the minimal starting choice.

## Supported autoscaling fields and request retries

For AI compute, the reviewed creation contract exposes `autoScaleConfiguration`
with `metrics` and `cooldownPeriodInMinutes`. Each metric requires a `name` and
string `targetAverageValue`; reviewed names are `API_REQUESTS_PER_SECOND`,
`CPU_UTILIZATION` and `MEMORY_UTILIZATION`. Use only the metrics and targets the
user accepts in the single Configuration confirmation, after the availability
check above. Use the initial metric targets and cooldown already described;
do not ask separate questions for each value or add memory-based scaling unless
requested.

The SDK may retry requests automatically and attach an OCI retry token. A timeout
or retry exhaustion does not prove that creation failed. Preserve any known retry
token and operation/resource identifiers, inspect current state after an uncertain
result, and do not submit a new creation request blindly. The public creation
route and required instance/workspace arguments remain authoritative; CLI command
groups outside this workflow do not grant permission to operate other resources.

## Show the configuration and wait for confirmation

After collecting the cluster name, type, and workspace selection, check feature
availability and validate the body against installed help. Show the complete
configuration together: instance, workspace name and key, cluster name and type,
CPU and memory sizing, worker or replica count, autoscaling state and any accepted
limits, runtime where applicable, termination setting where applicable, and any
user-supplied overrides. Include autoscaling limits only when the relevant flag
is confirmed enabled. Call this **Configuration** and state that creation
provisions chargeable compute.

Ask: "Tell me if you need any changes here, or shall I create it with this configuration?"

Wait for the user's explicit confirmation of the displayed configuration before
executing any creation request. A generic request to create a cluster, answers
to the name/type/workspace questions, or silence do not confirm the displayed
configuration. If the user requests changes, update and validate the configuration,
show it again, and obtain confirmation of that version. If validation requires
changing the configuration after confirmation, obtain confirmation again.
This is the main skill's provisioning confirmation, not an additional approval
round after the configuration has already been explicitly confirmed.

Only then create through the supported CLI command. Follow the main skill's
handling for failed mutations; do not retry creation blindly.

## Return after creation is accepted

For both Spark and AI compute, finish the creation request once the service
confirms acceptance. Do not wait for the compute to become ACTIVE, start a
status-polling loop, or schedule a status monitor unless the user explicitly
asks for that follow-up. Acceptance means creation was triggered, not that the
compute is ready to use.

Retain the instance, workspace key, compute key, and any operation key returned
for a later status request. Report the operation key when one is returned, as
required by the main skill. Use this completion message, substituting the
confirmed name:

"Compute creation has been triggered for <name>. Let me know if you want me to check its current status."

If the request fails or its outcome is uncertain, do not claim creation was
triggered. Follow the main skill's mutation-error handling and inspect resulting
state when needed to resolve uncertainty without submitting a duplicate request.

## Additional properties
