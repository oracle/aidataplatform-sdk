# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
"""Installed transfer-package checks without service requests or credentials."""
from __future__ import annotations

import copy
from importlib import metadata
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from folder_transfer_contract import (CLIENTS, check_folder_transfer_contract,
                                      collect_folder_transfer_contract)
import sensitive_contract


class InstalledFolderTransferContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.actual = collect_folder_transfer_contract(installed=True)

    def test_installed_transfer_contract_matches_separately_reviewed_baseline(self):
        check_folder_transfer_contract(installed=True, actual=self.actual)
        repository = collect_folder_transfer_contract()
        installed = copy.deepcopy(self.actual)
        installed.pop("installedCliManifest")
        self.assertEqual(repository, installed)

    def test_installed_manifest_groups_and_help_match_transfer_commands(self):
        for group, (_, methods) in CLIENTS.items():
            for method in methods:
                entry = self.actual["installedCliManifest"][method]
                operation = self.actual["operations"][group]["operations"][method]
                self.assertEqual(entry["group"], group)
                self.assertEqual(entry["command"]["name"], operation["name"])
                result = subprocess.run([sys.executable, "-m", "aidp_cli.main", group,
                                         operation["name"], "--help"], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(operation["name"], result.stdout)

    def test_stale_installed_upload_action_enum_blocks_release(self):
        sdk, cli = metadata.distribution("aidp-python-client"), metadata.distribution("aidp-cli")
        manifest = json.loads(Path(cli.locate_file("aidp_cli/operation_manifest.json")).read_text())
        changed = 0
        for group in manifest["commandGroups"]:
            for operation in group["commands"]:
                if operation["sdkMethodName"] in {"upload_and_extract_workspace_zip", "upload_and_extract_volume_zip"}:
                    operation["bodyEnumFields"]["action"] = ["CREATE"]
                    changed += 1
        self.assertEqual(changed, 2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest))
            fake_cli = SimpleNamespace(version=cli.version, locate_file=lambda name:
                path if name == "aidp_cli/operation_manifest.json" else cli.locate_file(name))
            with patch.object(sensitive_contract.metadata, "distribution", side_effect=lambda name: sdk if name == "aidp-python-client" else fake_cli):
                with self.assertRaisesRegex(ValueError, "Installed CLI manifest differs from SDK"):
                    collect_folder_transfer_contract(installed=True)

    def test_installed_response_field_drift_blocks_release(self):
        changed = copy.deepcopy(self.actual)
        changed["models"]["ZipAndDownloadFolderResult"]["fields"].pop("downloadUrl")
        with self.assertRaisesRegex(AssertionError, "REMOVED contract.models.ZipAndDownloadFolderResult.fields.downloadUrl"):
            check_folder_transfer_contract(installed=True, actual=changed)


if __name__ == "__main__":
    unittest.main()
