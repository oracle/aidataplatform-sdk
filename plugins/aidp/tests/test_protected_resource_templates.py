# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
"""Generic JSON preparation and resolution, independent of resource field names."""
from __future__ import annotations

import base64
import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_sensitive_contracts import load_helper

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "codex/skills/aidp-cli"
FIXTURES = json.loads((ROOT / "tests/fixtures/protected_resource_bodies.json").read_text())
CANARY = "SYNTHETIC_PRIVATE_VALUE_7821"


class GenericResourceTemplateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.counter = 0
        self.protected = load_helper("generic_template_test", "protected_aidp.py")

    def prepare(self, body, variant="codex"):
        self.counter += 1
        target = self.root / f"body-{self.counter}.json"
        wrapper = load_helper("generic_" + variant, str(ROOT / variant / "skills/aidp-cli/scripts/protected_aidp.py"))
        original = copy.deepcopy(body)
        wrapper.write_body_template(target, body)
        self.assertEqual(body, original)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        return json.loads(target.read_text()), target

    def test_all_reviewed_resource_templates_are_preserved_in_both_variants(self):
        for variant in ("codex", "claude"):
            for name, template in FIXTURES.items():
                with self.subTest(variant=variant, template=name):
                    body, _ = self.prepare(template, variant)
                    self.assertEqual(body, template)

    def test_future_fields_types_references_and_public_schema_labels_are_opaque(self):
        body = {"type": "FUTURE_TYPE", "public": {"token": "A field label", "password": "Another label"},
                "reference": json.dumps({"type": "NEW_RESOURCE_REFERENCE", "key": "public-key"}),
                "nested": [False, 0, None, {"properties": {"api_key": {"type": "string"}}}],
                "optionalOmitted": {}, "unknownAuth": {"authType": "FUTURE"}}
        actual, _ = self.prepare(body)
        self.assertEqual(actual, body)
        self.assertNotIn("prompt_input", json.dumps(actual))
        self.assertNotIn("clientSecret", actual["unknownAuth"])

    def test_arrays_and_empty_objects_are_not_rewritten_or_given_defaults(self):
        for body in ({}, [], [None, False, 0, "", {"isDefault": True}]):
            actual, _ = self.prepare(body)
            self.assertEqual(actual, body)

    def test_writing_template_never_reads_attachments_or_prompts(self):
        target = self.root / "body.json"
        body = {"one": "{textof:/not-accessed/private.pem}", "two": "{base64of:/not-accessed/wallet.zip}",
                "three": "{invisible_prompt_input:required:Enter a private value}"}
        with patch.object(self.protected, "read_file", side_effect=AssertionError("No attachment reads")), \
             patch("builtins.input", side_effect=AssertionError("No prompting")), \
             patch.object(self.protected.getpass, "getpass", side_effect=AssertionError("No secret input")):
            self.protected.write_body_template(target, body)
        self.assertEqual(json.loads(target.read_text()), body)

    def test_existing_output_is_not_overwritten(self):
        target = self.root / "existing.json"
        target.write_text("unchanged")
        with self.assertRaises(FileExistsError):
            self.protected.write_body_template(target, {})
        self.assertEqual(target.read_text(), "unchanged")

    def test_required_optional_text_base64_and_nested_values_resolve_generically(self):
        attachment = self.root / "attachment.txt"
        content = CANARY + "\nsecond line\n"
        attachment.write_text(content)
        body = {"newField": "{invisible_prompt_input:required:Private input}",
                "nested": ["{visible_prompt_input:optional:Optional input}",
                           {"file": "{textof:" + str(attachment) + "}",
                            "encoded": "{base64of:" + str(attachment) + "}"}],
                "unchanged": [False, 0, None, "public"]}
        _, template = self.prepare(body)
        original = template.read_bytes()
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(output, "isatty", return_value=True), \
             patch.object(sys.stdin, "isatty", return_value=True), patch("builtins.input", return_value=""), \
             patch.object(self.protected.getpass, "getpass", return_value=CANARY):
            resolved = self.protected.resolve(body)
        self.assertEqual(resolved["newField"], CANARY)
        self.assertEqual(resolved["nested"][0], "", "Optional blank is an empty string, not omission")
        self.assertEqual(resolved["nested"][1]["file"], content)
        self.assertEqual(resolved["nested"][1]["encoded"], base64.b64encode(content.encode()).decode())
        self.assertEqual(resolved["unchanged"], body["unchanged"])
        self.assertEqual(template.read_bytes(), original)
        self.assertEqual(attachment.read_text(), content)
        self.assertNotIn(CANARY, output.getvalue())

    def test_required_prompt_retries_blank_and_reuses_only_identical_markers(self):
        marker = "{visible_prompt_input:required:Enter first value}"
        body = [marker, marker, "{visible_prompt_input:required:Enter second value}"]
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(output, "isatty", return_value=True), \
             patch.object(sys.stdin, "isatty", return_value=True), \
             patch("builtins.input", side_effect=[" ", "first", "second"]) as ask:
            resolved = self.protected.resolve(body)
        self.assertEqual(resolved, ["first", "first", "second"])
        self.assertEqual(ask.call_count, 3)
        self.assertIn("A value is required", output.getvalue())

    def test_same_optional_and_required_behavior_for_hidden_prompts(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(output, "isatty", return_value=True), \
             patch.object(sys.stdin, "isatty", return_value=True), \
             patch.object(self.protected.getpass, "getpass", side_effect=["", CANARY, ""]):
            resolved = self.protected.resolve(["{invisible_prompt_input:required:Secret}",
                                               "{invisible_prompt_input:optional:Optional secret}"])
        self.assertEqual(resolved, [CANARY, ""])
        self.assertNotIn(CANARY, output.getvalue())

    def test_generic_execution_preserves_references_and_cleans_up_on_success_and_failure(self):
        protected = self.protected
        for name, fixture in FIXTURES.items():
            for exit_code in (0, 153):
                body = copy.deepcopy(fixture)
                attachment = self.root / "private.pem"
                attachment.write_text(CANARY + "\n")
                def local_paths(value):
                    if isinstance(value, dict): return {k: local_paths(v) for k, v in value.items()}
                    if isinstance(value, list): return [local_paths(v) for v in value]
                    return "{textof:" + str(attachment) + "}" if value == "{textof:/synthetic/private.pem}" else value
                body = local_paths(body)
                _, template = self.prepare(body)
                original = template.read_bytes()
                target = self.root / f"result-{self.counter}.json"
                actual_paths = []
                def fake_cli(args, **kwargs):
                    actual = Path(args[args.index("--body") + 1][1:]); actual_paths.append(actual)
                    self.assertEqual(actual.stat().st_mode & 0o777, 0o600)
                    resolved = json.loads(actual.read_text())
                    self.assertNotIn("prompt_input", json.dumps(resolved))
                    self.assertNotIn("{textof:", json.dumps(resolved))
                    # A reference is copied, not transformed to a secret input.
                    if name == "agent_registry_reference":
                        self.assertEqual(resolved, fixture)
                    kwargs["stdout"].write(b'Response:\n{"status":200}\n')
                    return SimpleNamespace(returncode=exit_code)
                output = io.StringIO()
                with contextlib.redirect_stdout(output), patch.object(output, "isatty", return_value=True), \
                     patch.object(sys.stdin, "isatty", return_value=True), patch("builtins.input", return_value="local-user"), \
                     patch.object(protected.getpass, "getpass", return_value=CANARY), \
                     patch.object(protected.subprocess, "run", side_effect=fake_cli):
                    code = protected.main(["--output-file", str(target), "--", "aidp", "future-operation",
                                           "--body", "@" + str(template)])
                self.assertEqual(code, exit_code)
                self.assertEqual(output.getvalue(), "Operation output handed off to AI agent. Ask it to continue.\n")
                self.assertTrue(actual_paths)
                self.assertTrue(all(not p.exists() and not p.parent.exists() for p in actual_paths))
                self.assertEqual(template.read_bytes(), original)
                self.assertEqual(attachment.read_text(), CANARY + "\n")
                self.assertEqual(target.stat().st_mode & 0o777, 0o600)
                self.assertEqual(json.loads(target.read_text())["exitCode"], exit_code)

    def test_cancellation_never_invokes_cli_and_keeps_unresolved_template(self):
        body, template = self.prepare({"arbitrarySecretField": "{invisible_prompt_input:required:Enter private input}"})
        target = self.root / "cancelled-result.json"
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(output, "isatty", return_value=True), \
             patch.object(sys.stdin, "isatty", return_value=True), \
             patch.object(self.protected.getpass, "getpass", side_effect=KeyboardInterrupt), \
             patch.object(self.protected.subprocess, "run") as cli:
            self.assertEqual(self.protected.main(["--output-file", str(target), "--", "aidp", "future",
                                                  "--body", "@" + str(template)]), 1)
        cli.assert_not_called()
        self.assertEqual(json.loads(template.read_text()), body)
        self.assertNotIn(CANARY, output.getvalue())
        self.assertIn("CANCELLED", json.loads(target.read_text())["stdout"])

    def test_variants_ship_identical_generic_code_and_retire_old_builders(self):
        for relative in ("scripts/protected_aidp.py",):
            self.assertEqual((SKILL / relative).read_bytes(),
                             (ROOT / "claude/skills/aidp-cli" / relative).read_bytes())
        for variant in ("codex", "claude"):
            base = ROOT / variant / "skills/aidp-cli/scripts"
            for old in ("common/protected_resource_templates.py", "credentials/prepare-body.py",
                        "agents/prepare-body.py", "user-settings/prepare-body.py"):
                self.assertFalse((base / old).exists())


if __name__ == "__main__":
    unittest.main()
