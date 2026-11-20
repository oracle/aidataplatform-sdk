# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
from __future__ import annotations

import base64
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "codex/skills/aidp-cli/scripts/ext-catalogs/common"
sys.path.insert(0, str(COMMON))
import catalog_inputs as private


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = load("wallet_path_validator", COMMON / "validate-private-paths.py")
protected = load("catalog_protected_wrapper", COMMON.parents[1] / "protected_aidp.py")
BODIES = json.loads((ROOT / "tests/fixtures/protected_catalog_bodies.json").read_text())
CANARY = "PRIVATE_CANARY_7429"


class ExternalCatalogInputsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def call(self, script, *arguments):
        return subprocess.run([sys.executable, str(COMMON / script), *map(str, arguments)],
                              text=True, capture_output=True, check=False)

    def wallet(self, tns=None):
        path = self.root / "private-wallet.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("tnsnames.ora", tns or f"""# {CANARY}
sales_low =
 (DESCRIPTION =
   (ADDRESS = (HOST = {CANARY})(PORT = 1522))
   (CONNECT_DATA = (SERVICE_NAME = {CANARY})))
sales_high, sales_alias = (DESCRIPTION=(ADDRESS=(HOST={CANARY})))
""")
            archive.writestr("private.key", CANARY)
        return path

    def test_seven_original_sources_resolve_protected_bodies_without_secret_drafts(self):
        wallet = self.wallet()
        cert = self.root / "cert.pem"; cert.write_text("certificate-" + CANARY)
        key = self.root / "key.pem"; key.write_text("key-" + CANARY)
        secret = CANARY + '\"\\\n$()`'
        files = {"/synthetic/wallet.zip": wallet, "/synthetic/cert.pem": cert, "/synthetic/key.pem": key}
        for source, body in BODIES.items():
            for operation in ("create", "test-connection"):
                with self.subTest(source=source, operation=operation):
                    template = json.loads(json.dumps(body))
                    if operation == "test-connection":
                        template.pop("displayName"); template.pop("catalogType")
                    for prop, value in template["connectionDetails"]["connectionProperties"].items():
                        for original, actual in files.items():
                            value = value.replace(original, str(actual))
                        template["connectionDetails"]["connectionProperties"][prop] = value
                    original = json.dumps(template)
                    with patch.object(protected, "prompt", return_value=secret):
                        cache = {}; protected.preflight(template, cache)
                        resolved = protected.resolve(template, cache)
                    self.assertEqual(json.dumps(template), original)
                    self.assertNotIn(CANARY, original)
                    props = resolved["connectionDetails"]["connectionProperties"]
                    if source == "ORACLE_ANALYTICS":
                        self.assertEqual(base64.b64decode(props["OAC_IDCS_PRIVATE_KEY"]).decode(), "key-" + CANARY)
                    else:
                        self.assertEqual(props["PASSWORD" if source == "KAFKA" else source + "_PASSWORD"], secret)
                    if source in ("ADW", "ALH", "ATP"):
                        self.assertEqual(base64.b64decode(props[source + "_WALLET_CONTENT_BASE64"]), wallet.read_bytes())

    def test_stored_password_templates_need_no_attachment(self):
        for source in ("ADW", "ALH", "ATP", "KAFKA", "ORACLE", "EXADATA"):
            prop = "PASSWORD" if source == "KAFKA" else source + "_PASSWORD"
            body = {"key": "catalog-key", "sourceType": source, "connectionDetails": {
                "connectionProperties": {prop: "{invisible_prompt_input:required:Enter replacement password}"}}}
            with patch.object(protected, "prompt", return_value=CANARY), patch.object(protected, "read_file") as files:
                cache = {}; protected.preflight(body, cache); resolved = protected.resolve(body, cache)
            files.assert_not_called()
            self.assertEqual(resolved["connectionDetails"]["connectionProperties"], {prop: CANARY})

    def test_service_listing_exposes_only_top_level_aliases(self):
        result = self.call("list-wallet-services.py", "--wallet", self.wallet())
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)["services"], ["sales_alias", "sales_high", "sales_low"])
        self.assertNotIn(CANARY, result.stdout + result.stderr)
        self.assertNotIn("private-wallet", result.stdout)

    def test_wallet_errors_do_not_echo_private_paths_or_contents(self):
        for path, code in ((self.root / CANARY, "FILE_NOT_FOUND"), (self.root / "broken.zip", "INVALID_WALLET_ZIP")):
            if code == "INVALID_WALLET_ZIP": path.write_text(CANARY)
            result = self.call("list-wallet-services.py", "--wallet", path)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["errorCode"], code)
            self.assertNotIn(CANARY, result.stdout + result.stderr)

    @unittest.skipIf(os.name == "nt", "POSIX symlink/FIFO invariants")
    def test_wallet_inputs_reject_symlinks_fifos_and_oversized_files(self):
        wallet = self.wallet(); link = self.root / "link.zip"; link.symlink_to(wallet)
        with self.assertRaises(private.InputError) as error: private.read_bytes(link, 100)
        self.assertEqual(error.exception.code, "SYMLINK_NOT_ALLOWED")
        fifo = self.root / "fifo"; os.mkfifo(fifo)
        with self.assertRaises(private.InputError): private.read_bytes(fifo, 100)
        with self.assertRaises(private.InputError): private.read_bytes(wallet, 1)
        with self.assertRaises(FileExistsError): private.write_private(link, {})

    def test_denied_access_has_safe_stage_and_no_os_error_excerpt(self):
        with patch.object(private.os, "open", side_effect=PermissionError(1, CANARY)):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = private.guarded(lambda: private.read_bytes(CANARY, 10, stage="wallet_file"))
        self.assertEqual(code, 1)
        result = json.loads(out.getvalue())
        self.assertEqual((result["errorCode"], result["stage"]), ("FILE_ACCESS_DENIED", "wallet_file"))
        self.assertNotIn(CANARY, out.getvalue())

    def test_wallet_zip_tns_and_format_errors_have_distinct_safe_codes(self):
        wallet = self.root / "wallet.zip"
        cases = [(None, "TNS_FILE_MISSING"), ("broken-tns", "INVALID_TNS_SYNTAX"),
                 ("a=(DESCRIPTION=broken", "INVALID_TNS_SYNTAX")]
        for text, code in cases:
            with zipfile.ZipFile(wallet, "w") as archive:
                archive.writestr("private.key" if text is None else "tnsnames.ora", text or CANARY)
            result = self.call("list-wallet-services.py", "--wallet", wallet)
            self.assertEqual(json.loads(result.stdout)["errorCode"], code)
            self.assertNotIn(CANARY, result.stdout + result.stderr)

    def test_quoted_hash_in_tns_and_path_expansion_are_supported(self):
        wallet = self.wallet('sales_low=(DESCRIPTION=(ADDRESS=(HOST=private))(SECURITY=(SSL_SERVER_CERT_DN="CN=server # (private)"))) # comment\n')
        result = self.call("list-wallet-services.py", "--wallet", wallet)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)["services"], ["sales_low"])
        with patch.object(private.os.path, "expanduser", return_value=str(wallet)):
            self.assertEqual(private.wallet_services("~/private-wallet.zip"), ["sales_low"])

    def test_path_validation_separates_readability_from_wallet_format(self):
        attachment = self.root / (CANARY + ".zip"); attachment.write_text(CANARY)
        result = self.call("validate-private-paths.py", "--wallet", attachment)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(json.loads(result.stdout)["checks"][0]["readable"])
        self.assertNotIn(CANARY, result.stdout + result.stderr)
        result = self.call("validate-private-paths.py", "--wallet", attachment, "--check-wallet")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["checks"][0]["errorCode"], "INVALID_WALLET_ZIP")
        self.assertNotIn(CANARY, result.stdout + result.stderr)

    def test_path_validation_checks_format_without_exposing_aliases(self):
        result = self.call("validate-private-paths.py", "--wallet", self.wallet(), "--check-wallet")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(json.loads(result.stdout)["checks"][0]["walletServicesParseable"])
        for value in ("sales_low", "sales_high", CANARY, "private-wallet.zip"):
            self.assertNotIn(value, result.stdout + result.stderr)

    def test_path_validation_reports_denied_access_and_empty_files(self):
        out = io.StringIO()
        with patch.object(sys, "argv", ["validator", "--wallet", CANARY]), \
             patch.object(validator, "read_bytes", side_effect=private.InputError("Access denied.", "FILE_ACCESS_DENIED", "wallet_file")), \
             contextlib.redirect_stdout(out):
            self.assertEqual(validator.main(), 1)
        self.assertEqual(json.loads(out.getvalue())["checks"][0]["errorCode"], "FILE_ACCESS_DENIED")
        self.assertNotIn(CANARY, out.getvalue())
        path = self.root / "empty.zip"; path.touch()
        result = self.call("validate-private-paths.py", "--wallet", path)
        self.assertEqual(json.loads(result.stdout)["checks"][0]["errorCode"], "EMPTY_FILE")

    def test_standalone_wallet_download_prompts_without_retaining_a_secret_draft(self):
        download_spec = importlib.util.spec_from_file_location("standalone_wallet", COMMON / "download-autonomous-wallet.py")
        download = importlib.util.module_from_spec(download_spec)
        download_spec.loader.exec_module(download)
        destination = self.root / "downloaded.zip"
        request_paths = []

        def run(command, **kwargs):
            request_path = Path(command[command.index("--from-json") + 1].removeprefix("file://"))
            request_paths.append(request_path)
            self.assertEqual(json.loads(request_path.read_text())["password"], CANARY)
            self.assertEqual(request_path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(CANARY, command)
            self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
            self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
            with zipfile.ZipFile(command[command.index("--file") + 1], "w") as archive:
                archive.writestr("tnsnames.ora", "sales_low=(DESCRIPTION=(ADDRESS=(HOST=private)))")
            return type("Result", (), {"returncode": 0})()

        out = io.StringIO()
        with contextlib.redirect_stdout(out), patch.object(out, "isatty", return_value=True), \
             patch.object(sys.stdin, "isatty", return_value=True), \
             patch.object(sys, "argv", ["download", "--wallet-output", str(destination), "--database-id", "db-id", "--auth", "api_key", "--profile", "chosen", "--region", "source-region"]), \
             patch.object(download.getpass, "getpass", return_value=CANARY), \
             patch.object(download.subprocess, "run", side_effect=run):
            self.assertEqual(download.main(), 0, out.getvalue())
        self.assertTrue(destination.exists())
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(out.getvalue())["walletFilePath"], str(destination))
        self.assertNotIn(CANARY, out.getvalue())
        self.assertTrue(all(not path.exists() for path in request_paths))
        self.assertEqual(list(self.root.glob("*.json")), [])

    def test_wallet_download_failures_delete_private_request_without_exposing_diagnostics(self):
        download = load("failed_wallet_download", COMMON / "download-autonomous-wallet.py")
        for failure in (None, FileNotFoundError(CANARY), subprocess.TimeoutExpired(CANARY, 1)):
            destination = self.root / "not-created.zip"
            requests = []

            def run(command, **kwargs):
                request = Path(command[command.index("--from-json") + 1].removeprefix("file://"))
                requests.append(request)
                self.assertEqual(json.loads(request.read_text())["password"], CANARY)
                if failure is not None:
                    raise failure
                return type("Result", (), {"returncode": 1})()

            out = io.StringIO()
            with contextlib.redirect_stdout(out), patch.object(out, "isatty", return_value=True), \
                 patch.object(sys.stdin, "isatty", return_value=True), \
                 patch.object(sys, "argv", ["download", "--wallet-output", str(destination), "--database-id", "db-id", "--auth", "api_key", "--profile", "chosen", "--region", "source-region"]), \
                 patch.object(download.getpass, "getpass", return_value=CANARY), \
                 patch.object(download.subprocess, "run", side_effect=run):
                self.assertEqual(private.guarded(download.main), 1)
            self.assertNotIn(CANARY, out.getvalue())
            self.assertFalse(destination.exists())
            self.assertTrue(requests)
            self.assertTrue(all(not path.exists() for path in requests))

    def test_codex_and_claude_catalog_resources_are_identical(self):
        for folder in ("references/ext-catalogs", "scripts/ext-catalogs"):
            codex = ROOT / "codex/skills/aidp-cli" / folder
            claude = ROOT / "claude/skills/aidp-cli" / folder
            files = [p for p in codex.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
            self.assertTrue(files)
            for path in files:
                self.assertEqual(path.read_bytes(), (claude / path.relative_to(codex)).read_bytes())


if __name__ == "__main__":
    unittest.main()
