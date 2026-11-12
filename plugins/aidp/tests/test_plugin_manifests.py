# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
from __future__ import annotations

import json
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_MANIFEST = PLUGIN_ROOT / "claude/.claude-plugin/plugin.json"
CODEX_MANIFEST = PLUGIN_ROOT / "codex/.codex-plugin/plugin.json"


class PluginManifestTest(unittest.TestCase):
    def test_claude_and_codex_versions_match(self) -> None:
        claude = json.loads(CLAUDE_MANIFEST.read_text())
        codex = json.loads(CODEX_MANIFEST.read_text())
        self.assertEqual(claude["name"], codex["name"])
        self.assertEqual(claude["version"], codex["version"])


if __name__ == "__main__":
    unittest.main()
