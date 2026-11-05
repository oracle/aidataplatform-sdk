from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sensitive_contract import BASELINE, INSTALLED_BASELINE, REPO, validate_body

SKILL = REPO / "plugins/aidp/codex/skills/aidp-cli"
SECRET = "SYNTHETIC_BIGQUERY_PRIVATE_KEY_DO_NOT_PRINT_9284"


class GoogleBigQueryInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {"host": "https://www.googleapis.com/bigquery/v2", "port": "443", "projectId": "example-project",
                       "serviceAccountEmail": "reader@example-project.iam.gserviceaccount.com", "privateKeyFilePath": str(self.root / "key.json")}
        self.key = Path(self.config["privateKeyFilePath"])
        self.key.write_text(json.dumps({"type": "service_account", "project_id": self.config["projectId"],
                                        "client_email": self.config["serviceAccountEmail"], "private_key": SECRET,
                                        "private_key_id": SECRET, "client_id": SECRET}))
        self.counter = 0

    def call(self, relative, *args):
        result = subprocess.run([sys.executable, str(SKILL / "scripts" / relative), *map(str, args)], capture_output=True, text=True)
        self.assertNotIn(SECRET, result.stdout + result.stderr)
        return result

    def prepare(self, operation, config=None, success=True):
        self.counter += 1
        source, target = self.root / f"config-{self.counter}.json", self.root / f"body-{self.counter}.json"
        source.write_text(json.dumps(self.config if config is None else config))
        result = self.call("ext-catalogs/google-bigquery/prepare-body.py", "--operation", operation, "--config", "@" + str(source), "--output", target)
        self.assertEqual(result.returncode, 0 if success else 1, result.stdout + result.stderr)
        if success:
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            return json.loads(target.read_text()), target
        self.assertFalse(target.exists())
        return json.loads(result.stdout), target

    def test_create_and_full_test_match_reviewed_six_key_contract_and_installed_sdk(self):
        contract = json.loads(BASELINE.with_name("google-bigquery-key-contract.json").read_text())
        models = json.loads(INSTALLED_BASELINE.read_text())["models"]
        for operation in ("create", "test-connection"):
            config = dict(self.config)
            if operation == "create":
                config.update(displayName="bigquery", description="chosen", properties={"public": "value"})
            body, _ = self.prepare(operation, config)
            self.assertEqual(body["sourceType"], contract["sourceType"])
            props = body["connectionDetails"]["connectionProperties"]
            self.assertEqual(set(props), set(contract["requiredConnectionPropertyKeys"]))
            self.assertEqual(props["GOOGLE_BIGQUERY_OAUTH_TYPE"], contract["authenticationType"])
            self.assertEqual(props["GOOGLE_BIGQUERY_OAUTH_PVT_KEY"], "{textof:" + str(self.key) + "}")
            self.assertNotIn("prompt_input", json.dumps(body))
            self.assertNotIn(SECRET, json.dumps(body))
            self.assertEqual("displayName" in body, operation == "create")
            self.assertEqual("catalogType" in body, operation == "create")
            validate_body(models, "CreateCatalogDetails" if operation == "create" else "CatalogTestConnectionDetails", body)

    def test_stored_catalog_test_replaces_only_key_without_password_or_wallet(self):
        body, _ = self.prepare("test-connection", {"catalogKey": "existing", "privateKeyFilePath": str(self.key)})
        self.assertEqual(body, {"key": "existing", "sourceType": "GOOGLE_BIGQUERY", "connectionDetails": {
            "connectionProperties": {"GOOGLE_BIGQUERY_OAUTH_PVT_KEY": "{textof:" + str(self.key) + "}"}}})
        for config in ({"catalogKey": "existing", "privateKeyFilePath": str(self.key), "host": "another"},
                       {"catalogKey": "existing", "privateKeyFilePath": str(self.key), "projectId": "another"}):
            self.prepare("test-connection", config, success=False)
        self.prepare("create", {"catalogKey": "existing", "privateKeyFilePath": str(self.key)}, success=False)

    def test_helper_does_not_open_key_and_path_validation_rejects_missing_key(self):
        self.key.unlink()
        body, path = self.prepare("test-connection")
        self.assertNotIn(SECRET, json.dumps(body))
        result = self.call("validate-protected-paths.py", path)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["errorCode"], "FILE_NOT_FOUND")

    def test_public_metadata_inspector_never_prints_key_fields_and_suppresses_parse_errors(self):
        result = self.call("ext-catalogs/google-bigquery/inspect-service-account-key.py", "--key-path", self.key)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {"ok": True, "projectId": self.config["projectId"],
                                                    "serviceAccountEmail": self.config["serviceAccountEmail"]})
        for content in ('{"broken":' + SECRET, json.dumps({"type": "authorized_user", "refresh_token": SECRET}),
                        json.dumps({"type": "service_account", "project_id": SECRET + "\n", "client_email": SECRET})):
            self.key.write_text(content)
            result = self.call("ext-catalogs/google-bigquery/inspect-service-account-key.py", "--key-path", self.key)
            self.assertEqual(result.returncode, 1)
            self.assertFalse(json.loads(result.stdout)["ok"])

    def test_bad_inputs_and_inline_secrets_are_rejected(self):
        for field, value in (("port", "0"), ("port", 443), ("port", "65536"), ("projectId", ""),
                             ("serviceAccountEmail", ""), ("privateKeyFilePath", ""),
                             ("privateKeyContent", SECRET), ("password", SECRET), ("username", SECRET),
                             ("authenticationMethod", "OAuth"), ("sslEnabled", False), ("databaseName", "dataset")):
            with self.subTest(field=field, value=value):
                self.prepare("test-connection", {**self.config, field: value}, success=False)

    def test_output_handoff_and_actual_body_cleanup_on_success_and_failure(self):
        original_key = self.key.read_bytes()
        for operation, config in (("create", {**self.config, "displayName": "bigquery"}),
                                  ("test-connection", dict(self.config)),
                                  ("test-connection", {"catalogKey": "existing", "privateKeyFilePath": str(self.key)})):
            for status, exit_code in ((200, 0), (409, 153)):
                _, template = self.prepare(operation, config)
                original_template = template.read_bytes()
                trace, result_path = self.root / "actual-path.txt", self.root / "result.json"
                fake = self.root / "fake-cli.py"
                fake.write_text("import json,os,sys\nfrom pathlib import Path\n"
                    "p=Path(sys.argv[sys.argv.index('--body')+1][1:])\n"
                    "assert p.stat().st_mode & 0o777 == 0o600\n"
                    "assert os.environ['AIDP_CLI_STRICT_URL_ENCODING']=='true'\n"
                    "body=json.loads(p.read_text())\n"
                    "key=json.loads(body['connectionDetails']['connectionProperties']['GOOGLE_BIGQUERY_OAUTH_PVT_KEY'])\n"
                    "assert key['private_key']==" + repr(SECRET) + "\n"
                    "Path(" + repr(str(trace)) + ").write_text(str(p))\n"
                    "print('Response:');print(json.dumps({'status':" + str(status) + ", 'data':None,'headers':{'opc-request-id':'synthetic'}}))\n"
                    "sys.exit(" + str(exit_code) + ")\n")
                result = self.call("protected_aidp.py", "--output-file", result_path, "--", sys.executable, fake,
                                   "--body", "@" + str(template))
                self.assertEqual(result.returncode, exit_code, result.stdout + result.stderr)
                self.assertEqual(result.stdout, "Operation output handed off to AI agent. Ask it to continue.\n")
                self.assertEqual(result.stderr, "")
                actual = Path(trace.read_text())
                self.assertFalse(actual.exists())
                self.assertFalse(actual.parent.exists())
                self.assertEqual(template.read_bytes(), original_template)
                self.assertEqual(self.key.read_bytes(), original_key)
                consumed = self.call("read-protected-result.py", result_path)
                self.assertEqual(consumed.returncode, 0)
                payload = json.loads(consumed.stdout)
                self.assertEqual(payload["exitCode"], exit_code)
                self.assertTrue(payload["complete"])
                self.assertEqual(json.loads(payload["stdout"].split("\n", 1)[1])["status"], status)
                self.assertFalse(result_path.exists())

    def test_codex_claude_bigquery_helpers_and_references_match(self):
        other = REPO / "plugins/aidp/claude/skills/aidp-cli"
        for path in (SKILL / "scripts/ext-catalogs/google-bigquery").glob("*.py"):
            self.assertEqual(path.read_bytes(), (other / path.relative_to(SKILL)).read_bytes())
        self.assertEqual((SKILL / "references/ext-catalogs/google-bigquery.md").read_bytes(),
                         (other / "references/ext-catalogs/google-bigquery.md").read_bytes())


if __name__ == "__main__":
    unittest.main()
