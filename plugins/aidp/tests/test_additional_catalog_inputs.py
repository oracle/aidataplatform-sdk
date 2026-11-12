# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "codex/skills/aidp-cli"
SOURCES = {"MYSQL": "mysql", "DB2": "db2", "AZURE_SQLSERVER": "azure-sqlserver", "SNOWFLAKE": "snowflake"}
spec = importlib.util.spec_from_file_location("additional_catalog_templates", SKILL / "scripts/ext-catalogs/common/protected_catalog_templates.py")
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)
import protected_aidp as protected

SECRET = "PRIVATE_TEST_CANARY_2294"


class AdditionalCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.counter = 0

    def config(self, source):
        value = {"host": "chosen.example", "port": "1234"}
        if source != "MYSQL":
            value["databaseName"] = "SALES"
        if source == "SNOWFLAKE":
            value.update(authenticationMethod="Basic", warehouse="CHOSEN_WH")
        return value

    def prepare(self, source, operation, config, success=True):
        self.counter += 1
        path = self.root / f"config-{self.counter}.json"
        output = self.root / f"body-{self.counter}.json"
        path.write_text(json.dumps(config))
        original = path.read_bytes()
        result = subprocess.run([sys.executable, str(SKILL / "scripts/ext-catalogs" / SOURCES[source] / "prepare-body.py"),
                                 "--operation", operation, "--config", "@" + str(path), "--output", str(output)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0 if success else 1, result.stdout + result.stderr)
        self.assertEqual(path.read_bytes(), original)
        self.assertNotIn(SECRET, result.stdout + result.stderr)
        if success:
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            return json.loads(output.read_text()), output
        self.assertFalse(output.exists())
        return json.loads(result.stdout), output

    def test_all_four_create_and_full_test_shapes_and_required_prompts(self):
        for source in SOURCES:
            for operation in ("create", "test-connection"):
                config = self.config(source)
                if operation == "create":
                    config.update(displayName="chosen_catalog", description="Chosen description", properties={"isHarvestingRequired": "false"})
                body, _ = self.prepare(source, operation, config)
                self.assertEqual(body["sourceType"], source)
                self.assertEqual("catalogType" in body, operation == "create")
                self.assertEqual("displayName" in body, operation == "create")
                props = body["connectionDetails"]["connectionProperties"]
                user = "user.name" if source == "DB2" else source + "_USERNAME"
                password = "password" if source == "DB2" else source + "_PASSWORD"
                self.assertTrue(props[user].startswith("{visible_prompt_input:required:"))
                self.assertTrue(props[password].startswith("{invisible_prompt_input:required:"))
                self.assertNotIn("wallet", json.dumps(props).lower())
                if operation == "create":
                    self.assertEqual(body["properties"], {"isHarvestingRequired": "false"})

    def test_mysql_database_optional_and_db2_exact_property_names(self):
        body, _ = self.prepare("MYSQL", "test-connection", self.config("MYSQL"))
        self.assertNotIn("MYSQL_DATABASE_NAME", body["connectionDetails"]["connectionProperties"])
        config = self.config("DB2"); config.update(sslEnabled=False, workspaceKey="workspace")
        body, _ = self.prepare("DB2", "test-connection", config)
        self.assertEqual(set(body["connectionDetails"]["connectionProperties"]),
                         {"host", "port", "database.name", "user.name", "password", "ssl.enabled", "WORKSPACE_KEY"})
        self.assertEqual(body["connectionDetails"]["connectionProperties"]["ssl.enabled"], "false")

    def test_database_and_snowflake_warehouse_are_required(self):
        for source in ("DB2", "AZURE_SQLSERVER", "SNOWFLAKE"):
            config = self.config(source); config.pop("databaseName")
            self.prepare(source, "test-connection", config, success=False)
        config = self.config("SNOWFLAKE"); config.pop("warehouse")
        self.prepare("SNOWFLAKE", "test-connection", config, success=False)

    def test_ssl_mapping_and_invalid_port_and_unknown_fields(self):
        for source, key in (("MYSQL", "MYSQL_SSL_ENABLED"), ("AZURE_SQLSERVER", "AZURE_SQLSERVER_SSL_ENABLED")):
            config = self.config(source); config["sslEnabled"] = True
            body, _ = self.prepare(source, "test-connection", config)
            self.assertEqual(body["connectionDetails"]["connectionProperties"][key], "true")
        for field, value in (("port", "65536"), ("port", 3306), ("sslEnabled", "false"),
                             ("accountPassword", SECRET), ("username", SECRET), ("walletFilePath", "/wallet.zip")):
            config = self.config("MYSQL"); config[field] = value
            self.prepare("MYSQL", "test-connection", config, success=False)

    def test_snowflake_keypair_passphrase_modes_and_no_account_password(self):
        for encrypted in (True, False, None):
            config = self.config("SNOWFLAKE")
            config.update(authenticationMethod="KeyPair", privateKeyFilePath="/not-accessed/local-key.pem", role="CHOSEN_ROLE")
            if encrypted is not None:
                config["privateKeyEncrypted"] = encrypted
            for operation in ("create", "test-connection"):
                current = dict(config)
                if operation == "create":
                    current["displayName"] = "snowflake"
                body, _ = self.prepare("SNOWFLAKE", operation, current)
                props = body["connectionDetails"]["connectionProperties"]
                self.assertEqual(props["SNOWFLAKE_PRIVATE_KEY_CONTENT"], "{textof:/not-accessed/local-key.pem}")
                self.assertNotIn("SNOWFLAKE_PRIVATE_KEY_FILE", props)
                self.assertNotIn("SNOWFLAKE_PASSWORD", props)
                if encrypted is False:
                    self.assertNotIn("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE", props)
                else:
                    self.assertIn(":required:" if encrypted else ":optional:", props["SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"])

    def test_snowflake_invalid_and_mixed_auth_is_rejected(self):
        for fields in ({"authenticationMethod": "OAuth"}, {"privateKeyFilePath": "/key"},
                       {"authenticationMethod": "KeyPair"}, {"sslEnabled": True},
                       {"authenticationMethod": "KeyPair", "privateKeyFilePath": "/key", "privateKeyEncrypted": "true"}):
            config = self.config("SNOWFLAKE"); config.update(fields)
            self.prepare("SNOWFLAKE", "test-connection", config, success=False)

    def test_stored_password_tests_and_keypair_shortcut_rejection(self):
        for source in SOURCES:
            config = {"catalogKey": "existing-key"}
            if source == "SNOWFLAKE":
                config["authenticationMethod"] = "Basic"
            body, _ = self.prepare(source, "test-connection", config)
            self.assertEqual(body["key"], "existing-key")
            key = "password" if source == "DB2" else source + "_PASSWORD"
            self.assertEqual(set(body["connectionDetails"]["connectionProperties"]), {key})
            self.prepare(source, "create", config, success=False)
        result, _ = self.prepare("SNOWFLAKE", "test-connection", {"catalogKey": "existing-key", "authenticationMethod": "KeyPair"}, success=False)
        self.assertEqual(result["errorCode"], "KEYPAIR_FULL_TEST_REQUIRED")

    def test_key_inspector_only_exposes_envelope_metadata(self):
        inspector = SKILL / "scripts/ext-catalogs/snowflake/inspect-private-key.py"
        for label, encrypted in (("PRIVATE KEY", False), ("ENCRYPTED PRIVATE KEY", True)):
            path = self.root / "private.pem"
            path.write_text("-----BEGIN " + label + "-----\n" + SECRET + "\n-----END " + label + "-----\n")
            result = subprocess.run([sys.executable, str(inspector), "--key-path", str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout), {"ok": True, "encrypted": encrypted, "format": "PKCS8"})
            self.assertNotIn(SECRET, result.stdout + result.stderr)
        path.write_text(SECRET)
        result = subprocess.run([sys.executable, str(inspector), "--key-path", str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(SECRET, result.stdout + result.stderr)

    def test_generated_templates_execute_with_handoff_and_cleanup(self):
        scenarios = [(source, self.config(source)) for source in SOURCES]
        key = self.root / "private.pem"; key.write_text("SYNTHETIC_PEM_" + SECRET)
        scenarios.append(("SNOWFLAKE", dict(self.config("SNOWFLAKE"), authenticationMethod="KeyPair",
                                            privateKeyFilePath=str(key), privateKeyEncrypted=True)))
        for index, (source, config) in enumerate(scenarios):
            body, template = self.prepare(source, "test-connection", config)
            original = template.read_bytes()
            target = self.root / f"result-{index}.json"
            actuals = []
            def fake_cli(args, **kwargs):
                path = Path(args[args.index("--body") + 1][1:]); actuals.append(path)
                resolved = json.loads(path.read_text())
                props = resolved["connectionDetails"]["connectionProperties"]
                self.assertEqual(props["user.name" if source == "DB2" else source + "_USERNAME"], "local-user")
                if config.get("authenticationMethod") == "KeyPair":
                    self.assertEqual(props["SNOWFLAKE_PRIVATE_KEY_CONTENT"], "SYNTHETIC_PEM_" + SECRET)
                    self.assertEqual(props["SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"], SECRET)
                else:
                    self.assertEqual(props["password" if source == "DB2" else source + "_PASSWORD"], SECRET)
                kwargs["stdout"].write(b'Response:\n{"status":200}\n')
                return SimpleNamespace(returncode=0)
            out = io.StringIO()
            with contextlib.redirect_stdout(out), patch.object(out, "isatty", return_value=True), \
                 patch.object(sys.stdin, "isatty", return_value=True), patch("builtins.input", return_value="local-user"), \
                 patch.object(protected.getpass, "getpass", return_value=SECRET), patch.object(protected.subprocess, "run", side_effect=fake_cli):
                code = protected.main(["--output-file", str(target), "--", "aidp", "catalog", "test-connection", "--body", "@" + str(template)])
            self.assertEqual(code, 0)
            self.assertEqual(out.getvalue(), "Operation output handed off to AI agent. Ask it to continue.\n")
            self.assertEqual(template.read_bytes(), original)
            self.assertTrue(all(not path.exists() for path in actuals))
            consumed = subprocess.run([sys.executable, str(SKILL / "scripts/read-protected-result.py"), str(target)], capture_output=True, text=True)
            self.assertEqual(consumed.returncode, 0)
            self.assertEqual(json.loads(consumed.stdout)["stdout"], 'Response:\n{"status":200}\n')
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
