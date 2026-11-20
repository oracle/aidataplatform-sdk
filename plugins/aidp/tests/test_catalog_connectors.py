# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
"""New connector payloads and private-input execution; no service requests."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sensitive_contract import BASELINE, INSTALLED_BASELINE, REPO, validate_body

CONTRACT = json.loads(BASELINE.with_name("catalog-connectors-contract.json").read_text())
SOURCES = CONTRACT["sources"]
SECRET = "SYNTHETIC_CONNECTOR_SECRET_75381"


class CatalogConnectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.counter = 0
        self.installed_models = json.loads(INSTALLED_BASELINE.read_text())["models"]
        self.repository_models = json.loads(BASELINE.read_text())["models"]

    def config(self, source):
        if source == "DATABRICKS_UNITY_CATALOG":
            return {"workspaceUrl": "https://workspace.example.com", "clientId": "public-client-id",
                    "remoteCatalog": "main"}
        value = {"host": "db.example.com"}
        if source == "POSTGRESQL":
            value.update(port="5432", databaseName="sales")
        return value

    def prepare(self, variant, source, operation, config, success=True):
        self.counter += 1
        config_path = self.root / f"config-{self.counter}.json"
        body_path = self.root / f"body-{self.counter}.json"
        config_path.write_text(json.dumps(config))
        original = config_path.read_bytes()
        skill = REPO / "plugins/aidp" / variant / "skills/aidp-cli"
        result = subprocess.run([sys.executable, str(skill / "scripts/ext-catalogs" / SOURCES[source]["folder"] / "prepare-body.py"),
                                 "--operation", operation, "--config", "@" + str(config_path), "--output", str(body_path)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0 if success else 1, result.stdout + result.stderr)
        self.assertNotIn(SECRET, result.stdout + result.stderr)
        self.assertEqual(config_path.read_bytes(), original)
        if success:
            self.assertEqual(body_path.stat().st_mode & 0o777, 0o600)
            return json.loads(body_path.read_text()), body_path
        self.assertFalse(body_path.exists())
        return json.loads(result.stdout), body_path

    def test_both_plugins_emit_exact_reviewed_create_and_full_test_payloads(self):
        for variant in ("codex", "claude"):
            for source, contract in SOURCES.items():
                for operation in ("create", "test-connection"):
                    with self.subTest(variant=variant, source=source, operation=operation):
                        config = self.config(source)
                        if operation == "create":
                            config["displayName"] = "chosen_catalog"
                        body, _ = self.prepare(variant, source, operation, config)
                        self.assertEqual(body["sourceType"], source)
                        self.assertEqual(set(body), {"sourceType", "connectionDetails"} |
                                         ({"displayName", "catalogType"} if operation == "create" else set()))
                        props = body["connectionDetails"]["connectionProperties"]
                        self.assertEqual(set(props), set(contract["requiredConnectionPropertyKeys"]))
                        for secret in contract["sensitiveConnectionPropertyKeys"]:
                            self.assertTrue(props[secret].startswith("{invisible_prompt_input:required:"))
                        if source == "DATABRICKS_UNITY_CATALOG":
                            self.assertEqual(props["DATABRICKS_UNITY_CATALOG_AUTH_TYPE"], contract["authenticationType"])
                            self.assertEqual(props["DATABRICKS_UNITY_CATALOG_OAUTH_CLIENT_ID"], config["clientId"])
                        else:
                            self.assertTrue(props[source + "_USERNAME"].startswith("{visible_prompt_input:required:"))
                        model = "CreateCatalogDetails" if operation == "create" else "CatalogTestConnectionDetails"
                        validate_body(self.installed_models, model, body)

    def test_sqlserver_default_optional_database_and_explicit_private_network_settings(self):
        for variant in ("codex", "claude"):
            body, _ = self.prepare(variant, "SQLSERVER", "test-connection", self.config("SQLSERVER"))
            props = body["connectionDetails"]["connectionProperties"]
            self.assertEqual(props["SQLSERVER_PORT"], SOURCES["SQLSERVER"]["defaultPort"])
            self.assertNotIn("SQLSERVER_DATABASE_NAME", props)
            for source in ("SQLSERVER", "POSTGRESQL"):
                config = {**self.config(source), "port": "15432", "databaseName": "selected", "workspaceKey": "private-route"}
                body, _ = self.prepare(variant, source, "test-connection", config)
                props = body["connectionDetails"]["connectionProperties"]
                self.assertEqual(props[source + "_PORT"], "15432")
                self.assertEqual(props[source + "_DATABASE_NAME"], "selected")
                self.assertEqual(props["WORKSPACE_KEY"], "private-route")

    def test_postgresql_requires_database_and_explicit_port(self):
        for field in ("host", "port", "databaseName"):
            config = self.config("POSTGRESQL")
            config.pop(field)
            self.prepare("codex", "POSTGRESQL", "test-connection", config, success=False)

    def test_stored_tests_prompt_for_only_the_replacement_and_reject_metadata_overrides(self):
        for variant in ("codex", "claude"):
            for source, contract in SOURCES.items():
                body, _ = self.prepare(variant, source, "test-connection", {"catalogKey": "stored-key"})
                self.assertEqual(set(body), {"key", "sourceType", "connectionDetails"})
                self.assertEqual(body["key"], "stored-key")
                props = body["connectionDetails"]["connectionProperties"]
                self.assertEqual(set(props), {contract["storedTestProperty"]})
                self.assertTrue(props[contract["storedTestProperty"]].startswith("{invisible_prompt_input:required:"))
                validate_body(self.installed_models, "CatalogTestConnectionDetails", body)
                self.prepare(variant, source, "create", {"catalogKey": "stored-key"}, success=False)
                self.prepare(variant, source, "test-connection", {"catalogKey": "stored-key", **self.config(source)}, success=False)

    def test_create_only_options_preserve_values_and_require_real_booleans(self):
        for source in SOURCES:
            for enabled in (True, False):
                config = {**self.config(source), "displayName": "chosen", "description": "",
                          "properties": {"isHarvestingRequired": "false"}, "isTestConnectionEnabled": enabled}
                body, _ = self.prepare("codex", source, "create", config)
                self.assertIs(body["isTestConnectionEnabled"], enabled)
                self.assertEqual(body["description"], "")
                self.assertEqual(body["properties"], config["properties"])
                validate_body(self.installed_models, "CreateCatalogDetails", body)
                self.prepare("codex", source, "test-connection", config, success=False)
            for value in (None, 0, "false"):
                self.prepare("codex", source, "create", {**self.config(source), "displayName": "chosen",
                                                       "isTestConnectionEnabled": value}, success=False)

    def test_inline_credentials_and_unreviewed_auth_ssl_and_wallet_options_are_rejected(self):
        for source in SOURCES:
            for field in ("password", "username", "clientSecret", "connectionProperties", "token",
                          "authenticationMethod", "sslEnabled", "walletFilePath"):
                self.prepare("codex", source, "test-connection", {**self.config(source), field: SECRET}, success=False)
        self.prepare("codex", "DATABRICKS_UNITY_CATALOG", "test-connection",
                     {**self.config("DATABRICKS_UNITY_CATALOG"), "workspaceKey": "unsupported"}, success=False)

    def test_ports_are_validated_before_any_credential_prompt(self):
        for source in ("SQLSERVER", "POSTGRESQL"):
            for port in ("0", "65536", "-1", "1.5", "5432x", "", 5432, "１２３"):
                self.prepare("codex", source, "test-connection", {**self.config(source), "port": port}, success=False)
            for port in ("1", "65535"):
                body, _ = self.prepare("codex", source, "test-connection", {**self.config(source), "port": port})
                self.assertEqual(body["connectionDetails"]["connectionProperties"][source + "_PORT"], port)

    def test_databricks_requires_public_fields_and_https_workspace_base_url(self):
        for field in ("workspaceUrl", "clientId", "remoteCatalog"):
            config = self.config("DATABRICKS_UNITY_CATALOG")
            config.pop(field)
            self.prepare("codex", "DATABRICKS_UNITY_CATALOG", "test-connection", config, success=False)
        for url in ("http://workspace.example.com", "https://", "https://user:secret@workspace.example.com",
                    "https://workspace.example.com/sql/path", "https://workspace.example.com?token=private",
                    "https://workspace.example.com/#fragment", "https://workspace.example.com:bad", "https://bad host"):
            self.prepare("codex", "DATABRICKS_UNITY_CATALOG", "test-connection",
                         {**self.config("DATABRICKS_UNITY_CATALOG"), "workspaceUrl": url}, success=False)

    def test_reviewed_repository_version_gap_is_explicit_and_new_sources_are_not_silently_coerced(self):
        self.assertEqual(set(CONTRACT["repositoryUnsupportedSources"]), set(SOURCES))
        for source in SOURCES:
            body, _ = self.prepare("codex", source, "test-connection", self.config(source))
            with self.assertRaisesRegex(AssertionError, "unsupported enum"):
                validate_body(self.repository_models, "CatalogTestConnectionDetails", body)
            validate_body(self.installed_models, "CatalogTestConnectionDetails", body)

    def test_private_execution_handoff_and_cleanup_for_full_and_stored_operations(self):
        from test_sensitive_contracts import load_helper
        load_helper("connector_execution_helper", "ext-catalogs/common/protected_catalog_templates.py")
        protected = sys.modules["protected_aidp"]
        for source in SOURCES:
            for operation, config in (("create", {**self.config(source), "displayName": "chosen"}),
                                      ("test-connection", self.config(source)),
                                      ("test-connection", {"catalogKey": "existing"})):
                for status, exit_code in ((202, 0), (409, 153)):
                    body, template = self.prepare("codex", source, operation, config)
                    original = template.read_bytes()
                    target = self.root / f"result-{self.counter}.json"
                    actual_paths = []
                    def fake_cli(args, **kwargs):
                        path = Path(args[args.index("--body") + 1][1:])
                        actual_paths.append(path)
                        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                        props = json.loads(path.read_text())["connectionDetails"]["connectionProperties"]
                        self.assertEqual(props[SOURCES[source]["storedTestProperty"]], SECRET)
                        if "catalogKey" not in config and source != "DATABRICKS_UNITY_CATALOG":
                            self.assertEqual(props[source + "_USERNAME"], "local-user")
                        self.assertNotIn("prompt_input", json.dumps(props))
                        kwargs["stdout"].write(("Response:\n" + json.dumps({"status": status}) + "\n").encode())
                        return SimpleNamespace(returncode=exit_code)
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output), patch.object(output, "isatty", return_value=True), \
                         patch.object(sys.stdin, "isatty", return_value=True), patch("builtins.input", return_value="local-user"), \
                         patch.object(protected.getpass, "getpass", return_value=SECRET), \
                         patch.object(protected.subprocess, "run", side_effect=fake_cli):
                        result = protected.main(["--output-file", str(target), "--", "aidp", "catalog", operation,
                                                 "--body", "@" + str(template)])
                    self.assertEqual(result, exit_code)
                    self.assertEqual(output.getvalue(), "Operation output handed off to AI agent. Ask it to continue.\n")
                    self.assertNotIn(SECRET, output.getvalue())
                    self.assertEqual(template.read_bytes(), original)
                    self.assertTrue(actual_paths)
                    self.assertTrue(all(not path.exists() and not path.parent.exists() for path in actual_paths))
                    self.assertEqual(target.stat().st_mode & 0o777, 0o600)
                    envelope = json.loads(target.read_text())
                    self.assertEqual(envelope["exitCode"], exit_code)
                    self.assertEqual(json.loads(envelope["stdout"].split("\n", 1)[1])["status"], status)
                    reader = REPO / "plugins/aidp/codex/skills/aidp-cli/scripts/read-protected-result.py"
                    consumed = subprocess.run([sys.executable, str(reader), str(target)], capture_output=True, text=True)
                    self.assertEqual(consumed.returncode, 0, consumed.stderr)
                    self.assertFalse(target.exists())

    def test_both_plugin_variants_ship_identical_helpers_and_source_references(self):
        codex = REPO / "plugins/aidp/codex/skills/aidp-cli"
        claude = REPO / "plugins/aidp/claude/skills/aidp-cli"
        paths = ["scripts/ext-catalogs/common/protected_catalog_templates.py", "references/ext-catalogs/common.md"]
        for contract in SOURCES.values():
            paths.extend((f"scripts/ext-catalogs/{contract['folder']}/prepare-body.py",
                          f"references/ext-catalogs/{contract['folder']}.md"))
        for path in paths:
            self.assertEqual((codex / path).read_bytes(), (claude / path).read_bytes(), path)


if __name__ == "__main__":
    unittest.main()
