from __future__ import annotations

import ast
import copy
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sensitive_contract import (BASELINE, INSTALLED_BASELINE, REPO, check_contract, collect_contract,
                                differences, validate_body)

SKILL = REPO / "plugins/aidp/codex/skills/aidp-cli"


def load_helper(name, relative):
    sys.path.insert(0, str((SKILL / "scripts" / relative).parent))
    spec = importlib.util.spec_from_file_location(name, SKILL / "scripts" / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SensitiveContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = collect_contract()
        cls.models = cls.contract["models"]
        cls.installed_models = json.loads(INSTALLED_BASELINE.read_text())["models"]

    def test_reviewed_input_and_output_contract_has_no_drift(self):
        self.assertEqual(differences(json.loads(BASELINE.read_text()), self.contract), [],
                         "SDK/CLI drift: run run_sensitive_contracts.py for field-level diagnostics")

    def test_new_removed_changed_sdk_and_cli_contracts_fail_release(self):
        # Real source mutations prove that extraction, traversal and comparison
        # notice drift; these are not only comparisons of hand-written dicts.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in ("aidp-python-client/src", "aidp-cli/aidp-py-cli/scripts",
                             "aidp-cli/aidp-py-cli/src", "aidp-typescript-client/lib/model",
                             "aidp-typescript-client/lib/response"):
                shutil.copytree(REPO / relative, root / relative, ignore=shutil.ignore_patterns("__pycache__"))
            model = root / "aidp-python-client/src/aidp_python_client/aidataplatform_dp/models/create_agent_details.py"
            text = model.read_text().replace("'description': 'str',", "'new_secret': 'str',")
            text = text.replace("'description': 'description',", "'new_secret': 'newSecret',")
            text = text.replace("'display_name': 'str',", "'display_name': 'int',")
            text = text.replace('**[Required]** Gets the path_info', 'Gets the path_info')
            model.write_text(text)
            subtype = root / "aidp-python-client/src/aidp_python_client/aidataplatform_dp/models/setting_data.py"
            subtype.write_text(subtype.read_text().replace('allowed_values = ["IAM_USER_CREDENTIAL",', 'allowed_values = ["NEW_SETTING", "IAM_USER_CREDENTIAL",'))
            response = root / "aidp-python-client/src/aidp_python_client/aidataplatform_dp/models/agent.py"
            response.write_text(response.read_text().replace("'description': 'str',", "'description': 'bool',"))
            auth = root / "aidp-python-client/src/aidp_python_client/aidataplatform_dp/models/auth.py"
            auth.write_text(auth.read_text().replace('allowed_values = ["NO_AUTH",', 'allowed_values = ["NEW_AUTH", "NO_AUTH",'))
            enum = root / "aidp-typescript-client/lib/model/mysql-external-catalog-connection-property-key.ts"
            enum.write_text(enum.read_text().replace('export enum MysqlExternalCatalogConnectionPropertyKey {', 'export enum MysqlExternalCatalogConnectionPropertyKey {\n NewSecret = "MYSQL_NEW_SECRET",'))
            cli = root / "aidp-cli/aidp-py-cli/src/aidp_cli/main.py"
            cli.write_text(cli.read_text().replace('"headers": dict(getattr(response, "headers", {}) or {}),', '"changedHeaders": dict(getattr(response, "headers", {}) or {}),'))
            models = root / "aidp-python-client/src/aidp_python_client/aidataplatform_dp/models"
            llm = models / "third_party_llm_config.py"
            llm.write_text(llm.read_text().replace("**[Required]** Gets the api_key_credstore_ref", "Gets the api_key_credstore_ref"))
            memory = models / "long_term_memory_configuration.py"
            memory.write_text(memory.read_text().replace("'share_between_chat_threads': 'bool'", "'share_between_chat_threads': 'str'"))
            with self.assertRaisesRegex(AssertionError, "Sensitive-input SDK/CLI contract drift") as failure:
                check_contract(root)
            message = str(failure.exception)
            for expected in ("ADDED contract.models.CreateAgentDetails.fields.newSecret",
                             "REMOVED contract.models.CreateAgentDetails.fields.description",
                             "fields.displayName.type", "fields.pathInfo.required",
                             "contract.models.SettingData.fields.type.enum",
                             "contract.models.Agent.fields.description.type",
                             "contract.models.Auth.fields.authType.enum",
                             "contract.models.ThirdPartyLlmConfig.fields.apiKeyCredstoreRef.required",
                             "contract.models.LongTermMemoryConfiguration.fields.shareBetweenChatThreads.type",
                             "catalogPropertyEnums.MysqlExternalCatalogConnectionPropertyKey.NewSecret",
                             "contract.cli.print_response"):
                self.assertIn(expected, message)
            client = root / "aidp-python-client/src/aidp_python_client/aidataplatform_dp/catalog_client.py"
            client.write_text(client.read_text().replace('def create_catalog(', 'def renamed_create_catalog('))
            with self.assertRaisesRegex(ValueError, "SDK operation missing: create_catalog"):
                collect_contract(root)

    def test_missing_sdk_source_and_operation_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises((FileNotFoundError, RuntimeError)):
                collect_contract(Path(directory))

    def test_current_sdk_rejects_extra_fields_bad_enums_and_missing_required_input(self):
        for value, message in (({"displayName": "a", "pathInfo": "/Shared", "newSecret": "synthetic"}, "newSecret"),
                               ({"displayName": "a", "pathInfo": "/Shared", "type": "NEW_TYPE"}, "unsupported enum"),
                               ({"displayName": "a"}, "missing required")):
            with self.subTest(value=value), self.assertRaisesRegex(AssertionError, message):
                validate_body(self.models, "CreateAgentDetails", value)

    def test_credential_and_user_setting_helpers_emit_current_sdk_wire_shapes(self):
        helper = load_helper("contract_resource_helper", "common/protected_resource_templates.py")
        def options(kind=None, operation="create", **kwargs):
            return SimpleNamespace(type=kind, operation=operation, replace_secrets=operation == "update",
                                   secret_key=["synthetic"], private_key_path="/synthetic/key.pem", current_setting=None, **kwargs)
        values = {
            "SECRET_TOKEN": {},
            "SERVICE_ACCOUNT": {"userId": "u", "tenancy": "t", "region": "r", "fingerprint": "f", "isReadOnly": False},
            "VAULT_REFERENCE": {"secretId": "ocid1.synthetic"},
        }
        enum = set(self.models["CreateDataLakeCredentialDetails"]["fields"]["type"]["enum"])
        self.assertEqual(set(values), enum, "Credential enum changed: classify every variant before release")
        for kind, details in values.items():
            for operation in ("create", "update"):
                body = helper.credentials({"displayName": "synthetic", "credentialDetails": dict(details)}, options(kind, operation))
                validate_body(self.models, ("Create" if operation == "create" else "Update") + "DataLakeCredentialDetails", body)
        self.assertEqual(set(helper.SETTING_PUBLIC_FIELDS), {"GIT_ACCOUNT", "IAM_USER_CREDENTIAL"})
        for kind, data in (("GIT_ACCOUNT", {"providerName": "GITHUB"}),
                           ("IAM_USER_CREDENTIAL", {"userId": "u", "tenancy": "t", "region": "r", "fingerprint": "f"})):
            for operation in ("create", "update"):
                body = helper.user_settings({"name": "synthetic", "isDefault": True, "data": dict(data)}, options(kind, operation))
                validate_body(self.models, ("Create" if operation == "create" else "Update") + "UserSettingDetails", body)
        # SettingData is shared with admin APIs; its enum is not an endpoint
        # allowlist. Keep this deliberate exclusion reviewed and explicit.
        for operation in ("create", "update"):
            args = options("OAUTH", operation)
            with self.assertRaises(helper.ProtectedError):
                helper.user_settings({"name": "synthetic", "isDefault": False, "data": {"type": "OAUTH"}}, args)

    def test_all_catalog_protected_bodies_emit_current_sdk_wire_shapes(self):
        original = json.loads((REPO / "plugins/aidp/tests/fixtures/protected_catalog_bodies.json").read_text())
        modern = load_helper("contract_modern_catalog", "ext-catalogs/common/protected_catalog_templates.py")
        supported = set(original) | set(modern.TYPES)
        for name in ("CreateCatalogDetails", "CatalogTestConnectionDetails", "Catalog"):
            self.assertEqual(supported, set(self.models[name]["fields"]["sourceType"]["enum"]),
                             f"{name}.sourceType changed: add/review source helpers and references")
            self.assertEqual(supported, set(self.installed_models[name]["fields"]["sourceType"]["enum"]),
                             f"Installed {name}.sourceType changed: review every supported source")
        enum_names = {"ADW": "Adw", "ALH": "Alh", "ATP": "Atp", "ORACLE": "Oracle", "EXADATA": "Exadata",
                      "KAFKA": "Kafka", "MYSQL": "Mysql", "DB2": "Db2", "AZURE_SQLSERVER": "SqlServerOnAzure",
                      "SNOWFLAKE": "Snowflake", "ORACLE_ANALYTICS": "Oac", "GOOGLE_BIGQUERY": "GoogleBigquery"}
        # Reviewed shared networking context already used by the skills. The
        # SDK wire type is dict(str, str), not a closed per-source enum map.
        # Keep this one shared key explicit; never accept arbitrary extra keys.
        shared_keys = {self.contract["catalogPropertyEnums"]["ExadataExternalCatalogConnectionPropertyKey"]["WorkspaceKey"]}
        for source in supported:
            for operation in ("create", "test-connection"):
                if source in modern.TYPES:
                    config = {"host": "db.example", "port": "1234", "databaseName": "SALES"}
                    if source == "GOOGLE_BIGQUERY":
                        config = {"host": "https://www.googleapis.com/bigquery/v2", "port": "443", "projectId": "example-project",
                                  "serviceAccountEmail": "reader@example-project.iam.gserviceaccount.com", "privateKeyFilePath": "/synthetic/key.json"}
                    if operation == "create":
                        config["displayName"] = "synthetic"
                    if source == "SNOWFLAKE":
                        config.update(authenticationMethod="Basic", warehouse="WH")
                    body = modern.template(source, operation, config)
                else:
                    body = json.loads(json.dumps(original[source]))
                    if operation == "test-connection":
                        body.pop("displayName")
                        body.pop("catalogType")
                model_name = "CreateCatalogDetails" if operation == "create" else "CatalogTestConnectionDetails"
                validate_body(self.models, model_name, body)
                validate_body(self.installed_models, model_name, body)
                properties = body["connectionDetails"]["connectionProperties"]
                if source == "GOOGLE_BIGQUERY":
                    keys = json.loads(BASELINE.with_name("google-bigquery-key-contract.json").read_text())
                    allowed = set(keys["requiredConnectionPropertyKeys"]) | set(keys["optionalSharedConnectionPropertyKeys"])
                    sdk_keys = set(self.contract["catalogPropertyEnums"]["GoogleBigqueryExternalCatalogConnectionPropertyKey"].values())
                    self.assertEqual(sdk_keys, set(keys["requiredConnectionPropertyKeys"]))
                else:
                    allowed = set(self.contract["catalogPropertyEnums"][enum_names[source] + "ExternalCatalogConnectionPropertyKey"].values()) | shared_keys
                self.assertFalse(set(properties) - allowed,
                                 f"{source} helper emits keys absent from SDK: {sorted(set(properties) - allowed)}")

    def test_polymorphic_llm_contract_preserves_inherited_fields_and_required_references(self):
        # Exercises the manifest helpers' method-list interface as well as the
        # extractor's separate inheritance merge, without weakening either.
        self.assertEqual(self.models["BaseLlmConfig"]["variants"], {
            "type=OCI_GEN_AI": "LlmConfig", "type=THIRD_PARTY": "ThirdPartyLlmConfig"})
        third_party = self.models["ThirdPartyLlmConfig"]
        self.assertEqual(third_party["bases"], ["BaseLlmConfig"])
        self.assertEqual(third_party["fields"]["type"]["enum"], ["OCI_GEN_AI", "THIRD_PARTY"])
        self.assertTrue(third_party["fields"]["provider"]["required"])
        self.assertTrue(third_party["fields"]["apiKeyCredstoreRef"]["required"])
        reference = self.models["CredentialV2NameAndSecretKey"]["fields"]
        self.assertTrue(reference["displayName"]["required"])
        self.assertFalse(reference["secretKey"]["required"])
        for provider in ("openai", "anthropic", "gemini"):
            validate_body(self.models, "BaseLlmConfig", {
                "type": "THIRD_PARTY", "provider": provider,
                "apiKeyCredstoreRef": {"displayName": "chosen-credential"},
                "modelId": "chosen-model", "endpointUrl": "https://model.example"})
        invalid = [
            ({"type": "THIRD_PARTY", "provider": "openai"}, "apiKeyCredstoreRef"),
            ({"type": "THIRD_PARTY", "apiKeyCredstoreRef": {"displayName": "chosen"}}, "provider"),
            ({"type": "THIRD_PARTY", "provider": "other", "apiKeyCredstoreRef": {"displayName": "chosen"}}, "unsupported enum"),
            ({"type": "THIRD_PARTY", "provider": "openai", "apiKeyCredstoreRef": {"secretKey": "label"}}, "displayName"),
            ({"type": "THIRD_PARTY", "provider": "openai", "apiKeyCredstoreRef": {"displayName": "chosen", "apiKey": "synthetic"}}, "apiKey"),
        ]
        for body, diagnostic in invalid:
            with self.subTest(body=body), self.assertRaisesRegex(AssertionError, diagnostic):
                validate_body(self.models, "BaseLlmConfig", body)

    def test_agent_helpers_preserve_reviewed_model_references_and_session_policy(self):
        for variant in ("codex", "claude"):
            path = REPO / "plugins/aidp" / variant / "skills/aidp-cli/scripts/common/protected_resource_templates.py"
            spec = importlib.util.spec_from_file_location("reviewed_agent_" + variant, path)
            helper = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(helper)
            metadata = {"displayName": "synthetic", "pathInfo": "/Shared", "diagram": {"nodes": {"agent": {
                "key": "agent", "type": "AGENT", "llm": {"type": "THIRD_PARTY", "provider": "anthropic",
                "modelId": "chosen", "apiKeyCredstoreRef": {"displayName": "existing", "secretKey": "label"},
                "llmConnectionSettings": {"timeout": 30.0, "maxRetries": 0, "defaultQuery": {"chosen": "value"}}}}}},
                "sessionConfig": {"automaticSummarizationConfig": {"isEnabled": False},
                    "longTermMemoryConfig": {"isEnabled": False, "shareBetweenChatThreads": False,
                        "llmConfig": {"type": "OCI_GEN_AI", "modelId": "chosen-oci-model"}},
                    "sessionRetentionConfig": {"isRetentionPolicyEnabled": False, "breachAction": "DELETE_FIFO"}}}
            for operation in ("create", "update"):
                body = copy.deepcopy(metadata)
                if operation == "update":
                    body.pop("pathInfo")
                args = SimpleNamespace(operation=operation, type=None, private_key_path=None, secret_key=[], replace_secrets=False)
                actual = helper.agents(copy.deepcopy(body), args)
                self.assertEqual(actual, body)
                self.assertNotIn("prompt_input", json.dumps(actual))
                model_name = "CreateAgentDetails" if operation == "create" else "UpdateAgentDetails"
                validate_body(self.models, model_name, actual)
                for response_field, value in (("a2aEndpointUrl", "https://agent.example"), ("deploymentState", {"PROD": "ACTIVE"})):
                    with self.subTest(variant=variant, operation=operation, field=response_field):
                        with self.assertRaisesRegex(AssertionError, response_field):
                            validate_body(self.models, model_name, {**actual, response_field: value})

    def test_agent_helper_emits_typed_sdk_container_and_preserves_protected_auth(self):
        helper = load_helper("contract_agent_helper", "common/protected_resource_templates.py")
        for operation in ("create", "update"):
            args = SimpleNamespace(operation=operation, type=None, private_key_path=None,
                                   secret_key=[], replace_secrets=operation == "update")
            metadata = {"displayName": "synthetic", "diagram": {
                "toolsMap": {"http": {"toolType": "HTTP", "toolConfig": {"auth": {"authType": "BEARER_TOKEN"}}}}}}
            if operation == "create":
                metadata["pathInfo"] = "/Shared"
            body = helper.agents(metadata, args)
            validate_body(self.models, "CreateAgentDetails" if operation == "create" else "UpdateAgentDetails", body)
            self.assertIn("invisible_prompt_input", json.dumps(body))

    def test_cli_success_and_error_output_envelopes(self):
        path = REPO / "aidp-cli/aidp-py-cli/src/aidp_cli/main.py"
        tree = ast.parse(path.read_text())
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name in {"print_response", "print_error_response"}]
        namespace = {"Any": object, "json": json, "sys": sys, "to_dict": lambda value: value}
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), "exec"), namespace)
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            namespace["print_response"](SimpleNamespace(data={"key": "synthetic"}, headers={"etag": "version"}, status=200))
            namespace["print_error_response"]({"status": 409, "code": "Conflict", "message": "synthetic", "opc-request-id": "request"})
        self.assertTrue(output.getvalue().startswith("Response:\n"))
        self.assertEqual(json.loads(output.getvalue().split("\n", 1)[1]),
                         {"data": {"key": "synthetic"}, "headers": {"etag": "version"}, "status": 200})
        self.assertEqual(set(json.loads(error.getvalue().split("\n", 1)[1])), {"status", "code", "message", "opc-request-id"})

    def test_candidate_export_cannot_overwrite_approved_contract(self):
        for baseline in (BASELINE, INSTALLED_BASELINE):
            result = subprocess.run([sys.executable, str(Path(__file__).with_name("run_sensitive_contracts.py")),
                                     "--write-candidate", str(baseline)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Export to a separate file", result.stderr)

    def test_release_gate_rejects_missing_empty_or_skipped_suites(self):
        import run_sensitive_contracts as runner
        output, error = io.StringIO(), io.StringIO()
        with patch.object(runner, "check_contract", return_value=self.contract), contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            with patch.object(Path, "is_file", return_value=False):
                self.assertEqual(runner.main(["--target", "repository"]), 1)
            self.assertIn("required test suite is missing", error.getvalue())
            with patch.object(runner.unittest.defaultTestLoader, "discover", return_value=unittest.TestSuite()):
                self.assertEqual(runner.main(["--target", "repository"]), 1)
            self.assertIn("contains no tests", error.getvalue())
            tests = unittest.TestSuite([unittest.FunctionTestCase(lambda: None)])
            skipped = SimpleNamespace(wasSuccessful=lambda: True, skipped=[("synthetic", "not run")], testsRun=1)
            with patch.object(runner.unittest.defaultTestLoader, "discover", return_value=tests), patch.object(runner.unittest.TextTestRunner, "run", return_value=skipped):
                self.assertEqual(runner.main(["--target", "repository"]), 1)
            self.assertIn("were skipped", error.getvalue())


if __name__ == "__main__":
    unittest.main()
