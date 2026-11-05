ORACLE AND ITS AFFILIATES DO NOT PROVIDE ANY WARRANTY WHATSOEVER, EXPRESS OR IMPLIED, FOR ANY SOFTWARE, MATERIAL OR CONTENT OF ANY KIND CONTAINED OR PRODUCED WITHIN THIS REPOSITORY, AND IN PARTICULAR SPECIFICALLY DISCLAIM ANY AND ALL IMPLIED WARRANTIES OF TITLE, NON-INFRINGEMENT, MERCHANTABILITY, AND FITNESS FOR A PARTICULAR PURPOSE.  FURTHERMORE, ORACLE AND ITS AFFILIATES DO NOT REPRESENT THAT ANY CUSTOMARY SECURITY REVIEW HAS BEEN PERFORMED WITH RESPECT TO ANY SOFTWARE, MATERIAL OR CONTENT CONTAINED OR PRODUCED WITHIN THIS REPOSITORY.  IN ADDITION, AND WITHOUT LIMITING THE FOREGOING, THIRD PARTIES MAY HAVE POSTED SOFTWARE, MATERIAL OR CONTENT TO THIS REPOSITORY WITHOUT ANY REVIEW. USE AT YOUR OWN RISK.

# Oracle AI Data Platform

Work with Oracle AI Data Platform (AIDP) through an AI assistant, terminal commands,
or your own application. Explore and manage AIDP resources, including workspaces,
clusters, notebooks, workflows, catalogs, and more.

**New here? [Start with an AI assistant](#get-started-with-an-ai-assistant).**
The AIDP plugin guides you through setup, then lets you ask for tasks in everyday
language.

## Choose how you want to work

| What you want to do | What to use | Where to start |
| --- | --- | --- |
| Ask an AI assistant to help you work with AIDP | The AIDP plugin for Codex or Claude Code | [Guided setup](#get-started-with-an-ai-assistant) |
| Type commands in a terminal | The command line interface (CLI) | [Manual CLI installation](#cli) |
| Connect your own application to AIDP | A software development kit (SDK) for Python, TypeScript, or Java | [Manual SDK installation](#sdk) |

## Get started with an AI assistant

The AIDP plugin adds AIDP support to Codex or Claude Code. You can describe what
you want to do without writing code or learning terminal commands.

Before you begin, you need access to an AIDP instance—your organization's AIDP
environment—and an Oracle Cloud account with permission to use it. If you need
access, contact your organization's AIDP administrator.

### First-time setup

1. **Install the plugin.** Choose either the terminal or your assistant's interface.

   **From a terminal** (with Codex or Claude Code installed), run the commands
   for your assistant:

   **Codex**

   ```bash
   codex plugin marketplace add oracle-samples/aidataplatform-sdk
   codex plugin add aidp@aidp-skills
   ```

   **Claude Code**

   ```bash
   claude plugin marketplace add oracle-samples/aidataplatform-sdk
   claude plugin install aidp@aidp-skills
   ```

   **From the app:** You can also use your assistant's plugin management options
   to find and install Oracle AIDP Plugin from the `aidp-skills` marketplace.
   Available options vary by app and version.

   After installation, start a new chat so the assistant can use the plugin.

2. **Start setup.** Send this message to your assistant:

   > [@Oracle AIDP](plugin://aidp@aidp-skills) Set up the AIDP CLI on my machine.

3. **Follow the prompts.** The assistant helps install the tools you need,
   sign in to Oracle Cloud Infrastructure (OCI), and connect to your AIDP instance.

You do not need to install the SDK or CLI, or configure your Oracle Cloud sign-in,
yourself beforehand. The assistant asks for only the information and choices it
needs.

### Everyday use

Once connected, ask for what you need. For example:

> List workspaces in my aidp instance.

> Show the clusters in my aidp workspace.

The plugin remembers your connection settings so you can get straight to work
without repeating the initial setup. If your sign-in expires or your environment
changes, the assistant helps you reconnect.

You can continue working through your AI assistant. The manual instructions below
are for people who want to use terminal commands or build applications.

## Install CLI or SDK manually

Choose the CLI for terminal commands or an SDK for application development. You
only need the language you plan to use. If you use an AI plugin, it guides you
through installation instead.

The package links below are for manual installation from PyPI, npm, or Maven Central.

[![Python SDK](https://img.shields.io/badge/Python%20SDK-2563EB.svg?style=flat-square&logo=pypi&logoColor=white)](https://pypi.org/project/aidp-python-client/)
[![Python CLI](https://img.shields.io/badge/Python%20CLI-2563EB.svg?style=flat-square&logo=pypi&logoColor=white)](https://pypi.org/project/aidp-cli/)
[![TypeScript SDK](https://img.shields.io/badge/TypeScript%20SDK-6D28D9.svg?style=flat-square&logo=npm&logoColor=white)](https://www.npmjs.com/package/aidp-typescript-client)
[![TypeScript CLI](https://img.shields.io/badge/TypeScript%20CLI-6D28D9.svg?style=flat-square&logo=npm&logoColor=white)](https://www.npmjs.com/package/aidp-cli)
[![Java SDK](https://img.shields.io/badge/Java%20SDK-C2410C.svg?style=flat-square&logo=apachemaven&logoColor=white)](https://mvnrepository.com/artifact/com.oracle.aidataplatform/aidp-java-client)

### CLI

Choose either the Python CLI or the Node.js CLI. Both provide the `aidp` command;
you only need one.

#### Python CLI

Use Python 3.9 or later. Install or update the CLI and Python SDK from
[PyPI](https://pypi.org/project/aidp-cli/):

```bash
python3 -m pip install --upgrade aidp-cli aidp-python-client

aidp --help
```

If Python requires an isolated environment, create and activate a virtual
environment before installing. See the
[Python CLI installation guide](./aidp-cli/aidp-py-cli/README.md).

#### Node.js CLI

With Node.js and npm installed, install or update the CLI and TypeScript SDK from
[npm](https://www.npmjs.com/package/aidp-cli):

```bash
npm install -g aidp-cli@latest aidp-typescript-client@latest

aidp --help
```

#### Oracle Cloud sign-in tool

Install the Oracle Cloud command line tool (OCI CLI) for the sign-in steps below.
Skip this step if you already have it. For installation options, see
[Install OCI CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm).

```bash
python3 -m pip install --upgrade oci-cli
```

### SDK

Use an SDK when you want to call AIDP from your own application.

#### Python

Install or update the Python SDK from
[PyPI](https://pypi.org/project/aidp-python-client/):

```bash
python3 -m pip install --upgrade aidp-python-client
```

You can skip this step if you already installed it with the Python CLI above.

#### TypeScript/Node.js

From your application's directory, install the TypeScript SDK from
[npm](https://www.npmjs.com/package/aidp-typescript-client):

```bash
npm install aidp-typescript-client@latest
```

This adds the SDK to your application's dependencies. Install it here even if
you previously installed the CLI globally.

#### Java

Add this dependency inside the `<dependencies>` section of your application's
`pom.xml`. Maven downloads the SDK and its dependencies from Maven Central when
you build your application.

Replace `latest_version` with the latest published version shown on the
[Java SDK package page](https://mvnrepository.com/artifact/com.oracle.aidataplatform/aidp-java-client).

```xml
<dependency>
  <groupId>com.oracle.aidataplatform</groupId>
  <artifactId>aidp-java-client</artifactId>
  <version>latest_version</version>
</dependency>
```

## Use the CLI or SDK manually

### Set up Oracle Cloud sign-in

The CLI and SDKs use your Oracle Cloud credentials to access AIDP. Before using
them, set up an OCI profile: a named set of connection and sign-in settings.
If you are working through an AI plugin, it guides you through this step.

Prefer short-lived, workload-scoped credentials for CI and runtime workloads.
Do not commit OCI configuration, private keys, session-token files, or
credential-bearing request bodies, and redact them from logs and support bundles.

For API-key authentication, create an OCI config profile once if you do not
already have one. OCI CLI can create the file for you if it is installed.
Existing OCI config profiles can be reused.

```bash
oci setup config
```

To sign in with a temporary session token, replace `<tenancy_name>` with your
Oracle Cloud tenancy name and use the region for your AIDP instance:

```bash
oci session authenticate \
  --profile-name DEFAULT \
  --region <oci_region> \
  --tenancy-name <tenancy_name>
```

### Use the CLI

To see available commands and how to use them:

```bash
aidp --help
aidp command-groups
aidp workspace
aidp workspace list --help
```

To list workspaces, replace `<oci_region>` with your instance's Oracle Cloud
region and `<ai_data_platform_ocid>` with its unique identifier (OCID). Your AIDP
administrator can help you find these values. This example uses the `DEFAULT`
profile and session-token sign-in from the previous step:

```bash
aidp \
  --auth security_token \
  --profile DEFAULT \
  --region <oci_region> \
  --instance-id <ai_data_platform_ocid> \
  workspace list
```

Use `--endpoint <service_endpoint>` only with a trusted endpoint; otherwise use
region-based endpoint resolution.

For APIs that accept a JSON body, write the body to a file and pass
`--body @file.json`. Do not commit sensitive bodies or expose them in debug logs.

### Use the SDK

Use an SDK to call AIDP from your application. It handles request authentication,
connections, and common error responses.

These short snippets show how to list workspaces after you have configured the
client and request. For complete, runnable code, see the
[examples](./examples/README.md).

Java:

```java
WorkspaceClient client = WorkspaceClient.builder().region(region).build(provider);
ListWorkspacesResponse response = client.listWorkspaces(request);
```

Python:

```python
client = WorkspaceClient(config, signer=signer)
response = client.list_workspaces(ai_data_platform_id, limit=10)
```

TypeScript/Node.js:

```ts
const client = new WorkspaceClient({ authenticationDetailsProvider: authProvider });
const response = await client.listWorkspaces({ aiDataPlatformId, limit: 10 });
```

For runnable notebook workflow samples, see [examples](./examples/README.md).

## Documentation and Help

For complete workflows, see the [examples](./examples/README.md) and
[CLI and SDK documentation](./docs/README.md).

For AI plugin changes and compatibility information, see the
[AIDP plugin release notes](./plugins/aidp/CHANGELOG.md).

For help finding your AIDP instance or getting access, contact your organization's
AIDP administrator. To report a bug or request an improvement to these tools, see
[how to open an issue](./CONTRIBUTING.md#opening-issues).

## Contributing

This project welcomes contributions from the community. Before submitting a pull
request, please [review our contribution guide](./CONTRIBUTING.md).

## Security

Please consult the [security guide](./SECURITY.md) for our responsible security
vulnerability disclosure process.

## License

Copyright (c) 2026, Oracle and/or its affiliates.

This software is licensed under the Universal Permissive License 1.0.
