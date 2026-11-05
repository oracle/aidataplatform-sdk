from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CODEX_SKILL = REPO_ROOT / "plugins/aidp/codex/skills/aidp-setup-local"
CLAUDE_SKILL = REPO_ROOT / "plugins/aidp/claude/skills/aidp-setup-local"
SCRIPT = CODEX_SKILL / "scripts/validate_oci_security_token.py"

EXPIRED_LINE = "ERROR: This CLI session has expired, so it cannot currently be used to run commands"


def load_module():
    spec = importlib.util.spec_from_file_location("validate_token", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # Dataclasses resolve their module through sys.modules while loading.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ValidateSecurityTokenTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.module = load_module()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def fake_oci(self, body: str) -> str:
        """A stand-in `oci` command that runs the given shell body."""
        path = Path(self.temp_dir.name) / "oci"
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return str(path)

    def validate(self, oci_path: str) -> dict:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.module.validate("DEFAULT", "us-phoenix-1", oci_path)
        return json.loads(output.getvalue())

    def test_oci_expired_session_message_is_expired(self) -> None:
        oci = self.fake_oci(
            "echo '" + EXPIRED_LINE + "'\n"
            "echo 'Do you want to re-authenticate your CLI session profile? [Y/n]: Abort:' >&2\n"
            "exit 1"
        )
        result = self.validate(oci)
        self.assertEqual(result["status"], "expired")
        self.assertEqual(result["detail"], EXPIRED_LINE)

    def test_other_failure_mentioning_expired_is_invalid(self) -> None:
        oci = self.fake_oci("echo 'ERROR: SSL certificate has expired for the proxy' >&2\nexit 1")
        result = self.validate(oci)
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["detail"], "ERROR: SSL certificate has expired for the proxy")

    def test_missing_profile_keeps_its_status(self) -> None:
        oci = self.fake_oci("echo \"ERROR: Profile 'DEFAULT' not found in config file\" >&2\nexit 1")
        result = self.validate(oci)
        self.assertEqual(result["status"], "profile_missing")
        self.assertIn("not found", result["detail"])

    def test_detail_is_one_bounded_line_without_colour_codes(self) -> None:
        long_text = "x" * 400
        oci = self.fake_oci(
            "printf '\\033[31mERROR: " + long_text + "\\033[0m\\nsecond line\\n' >&2\nexit 1"
        )
        detail = self.validate(oci)["detail"]
        self.assertTrue(detail.startswith("ERROR: x"))
        self.assertNotIn("\n", detail)
        self.assertNotIn("\x1b", detail)
        self.assertLessEqual(len(detail), self.module.DETAIL_MAX_LENGTH)

    def test_interactive_prompt_does_not_wait_for_input(self) -> None:
        # Real `oci session validate` asks to re-authenticate an expired
        # session; with closed input it must abort at once, not time out.
        oci = self.fake_oci(
            "if read answer; then echo 'ERROR: waited for input' >&2; exit 1; fi\n"
            "echo '" + EXPIRED_LINE + "'\nexit 1"
        )
        started = time.monotonic()
        result = self.validate(oci)
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(result["status"], "expired")

    def test_success_has_no_detail(self) -> None:
        oci = self.fake_oci(
            'case "$*" in *"session validate"*) echo "Session is valid until 2026-10-09 15:02:24"; exit 0;; esac\n'
            "exit 1"
        )
        result = self.validate(oci)
        self.assertNotIn("detail", result)
        self.assertEqual(result["validUntil"], "2026-10-09 15:02:24")

    def test_claude_and_codex_copies_are_identical(self) -> None:
        for relative_path in (
            "scripts/validate_oci_security_token.py",
            "references/oci-profile-validation.md",
        ):
            self.assertEqual(
                (CODEX_SKILL / relative_path).read_bytes(),
                (CLAUDE_SKILL / relative_path).read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
