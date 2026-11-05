from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "codex/skills/aidp-cli"
CANARY = "DO_NOT_PRINT_PRIVATE_VALUE_7821"


class ProtectedResourceTemplateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.counter = 0

    def prepare(self, family, operation, body, *options, success=True):
        self.counter += 1
        metadata = self.root / f"metadata-{self.counter}.json"
        output = self.root / f"body-{self.counter}.json"
        metadata.write_text(json.dumps(body))
        original = metadata.read_bytes()
        result = subprocess.run([sys.executable, str(SKILL / "scripts" / family / "prepare-body.py"),
                                 "--operation", operation, "--metadata", "@" + str(metadata),
                                 "--output", str(output), *options], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0 if success else 1, result.stdout + result.stderr)
        self.assertEqual(metadata.read_bytes(), original)
        self.assertNotIn(CANARY, result.stdout + result.stderr)
        if success:
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            return json.loads(output.read_text())
        self.assertFalse(output.exists())
        return json.loads(result.stdout)

    def test_create_secret_pairs_and_explicit_update_rotation(self):
        for operation, flags in (("create", []), ("update", ["--replace-secrets"])):
            body = self.prepare("credentials", operation, {"displayName": "my_keys"},
                                "--type", "SECRET_TOKEN", "--secret-key", "first", "--secret-key", "second", *flags)
            details = body["credentialDetails"]
            self.assertEqual(body["type"], details["credentialType"])
            pairs = details["secretTokenPair"]
            self.assertEqual([pair["secretKey"] for pair in pairs], ["first", "second"])
            self.assertTrue(all(pair["secretValue"].startswith("{invisible_prompt_input:required:") for pair in pairs))
            self.assertNotEqual(pairs[0]["secretValue"], pairs[1]["secretValue"])

    def test_secret_prompts_identify_each_provided_key_for_create_and_update(self):
        keys = ["unsername", "password", "special_secret"]
        for operation, flags in (("create", []), ("update", ["--replace-secrets"])):
            for from_metadata in (False, True):
                metadata = {"displayName": "my_creds"}
                options = ["--type", "SECRET_TOKEN", *flags]
                if from_metadata:
                    metadata["credentialDetails"] = {"secretTokenPair": [{"secretKey": key} for key in keys]}
                else:
                    for key in keys:
                        options.extend(["--secret-key", key])
                body = self.prepare("credentials", operation, metadata, *options)
                self.assertEqual(body["credentialDetails"]["secretTokenPair"], [
                    {"secretKey": key, "secretValue": "{invisible_prompt_input:required:Enter secret value `" + key + "`}"}
                    for key in keys])

    def test_service_account_key_is_not_read_or_base64_encoded(self):
        nonexistent = self.root / "not-readable.pem"
        metadata = {"displayName": "svc", "credentialDetails": {
            "userId": "user", "tenancy": "tenant", "region": "region", "fingerprint": "fingerprint", "isReadOnly": False}}
        body = self.prepare("credentials", "create", metadata, "--type", "SERVICE_ACCOUNT",
                            "--private-key-path", str(nonexistent))
        self.assertEqual(body["credentialDetails"]["privateKey"], "{textof:" + str(nonexistent) + "}")
        self.assertFalse(body["credentialDetails"]["isReadOnly"])
        self.assertFalse(nonexistent.exists())

    def test_vault_reference_does_not_add_secret_prompt(self):
        body = self.prepare("credentials", "create", {"displayName": "vault", "credentialDetails": {"secretId": "ocid1.vaultsecret.example"}},
                            "--type", "VAULT_REFERENCE")
        self.assertNotIn("prompt_input", json.dumps(body))
        self.assertEqual(body["credentialDetails"]["secretId"], "ocid1.vaultsecret.example")

    def test_metadata_only_update_all_families_needs_no_secrets(self):
        for family, metadata in (("credentials", {"credentialDescription": "changed"}),
                                 ("agents", {"description": "changed"})):
            body = self.prepare(family, "update", metadata)
            self.assertEqual(body, metadata)

    def test_metadata_only_settings_keep_type_without_prompting_for_credentials(self):
        for setting_type in ("GIT_ACCOUNT", "IAM_USER_CREDENTIAL"):
            for use_option in (False, True):
                public = ({"entityType": "PERSONAL_ACCESS_TOKEN"} if setting_type == "GIT_ACCOUNT"
                          else {"tenancy": "existing-tenant", "region": "existing-region"})
                metadata = {"name": "existing_name", "isDefault": False, "data": dict(public)}
                flags = ["--type", setting_type] if use_option else []
                if not use_option:
                    metadata["data"]["type"] = setting_type
                body = self.prepare("user-settings", "update", metadata, *flags)
                self.assertEqual(body, {"name": "existing_name", "isDefault": False,
                                        "data": {"type": setting_type, **public}})
                self.assertNotIn("prompt_input", json.dumps(body))

    def test_setting_rename_and_default_patch_preserve_current_public_configuration(self):
        for setting_type, public in (("GIT_ACCOUNT", {"entityType": "PERSONAL_ACCESS_TOKEN", "providerName": "GITHUB"}),
                                      ("IAM_USER_CREDENTIAL", {"tenancy": "existing-tenant", "region": "existing-region"})):
            existing = {"name": "existing_name", "isDefault": True, "data": {"type": setting_type, **public}}
            snapshot = self.root / "public-existing.json"
            snapshot.write_text(json.dumps(existing))
            original = snapshot.read_bytes()
            for patch_body in ({"name": "renamed"}, {"isDefault": False}):
                body = self.prepare("user-settings", "update", patch_body, "--existing-metadata", "@" + str(snapshot))
                self.assertEqual(body["data"], existing["data"])
                self.assertEqual(body["isDefault"], patch_body.get("isDefault", True))
                self.assertEqual(body["name"], patch_body.get("name", "existing_name"))
                self.assertEqual(snapshot.read_bytes(), original)
                # These are exactly the fields that the inspected backend maps
                # unconditionally and merges with putAll; none may become null.
                for key in public:
                    self.assertEqual(body["data"][key], public[key])
                self.assertNotIn("prompt_input", json.dumps(body))
                self.assertNotIn("privateApiKey", body["data"])
                self.assertNotIn("personalAccessToken", body["data"])

    def test_type_only_setting_updates_cannot_clear_public_metadata_or_default(self):
        for setting_type in ("GIT_ACCOUNT", "IAM_USER_CREDENTIAL"):
            self.prepare("user-settings", "update", {"isDefault": False, "data": {"type": setting_type}}, success=False)
        self.prepare("user-settings", "update", {"name": "renamed", "data": {
            "type": "IAM_USER_CREDENTIAL", "tenancy": "tenant", "region": "region"}}, success=False)

    def test_snapshot_does_not_allow_type_changes_or_credential_inputs(self):
        snapshot = self.root / "public-existing.json"
        snapshot.write_text(json.dumps({"isDefault": True, "data": {"type": "IAM_USER_CREDENTIAL",
                                                                     "tenancy": "tenant", "region": "region"}}))
        for patch_body in ({"data": {"type": "GIT_ACCOUNT"}}, {"data": {"region": "another-region"}},
                           {"data": {"privateApiKey": "{textof:/local/key.pem}"}}):
            self.prepare("user-settings", "update", patch_body, "--existing-metadata", str(snapshot), success=False)
        snapshot.write_text(json.dumps({"isDefault": True, "data": {"type": "GIT_ACCOUNT",
            "entityType": "PERSONAL_ACCESS_TOKEN", "personalAccessToken": CANARY}}))
        self.prepare("user-settings", "update", {"name": "renamed"}, "--existing-metadata", str(snapshot), success=False)

    def test_metadata_only_settings_require_verified_matching_type(self):
        result = self.prepare("user-settings", "update", {"isDefault": False}, success=False)
        self.assertEqual(result["errorCode"], "SETTING_TYPE_REQUIRED")
        result = self.prepare("user-settings", "update", {"isDefault": False, "data": {"type": "GIT_ACCOUNT"}},
                              "--type", "IAM_USER_CREDENTIAL", success=False)
        self.assertEqual(result["errorCode"], "TYPE_MISMATCH")

    def test_setting_type_only_mode_cannot_add_credential_changes(self):
        for data in ({"type": "GIT_ACCOUNT", "personalAccessToken": "{invisible_prompt_input:required:Token}"},
                     {"type": "IAM_USER_CREDENTIAL", "privateApiKey": "{textof:/local/key.pem}"}):
            result = self.prepare("user-settings", "update", {"isDefault": False, "data": data}, success=False)
            self.assertEqual(result["errorCode"], "REPLACEMENT_NOT_SELECTED")

    def test_replacement_is_not_selected_implicitly(self):
        for family, metadata in (("credentials", {"credentialDetails": {"secretTokenPair": []}}),
                                 ("user-settings", {"data": {"type": "GIT_ACCOUNT", "personalAccessToken": "{invisible_prompt_input:required:Token}"}}),
                                 ("agents", {"diagram": {"toolsMap": {"t": {"toolConfig": {"auth": {"authType": "BEARER_TOKEN"}}}}}})):
            result = self.prepare(family, "update", metadata, success=False)
            self.assertEqual(result["errorCode"], "REPLACEMENT_NOT_SELECTED")

    def test_git_setting_pat_is_required_and_username_visible(self):
        for operation, flags in (("create", []), ("update", ["--replace-secrets"])):
            body = self.prepare("user-settings", operation, {"name": "git", "isDefault": False, "data": {"providerName": "GITHUB"}},
                                "--type", "GIT_ACCOUNT", *flags)
            self.assertEqual(body["data"]["username"], "{visible_prompt_input:required:Enter Git account username}")
            self.assertTrue(body["data"]["personalAccessToken"].startswith("{invisible_prompt_input:required:"))
            self.assertEqual(body["data"]["entityType"], "PERSONAL_ACCESS_TOKEN")

    def test_rotation_retains_existing_default_for_git_and_iam(self):
        for setting_type, public in (("GIT_ACCOUNT", {"entityType": "PERSONAL_ACCESS_TOKEN", "providerName": "GITHUB"}),
                                      ("IAM_USER_CREDENTIAL", {"tenancy": "tenant", "region": "region", "userId": "user", "fingerprint": "fp"})):
            for default in (True, False):
                snapshot = self.root / "rotation-current.json"
                existing = {"name": "existing", "isDefault": default, "data": {"type": setting_type, **public}}
                snapshot.write_text(json.dumps(existing))
                original = snapshot.read_bytes()
                flags = ["--replace-secrets", "--existing-metadata", "@" + str(snapshot)]
                if setting_type == "IAM_USER_CREDENTIAL":
                    flags.extend(["--private-key-path", "/local/replacement.pem"])
                body = self.prepare("user-settings", "update", {"data": {}}, *flags)
                self.assertIs(body["isDefault"], default)
                self.assertEqual(body["name"], "existing")
                self.assertEqual(snapshot.read_bytes(), original)
                for key, value in public.items():
                    self.assertEqual(body["data"][key], value)
                if setting_type == "GIT_ACCOUNT":
                    self.assertIn(":required:", body["data"]["personalAccessToken"])
                else:
                    self.assertEqual(body["data"]["privateApiKey"], "{textof:/local/replacement.pem}")

    def test_rotation_allows_an_explicit_default_change(self):
        for current_default in (True, False):
            snapshot = self.root / "rotation-current.json"
            snapshot.write_text(json.dumps({"isDefault": current_default, "data": {
                "type": "GIT_ACCOUNT", "providerName": "GITHUB", "entityType": "PERSONAL_ACCESS_TOKEN"}}))
            body = self.prepare("user-settings", "update", {"isDefault": not current_default},
                                "--replace-secrets", "--existing-metadata", str(snapshot))
            self.assertIs(body["isDefault"], not current_default)

    def test_rotation_never_guesses_a_missing_or_invalid_default(self):
        result = self.prepare("user-settings", "update", {"data": {"providerName": "GITHUB"}},
                              "--replace-secrets", "--type", "GIT_ACCOUNT", success=False)
        self.assertEqual(result["errorCode"], "DEFAULT_STATE_REQUIRED")
        for invalid in (None, "false", 0):
            result = self.prepare("user-settings", "update", {"isDefault": invalid, "data": {"providerName": "GITHUB"}},
                                  "--replace-secrets", "--type", "GIT_ACCOUNT", success=False)
            self.assertEqual(result["errorCode"], "INVALID_METADATA")

    def test_iam_setting_and_reject_admin_oauth_setting(self):
        body = self.prepare("user-settings", "create", {"name": "iam", "isDefault": False, "data": {
            "userId": "user", "tenancy": "tenant", "region": "region", "fingerprint": "fp"}},
                            "--type", "IAM_USER_CREDENTIAL", "--private-key-path", "/local/key.pem")
        self.assertEqual(body["data"]["privateApiKey"], "{textof:/local/key.pem}")
        body = self.prepare("user-settings", "create", {"name": "public_oauth", "isDefault": False, "data": {
            "identityProviderUrl": "https://idp.example", "retrieveJksUrl": "https://idp.example/jks"}}, "--type", "OAUTH", success=False)
        self.assertEqual(body["errorCode"], "UNSUPPORTED_TYPE")

    def test_agent_nested_auth_in_nodes_and_tools_and_distinct_prompts(self):
        metadata = {"displayName": "agent", "pathInfo": "/Workspace/Shared", "diagram": {
            "toolsMap": {"http": {"toolConfig": {"auth": {"authType": "BEARER_TOKEN"}}},
                         "mcp": {"toolConfig": {"auth": {"authType": "BEARER_TOKEN"}}}},
            "nodes": {"oauth": {"configuration": {"auth": {"authType": "OAUTH", "clientId": "id", "issuerIdpEndpoint": "https://idp.example", "scopes": ["read"]}}}}}}
        for operation, flags in (("create", []), ("update", ["--replace-secrets"])):
            body = self.prepare("agents", operation, metadata, *flags)
            tools = body["diagram"]["toolsMap"]
            self.assertNotEqual(tools["http"]["toolConfig"]["auth"]["token"], tools["mcp"]["toolConfig"]["auth"]["token"])
            auth = body["diagram"]["nodes"]["oauth"]["configuration"]["auth"]
            self.assertEqual(auth["scopes"], ["read"])
            self.assertTrue(auth["clientSecret"].startswith("{invisible_prompt_input:required:"))

    def test_agent_no_auth_resource_principal_and_reference_stay_unchanged(self):
        reference = json.dumps({"displayName": "integration_keys", "secretKey": "api_token"})
        metadata = {"displayName": "agent", "pathInfo": "/Workspace/Shared", "diagram": {"toolsMap": {
            "http": {"toolConfig": {"auth": {"authType": "BEARER_TOKEN", "token": reference}}},
            "mcp": {"toolConfig": {"auth": {"authType": "OCI_RESOURCE_PRINCIPAL"}}},
            "public": {"toolConfig": {"auth": {"authType": "NO_AUTH"}}}}}}
        for operation in ("create", "update"):
            self.assertEqual(self.prepare("agents", operation, metadata), metadata)

    def test_each_credential_and_setting_payload_rejects_its_own_inline_secret(self):
        cases = [
            ("credentials", "SECRET_TOKEN", {"displayName": "keys", "credentialDetails": {
                "secretTokenPair": [{"secretKey": "password", "secretValue": CANARY}]}}, []),
            ("credentials", "SERVICE_ACCOUNT", {"displayName": "service", "credentialDetails": {
                "userId": "user", "tenancy": "tenant", "region": "region", "fingerprint": "fp",
                "privateKey": CANARY}}, ["--private-key-path", "/local/key.pem"]),
            ("user-settings", "GIT_ACCOUNT", {"name": "git", "isDefault": False, "data": {
                "providerName": "GITHUB", "personalAccessToken": CANARY}}, []),
            ("user-settings", "IAM_USER_CREDENTIAL", {"name": "iam", "isDefault": False, "data": {
                "userId": "user", "tenancy": "tenant", "region": "region", "fingerprint": "fp",
                "privateApiKey": CANARY}}, ["--private-key-path", "/local/key.pem"]),
        ]
        for operation, flags in (("create", []), ("update", ["--replace-secrets"])):
            for family, kind, metadata, options in cases:
                with self.subTest(operation=operation, family=family, kind=kind):
                    result = self.prepare(family, operation, metadata, "--type", kind, *options, *flags, success=False)
                    self.assertEqual(result["errorCode"], "INLINE_SECRET")

    def test_agent_actual_auth_fields_reject_inline_secrets_at_reviewed_locations(self):
        for operation, flags in (("create", []), ("update", ["--replace-secrets"])):
            for kind, field in (("BEARER_TOKEN", "token"), ("OAUTH", "clientSecret")):
                auth = {"authType": kind, field: CANARY, "clientId": "public", "issuerIdpEndpoint": "https://idp.example"}
                configs = [
                    {"toolsMap": {"http": {"toolType": "HTTP", "toolConfig": {"auth": auth}}}},
                    {"toolsMap": {"mcp": {"toolType": "MCP", "toolConfig": {"auth": auth}}}},
                    {"nodes": {"http": {"key": "http", "type": "HTTP_TOOL", "configuration": {"auth": auth}}}},
                    {"nodes": {"mcp": {"key": "mcp", "type": "MCP_TOOL", "configuration": {"toolConfig": {"auth": auth}}}}},
                    {"nodes": {"agent": {"key": "agent", "type": "AGENT", "tools": [
                        {"toolType": "HTTP", "toolConfig": {"auth": auth}}]}}},
                ]
                for diagram in configs:
                    result = self.prepare("agents", operation, {"displayName": "agent", "pathInfo": "/Shared",
                                          "diagram": diagram}, *flags, success=False)
                    self.assertEqual(result["errorCode"], "INLINE_SECRET")

    def test_agent_nullable_optional_containers_preserve_create_and_update_payloads(self):
        from sensitive_contract import validate_body
        contracts = [json.loads((ROOT / "tests/contracts" / name).read_text())["models"]
                     for name in ("sensitive-contract.json", "sensitive-contract-installed.json")]
        diagrams = [None, {"toolsMap": None}, {"nodes": None}, {"toolsMap": None, "nodes": None},
                    {"nodes": {"agent": {"key": "agent", "type": "AGENT", "tools": None}}},
                    {"nodes": {"agent": {"key": "agent", "type": "SUPERVISOR_AGENT", "tools": None}}},
                    {"toolsMap": {}, "nodes": {}},
                    {"nodes": {"agent": {"key": "agent", "type": "AGENT", "tools": []}}}]
        for operation in ("create", "update"):
            for diagram in diagrams:
                with self.subTest(operation=operation, diagram=diagram):
                    metadata = {"displayName": "agent", "diagram": diagram}
                    if operation == "create":
                        metadata.update(pathInfo="/Shared", type="CODE" if diagram is None else "CANVAS")
                    for models in contracts:
                        validate_body(models, "CreateAgentDetails" if operation == "create" else "UpdateAgentDetails", metadata)
                    self.assertEqual(self.prepare("agents", operation, metadata), metadata)

    def test_agent_non_null_malformed_containers_remain_invalid(self):
        diagrams = [[], False, {"toolsMap": []}, {"toolsMap": False}, {"nodes": "invalid"},
                    {"nodes": {"agent": {"type": "AGENT", "tools": {}}}}]
        for operation in ("create", "update"):
            for diagram in diagrams:
                with self.subTest(operation=operation, diagram=diagram):
                    result = self.prepare("agents", operation, {"displayName": "agent", "pathInfo": "/Shared",
                                          "diagram": diagram}, success=False)
                    self.assertEqual(result["errorCode"], "INVALID_METADATA")

    def test_agent_null_containers_do_not_skip_other_auth_checks(self):
        auth = {"authType": "BEARER_TOKEN", "token": CANARY}
        diagrams = [
            {"nodes": None, "toolsMap": {"http": {"toolType": "HTTP", "toolConfig": {"auth": auth}}}},
            {"toolsMap": None, "nodes": {"agent": {"key": "agent", "type": "AGENT", "tools": [
                {"toolType": "HTTP", "toolConfig": {"auth": auth}}]}}},
        ]
        for operation in ("create", "update"):
            for diagram in diagrams:
                result = self.prepare("agents", operation, {"displayName": "agent", "pathInfo": "/Shared",
                                      "diagram": diagram}, success=False)
                self.assertEqual(result["errorCode"], "INLINE_SECRET")

    def test_agent_public_metadata_and_schema_payloads_need_no_exceptions(self):
        from sensitive_contract import validate_body
        models = json.loads((ROOT / "tests/contracts/sensitive-contract.json").read_text())["models"]
        # These are field definitions and public labels, not secret values.
        schema = {"type": "object", "properties": {
            "api_key": {"type": "string"}, "accessToken": {"type": "string"},
            "auth": {"type": "object", "properties": {"client_secret": {"type": "string"}}}}}
        public_body = {"properties": schema["properties"], "authType": "schema-label",
                       "auth": {"authType": "OAUTH", "clientSecret": "Field label"}}
        for operation in ("create", "update"):
            metadata = {"displayName": "agent", "diagram": {
                "toolsMap": {"http/~": {"toolType": "HTTP", "inputSchema": schema,
                    "properties": {"accessToken": {"description": "Field label", "required": False}},
                    "toolConfig": {"method": "POST", "body": public_body,
                                   "params": {"api_key": "Field label"},
                                   "headers": {"x-api-key": "Field label"}}}},
                "nodes": {"node": {"key": "node", "configuration": {
                    "fields": [{"client_secret": "Field label"}]}}}}}
            if operation == "create":
                metadata["pathInfo"] = "/Shared"
            body = self.prepare("agents", operation, metadata)
            self.assertEqual(body, metadata)
            validate_body(models, "CreateAgentDetails" if operation == "create" else "UpdateAgentDetails", body)
            self.assertNotIn("prompt_input", json.dumps(body))

    def test_custom_tool_secrets_use_exact_explicit_placeholders(self):
        for field in ("api_key", "client_secret", "accessToken", "refresh_token", "password"):
            placeholder = "{invisible_prompt_input:required:Enter secret for the selected tool}"
            metadata = {"displayName": "agent", "pathInfo": "/Shared", "diagram": {
                "toolsMap": {"http": {"toolType": "HTTP", "toolConfig": {"body": {field: placeholder}}}}}}
            for operation in ("create", "update"):
                self.assertEqual(self.prepare("agents", operation, metadata), metadata)

    def test_agent_registry_names_do_not_determine_sensitivity(self):
        for registry in ("toolsMap", "nodes", "edges", "guardrailsMap"):
            for identifier in ("token", "password", "clientSecret", "Authorization", "api_key", "accessToken"):
                definition = {"displayName": "Metadata label", "description": "No credentials"}
                metadata = {"displayName": "agent", "pathInfo": "/Shared", "diagram": {registry: {identifier: definition}}}
                self.assertEqual(self.prepare("agents", "create", metadata), metadata)

    def test_tool_named_token_still_prompts_for_its_runtime_bearer_token(self):
        metadata = {"displayName": "agent", "pathInfo": "/Shared", "diagram": {
            "toolsMap": {"token": {"toolConfig": {"auth": {"authType": "BEARER_TOKEN"}}}}}}
        body = self.prepare("agents", "create", metadata)
        token = body["diagram"]["toolsMap"]["token"]["toolConfig"]["auth"]["token"]
        self.assertTrue(token.startswith("{invisible_prompt_input:required:"))

    def test_agent_inline_tool_auth_gets_prompts_and_preserves_schema(self):
        schema = {"properties": {"auth": {"authType": "OAUTH", "clientSecret": "Field label"}}}
        diagram = {"nodes": {"agent": {"type": "AGENT", "key": "agent", "tools": [
            {"toolType": "HTTP", "inputSchema": schema,
             "toolConfig": {"auth": {"authType": "BEARER_TOKEN"}}}]}}}
        for operation, flags in (("create", []), ("update", ["--replace-secrets"])):
            body = self.prepare("agents", operation, {"displayName": "agent", "pathInfo": "/Shared", "diagram": diagram}, *flags)
            tool = body["diagram"]["nodes"]["agent"]["tools"][0]
            self.assertEqual(tool["inputSchema"], schema)
            self.assertTrue(tool["toolConfig"]["auth"]["token"].startswith("{invisible_prompt_input:required:"))

    def test_missing_metadata_duplicate_keys_and_type_mismatch(self):
        for family, body, flags in (
            ("credentials", {"displayName": "x"}, ["--type", "SERVICE_ACCOUNT", "--private-key-path", "/key"]),
            ("credentials", {"displayName": "x"}, ["--type", "SECRET_TOKEN", "--secret-key", "same", "--secret-key", "same"]),
            ("credentials", {"displayName": "x", "type": "VAULT_REFERENCE"}, ["--type", "SECRET_TOKEN", "--secret-key", "key"]),
            ("user-settings", {"name": "x", "isDefault": False, "data": {}}, ["--type", "GIT_ACCOUNT"]),
            ("agents", {"displayName": "x"}, [])):
            self.prepare(family, "create", body, *flags, success=False)

    def test_new_resource_copies_match(self):
        for directory in ("references/credentials", "references/user-settings", "references/agents",
                          "scripts/common", "scripts/credentials", "scripts/user-settings", "scripts/agents"):
            for path in (SKILL / directory).rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    other = ROOT / "claude/skills/aidp-cli" / path.relative_to(SKILL)
                    self.assertEqual(path.read_bytes(), other.read_bytes())


if __name__ == "__main__":
    unittest.main()
