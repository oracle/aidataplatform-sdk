from __future__ import annotations

import importlib.util
import errno
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
CODEX_SKILL = REPO_ROOT / "plugins/aidp/codex/skills/aidp-cli"
CLAUDE_SKILL = REPO_ROOT / "plugins/aidp/claude/skills/aidp-cli"
SCRIPT = CODEX_SKILL / "scripts/GenerateAIDPCLIDoc.py"

MANIFEST = {
    "commandGroups": [
        {
            "name": "catalog",
            "description": "Catalogs.",
            "commands": [],
        }
    ]
}


def load_module():
    spec = importlib.util.spec_from_file_location("generate_cli_doc", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GenerateCliDocTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name) / "docs"
        self.module = load_module()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def generate(self, version: str = "9.9.9"):
        with mock.patch.object(self.module.metadata, "version", return_value=version), \
                mock.patch.object(self.module, "installed_cli", return_value=(version, MANIFEST)):
            return self.module.generate(self.output_dir)

    def test_generates_versioned_reference(self) -> None:
        target = self.generate()
        self.assertEqual(target, self.output_dir / "aidp-cli-9.9.9.md")
        text = target.read_text()
        self.assertIn("# AIDP CLI Command Reference", text)
        self.assertIn("Catalog", text)

    def test_existing_reference_is_left_unchanged(self) -> None:
        self.output_dir.mkdir()
        existing = self.output_dir / "aidp-cli-9.9.9.md"
        existing.write_text("kept")
        self.assertIsNone(self.generate())
        self.assertEqual(existing.read_text(), "kept")

    def test_new_version_gets_its_own_reference(self) -> None:
        self.generate("9.9.9")
        self.generate("10.0.0")
        names = sorted(path.name for path in self.output_dir.iterdir())
        self.assertEqual(names, ["aidp-cli-10.0.0.md", "aidp-cli-9.9.9.md"])

    def test_rejects_version_with_path_separator(self) -> None:
        with self.assertRaises(RuntimeError):
            self.generate("../escape")

    def test_windows_lock_branch_preserves_generated_document(self) -> None:
        busy = OSError(errno.EACCES, "file is locked")
        locking = mock.Mock(side_effect=[busy, None, None])
        windows_lock = SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=locking)
        with mock.patch.object(self.module, "fcntl", None), \
                mock.patch.dict(sys.modules, {"msvcrt": windows_lock}), \
                mock.patch.object(self.module.time, "sleep") as sleep:
            target = self.generate()
        self.assertIn("# AIDP CLI Command Reference", target.read_text())
        self.assertEqual([call.args[1:] for call in locking.call_args_list], [(1, 1), (1, 1), (2, 1)])
        sleep.assert_called_once_with(0.1)

    def test_claude_and_codex_copies_are_identical(self) -> None:
        for relative_path in ("SKILL.md", "scripts/GenerateAIDPCLIDoc.py"):
            self.assertEqual(
                (CODEX_SKILL / relative_path).read_bytes(),
                (CLAUDE_SKILL / relative_path).read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
