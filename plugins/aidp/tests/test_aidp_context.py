# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CODEX_SKILL = REPO_ROOT / "plugins/aidp/codex/skills/aidp-setup-local"
CLAUDE_SKILL = REPO_ROOT / "plugins/aidp/claude/skills/aidp-setup-local"
SCRIPT = CODEX_SKILL / "scripts/aidp_context.py"

INSTANCE_OCID = (
    "ocid1.aidataplatformenv.oc1.phx."
    "amaaaaaaeq37tyqa4mj7w46hnv4dj722ql7wgvtrnvjmfn2bao55iaf5kpmq"
)
class AidpContextTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.context_file = Path(self.temp_dir.name) / "context.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_context(self, *arguments: str, expected: int = 0) -> object:
        environment = os.environ.copy()
        environment["AIDP_CONTEXT_FILE"] = str(self.context_file)
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(completed.returncode, expected, completed.stderr)
        output = completed.stdout if expected == 0 else completed.stderr
        return json.loads(output)

    def test_missing_context_is_read_only(self) -> None:
        self.assertIsNone(self.run_context("get", "lastUsedAuth"))
        self.assertFalse(self.context_file.exists())

    def test_write_does_not_require_consent(self) -> None:
        auth = self.run_context(
            "set",
            "lastUsedAuth",
            "--auth-type",
            "security_token",
            "--profile",
            "DEFAULT",
        )
        self.assertTrue(auth["saved"])
        self.assertEqual(auth["field"], "lastUsedAuth")
        self.assertEqual(auth["value"]["profile"], "DEFAULT")

    def test_records_all_context_fields(self) -> None:
        auth = self.run_context(
            "set",
            "lastUsedAuth",
            "--authType",
            "security_token",
            "--profile",
            "DEFAULT",
        )
        self.assertTrue(auth["saved"])
        self.assertEqual(auth["field"], "lastUsedAuth")
        self.assertEqual(auth["value"]["profile"], "DEFAULT")

        self.run_context(
            "set",
            "endpoints",
            "--relm",
            "oc1",
            "--resourceType",
            "aidataplatformenv",
            "--template",
            "https://aidpenv.{region}.example.com",
        )
        recent = self.run_context(
            "set",
            "recentlyUsedAIDP",
            "--instanceOcid",
            INSTANCE_OCID,
            "--region",
            "us-phoenix-1",
            "--endpoint",
            "https://aidpenv.us-phoenix-1.example.com",
            "--name",
            "example",
        )
        self.assertTrue(recent["saved"])
        self.assertEqual(recent["field"], "recentlyUsedAIDP")
        self.assertEqual(recent["value"]["resourceType"], "aidataplatformenv")

        recent_read = self.run_context("get", "recentlyUsedAIDP")
        self.assertEqual(
            recent_read[0]["displayOcid"],
            "ocid1.aidataplatformenv.oc1.phx.…iaf5kpmq",
        )

        stored = self.run_context("get", "all")
        self.assertEqual(stored["schemaVersion"], 2)
        self.assertNotIn("consent", stored)
        self.assertNotIn("userOcids", stored)
        # `get all` adds displayOcid for display; the file itself never stores it.
        self.assertIn("displayOcid", stored["recentlyUsedAIDP"][0])
        on_disk = json.loads(self.context_file.read_text())
        self.assertNotIn("displayOcid", on_disk["recentlyUsedAIDP"][0])
        self.assertEqual(stat.S_IMODE(self.context_file.stat().st_mode), 0o600)

    def test_endpoint_mru_limit_deduplication_and_standard_rule(self) -> None:
        for index in range(1, 7):
            self.run_context(
                "set",
                "endpoints",
                "--realm",
                "oc1",
                "--resource-type",
                "aidataplatformenv",
                "--template",
                f"https://aidpenv{index}.{{region}}.example.com",
            )
        endpoints = self.run_context(
            "get",
            "endpoints",
            "--realm",
            "oc1",
            "--resource-type",
            "aidataplatformenv",
        )
        self.assertEqual(len(endpoints), 5)
        self.assertEqual(
            endpoints[0]["template"], "https://aidpenv6.{region}.example.com"
        )

        error = self.run_context(
            "set",
            "endpoints",
            "--realm",
            "oc1",
            "--resource-type",
            "aidataplatform",
            "--template",
            "https://wrong.{region}.example.com",
            expected=2,
        )
        self.assertEqual(error["error"]["code"], "invalid_standard_endpoint")

    def test_recent_instance_mru_limit(self) -> None:
        for index in range(12):
            self.run_context(
                "set",
                "recentlyUsedAIDP",
                "--instance-ocid",
                f"ocid1.aidataplatformenv.oc1.phx.unique{index}",
                "--region",
                "us-phoenix-1",
                "--endpoint",
                "https://aidpenv.us-phoenix-1.example.com",
                "--name",
                f"instance-{index}",
            )
        recent = self.run_context("get", "recentlyUsedAIDP")
        self.assertEqual(len(recent), 10)
        self.assertEqual(recent[0]["name"], "instance-11")
        self.assertEqual(recent[-1]["name"], "instance-2")

    def test_migrates_v1_without_identity_or_consent(self) -> None:
        legacy = {
            "schemaVersion": 1,
            "consent": {"granted": True},
            "lastUsedAuth": {
                "authType": "security_token",
                "profile": "DEFAULT",
                "configFilePath": None,
                "lastValidatedAt": "2026-09-27T10:00:00Z",
            },
            "userOcids": {
                "ocid1.tenancy.oc1..legacy": "ocid1.user.oc1..legacy"
            },
        }
        self.context_file.write_text(json.dumps(legacy) + "\n")
        self.run_context("migrate")
        data = self.run_context("get", "all")
        self.assertEqual(data["schemaVersion"], 2)
        self.assertEqual(data["lastUsedAuth"]["profile"], "DEFAULT")
        self.assertNotIn("consent", data)
        self.assertNotIn("userOcids", data)
        stored = json.loads(self.context_file.read_text())
        self.assertNotIn("consent", stored)
        self.assertNotIn("userOcids", stored)

    def test_get_all_adds_display_ocid_without_storing_it(self) -> None:
        self.run_context(
            "set", "recentlyUsedAIDP",
            "--instance-ocid", INSTANCE_OCID,
            "--region", "us-phoenix-1",
            "--endpoint", "https://aidpenv.us-phoenix-1.example.com",
        )
        stored_before = self.context_file.read_bytes()
        everything = self.run_context("get", "all")
        single = self.run_context("get", "recentlyUsedAIDP")
        self.assertEqual(everything["recentlyUsedAIDP"], single)
        self.assertIn("displayOcid", everything["recentlyUsedAIDP"][0])
        self.assertEqual(self.context_file.read_bytes(), stored_before)
        self.assertNotIn("displayOcid", self.context_file.read_text())

    def test_latest_version_check_round_trip(self) -> None:
        self.assertIsNone(self.run_context("get", "latestVersionCheck"))
        saved = self.run_context("set", "latestVersionCheck")
        self.assertTrue(saved["saved"])
        self.assertEqual(set(saved["value"]), {"checkedAt"})
        self.assertEqual(self.run_context("get", "latestVersionCheck"), saved["value"])
        self.assertEqual(self.run_context("remove", "latestVersionCheck"), {"removed": True})
        self.assertIsNone(self.run_context("get", "latestVersionCheck"))

    def test_rejects_invalid_stored_records_without_rewriting(self) -> None:
        timestamp = "2026-09-27T10:00:00Z"
        invalid_documents = {
            "auth profile": {
                "schemaVersion": 2,
                "lastUsedAuth": {
                    "authType": "api_key",
                    "profile": "invalid profile",
                    "configFilePath": None,
                    "lastValidatedAt": timestamp,
                },
            },
            "endpoint template": {
                "schemaVersion": 2,
                "endpoints": {
                    "oc1:aidataplatformenv": [
                        {
                            "template": "http://unsafe.{region}.example.com",
                            "lastValidatedAt": timestamp,
                        }
                    ]
                },
            },
            "recent instance metadata": {
                "schemaVersion": 2,
                "recentlyUsedAIDP": [
                    {
                        "instanceOcid": INSTANCE_OCID,
                        "resourceType": "aidataplatformenv2",
                        "realm": "oc1",
                        "region": "us-phoenix-1",
                        "endpoint": "https://aidpenv.us-phoenix-1.example.com",
                        "lastUsedAt": timestamp,
                    }
                ],
            },
            "latest version check extra field": {
                "schemaVersion": 2,
                "latestVersionCheck": {
                    "checkedAt": timestamp,
                    "userOcid": "ocid1.user.oc1..smuggled",
                },
            },
            "forbidden user mapping": {
                "schemaVersion": 2,
                "userOcids": {
                    "ocid1.tenancy.oc1..legacy": "ocid1.user.oc1..legacy"
                },
            },
        }

        for label, document in invalid_documents.items():
            with self.subTest(label=label):
                original = (json.dumps(document, indent=2) + "\n").encode()
                self.context_file.write_bytes(original)
                error = self.run_context("get", "all", expected=2)
                self.assertIn("error", error)
                self.run_context("migrate", expected=2)
                self.assertEqual(self.context_file.read_bytes(), original)

    def test_python_cli_round_trip_preserves_other_context(self) -> None:
        self.run_context("set", "lastUsedAuth", "--auth-type", "api_key", "--profile", "DEFAULT")
        cli = "/example directory/.venv/bin/aidp"
        python = "/example directory/.venv/bin/python"
        receipt = self.run_context("set", "pythonCli", "--path", cli, "--python-path", python)
        self.assertEqual(receipt, {"saved": True, "field": "pythonCli",
            "value": {"path": cli, "pythonPath": python}})
        self.assertEqual(self.run_context("get", "pythonCli"), receipt["value"])
        self.assertEqual(self.run_context("get", "all")["lastUsedAuth"]["profile"], "DEFAULT")
        self.assertEqual(self.run_context("remove", "pythonCli"), {"removed": True})
        self.assertIsNone(self.run_context("get", "pythonCli"))
        self.assertIsNotNone(self.run_context("get", "lastUsedAuth"))

    def test_python_cli_paths_must_be_absolute_without_requiring_live_files(self) -> None:
        for cli, python in (("relative/aidp", "/python"), ("/aidp", "relative/python")):
            error = self.run_context("set", "pythonCli", "--path", cli, "--python-path", python, expected=2)
            self.assertEqual(error["error"]["code"], "invalid_context")
        self.assertFalse(self.context_file.exists())

    def test_claude_and_codex_resources_are_identical(self) -> None:
        for relative_path in (
            "references/context-cli.md",
            "scripts/aidp_context.py",
        ):
            self.assertEqual(
                (CODEX_SKILL / relative_path).read_bytes(),
                (CLAUDE_SKILL / relative_path).read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
