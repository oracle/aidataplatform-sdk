from __future__ import annotations

import contextlib
from contextlib import contextmanager
import importlib.util
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from folder_transfer_contract import (BASELINE, INSTALLED_BASELINE, REPO, check_folder_transfer_contract,
                                      collect_folder_transfer_contract)
from sensitive_contract import validate_body


SDK = "aidp-python-client/src/aidp_python_client/aidataplatform_dp/"
MODELS = SDK + "models/"


def load_transfer(variant):
    path = REPO / "plugins/aidp" / variant / "skills/aidp-cli/scripts/folder-transfer.py"
    spec = importlib.util.spec_from_file_location("contract_transfer_" + variant, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FolderTransferContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = collect_folder_transfer_contract()
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.repo = Path(cls.directory.name)
        for relative in ("aidp-python-client/src", "aidp-cli/aidp-py-cli/scripts",
                         "aidp-cli/aidp-py-cli/src", "aidp-typescript-client/lib/model",
                         "aidp-typescript-client/lib/response"):
            shutil.copytree(REPO / relative, cls.repo / relative,
                            ignore=shutil.ignore_patterns("__pycache__"))

    @contextmanager
    def changed(self, relative, old, new):
        path = self.repo / relative
        original = path.read_text()
        self.assertIn(old, original, "Mutation target moved; review this scenario")
        try:
            path.write_text(original.replace(old, new, 1))
            yield
        finally:
            path.write_text(original)

    def assert_drift(self, relative, old, new, diagnostic):
        with self.changed(relative, old, new):
            with self.assertRaisesRegex(AssertionError, "Folder-transfer SDK/CLI contract drift") as error:
                check_folder_transfer_contract(self.repo)
            self.assertIn(diagnostic, str(error.exception))
            self.assertIn("BOTH plugins/aidp/codex", str(error.exception))

    def test_reviewed_repository_transfer_contract_has_no_drift(self):
        check_folder_transfer_contract()
        self.assertEqual(sum(len(group["operations"]) for group in self.contract["operations"].values()), 5)

    def test_candidate_export_cannot_overwrite_transfer_baselines(self):
        runner = Path(__file__).with_name("run_sensitive_contracts.py")
        for baseline in (BASELINE, INSTALLED_BASELINE):
            original = baseline.read_bytes()
            result = subprocess.run([sys.executable, str(runner), "--write-candidate", str(baseline)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Export to a separate file", result.stderr)
            self.assertEqual(baseline.read_bytes(), original)

    def test_helper_commands_and_bodies_match_sdk_for_both_targets_and_variants(self):
        models = self.contract["models"]
        for variant in ("codex", "claude"):
            helper = load_transfer(variant)
            for target in ("workspace", "volume"):
                with self.subTest(variant=variant, target=target), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    archive = root / "synthetic.zip"
                    with zipfile.ZipFile(archive, "w") as stream:
                        stream.writestr("file.txt", "synthetic")
                    group = "workspace-object" if target == "workspace" else "volume"
                    events = []

                    def api(args, command, body=None):
                        operation = next(op for op in self.contract["operations"][command[0]]["operations"].values()
                                         if op["name"] == command[1])
                        positional = [field for field in operation["fields"].values()
                                      if field.get("in") == "path" and field["originalName"] != "aiDataPlatformId"]
                        # Target keys/operation keys are the only path arguments after the command.
                        self.assertEqual(len(command[2:]), len(positional))
                        if body is not None:
                            validate_body(models, operation["bodyModel"], body)
                        events.append((command, body))
                        if command[0] == "async-operations":
                            return {"status": "SUCCEEDED"}
                        if "upload-and-extract" in command[1]:
                            result = {"operationKey": "job", "uploadUrl": "https://storage.example/p/synthetic/archive"}
                        else:
                            result = {"operationKey": "job", "downloadUrl": "https://storage.example/p/synthetic/archive",
                                      "archiveName": "synthetic.zip"}
                        validate_body(models, operation["responseModel"], result)
                        return result

                    common = ["--aidpOCID", "instance", "--" + target + "Key", "target",
                              "--region", "region", "--destPath", str(root / "download")]
                    with patch.object(helper, "api", side_effect=api), \
                            patch.object(helper, "put_archive", return_value=("etag", archive.stat().st_size)), \
                            patch.object(helper, "get_archive"), contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(helper.main(["upload", *common, "--sourceZipPath", str(archive)]), 0)
                        self.assertEqual(helper.main(["download", *common, "--sourcePath", "folder"]), 0)
                    self.assertEqual([call[0][0] for call in events], [group, group, "async-operations", group, "async-operations"])
                    self.assertEqual(events[0][1]["action"], "CREATE")
                    self.assertFalse(events[0][1]["isOverwrite"])
                    self.assertEqual(events[1][1], {"action": "UPDATE", "operationKey": "job", "eTag": "etag",
                                                  "sizeInBytes": archive.stat().st_size})

    def test_polling_handles_every_reviewed_sdk_status(self):
        statuses = set(self.contract["models"]["AsyncOperation"]["fields"]["status"]["enum"])
        self.assertEqual(statuses, {"IN_PROGRESS", "SUCCEEDED", "FAILED", "CANCELED"})
        for variant in ("codex", "claude"):
            helper = load_transfer(variant)
            args = SimpleNamespace(waitTimeout=1, pollInterval=0.01)
            for status in sorted(statuses):
                values = [{"status": status}]
                if status == "IN_PROGRESS":
                    values.append({"status": "SUCCEEDED"})
                with self.subTest(variant=variant, status=status), \
                        patch.object(helper, "api", side_effect=values) as api, \
                        patch.object(helper.time, "sleep"), contextlib.redirect_stdout(io.StringIO()):
                    if status in {"FAILED", "CANCELED"}:
                        with self.assertRaises(helper.TransferError):
                            helper.wait(args, "job")
                    else:
                        helper.wait(args, "job")
                    self.assertEqual(api.call_args.args[1], ["async-operations", "get", "job"])

    def test_added_and_removed_payload_fields_fail(self):
        path = MODELS + "upload_and_extract_zip_details.py"
        with self.changed(path, "'e_tag': 'str',", "'e_tag': 'str',\n            'new_option': 'bool',"):
            self.assert_drift(path, "'e_tag': 'eTag',", "'e_tag': 'eTag',\n            'new_option': 'newOption',",
                              "ADDED contract.models.UploadAndExtractZipDetails.fields.newOption")
        with self.changed(path, "            'e_tag': 'str',\n", ""):
            self.assert_drift(path, "            'e_tag': 'eTag',\n", "",
                              "REMOVED contract.models.UploadAndExtractZipDetails.fields.eTag")

    def test_payload_type_requiredness_and_action_enum_drift_fail(self):
        path = MODELS + "upload_and_extract_zip_details.py"
        self.assert_drift(path, "'size_in_bytes': 'int'", "'size_in_bytes': 'str'",
                          "contract.models.UploadAndExtractZipDetails.fields.sizeInBytes.type")
        self.assert_drift(path, "**[Required]** Gets the action", "Gets the action",
                          "contract.models.UploadAndExtractZipDetails.fields.action.required")
        self.assert_drift(path, 'allowed_values = ["CREATE", "UPDATE"]',
                          'allowed_values = ["CREATE", "UPDATE", "FUTURE"]',
                          "contract.models.UploadAndExtractZipDetails.fields.action.enum")

    def test_transfer_response_and_async_status_drift_fail(self):
        for filename, old, new, diagnostic in (
            ("upload_and_extract_zip_result.py", "'upload_url': 'uploadUrl'", "'upload_url': 'newUploadUrl'", "fields.uploadUrl"),
            ("zip_and_download_folder_result.py", "'operation_key': 'operationKey'", "'operation_key': 'newOperationKey'", "fields.operationKey"),
            ("zip_and_download_folder_result.py", "'download_url': 'str'", "'download_url': 'int'", "fields.downloadUrl.type"),
            ("async_operation.py", 'allowed_values = ["IN_PROGRESS", "SUCCEEDED", "FAILED", "CANCELED"]',
             'allowed_values = ["IN_PROGRESS", "SUCCEEDED", "FAILED", "CANCELED", "PAUSED"]', "AsyncOperation.fields.status.enum"),
        ):
            with self.subTest(filename=filename):
                self.assert_drift(MODELS + filename, old, new, diagnostic)

    def test_route_version_naming_and_removed_operation_drift_fail(self):
        path = SDK + "workspace_object_client.py"
        self.assert_drift(path, '/actions/uploadAndExtractZip', '/actions/futureUpload',
                          "upload_and_extract_workspace_zip.path")
        self.assert_drift(path, "'base_path': '/20260430'", "'base_path': '/20990101'", "sdkBasePaths.workspace-object")
        self.assert_drift("aidp-cli/aidp-py-cli/scripts/generate_manifest.py",
                          'def command_name_from_sdk_method(method_name: str) -> str:',
                          'def command_name_from_sdk_method(method_name: str) -> str:\n    return "future-command"',
                          "contract.operations")
        with self.changed(path, 'def upload_and_extract_workspace_zip(', 'def future_upload('):
            with self.assertRaisesRegex(ValueError, "SDK operation missing"):
                collect_folder_transfer_contract(self.repo)


if __name__ == "__main__":
    unittest.main()
