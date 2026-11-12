# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
from __future__ import annotations

import base64
import contextlib
import importlib.util
import io
import json
import os
import signal
import time
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "codex/skills/aidp-cli/scripts/protected_aidp.py"
spec = importlib.util.spec_from_file_location("protected_aidp", SCRIPT)
protected = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protected)
SECRET = 'SECRET_CANARY_9012"\\\n$()`'


class ProtectedAidpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.handoff_count = 0

    def template(self, value, name="body.json"):
        path = self.root / name
        path.write_text(json.dumps(value))
        return path

    def run_interactive(self, command, visible=(), hidden=(), callback=None):
        out = io.StringIO()
        self.handoff_count += 1
        target = self.root / f"interactive-result-{self.handoff_count}.json"
        with contextlib.redirect_stdout(out), patch.object(out, "isatty", return_value=True), \
             patch.object(sys.stdin, "isatty", return_value=True), \
             patch("builtins.input", side_effect=visible) as visible_prompt, \
             patch.object(protected.getpass, "getpass", side_effect=hidden) as hidden_prompt, \
             patch.object(protected.subprocess, "run", side_effect=callback) as api:
            code = protected.main(["--output-file", str(target), "--", *command])
        self.assertTrue(out.getvalue().endswith("Operation output handed off to AI agent. Ask it to continue.\n"))
        self.assertNotIn(SECRET, out.getvalue())
        data = json.loads(target.read_text())
        target.unlink()
        self.assertEqual(data["exitCode"], code)
        return code, data["stdout"], visible_prompt, hidden_prompt, api

    def response(self, status=200, exit_code=0):
        def callback(command, **kwargs):
            kwargs["stdout"].write(("Response:\n" + json.dumps({"status": status, "message": SECRET, "data": {"secret": SECRET}}) + "\n").encode())
            return SimpleNamespace(returncode=exit_code)
        return callback

    def test_nested_prompts_files_generic_command_and_private_copy_disposal(self):
        wallet = self.root / "wallet with spaces.zip"; wallet.write_bytes(b"wallet secret")
        key = self.root / "key.pem"; key.write_text("PEM\n" + SECRET)
        body = {"items": [{"username": "{visible_prompt_input:required:Enter username}",
                           "password": "{invisible_prompt_input:required:Enter password}",
                           "wallet": "{base64of:" + str(wallet) + "}",
                           "privateKey": "{textof:" + str(key) + "}"}], "enabled": True, "count": 3}
        template = self.template(body); original = template.read_bytes(); actuals = []
        command = ["/custom/aidp", "--profile", "chosen", "credentials", "create", "--body", "@" + str(template)]

        def callback(args, **kwargs):
            self.assertEqual(args[:-1], command[:-1])
            actual = Path(args[-1][1:]); actuals.append(actual)
            self.assertNotEqual(actual, template)
            self.assertTrue(actual.name.startswith("actual_body_"))
            if os.name != "nt":
                self.assertEqual(actual.stat().st_mode & 0o777, 0o600)
                self.assertEqual(actual.parent.stat().st_mode & 0o777, 0o700)
            resolved = json.loads(actual.read_text())
            self.assertEqual(resolved["items"][0]["password"], SECRET)
            self.assertEqual(resolved["items"][0]["privateKey"], "PEM\n" + SECRET)
            self.assertEqual(base64.b64decode(resolved["items"][0]["wallet"]), b"wallet secret")
            self.assertTrue(resolved["enabled"])
            self.assertEqual(kwargs["env"]["AIDP_CLI_STRICT_URL_ENCODING"], "true")
            return self.response()(args, **kwargs)

        code, output, visible, hidden, api = self.run_interactive(command, visible=["user"], hidden=[SECRET], callback=callback)
        self.assertEqual(code, 0, output)
        self.assertEqual(template.read_bytes(), original)
        self.assertTrue(all(not path.exists() and not path.parent.exists() for path in actuals))
        self.assertEqual(visible.call_count, 1); self.assertEqual(hidden.call_count, 1)
        api.assert_called_once()
        self.assertEqual(output, "Response:\n" + json.dumps({"status": 200, "message": SECRET, "data": {"secret": SECRET}}) + "\n")

    def test_required_optional_and_identical_prompts(self):
        value = ["{visible_prompt_input:required:Username}",
                 "{invisible_prompt_input:required:Password}",
                 "{invisible_prompt_input:required:Password}",
                 "{invisible_prompt_input:optional:Wallet password}",
                 "{visible_prompt_input:optional:Optional username}"]
        out = io.StringIO()
        with contextlib.redirect_stdout(out), patch.object(out, "isatty", return_value=True), \
             patch.object(sys.stdin, "isatty", return_value=True), \
             patch("builtins.input", side_effect=["", "   ", "user", ""]) as visible, \
             patch.object(protected.getpass, "getpass", side_effect=["", SECRET, ""]) as hidden:
            result = protected.resolve(value)
        self.assertEqual(result, ["user", SECRET, SECRET, "", ""])
        self.assertEqual(visible.call_count, 4); self.assertEqual(hidden.call_count, 3)
        self.assertEqual(visible.call_args_list[0].args, ("Username: ",))
        self.assertEqual(hidden.call_args_list[-1].args[0], "Wallet password (optional): ")
        self.assertNotIn(SECRET, out.getvalue())

    def test_invalid_prompt_metadata_fails_before_any_input(self):
        for value in ("{visible_prompt_input:required:}",
                      "{invisible_prompt_input:optional:   }",
                      "{visible_prompt_input:maybe:Username}"):
            template = self.template({"first": "{invisible_prompt_input:required:Password}", "invalid": value})
            code, output, visible, hidden, api = self.run_interactive(["aidp", "--body", "@" + str(template)])
            self.assertEqual(code, 1)
            visible.assert_not_called(); hidden.assert_not_called(); api.assert_not_called()
            self.assertIn("INVALID_PROMPT", output)
        self.assertEqual(protected.prompt_spec("visible_prompt_input", "required:Account: username"),
                         ("Account: username", False, True))

    def test_removed_prompt_aliases_and_missing_modes_are_rejected_before_input(self):
        for value in ("{optional_visible_prompt_input:Name}", "{optional_invisible_prompt_input:Password}",
                      "{visible_prompt_input:Name}", "{invisible_prompt_input:Password}"):
            template = self.template({"value": value})
            code, output, visible, hidden, api = self.run_interactive(["aidp", "--body", "@" + str(template)])
            self.assertEqual(code, 1)
            visible.assert_not_called(); hidden.assert_not_called(); api.assert_not_called()

    def test_output_handoff_is_required_before_opening_any_body(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), patch.object(protected, "read_body_template") as body, \
             patch.object(protected.subprocess, "run") as api:
            code = protected.main(["aidp", "--body", "@unused"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out.getvalue())["errorCode"], "OUTPUT_ARGUMENT_REQUIRED")
        body.assert_not_called(); api.assert_not_called()

    def test_standalone_path_checker_without_credentials_or_cli(self):
        attachment = self.root / "private file.txt"
        checker = SCRIPT.with_name("validate-protected-paths.py")
        for data, error in ((None, "FILE_NOT_FOUND"), (b"", "EMPTY_FILE"), (SECRET.encode(), None)):
            if data is not None:
                attachment.write_bytes(data)
            template = self.template({"password": "{invisible_prompt_input:required:Password}",
                                      "nested": [{"file": "{base64of:" + str(attachment) + "}"}]})
            result = subprocess.run([sys.executable, str(checker), "@" + str(template)],
                                    capture_output=True, text=True, stdin=subprocess.DEVNULL)
            response = json.loads(result.stdout)
            self.assertEqual(result.returncode, 1 if error else 0, result.stdout)
            self.assertEqual(response["ok"], error is None)
            if error:
                self.assertEqual(response["errorCode"], error)
            else:
                self.assertEqual(response["fileReferences"], 1)
            self.assertNotIn(SECRET, result.stdout + result.stderr)
            self.assertNotIn(str(attachment), result.stdout + result.stderr)
            self.assertEqual(list(self.root.glob("aidp-protected-*")), [])

    def test_failed_http_response_still_disposes_body_and_preserves_template(self):
        template = self.template({"value": "{visible_prompt_input:optional:Optional value}"})
        actuals = []
        def failed(args, **kwargs):
            actuals.append(Path(args[-1][1:]))
            return self.response(409, 153)(args, **kwargs)
        code, output, _, _, api = self.run_interactive(["aidp", "agent", "update", "--body", "@" + str(template)], visible=[""], callback=failed)
        self.assertEqual(code, 153)
        self.assertFalse(actuals[0].exists()); self.assertTrue(template.exists())
        self.assertNotIn("temporaryBodyDeleted", output)
        self.assertEqual(json.loads(output.split("\n", 1)[1])["message"], SECRET); api.assert_called_once()

    def test_validation_happens_before_credentials_and_never_claims_collection(self):
        template = self.template({"password": "{invisible_prompt_input:required:Password}", "file": "{base64of:" + str(self.root / "missing") + "}"})
        code, output, visible, hidden, api = self.run_interactive(["aidp", "catalog", "create", "--body", "@" + str(template)])
        self.assertEqual(code, 1); hidden.assert_not_called(); api.assert_not_called()
        self.assertIn("FILE_NOT_FOUND", output)
        self.assertNotIn("collected successfully", output)

    def test_launch_timeout_and_cancellation_cleanup(self):
        constructor = protected.tempfile.TemporaryDirectory
        def temporary(*args, **kwargs):
            return constructor(*args, **dict(kwargs, dir=self.root))
        for exception in (FileNotFoundError(SECRET), subprocess.TimeoutExpired("private", 1), KeyboardInterrupt()):
            template = self.template({"value": "known"})
            with patch.object(protected.tempfile, "TemporaryDirectory", side_effect=temporary):
                code, output, _, _, api = self.run_interactive(["aidp", "catalog", "create", "--body", "@" + str(template)], callback=exception)
            self.assertEqual(code, 1); self.assertTrue(template.exists()); api.assert_called_once()
            self.assertEqual(list(self.root.glob("aidp-protected-*")), [])
            self.assertNotIn(SECRET, output)

    def test_hidden_input_never_falls_back_to_echoed_input(self):
        with patch.object(sys.stdin, "isatty", return_value=True), \
             patch.object(sys.stdout, "isatty", return_value=True), \
             patch.object(protected.getpass, "getpass", side_effect=protected.getpass.GetPassWarning()):
            with self.assertRaises(protected.ProtectedError) as error:
                protected.prompt("Password", True, True)
        self.assertEqual(error.exception.code, "HIDDEN_INPUT_UNAVAILABLE")
        with patch.object(sys.stdin, "isatty", return_value=False):
            with self.assertRaises(protected.ProtectedError): protected.prompt("Password", True, True)

    def test_malformed_embedded_legacy_and_key_placeholders_are_rejected(self):
        for value in ("prefix {invisible_prompt_input:required:Password}", "{aidp-secret-input.password}",
                      {"{visible_prompt_input:required:Name}": "value"},
                      {"{optional_visible_prompt_input:Name}": "value"},
                      {"{aidp-secret-input.password}": "value"}):
            with self.assertRaises(protected.ProtectedError): protected.preflight(value, {})

    def test_joined_body_flag_and_non_prompt_array_body(self):
        template = self.template([{"value": 1}]); copied = []
        def callback(args, **kwargs):
            reference = args[-1].removeprefix("--body=@")
            copied.append(Path(reference))
            self.assertEqual(json.loads(Path(reference).read_text()), [{"value": 1}])
            return self.response()(args, **kwargs)
        code, output, _, _, _ = self.run_interactive(["aidp", "generic", "operation", "--body=@" + str(template)], callback=callback)
        self.assertEqual(code, 0, output); self.assertFalse(copied[0].exists())

    def test_command_validation_rejects_inline_duplicate_and_debug_bodies(self):
        for command in (["aidp", "--body", "{}"], ["aidp", "--body", "@a", "--body", "@b"],
                        ["aidp", "--debug=true", "--body", "@a"]):
            code, output, _, _, api = self.run_interactive(command)
            self.assertEqual(code, 1); api.assert_not_called()

    def test_real_wrapper_process_passes_temporary_body_and_preserves_output(self):
        attachment = self.root / "attachment.txt"; attachment.write_text(SECRET)
        template = self.template({"secret": "{base64of:" + str(attachment) + "}"})
        trace = self.root / "child-body-path.txt"
        fake = self.root / "fake-cli.py"
        fake.write_text("import sys,json\nfrom pathlib import Path\n"
                        "p=sys.argv[sys.argv.index('--body')+1][1:]\n"
                        "Path(" + repr(str(trace)) + ").write_text(p)\n"
                        "body=json.loads(Path(p).read_text())\n"
                        "print('Response:')\nprint(json.dumps({'status':200,'data':body}))\n")
        target = self.root / "real-result.json"
        result = subprocess.run([sys.executable, str(SCRIPT), "--output-file", str(target), "--", sys.executable, str(fake),
                                 "--body", "@" + str(template)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        actual = Path(trace.read_text())
        self.assertNotEqual(actual, template)
        self.assertFalse(actual.exists()); self.assertFalse(actual.parent.exists())
        self.assertTrue(template.exists()); self.assertTrue(attachment.exists())
        self.assertEqual(result.stdout, "Operation output handed off to AI agent. Ask it to continue.\n")
        self.assertEqual(json.loads(target.read_text())["stdout"], "Response:\n" + json.dumps({"status": 200, "data": {"secret": base64.b64encode(SECRET.encode()).decode()}}) + "\n")

    def test_real_child_stderr_and_exit_code_are_unchanged(self):
        template = self.template({"value": 1})
        program = "import sys; sys.stdout.write('original output\\n'); sys.stderr.write('409 conflict details\\n'); sys.exit(153)"
        target = self.root / "real-result.json"
        result = subprocess.run([sys.executable, str(SCRIPT), "--output-file", str(target), "--", sys.executable, "-c", program,
                                 "--body", "@" + str(template)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 153)
        self.assertEqual(result.stdout, "Operation output handed off to AI agent. Ask it to continue.\n")
        self.assertEqual(result.stderr, "")
        data = json.loads(target.read_text())
        self.assertEqual(data["stdout"], "original output\n")
        self.assertEqual(data["stderr"], "409 conflict details\n")

    def handoff(self, program, target, template=None):
        template = template or self.template({"value": 1})
        return subprocess.run([sys.executable, str(SCRIPT), "--output-file", str(target), "--",
                               sys.executable, "-c", program, "--body", "@" + str(template)],
                              capture_output=True, text=True)

    def test_handoff_completion_output_exit_code_and_consume_delete(self):
        target = self.root / "result.json"
        trace = self.root / "body-path"
        program = ("import sys; from pathlib import Path; "
                   "p=sys.argv[sys.argv.index('--body')+1][1:]; "
                   "Path(" + repr(str(trace)) + ").write_text(p); "
                   "sys.stdout.write('original stdout\\n'); sys.stderr.write('original stderr\\n'); sys.exit(153)")
        result = self.handoff(program, target)
        self.assertEqual(result.returncode, 153)
        self.assertEqual(result.stdout, "Operation output handed off to AI agent. Ask it to continue.\n")
        self.assertEqual(result.stderr, "")
        self.assertFalse(Path(trace.read_text()).exists())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        data = json.loads(target.read_text())
        self.assertEqual(data, {"complete": True, "exitCode": 153, "stdout": "original stdout\n", "stderr": "original stderr\n"})
        consumed = subprocess.run([sys.executable, str(SCRIPT.with_name("read-protected-result.py")), str(target)],
                                  capture_output=True, text=True)
        self.assertEqual(consumed.returncode, 0, consumed.stdout)
        self.assertEqual(json.loads(consumed.stdout), data)
        self.assertFalse(target.exists())
        self.assertEqual(list(self.root.glob(".*.part")), [])

    def test_catalog_handoff_is_source_independent_including_oracle(self):
        password = self.root / "synthetic-password.txt"; password.write_text(SECRET)
        reader = SCRIPT.with_name("read-protected-result.py")
        for source in ("ADW", "ALH", "KAFKA", "ATP", "ORACLE", "EXADATA", "MYSQL", "DB2",
                       "AZURE_SQLSERVER", "SNOWFLAKE", "GOOGLE_BIGQUERY", "ORACLE_ANALYTICS"):
            for status, exit_code in ((200, 0), (409, 153)):
                with self.subTest(source=source, status=status):
                    template = self.template({"sourceType": source, "connectionDetails": {
                        "connectionProperties": {("password" if source == "DB2" else "GOOGLE_BIGQUERY_OAUTH_PVT_KEY" if source == "GOOGLE_BIGQUERY" else source + "_PASSWORD"): "{textof:" + str(password) + "}"}}},
                        source + str(status) + "-body.json")
                    target = self.root / (source + str(status) + "-result.json")
                    trace = self.root / (source + str(status) + "-trace.txt")
                    program = ("import sys,json; from pathlib import Path; "
                               "p=Path(sys.argv[sys.argv.index('--body')+1][1:]); "
                               "body=json.loads(p.read_text()); "
                               "Path(" + repr(str(trace)) + ").write_text(str(p)); "
                               "assert body['sourceType']==" + repr(source) + "; "
                               "print('Response:'); print(json.dumps({'status':" + str(status) + ", 'sourceType':body['sourceType']})); "
                               "sys.exit(" + str(exit_code) + ")")
                    result = self.handoff(program, target, template)
                    self.assertEqual(result.returncode, exit_code)
                    self.assertEqual(result.stdout, "Operation output handed off to AI agent. Ask it to continue.\n")
                    self.assertEqual(result.stderr, "")
                    self.assertFalse(Path(trace.read_text()).exists())
                    consumed = subprocess.run([sys.executable, str(reader), str(target)], capture_output=True, text=True)
                    self.assertEqual(consumed.returncode, 0)
                    data = json.loads(consumed.stdout)
                    self.assertEqual(data["exitCode"], exit_code)
                    self.assertEqual(json.loads(data["stdout"].split("\n", 1)[1]), {"status": status, "sourceType": source})
                    self.assertFalse(target.exists())

    def test_handoff_never_overwrites_and_reports_preflight_failure(self):
        target = self.root / "result.json"; target.write_text("existing")
        marker = self.root / "must-not-exist"
        result = self.handoff("from pathlib import Path; Path(" + repr(str(marker)) + ").touch()", target)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(marker.exists()); self.assertEqual(target.read_text(), "existing")
        target.unlink()
        template = self.template({"file": "{base64of:" + str(self.root / "missing") + "}"})
        result = self.handoff("raise RuntimeError('must not execute')", target, template)
        self.assertEqual(result.returncode, 1)
        data = json.loads(target.read_text())
        self.assertEqual(json.loads(data["stdout"])["errorCode"], "FILE_NOT_FOUND")
        self.assertEqual(data["exitCode"], 1)

    def test_result_reader_timeout_and_invalid_json_cleanup(self):
        reader = SCRIPT.with_name("read-protected-result.py")
        target = self.root / "result.json"
        result = subprocess.run([sys.executable, str(reader), str(target)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2); self.assertFalse(json.loads(result.stdout)["ready"])
        target.write_text("invalid " + SECRET); target.chmod(0o600)
        result = subprocess.run([sys.executable, str(reader), str(target)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1); self.assertFalse(target.exists())
        self.assertNotIn(SECRET, result.stdout + result.stderr)

    @unittest.skipUnless(os.name == "posix", "POSIX terminal interrupt")
    def test_ctrl_c_deletes_body_and_publishes_completed_handoff(self):
        target = self.root / "result.json"; trace = self.root / "body-path"
        template = self.template({"value": 1})
        program = ("import sys,time; from pathlib import Path; "
                   "Path(" + repr(str(trace)) + ").write_text(sys.argv[sys.argv.index('--body')+1][1:]); time.sleep(20)")
        proc = subprocess.Popen([sys.executable, str(SCRIPT), "--output-file", str(target), "--",
                                 sys.executable, "-c", program, "--body", "@" + str(template)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            deadline = time.monotonic() + 5
            while not trace.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(trace.exists())
            self.assertFalse(target.exists())  # No partial result can be consumed.
            os.killpg(proc.pid, signal.SIGINT)
            proc.communicate(timeout=5)
            self.assertFalse(Path(trace.read_text()).exists())
            self.assertTrue(json.loads(target.read_text())["complete"])
            self.assertNotEqual(json.loads(target.read_text())["exitCode"], 0)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.communicate()

    def test_skill_copies_match(self):
        self.assertEqual(SCRIPT.read_bytes(), (ROOT / "claude/skills/aidp-cli/scripts/protected_aidp.py").read_bytes())
        checker = "skills/aidp-cli/scripts/validate-protected-paths.py"
        self.assertEqual((ROOT / "codex" / checker).read_bytes(), (ROOT / "claude" / checker).read_bytes())
        reader = "skills/aidp-cli/scripts/read-protected-result.py"
        self.assertEqual((ROOT / "codex" / reader).read_bytes(), (ROOT / "claude" / reader).read_bytes())
        a = ROOT / "codex/skills/aidp-cli/references/protected-bodies.md"
        b = ROOT / "claude/skills/aidp-cli/references/protected-bodies.md"
        self.assertEqual(a.read_bytes(), b.read_bytes())


if __name__ == "__main__":
    unittest.main()
