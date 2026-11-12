# Oracle AI Data Platform plugin for Codex

Work with Oracle AI Data Platform (AIDP) directly from Codex using
natural-language requests. The plugin helps you set up the AIDP command-line
tool, connect to Oracle Cloud Infrastructure (OCI), and manage AIDP resources.

## Capabilities

- Guide local setup, OCI authentication, and connection validation.
- List and inspect workspaces, clusters, notebooks, workflows, catalogs, and other AIDP resources.
- Help create, update, and delete resources, with confirmation before submitting changes.
- Diagnose common setup and access issues.

Operations use your OCI credentials and the permissions assigned to your account.

## Install

```bash
codex plugin marketplace add oracle/aidataplatform-sdk
codex plugin add oracle-aidp@oracle-aidp-plugins
```

Start a new Codex chat after installation.

## Get started

You need macOS, Linux, or Windows, an OCI account with access to an AIDP instance,
and network access to the required cloud services and package sources. Local
setup requires Python 3.9 or later; the plugin can guide prerequisite installation
with your approval. Connect to your organization's VPN if required.

Example requests:

- "Set up the AIDP CLI on my machine."
- "List the workspaces in my AIDP instance."
- "Create an AIDP workspace named analytics-dev."

## Data and privacy

To streamline repeat use, the plugin stores a small set of connection
preferences locally in `~/.config/aidp/context.json`:

- Installed locations of the AIDP CLI and OCI CLI
- The most recently used OCI authentication method, profile, and configuration file
- Validated AIDP endpoints and recently used AIDP instances (OCID, name, and region)
- The time of the last AIDP CLI update check

This file remains on your machine and is not transmitted by the plugin. It does
not contain user identifiers such as your OCI user OCID, IAM username, or email
address, and it never stores passwords, private keys, or tokens. You can review
or remove these preferences at any time by asking Codex to show, forget, or
clear your remembered AIDP settings.

## Documentation and support

- [AIDP CLI and SDK documentation](../../../docs/README.md)
- [Plugin release notes](../CHANGELOG.md)
- [Bug reports and feature requests](../../../CONTRIBUTING.md#opening-issues)
- [Report a security vulnerability](../../../SECURITY.md)

For AIDP instance access, contact your organization's AIDP administrator.

## License

Copyright (c) 2026 Oracle and/or its affiliates. Released under the
[Universal Permissive License 1.0](../../../LICENSE.txt).
