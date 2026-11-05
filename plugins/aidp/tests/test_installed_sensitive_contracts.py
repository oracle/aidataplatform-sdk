"""Live installed-package checks; no authentication or network requests."""
from __future__ import annotations

import copy
import contextlib
from importlib import metadata
import json
import io
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import sensitive_contract as contract
from test_sensitive_contracts import load_helper


class InstalledSensitiveContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.actual, cls.version = contract.collect_installed_contract()

    def test_installed_sdk_and_cli_match_the_separately_reviewed_release_contract(self):
        contract.check_contract(baseline=contract.INSTALLED_BASELINE, actual=self.actual)

    def test_installed_source_types_exactly_match_skill_sources_and_cli_help(self):
        helper = load_helper("installed_catalog_helper", "ext-catalogs/common/protected_catalog_templates.py")
        original = json.loads((contract.REPO / "plugins/aidp/tests/fixtures/protected_catalog_bodies.json").read_text())
        supported = set(original) | set(helper.TYPES)
        for name in ("CreateCatalogDetails", "CatalogTestConnectionDetails", "Catalog", "CatalogSummary"):
            self.assertEqual(set(self.actual["models"][name]["fields"]["sourceType"]["enum"]), supported)
        for operation in ("create", "test-connection"):
            result = subprocess.run([sys.executable, "-m", "aidp_cli.main", "catalog", operation, "--help"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("GOOGLE_BIGQUERY", result.stdout)

    def test_installed_python_models_accept_bigquery_requests(self):
        from aidp_python_client.aidataplatform_dp.models import (CatalogConnectionDetails, CatalogTestConnectionDetails,
                                                               CreateCatalogDetails, CreateConnectionDetails)
        props = {"GOOGLE_BIGQUERY_OAUTH_PVT_KEY": "{textof:/synthetic/key.json}"}
        created = CreateCatalogDetails(display_name="synthetic", catalog_type="EXTERNAL", source_type="GOOGLE_BIGQUERY",
                                       connection_details=CreateConnectionDetails(connection_properties=props))
        tested = CatalogTestConnectionDetails(source_type="GOOGLE_BIGQUERY",
                                              connection_details=CatalogConnectionDetails(connection_properties=props))
        self.assertEqual(created.source_type, "GOOGLE_BIGQUERY")
        self.assertEqual(tested.source_type, "GOOGLE_BIGQUERY")

    def test_stale_installed_cli_manifest_cannot_hide_a_new_sdk_source(self):
        real_sdk, real_cli = metadata.distribution("aidp-python-client"), metadata.distribution("aidp-cli")
        manifest = json.loads(Path(real_cli.locate_file("aidp_cli/operation_manifest.json")).read_text())
        def remove_source(value):
            if isinstance(value, dict):
                return {key: remove_source(item) for key, item in value.items()}
            if isinstance(value, list):
                return [remove_source(item) for item in value if item != "GOOGLE_BIGQUERY"]
            return value
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(remove_source(manifest)))
            fake_cli = SimpleNamespace(version=real_cli.version, locate_file=lambda name:
                path if name == "aidp_cli/operation_manifest.json" else real_cli.locate_file(name))
            with patch.object(contract.metadata, "distribution", side_effect=lambda name: real_sdk if name == "aidp-python-client" else fake_cli):
                with self.assertRaisesRegex(ValueError, "Installed CLI manifest differs from SDK"):
                    contract.collect_installed_contract()

    def test_mismatched_or_missing_installed_packages_block_release(self):
        fake_sdk = SimpleNamespace(version="5.1.0.36.45595")
        fake_cli = SimpleNamespace(version="5.1.0.older")
        with patch.object(contract.metadata, "distribution", side_effect=[fake_sdk, fake_cli]):
            with self.assertRaisesRegex(ValueError, "Installed SDK/CLI versions differ"):
                contract.collect_installed_contract()
        with patch.object(contract.metadata, "distribution", side_effect=metadata.PackageNotFoundError("aidp-cli")):
            with self.assertRaises(metadata.PackageNotFoundError):
                contract.collect_installed_contract()

    def test_release_gate_never_falls_back_to_repository_when_installed_packages_are_missing(self):
        import run_sensitive_contracts as runner
        output, error = io.StringIO(), io.StringIO()
        with patch.object(runner, "check_contract", return_value=self.actual), patch.object(
                runner, "collect_installed_contract", side_effect=metadata.PackageNotFoundError("aidp-cli")), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            self.assertEqual(runner.main([]), 1)
        self.assertIn("RELEASE BLOCKED", error.getvalue())
        self.assertNotIn("Repository-only", output.getvalue())
        self.assertNotIn("validation passed", output.getvalue())
    def test_installed_field_enum_and_response_drift_still_fail_with_paths(self):
        for model, field in (("CreateCatalogDetails", "newSecret"), ("Agent", "newResponseField")):
            changed = copy.deepcopy(self.actual)
            changed["models"][model]["fields"][field] = {"type": "str", "required": False, "enum": []}
            with self.assertRaisesRegex(AssertionError, "ADDED contract.models." + model + ".fields." + field):
                contract.check_contract(baseline=contract.INSTALLED_BASELINE, actual=changed)
        changed = copy.deepcopy(self.actual)
        changed["models"]["Auth"]["fields"]["authType"]["enum"].append("NEW_AUTH")
        with self.assertRaisesRegex(AssertionError, "contract.models.Auth.fields.authType.enum"):
            contract.check_contract(baseline=contract.INSTALLED_BASELINE, actual=changed)

    def test_installed_agent_llm_credential_reference_and_public_session_fields_are_preserved(self):
        helper = load_helper("installed_agent_helper", "common/protected_resource_templates.py")
        reference = {"displayName": "llm_keys", "secretKey": "api_token"}
        metadata_body = {"displayName": "synthetic", "pathInfo": "/Shared", "diagram": {"nodes": {"agent": {
            "key": "agent", "type": "AGENT", "llm": {"type": "THIRD_PARTY", "provider": "openai", "modelId": "chosen",
              "apiKeyCredstoreRef": reference, "llmConnectionSettings": {"timeout": 30.0, "maxRetries": 1}}}}},
            "sessionConfig": {"automaticSummarizationConfig": {"isEnabled": False},
                              "longTermMemoryConfig": {"isEnabled": False},
                              "retentionConfig": {"isRetentionPolicyEnabled": True, "breachAction": "DELETE_FIFO"}}}
        # Use the exact installed name of the existing retention configuration.
        fields = self.actual["models"]["SessionConfiguration"]["fields"]
        retention_name = next(name for name, value in fields.items() if value["type"] == "SessionRetentionConfiguration")
        metadata_body["sessionConfig"][retention_name] = metadata_body["sessionConfig"].pop("retentionConfig")
        for operation in ("create", "update"):
            body = copy.deepcopy(metadata_body)
            if operation == "update":
                body.pop("pathInfo")
            args = SimpleNamespace(operation=operation, type=None, private_key_path=None, secret_key=[], replace_secrets=False)
            transformed = helper.agents(copy.deepcopy(body), args)
            self.assertEqual(transformed, body)
            self.assertNotIn("prompt_input", json.dumps(transformed))
            contract.validate_body(self.actual["models"], "CreateAgentDetails" if operation == "create" else "UpdateAgentDetails", transformed)


if __name__ == "__main__":
    unittest.main()
