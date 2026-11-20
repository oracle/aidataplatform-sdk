# AIDP Plugin Changelog

All notable changes to the AIDP plugins will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

These notes cover the AIDP plugins for AI assistants. Plugin versions are
independent of the AIDP SDK and CLI versions, which are documented in the
[project changelog](../../CHANGELOG.md).

## 1.0.0 - 2026-11-09

The first stable release brings guided setup and everyday AIDP operations to
Codex and Claude Code.

### Added

#### Guided first-time setup

- Get started by asking the installed AIDP plugin to set up the AIDP CLI.
  You do not need to install the SDK or CLI or configure Oracle Cloud sign-in
  yourself beforehand.
- Check required tools, help install missing prerequisites, and install matching
  Python SDK and CLI packages from the configured Python package index.
- Guide Oracle Cloud sign-in, AIDP instance selection, and an initial connection
  check by listing workspaces.
- Help diagnose installation, authentication, and connection problems.

#### Everyday work with AIDP

- Ask in everyday language to list or inspect AIDP resources, including
  workspaces, clusters, notebooks, workflows, catalogs, and volumes.
- Get help preparing and running commands to create, update, or delete resources,
  with confirmation where required by the workflow.
- Remember validated connection settings and recently used instances so users
  can select an instance and continue without repeating initial installation
  and configuration. Connection checks and sign-in renewal may still be needed.
- Use guided handling for sensitive inputs, including credentials and catalog
  connection settings.

### Requirements and compatibility

- Install the plugin for your assistant: [Codex](./codex) or
  [Claude Code](./claude).
- Have access to an AIDP instance and an Oracle Cloud account with permission
  to perform the requested operations.
- The plugin operates through the Python AIDP CLI and SDK. Setup requires Python
  3.9 or later, pip, OCI CLI, AIDP CLI 5.1.0 or later, and a matching Python SDK
  version. The guided setup checks these requirements and helps resolve gaps.
- Windows workflows use PowerShell; macOS and Linux workflows use a POSIX shell.
