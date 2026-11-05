# External catalogs: discovery, protected body, one command

Use the selected source reference and [protected request bodies](../protected-bodies.md).
The generic `scripts/protected_aidp.py` wrapper replaces the earlier credential
draft/collector/build/request-runner sequence for new operations.

References cover all twelve sources in the reviewed installed SDK: [ADW](adw.md), [ALH](alh.md),
[ATP](atp.md), [Oracle](oracle.md), [Exadata](exadata.md), [Kafka](kafka.md),
[MySQL](mysql.md), [DB2](db2.md), [Azure SQL Server](azure-sqlserver.md),
[Snowflake](snowflake.md), [Google BigQuery](google-bigquery.md), [Oracle Analytics](oracle-analytics.md).
MySQL/DB2/Azure SQL Server/Snowflake/Google BigQuery each have a documented
`scripts/ext-catalogs/<source-folder>/prepare-body.py` helper for unresolved
create/test bodies. No sensitive draft is needed.

## Ask for an unspecified source

When the user asks to test a connection without naming a source, present all
12 installed-SDK-supported sources. Do not shorten the choices to examples or “another
source”. If access to the selected instance has already been verified, use:

> Access to `<instance-name>` is working. Which source should I test—ADW, ALH, ATP, Oracle Database, Exadata, Kafka, MySQL, DB2, Azure SQL Server, Snowflake, Google BigQuery, or Oracle Analytics?

Substitute the verified instance name; do not claim access is working unless it
was verified for the selected target. Otherwise ask just the source question
without the access claim. If the source is already known, continue with that
source reference rather than asking again. Display names map to `ORACLE`,
`AZURE_SQLSERVER`, `GOOGLE_BIGQUERY`, and `ORACLE_ANALYTICS` for Oracle Database,
Azure SQL Server, Google BigQuery, and Oracle Analytics respectively. Other names
map directly to their uppercase source type. Installed help is authoritative;
a stale repository SDK enum must not be used to reject an installed connector.

## Discovery and execution

1. Resolve the source type and new-connection versus existing-catalog intent.
   Reuse validated AIDP context; source tenancy/region may differ. Discover
   accessible non-sensitive metadata and ask only unresolved choices in chat.
2. For Autonomous sources, ask whether to use a wallet or choose an instance.
   A wallet ZIP path is non-secret and can be provided in chat. Do not read or
   extract wallet contents into model context. Use the helpers below for access
   and service discovery. Select the service before asking for account credentials.
3. Prepare `body-<unique>.json` directly from chat and installed command help.
   Put `{visible_prompt_input:required:Enter account username}` and
   `{invisible_prompt_input:required:Enter account password}` in credential fields;
   use `{base64of:/path/from/chat/wallet.zip}` for wallet contents. Wallet password
   uses required or optional hidden prompt syntax according to the selected
   client/realm. No separate sensitive-data file is needed.
4. Check the unresolved template before requesting credentials:
   `python3 <skill_dir>/scripts/validate-protected-paths.py @/tmp/body-<unique>.json`.
   This separate helper checks referenced-file access and placeholder syntax
   without prompts or an AIDP call. Wallet-specific checks above still apply.
5. After the concrete operation has any required approval, give the user a
   command with `--output-file <fresh-result-path> --` before `aidp`, as shown
   below. This handoff is required for every agent-guided external catalog
   create/test operation, including Oracle Database basic and wallet connections,
   full new-connection tests, and stored-catalog replacement-password tests.
   Preserve the installed CLI arguments and established authentication/target.
6. Wait for and consume that exact result via `read-protected-result.py`; it
   deletes the result before returning its contents. Use the same result path
   across the terminal command and reader. A 202 means pending. Do not retry a
   mutation blindly. Do not ask the user to paste terminal output. The template
   remains unchanged with placeholders and no credential draft remains.

## Additional source template helpers

MySQL, DB2, Azure SQL Server, Snowflake and Google BigQuery share the following helper contract;
source-specific connection fields and authentication branches remain in their
individual references.

| Source | Script folder |
|---|---|
| `MYSQL` | `mysql` |
| `DB2` | `db2` |
| `AZURE_SQLSERVER` | `azure-sqlserver` |
| `SNOWFLAKE` | `snowflake` |
| `GOOGLE_BIGQUERY` | `google-bigquery` |

Each `scripts/ext-catalogs/<source-folder>/prepare-body.py` takes
`--operation create|test-connection`, `--config @<non-sensitive-config.json>`, and
`--output <fresh-body-template.json>`. It creates an unresolved body without
reading private attachments, requesting credentials or calling AIDP.
Use the source reference's exact preparation command, then steps 4–6 above and
the handoff commands below, replacing the example body path with that helper's
actual output path. Use one fresh result path consistently for execution/reading.

For creation, use `--operation create`, include the chosen `displayName`, choose
fresh body/result filenames, and execute `catalog create` after checking installed
help. The helper adds `catalogType: EXTERNAL`; tests have neither a creation name
nor catalog type. Optional create-only `description` and public string-to-string
`properties` are copied only when requested. Config contains only documented
non-sensitive settings; raw usernames/passwords/key contents are not config.

Preserve established authentication, profile, custom config and target. Follow
the existing approval requirements for the concrete operation. The wrapper
rechecks paths, prompts locally, deletes its actual body on completion/failure/
Ctrl+C, captures output, and prints the handoff message specified below. A 202
is pending; do not retry creation blindly or weaken TLS/change authentication
to work around a failed test. The common workflow governs waiting and cleanup.

## Required output handoff for every source

Handoff is source-independent: the wrapper does not branch on ADW versus Oracle
or any other source. Do not omit `--output-file` when constructing the command;
the wrapper refuses invocations without it.

Connection test (the body determines the selected source type):

```bash
python3 <skill_dir>/scripts/protected_aidp.py \
  --output-file /tmp/aidp-result-catalog-<unique>.json -- \
  aidp --auth <auth-mode> --profile <profile> --endpoint <endpoint> \
  --instance-id <instance-ocid> catalog test-connection --body @/tmp/body-<unique>.json
```

For catalog creation, use the same wrapper/output arguments and replace only the
resource operation with `catalog create` after checking installed help. Use a
new unique result path for each execution. The wrapper sets strict URL encoding
internally, captures CLI stdout/stderr in an owner-only file, deletes the actual
request body, then prints only:
`Operation output handed off to AI agent. Ask it to continue.`
Prompts remain visible as appropriate; command output does not appear on console.

While waiting, or when the user says “continue”, consume the agreed result:

```bash
python3 <skill_dir>/scripts/read-protected-result.py \
  /tmp/aidp-result-catalog-<unique>.json --wait-seconds 45
```

If `ready:false` is returned, the operation is not known to be complete; wait
again during the active turn. Do not rerun AIDP or scan unrelated output files.
Follow [protected bodies](../protected-bodies.md#result-handoff-to-the-agent)
for cancellation, waiting limits and continuation after a finished chat turn.

## Wallet access and service choices

```bash
python3 <skill_dir>/scripts/ext-catalogs/common/validate-private-paths.py --wallet /path/from/chat/wallet.zip --check-wallet
python3 <skill_dir>/scripts/ext-catalogs/common/list-wallet-services.py --wallet /path/from/chat/wallet.zip
```

Quote shell paths safely. Helpers expand `~`, open/read bounded regular files,
and expose only safe checks or service aliases, never wallet contents. A file in
Downloads may exist yet be inaccessible to this process. Distinguish access
errors from ZIP/TNS errors; do not repeatedly retry or assume corruption.
Request scoped access when supported or let the user choose another accessible
local location. ADW/ALH need a database-specific wallet, not a regional wallet.
Do not assume `_high`, `_low` or the first alias is the desired service.

## Choose an Autonomous instance

Discover accessible databases in the selected source compartment/region using
established OCI authentication. Ask only which instance when ambiguous. If wallet
download is authorized, have the user run the standalone helper locally:

```bash
python3 <skill_dir>/scripts/ext-catalogs/common/download-autonomous-wallet.py \
  --wallet-output /tmp/wallet-<unique>.zip --database-id <database-ocid> \
  --auth <oci-auth-mode> --profile <profile> --region <source-region>
```

It asks for a hidden protection password for the new wallet immediately before
the OCI download, sends that password through a private temporary request file,
and removes that temporary request. It prints the non-secret wallet path, not
the password, and does not create an account-credential draft. The user retains
that wallet password for the final catalog prompt if required. Add `--dedicated`
when OCI metadata identifies dedicated infrastructure, `--config-file <path>`
for custom configuration, and `--oci <executable>` when needed. The helper never
resets the database account password. Do not install/configure OCI CLI implicitly;
if unavailable or unauthorized, offer the existing-wallet route.

Run the access/services helpers on the downloaded path, then prepare the same
protected body as for an existing wallet. No account username/password is needed
for download or service discovery. Source tenancy/region may require another
already-authorized profile; the UI falls back to wallet upload for cross-region
or cross-tenancy selection rather than assuming access.

## Existing-catalog replacement-password tests

For ADW/ALH/ATP/Kafka/Oracle/Exadata/MySQL/DB2/Azure SQL Server and verified
Snowflake Basic authentication, when installed help supports this operation,
reuse the catalog's stable key and source type, and prompt only for a replacement
password. Example ADW body:

```json
{
  "key":"<existing-catalog-key>",
  "sourceType":"ADW",
  "connectionDetails":{"connectionProperties":{
    "ADW_PASSWORD":"{invisible_prompt_input:required:Enter replacement ADW password}"
  }}
}
```

The server reuses stored endpoint/account/wallet details. Testing does not save
the password. DB2 uses `password` instead of a source-prefixed property.
Snowflake KeyPair must use a full test without `key`: the stored shortcut only
replaces passwords, not private keys/passphrases. OAC does not use this shortcut: discover a separate stored-OAC test
if offered, or prepare its full protected connection-test body.

## Failures and cleanup

A safe `FILE_ACCESS_DENIED` result does not mean a wrong path or corrupt wallet.
`INVALID_WALLET_ZIP`/`TNS_FILE_MISSING` identify archive issues;
`INVALID_TNS_SYNTAX` identifies parser compatibility/syntax rather than proof of
corruption. `INTERACTIVE_TERMINAL_REQUIRED`/`HIDDEN_INPUT_UNAVAILABLE` require a
real user-controlled terminal; do not fall back to echoed passwords. Never ask to
read the wallet or resolved body to diagnose a failure. Work from safe codes,
the unresolved template and non-sensitive examples.

The wrapper disposes of its actual request copy regardless of success/failure.
Do not ask to retain it. Offer deletion of generated wallets or the unresolved
template separately when no longer needed, after approval for those exact
artifacts; never delete the user's original wallet/key/certificate. Any leftover
private drafts from the superseded flow still require explicit deletion approval.

## CLI version and additional properties

Always check the CLI reference documentation for the exact installed CLI
version. Properties may have been introduced or removed after this plugin
release. If the CLI reference lists a new field, also consult
[Additional properties](#additional-properties) for handling details. Verify
field requirements and sensitive-input handling in the CLI reference rather
than guessing when no additional guidance is recorded.

Perform this check yourself. Preserve documented defaults and explicit user
choices, and omit unrequested optional fields, including newly introduced ones.
Ask only for required information that is still missing and has no documented
default or established session value. An empty Additional properties section
must not add a user-input step or block the existing flow.

## Additional properties
