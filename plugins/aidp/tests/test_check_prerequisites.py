# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
import shlex
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
CODEX_SKILL = REPO_ROOT / "plugins/aidp/codex/skills/aidp-setup-local"
CLAUDE_SKILL = REPO_ROOT / "plugins/aidp/claude/skills/aidp-setup-local"
SCRIPT = CODEX_SKILL / "scripts/check_prerequisites.py"

# Stands in for the interpreter that owns `aidp`: it answers `aidp --version`,
# the package probe, and `pip index versions` from environment variables.
FAKE_PYTHON = """#!/bin/sh
case "$1" in
  */aidp)
    if [ -n "$FAKE_VERSION_LOG" ]; then echo "$1" >> "$FAKE_VERSION_LOG"; fi
    echo "aidp python cli version-$FAKE_CLI"
    exit 0
    ;;
  -c)
    if [ -n "$FAKE_CLIENT" ]; then client="\\"$FAKE_CLIENT\\""; else client=null; fi
    if [ -n "$FAKE_MANAGED" ]; then managed=true; else managed=false; fi
    printf '{"python": "3.12.1", "virtualenv": false, "user_base": "/nonexistent", '
    printf '"externally_managed": %s, ' "$managed"
    if [ -n "$FAKE_SCRIPT_DIR" ]; then printf '"script_dir": "%s", ' "$FAKE_SCRIPT_DIR"; fi
    if [ -n "$FAKE_NO_PIP" ]; then printf '"pip": false, '; else printf '"pip": true, '; fi
    if [ -n "$FAKE_NO_ENSUREPIP" ]; then printf '"ensurepip": false, '; else printf '"ensurepip": true, '; fi
    if [ -n "$FAKE_CLI" ]; then cli="\\"$FAKE_CLI\\""; else cli=null; fi
    printf '"packages": {"aidp-cli": %s, "aidp-python-client": %s}}\\n' "$cli" "$client"
    exit 0
    ;;
  -m)
    if [ -n "$FAKE_NO_PIP" ]; then
      echo "No module named pip" >&2
      exit 1
    fi
    if [ -n "$FAKE_INDEX_SLEEP" ]; then sleep "$FAKE_INDEX_SLEEP"; fi
    if [ -n "$FAKE_INDEX_FAIL" ]; then
      echo "ERROR: Could not reach the package index" >&2
      exit 1
    fi
    if [ "$5" = aidp-cli ] && [ -n "$FAKE_CLI_ONLY" ]; then
      echo "$5 ($FAKE_CLI_ONLY)"
      echo "Available versions: $FAKE_CLI_ONLY"
    elif [ "$5" = aidp-cli ] && [ -n "$FAKE_CLI_LATEST" ]; then
      echo "$5 ($FAKE_CLI_LATEST)"
      echo "Available versions: $FAKE_CLI_LATEST, $FAKE_LATEST, 5.1.1, 0.1.932026054"
    else
      echo "$5 ($FAKE_LATEST)"
      echo "Available versions: $FAKE_LATEST, 5.1.1, 0.1.932026054"
    fi
    exit 0
    ;;
esac
exit 3
"""

SH_WRAPPER = "#!/bin/sh\n'''exec' \"%s\" \"$0\" \"$@\"\n' '''"


def _executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class CheckPrerequisitesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.bin_dir = Path(self.temp_dir.name) / "bin"
        self.bin_dir.mkdir()
        self.home = Path(self.temp_dir.name) / "home"
        self.home.mkdir()
        self.context_file = self.home / "context.json"
        self.fake_python = self.bin_dir / "python3"
        _executable(self.fake_python, FAKE_PYTHON)
        _executable(self.bin_dir / "oci", "#!/bin/sh\necho 3.50.0\n")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def install_aidp(self, shebang: str | None = None) -> None:
        # macOS cannot exec a shebang that names another script, so the default
        # uses the /bin/sh wrapper form that pip writes for long interpreter paths.
        header = shebang or SH_WRAPPER % self.fake_python
        _executable(self.bin_dir / "aidp", "%s\nimport sys\n" % header)

    def load_module(self):
        spec = importlib.util.spec_from_file_location("check_prerequisites", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def run_check(
        self, *arguments: str, expected: int = 0, **fake: str
    ) -> dict:
        environment = os.environ.copy()
        environment["PATH"] = "%s%s/usr/bin%s/bin" % (self.bin_dir, os.pathsep, os.pathsep)
        environment.update(
            {
                "HOME": str(self.home),
                "AIDP_CONTEXT_FILE": str(self.context_file),
                "FAKE_CLI": "5.2.1",
                "FAKE_CLIENT": "5.2.1",
                "FAKE_LATEST": "5.2.1",
            }
        )
        environment.update(fake)
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(completed.returncode, expected, completed.stderr)
        summary = json.loads(completed.stdout)
        self.assertNotIn("cli_selection", summary)
        return summary

    def test_matching_and_current_packages_need_no_action(self) -> None:
        self.install_aidp()
        summary = self.run_check()
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["prerequisites"]["aidp_cli"]["version"], "5.2.1")
        self.assertEqual(summary["prerequisites"]["oci_cli"]["version"], "3.50.0")
        self.assertEqual(summary["aidp_python"]["path"], str(self.fake_python))
        self.assertEqual(summary["aidp_python"]["source"], "aidp")
        self.assertTrue(summary["versions"]["match"])
        self.assertEqual(summary["versions"]["aidp_cli_update"], "up to date")
        self.assertEqual(summary["actions"], [])

    def test_mismatch_offers_pinned_upgrade_of_both_packages(self) -> None:
        self.install_aidp()
        summary = self.run_check(FAKE_CLIENT="0.1.932026054")
        self.assertTrue(summary["ok"])
        self.assertFalse(summary["versions"]["match"])
        self.assertEqual(summary["versions"]["target_version"], "5.2.1")
        [action] = summary["actions"]
        self.assertIn("do not match", action["reasons"][0])
        self.assertEqual(
            action["command"],
            "%s -m pip install --upgrade aidp-python-client==5.2.1 aidp-cli==5.2.1"
            % self.fake_python,
        )

    def test_outdated_matching_packages_offer_upgrade(self) -> None:
        self.install_aidp()
        summary = self.run_check(FAKE_CLI="5.1.1", FAKE_CLIENT="5.1.1")
        self.assertTrue(summary["versions"]["match"])
        self.assertEqual(summary["versions"]["aidp_cli_update"], "update available")
        [action] = summary["actions"]
        self.assertEqual(action["target_version"], "5.2.1")
        self.assertIn("aidp-cli 5.2.1 is available", action["reasons"])

    def test_unmanaged_python_uses_plain_pip(self) -> None:
        self.install_aidp()
        summary = self.run_check(FAKE_CLIENT="0.1.932026054")
        self.assertFalse(summary["aidp_python"]["externally_managed"])
        [action] = summary["actions"]
        self.assertEqual(action["install_method"], "pip")
        self.assertNotIn("path_hint", action)

    def test_fresh_install_on_managed_python_uses_virtualenv(self) -> None:
        summary = self.run_check(
            "--python", str(self.fake_python), expected=1,
            FAKE_CLI="", FAKE_CLIENT="", FAKE_MANAGED="1",
        )
        self.assertTrue(summary["aidp_python"]["externally_managed"])
        [action] = summary["actions"]
        venv = str(self.home / ".aidp-venv")
        self.assertEqual(action["install_method"], "virtualenv")
        self.assertEqual(
            action["command"],
            "%s -m venv %s && %s/bin/python -m pip install --upgrade "
            "aidp-python-client==5.2.1 aidp-cli==5.2.1" % (self.fake_python, venv, venv),
        )
        self.assertEqual(action["path_hint"], os.path.join(venv, "bin"))
        self.assertNotIn("alternative_command", action)

    def test_existing_pipx_is_offered_as_alternative(self) -> None:
        _executable(self.bin_dir / "pipx", "#!/bin/sh\nexit 0\n")
        summary = self.run_check(
            "--python", str(self.fake_python), expected=1,
            FAKE_CLI="", FAKE_CLIENT="", FAKE_MANAGED="1",
        )
        [action] = summary["actions"]
        self.assertEqual(
            action["alternative_command"],
            "pipx install --force aidp-cli==5.2.1 && "
            "pipx inject aidp-cli aidp-python-client==5.2.1",
        )

    def check_in_process(
        self, checker_has_pip: bool = True, skip_latest: bool = False, **fake: str
    ) -> dict:
        """Run check() with the checker's own Python replaced by a stand-in.

        A pip-free owning environment makes the script fall back to the
        checker's Python for index lookups; replacing it keeps the test off
        the real package index.
        """
        checker = self.bin_dir / "checker-python"
        clear = "FAKE_NO_PIP= " if checker_has_pip else ""
        _executable(checker, '#!/bin/sh\n%sexec "%s" "$@"\n' % (clear, self.fake_python))
        environment = {
            "HOME": str(self.home),
            "AIDP_CONTEXT_FILE": str(self.context_file),
            "PATH": "%s%s/usr/bin%s/bin" % (self.bin_dir, os.pathsep, os.pathsep),
            "FAKE_CLI": "5.2.1",
            "FAKE_CLIENT": "5.2.1",
            "FAKE_LATEST": "5.2.1",
        }
        environment.update(fake)
        module = self.load_module()
        with mock.patch.dict(os.environ, environment), mock.patch.object(
            module.sys, "executable", str(checker)
        ), mock.patch.object(module, "_read_context", return_value=({"schemaVersion": 2}, None)):

            summary = module.check(skip_latest, 5)
        summary["_checker"] = str(checker)
        return summary

    def test_pip_free_owner_queries_index_with_checker_python(self) -> None:
        self.install_aidp()
        summary = self.check_in_process(FAKE_CLIENT="0.1.932026054", FAKE_NO_PIP="1")
        self.assertFalse(summary["aidp_python"]["pip"])
        self.assertEqual(summary["versions"]["index_python"], summary["_checker"])
        self.assertEqual(summary["versions"]["target_version"], "5.2.1")
        [action] = summary["actions"]
        self.assertEqual(action["install_method"], "pip")
        self.assertEqual(
            action["command"],
            "%s -m ensurepip --upgrade && %s -m pip install --upgrade "
            "aidp-python-client==5.2.1 aidp-cli==5.2.1" % (self.fake_python, self.fake_python),
        )

    def test_no_pip_anywhere_offers_restore_pip_first(self) -> None:
        self.install_aidp()
        summary = self.check_in_process(
            checker_has_pip=False, FAKE_CLIENT="0.1.932026054", FAKE_NO_PIP="1"
        )
        self.assertIsNone(summary["versions"]["index_python"])
        self.assertIsNone(summary["versions"]["target_version"])
        kinds = [action["kind"] for action in summary["actions"]]
        self.assertEqual(kinds, ["restore_pip", "upgrade_aidp_packages"])
        restore, upgrade = summary["actions"]
        self.assertEqual(restore["command"], "%s -m ensurepip --upgrade" % self.fake_python)
        self.assertIsNone(upgrade["command"])

    def test_skipped_lookup_does_not_offer_restore_pip(self) -> None:
        self.install_aidp()
        summary = self.check_in_process(
            checker_has_pip=False, skip_latest=True, FAKE_CLIENT="0.1.932026054", FAKE_NO_PIP="1"
        )
        [action] = summary["actions"]
        self.assertEqual(action["kind"], "upgrade_aidp_packages")
        self.assertIsNone(action["command"])
        self.assertEqual(action["blocked"], "the package-index lookup was skipped")

    def test_no_pip_or_ensurepip_uses_virtualenv_from_checker_python(self) -> None:
        self.install_aidp()
        summary = self.check_in_process(
            FAKE_CLIENT="0.1.932026054", FAKE_NO_PIP="1", FAKE_NO_ENSUREPIP="1"
        )
        [action] = summary["actions"]
        self.assertEqual(action["install_method"], "virtualenv")
        self.assertTrue(action["command"].startswith("%s -m venv " % summary["_checker"]))
        self.assertNotIn("in_place_command", action)

    def test_target_is_highest_version_published_for_both(self) -> None:
        self.install_aidp()
        summary = self.run_check(FAKE_CLIENT="0.1.932026054", FAKE_CLI_LATEST="5.3.0")
        self.assertEqual(summary["versions"]["latest"]["aidp-cli"], "5.3.0")
        self.assertEqual(summary["versions"]["target_version"], "5.2.1")
        [action] = summary["actions"]
        self.assertIn("aidp-python-client==5.2.1 aidp-cli==5.2.1", action["command"])

    def test_no_shared_release_offers_no_command(self) -> None:
        self.install_aidp()
        summary = self.run_check(FAKE_CLIENT="0.1.932026054", FAKE_CLI_ONLY="5.3.0")
        self.assertIsNone(summary["versions"]["target_version"])
        self.assertTrue(summary["versions"]["no_shared_release"])
        [action] = summary["actions"]
        self.assertEqual(action["kind"], "upgrade_aidp_packages")
        self.assertIsNone(action["command"])
        self.assertIsNone(action["install_method"])
        self.assertEqual(
            action["blocked"],
            "no release is published for both aidp-cli 5.3.0 and aidp-python-client 5.2.1",
        )

    def test_unreadable_index_defers_upgrade(self) -> None:
        self.install_aidp()
        summary = self.run_check(FAKE_CLIENT="0.1.932026054", FAKE_INDEX_FAIL="1")
        self.assertFalse(summary["versions"]["no_shared_release"])
        [action] = summary["actions"]
        self.assertEqual(action["kind"], "upgrade_aidp_packages")
        self.assertIsNone(action["command"])
        self.assertEqual(
            action["blocked"], "the package index could not be read to verify a matching release"
        )

    def test_skipped_lookup_defers_upgrade(self) -> None:
        self.install_aidp()
        summary = self.run_check("--skip-latest", FAKE_CLIENT="0.1.932026054")
        [action] = summary["actions"]
        self.assertIsNone(action["command"])
        self.assertEqual(action["blocked"], "the package-index lookup was skipped")

    def test_every_offered_command_is_one_pinned_pip_call(self) -> None:
        self.install_aidp()
        summary = self.run_check(FAKE_CLIENT="0.1.932026054")
        [action] = summary["actions"]
        self.assertNotIn("$(", action["command"])
        self.assertEqual(action["command"].count(" -m pip install "), 1)

    def test_unreachable_index_reports_unknown_without_failing(self) -> None:
        self.install_aidp()
        summary = self.run_check(FAKE_INDEX_FAIL="1")
        self.assertTrue(summary["ok"])
        self.assertIsNone(summary["versions"]["latest"]["aidp-cli"])
        self.assertEqual(summary["versions"]["aidp_cli_update"], "unknown")
        self.assertIn("package index", summary["versions"]["latest_detail"])
        self.assertTrue(summary["versions"]["match"])

    def test_slow_index_times_out_without_failing(self) -> None:
        self.install_aidp()
        summary = self.run_check("--index-timeout", "1", FAKE_INDEX_SLEEP="3")
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["versions"]["latest_detail"], "timed out after 1s")
        self.assertEqual(summary["versions"]["aidp_cli_update"], "unknown")

    def test_default_index_timeout(self) -> None:
        self.assertEqual(self.load_module().DEFAULT_INDEX_TIMEOUT_SECONDS, 20)

    def test_skip_latest_does_not_query_index(self) -> None:
        self.install_aidp()
        summary = self.run_check("--skip-latest", FAKE_INDEX_FAIL="1")
        self.assertEqual(summary["versions"]["latest_detail"], "skipped")
        self.assertEqual(summary["versions"]["aidp_cli_update"], "unknown")

    def test_missing_python_client_blocks_and_offers_install(self) -> None:
        self.install_aidp()
        summary = self.run_check(expected=1, FAKE_CLIENT="")
        self.assertFalse(summary["ok"])
        self.assertEqual(summary["blocking"], ["aidp_python_client"])
        self.assertEqual(summary["prerequisites"]["aidp_python_client"]["status"], "missing")
        self.assertIsNone(summary["versions"]["match"])
        [action] = summary["actions"]
        self.assertEqual(action["kind"], "install_aidp_packages")
        self.assertIn("aidp-python-client is not installed", action["reasons"])

    def test_cli_below_minimum_blocks_and_offers_install(self) -> None:
        self.install_aidp()
        summary = self.run_check(expected=1, FAKE_CLI="5.0.9", FAKE_CLIENT="5.0.9")
        self.assertFalse(summary["ok"])
        self.assertEqual(summary["blocking"], ["aidp_cli"])
        aidp_cli = summary["prerequisites"]["aidp_cli"]
        self.assertEqual(aidp_cli["status"], "invalid")
        self.assertEqual(aidp_cli["version"], "5.0.9")
        self.assertEqual(aidp_cli["detail"], "aidp-cli 5.1.0 or later is required")
        [action] = summary["actions"]
        self.assertEqual(action["kind"], "install_aidp_packages")
        self.assertIn("aidp-cli 5.1.0 or later is required; 5.0.9 is installed", action["reasons"])
        self.assertEqual(
            action["command"],
            "%s -m pip install --upgrade aidp-python-client==5.2.1 aidp-cli==5.2.1"
            % self.fake_python,
        )

    def test_cli_at_minimum_is_installed(self) -> None:
        self.install_aidp()
        summary = self.run_check(FAKE_CLI="5.1.0", FAKE_CLIENT="5.1.0", FAKE_LATEST="5.1.0")
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["prerequisites"]["aidp_cli"]["status"], "installed")
        self.assertEqual(summary["actions"], [])

    def test_cli_minimum_ignores_build_numbers_and_suffixes(self) -> None:
        self.install_aidp()
        for version in ("5.1.0.36.45595", "5.1.0.1.2.3", "5.1.0rc1", "5.1.0.dev1", "5.1.0-garbage"):
            with self.subTest(version=version):
                summary = self.run_check("--skip-latest", FAKE_CLI=version, FAKE_CLIENT=version)
                self.assertTrue(summary["ok"])
                self.assertEqual(summary["prerequisites"]["aidp_cli"]["status"], "installed")
                self.assertEqual(summary["prerequisites"]["aidp_cli"]["version"], version)
                self.assertEqual(summary["actions"], [])

    def test_minimum_uses_three_components_and_upgrades_use_full_numeric_version(self) -> None:
        module = self.load_module()
        for version in ("5.1.0", "5.1", "5.1.0.36.45595", "5.1.0rc1", "5.1.0.dev1", "6.0.0"):
            self.assertFalse(module._is_older(version, "5.1.0", components=3))
        for version in ("5.0.9.999999", "5.0.99999", "4.99.99"):
            self.assertTrue(module._is_older(version, "5.1.0", components=3))
        self.assertFalse(module._is_older("5.1.0.1", "5.1.0.999", components=3))
        self.assertTrue(module._is_older("5.1.0.1", "5.1.0.999"))
        self.assertTrue(module._is_older("5.1.0.36.45595", "5.1.0.36.45596"))
        self.assertIsNone(module._is_older("invalid", "5.1.0", components=3))
        for version in ("5.1.0rc1", "5.1.0.dev1", "5.1.0.36.45595", "5.1.0+local"):
            self.assertEqual(module._parse_version("aidp python cli version-" + version), version)
        target = module._common_target({module.CLI_PACKAGE: {"latest": "invalid", "available": ["5.1.0.36.45595", "5.1.0.36.45596"]},
                                       module.CLIENT_PACKAGE: {"available": ["5.1.0.36.45595", "5.1.0.36.45596"]}})
        self.assertEqual(target, "5.1.0.36.45596")

    def test_unparseable_installed_cli_version_cannot_bypass_minimum(self) -> None:
        self.install_aidp()
        # Keep fallback discovery inside this fixture: the interpreter running
        # the suite may itself contain a valid installed AIDP CLI.
        summary = self.run_check("--python", str(self.fake_python), expected=1,
                                 FAKE_CLI="not-a-version", FAKE_CLIENT="not-a-version")
        self.assertEqual(summary["prerequisites"]["aidp_cli"]["status"], "invalid")
        self.assertIn("aidp_cli", summary["blocking"])

    def test_numeric_build_update_is_still_offered(self) -> None:
        self.install_aidp()
        summary = self.run_check(FAKE_CLI="5.1.0.36.45595", FAKE_CLIENT="5.1.0.36.45595", FAKE_LATEST="5.1.0.36.45596")
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["versions"]["aidp_cli_update"], "update available")
        self.assertEqual(summary["versions"]["target_version"], "5.1.0.36.45596")

    def test_bootstrap_version_check_does_not_require_site_packages(self) -> None:
        program = ("import runpy; m=runpy.run_path(" + repr(str(SCRIPT)) + "); "
                   "assert m['_is_older']('5.1.0rc1','5.1.0',components=3) is False")
        result = subprocess.run([sys.executable, "-S", "-c", program], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cli_below_minimum_with_skipped_lookup_defers_install(self) -> None:
        self.install_aidp()
        summary = self.run_check("--skip-latest", expected=1, FAKE_CLI="4.2.1", FAKE_CLIENT="4.2.1")
        [action] = summary["actions"]
        self.assertEqual(action["kind"], "install_aidp_packages")
        self.assertIsNone(action["command"])
        self.assertEqual(action["blocked"], "the package-index lookup was skipped")

    def test_no_release_at_minimum_offers_no_command(self) -> None:
        self.install_aidp()
        summary = self.run_check(expected=1, FAKE_CLI="4.2.1", FAKE_CLIENT="4.2.1", FAKE_LATEST="5.0.0")
        [action] = summary["actions"]
        self.assertIsNone(action["command"])
        self.assertEqual(
            action["blocked"], "no release of aidp-cli 5.1.0 or later is published for both packages"
        )

    def test_version_problems_alone_are_an_upgrade(self) -> None:
        self.install_aidp()
        summary = self.run_check(FAKE_CLIENT="0.1.932026054")
        [action] = summary["actions"]
        self.assertEqual(action["kind"], "upgrade_aidp_packages")

    def test_installed_command_off_path_offers_path_fix(self) -> None:
        script_dir = Path(self.temp_dir.name) / "user-bin"
        script_dir.mkdir()
        _executable(script_dir / "aidp", "%s\nimport sys\n" % (SH_WRAPPER % self.fake_python))
        summary = self.run_check(
            "--skip-latest",
            "--python",
            str(self.fake_python),
            FAKE_SCRIPT_DIR=str(script_dir),
        )
        aidp_cli = summary["prerequisites"]["aidp_cli"]
        self.assertTrue(summary["ok"])
        self.assertEqual(aidp_cli["status"], "installed")
        self.assertFalse(aidp_cli["on_path"])
        [action] = summary["actions"]
        self.assertEqual(action["kind"], "add_to_path")
        self.assertEqual(action["path_hint"], str(script_dir))
        self.assertEqual(action["aidp_path"], str(script_dir / "aidp"))
        self.assertEqual(action["command"], 'export PATH=%s"${PATH:+:$PATH}"' % script_dir)

    def make_venv_install(self) -> Path:
        home = Path(self.temp_dir.name) / "venv-home"
        venv_bin = home / ".aidp-venv" / "bin"
        venv_bin.mkdir(parents=True)
        _executable(venv_bin / "aidp", "%s\nimport sys\n" % (SH_WRAPPER % self.fake_python))
        return home

    def test_venv_install_off_path_is_checked_by_full_path(self) -> None:
        home = self.make_venv_install()
        summary = self.run_check("--skip-latest", HOME=str(home))
        venv_bin = home / ".aidp-venv" / "bin"
        aidp_cli = summary["prerequisites"]["aidp_cli"]
        self.assertTrue(summary["ok"])
        self.assertEqual(aidp_cli["path"], str(venv_bin / "aidp"))
        self.assertFalse(aidp_cli["on_path"])
        self.assertTrue(summary["versions"]["match"])
        [action] = summary["actions"]
        self.assertEqual(action["kind"], "add_to_path")
        self.assertEqual(action["path_hint"], str(venv_bin))
        self.assertIn("not on PATH", action["reasons"][0])

    def test_new_session_reuses_oci_beside_remembered_aidp_without_reinstall(self) -> None:
        saved = self.new_candidate("saved bin")
        oci = saved.with_name("oci")
        _executable(oci, "#!/bin/sh\necho 3.96.0\n")
        (self.bin_dir / "oci").unlink()
        self.remember(saved)
        summary = self.run_check("--skip-latest")
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["blocking"], [])
        self.assertEqual(summary["prerequisites"]["oci_cli"]["path"], str(oci))
        self.assertEqual(summary["prerequisites"]["oci_cli"]["version"], "3.96.0")
        self.assertTrue(summary["prerequisites"]["oci_cli"]["path_adjustment_required"])
        self.assertEqual([action["kind"] for action in summary["actions"]], ["add_to_path"])
        [action] = summary["actions"]
        self.assertEqual(action["path_hint"], str(saved.parent))
        # A separate invocation with the returned environment can run OCI.
        environment = os.environ.copy()
        environment["PATH"] = action["path_hint"] + os.pathsep + str(self.bin_dir)
        result = subprocess.run(["oci", "--version"], env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "3.96.0")

    def test_new_environment_discovery_reuses_off_path_oci(self) -> None:
        home = self.make_venv_install()
        oci = home / ".aidp-venv/bin/oci"
        _executable(oci, "#!/bin/sh\necho 3.96.0\n")
        (self.bin_dir / "oci").unlink()
        summary = self.run_check("--skip-latest", HOME=str(home))
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["prerequisites"]["oci_cli"]["path"], str(oci))

    def test_existing_path_oci_remains_preferred(self) -> None:
        saved = self.new_candidate("saved bin")
        _executable(saved.with_name("oci"), "#!/bin/sh\necho 99.0.0\n")
        self.remember(saved)
        summary = self.run_check("--skip-latest")
        self.assertEqual(summary["prerequisites"]["oci_cli"]["path"], str(self.bin_dir / "oci"))
        self.assertEqual(summary["prerequisites"]["oci_cli"]["version"], "3.50.0")
        self.assertFalse(summary["prerequisites"]["oci_cli"]["path_adjustment_required"])

    def test_oci_only_path_adjustment_when_aidp_is_already_visible(self) -> None:
        saved = self.new_candidate("saved bin")
        _executable(saved.with_name("oci"), "#!/bin/sh\necho 3.96.0\n")
        (self.bin_dir / "oci").unlink()
        (self.bin_dir / "aidp").symlink_to(saved)
        self.remember(saved)
        summary = self.run_check("--skip-latest")
        self.assertTrue(summary["ok"])
        self.assertFalse(summary["prerequisites"]["aidp_cli"]["path_adjustment_required"])
        self.assertTrue(summary["prerequisites"]["oci_cli"]["path_adjustment_required"])
        self.assertEqual(summary["actions"][0]["path_hint"], str(saved.parent))

    def test_oci_in_selected_python_directory_uses_combined_session_prefix(self) -> None:
        saved = self.new_candidate("saved bin")
        owner_bin = Path(self.temp_dir.name) / "owner bin"
        owner_bin.mkdir()
        python = owner_bin / "python3"
        _executable(python, FAKE_PYTHON)
        oci = owner_bin / "oci"
        _executable(oci, "#!/bin/sh\necho 3.96.0\n")
        (self.bin_dir / "oci").unlink()
        self.remember(saved, python)
        summary = self.run_check("--skip-latest")
        self.assertTrue(summary["ok"])
        prefix = summary["actions"][0]["path_hint"]
        self.assertEqual(prefix.split(os.pathsep), [str(saved.parent), str(owner_bin)])
        environment = os.environ.copy()
        environment["PATH"] = prefix + os.pathsep + str(self.bin_dir)
        result = subprocess.run(["oci", "--version"], env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "3.96.0")

    def test_windows_oci_launcher_name_is_discovered_beside_selected_cli(self) -> None:
        module = self.load_module()
        folder = Path(self.temp_dir.name) / "Scripts"
        folder.mkdir()
        oci = folder / "oci.exe"
        _executable(oci, "#!/bin/sh\necho 3.96.0\n")
        with mock.patch.object(module, "OCI_EXE", "oci.exe"):
            result = module._oci_cli({"status": "missing"}, str(folder / "aidp.exe"), str(folder / "python.exe"))
        self.assertEqual(result["status"], "installed")
        self.assertEqual(result["path"], str(oci))
        self.assertTrue(result["path_adjustment_required"])

    def test_missing_and_broken_oci_still_block_setup(self) -> None:
        saved = self.new_candidate("saved bin")
        self.remember(saved)
        (self.bin_dir / "oci").unlink()
        missing = self.run_check("--skip-latest", expected=1)
        self.assertIn("oci_cli", missing["blocking"])
        self.assertEqual(missing["prerequisites"]["oci_cli"]["status"], "missing")
        _executable(saved.with_name("oci"), "#!/bin/sh\nexit 1\n")
        broken = self.run_check("--skip-latest", expected=1)
        self.assertEqual(broken["prerequisites"]["oci_cli"]["status"], "invalid")

    def test_path_python_cli_is_preferred_over_old_dedicated_environment(self) -> None:
        home = self.make_venv_install()
        self.install_aidp()
        old_python = home / ".aidp-venv/bin/python3"
        _executable(old_python, FAKE_PYTHON.replace(
            'version-$FAKE_CLI', 'version-5.0.9'))
        _executable(home / ".aidp-venv/bin/aidp", "%s\n" % (SH_WRAPPER % old_python))
        summary = self.run_check("--skip-latest", HOME=str(home))
        aidp_cli = summary["prerequisites"]["aidp_cli"]
        self.assertEqual(aidp_cli["path"], str(self.bin_dir / "aidp"))
        self.assertEqual(aidp_cli["version"], "5.2.1")
        self.assertTrue(aidp_cli["on_path"])
        self.assertFalse(aidp_cli["path_adjustment_required"])
        self.assertEqual(summary["actions"], [])

    def test_typescript_on_path_falls_back_to_dedicated_python_environment(self) -> None:
        home = self.make_venv_install()
        _executable(self.bin_dir / "aidp", "#!/usr/bin/env node\ninvalid typescript\n")
        summary = self.run_check("--skip-latest", HOME=str(home))
        aidp_cli = summary["prerequisites"]["aidp_cli"]
        self.assertEqual(aidp_cli["path"], str(home / ".aidp-venv/bin/aidp"))
        self.assertTrue(aidp_cli["path_adjustment_required"])
        self.assertTrue(summary["ok"])

    def test_selected_venv_cli_shadowed_on_path_offers_path_fix(self) -> None:
        home = self.make_venv_install()
        self.install_aidp()
        venv_aidp = home / ".aidp-venv" / "bin" / "aidp"
        summary = self.run_check("--skip-latest", "--aidp", str(venv_aidp), HOME=str(home))
        self.assertEqual(summary["prerequisites"]["aidp_cli"]["path"], str(venv_aidp))
        [action] = summary["actions"]
        self.assertEqual(action["kind"], "add_to_path")
        self.assertEqual(
            action["reasons"][0], "PATH runs %s instead of %s" % (self.bin_dir / "aidp", venv_aidp)
        )

    def test_existing_install_in_managed_python_defaults_to_virtualenv(self) -> None:
        self.install_aidp()
        summary = self.run_check(FAKE_CLIENT="0.1.932026054", FAKE_MANAGED="1")
        [action] = summary["actions"]
        self.assertEqual(action["install_method"], "virtualenv")
        self.assertNotIn("--break-system-packages", action["command"])
        self.assertIn("--break-system-packages", action["in_place_command"])
        self.assertEqual(
            action["verify_aidp"], str(self.home / ".aidp-venv" / "bin" / "aidp")
        )

    def test_missing_aidp_command_blocks(self) -> None:
        summary = self.run_check(
            "--skip-latest", "--python", str(self.fake_python), expected=1,
            FAKE_CLI="", FAKE_CLIENT="",
        )
        self.assertFalse(summary["ok"])
        self.assertIn("aidp_cli", summary["blocking"])
        self.assertEqual(summary["aidp_python"]["source"], "option")
        [action] = summary["actions"]
        self.assertEqual(action["kind"], "install_aidp_packages")

    def test_env_shebang_resolves_interpreter_on_path(self) -> None:
        self.install_aidp("#!/usr/bin/env python3")
        summary = self.run_check("--skip-latest")
        self.assertEqual(summary["aidp_python"]["path"], str(self.fake_python))

    def test_direct_shebang_resolves_interpreter(self) -> None:
        script = self.bin_dir / "aidp"
        script.write_text("#!%s\nimport sys\n" % self.fake_python)
        self.assertEqual(
            self.load_module().interpreter_from_script(str(script)), str(self.fake_python)
        )

    def test_non_python_shebang_is_ignored(self) -> None:
        script = self.bin_dir / "aidp"
        script.write_text("#!/bin/bash\necho hi\n")
        self.assertIsNone(self.load_module().interpreter_from_script(str(script)))

    def remember(self, cli: Path, python: Path | None = None, **fields) -> None:
        self.context_file.write_text(json.dumps({
            "schemaVersion": 2,
            "pythonCli": {"path": str(cli), "pythonPath": str(python or self.fake_python)},
            **fields,
        }))

    def new_candidate(self, directory: str) -> Path:
        folder = Path(self.temp_dir.name) / directory
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "aidp"
        _executable(path, "%s\n" % (SH_WRAPPER % self.fake_python))
        return path

    def test_saved_cli_skips_ownership_detection_and_runs_version_once(self) -> None:
        saved = self.new_candidate("saved bin")
        # A saved executable deliberately has no Python shebang. Its saved
        # interpreter is trusted; discovery must reject this same candidate.
        log = Path(self.temp_dir.name) / "versions.log"
        _executable(saved, '#!/bin/sh\necho saved >> "%s"\necho 5.2.1\n' % log)
        self.remember(saved)
        summary = self.run_check("--skip-latest")
        self.assertEqual(summary["prerequisites"]["aidp_cli"]["source"], "context")
        self.assertEqual(summary["prerequisites"]["aidp_cli"]["path"], str(saved))
        self.assertEqual(log.read_text().splitlines(), ["saved"])
        self.assertEqual(summary["context"]["pythonCli"]["path"], str(saved))
        self.assertEqual(summary["aidp_python"]["path"], str(self.fake_python))
        self.assertTrue(summary["prerequisites"]["aidp_cli"]["path_adjustment_required"])

    def test_saved_path_wins_over_dedicated_and_path_candidates(self) -> None:
        self.install_aidp()
        home = self.make_venv_install()
        saved = self.new_candidate("saved")
        self.remember(saved)
        summary = self.run_check("--skip-latest", HOME=str(home))
        self.assertEqual(summary["prerequisites"]["aidp_cli"]["path"], str(saved))
        self.assertEqual(summary["prerequisites"]["aidp_cli"]["source"], "context")

    def test_missing_or_broken_saved_cli_falls_back_in_same_invocation(self) -> None:
        self.install_aidp()
        for state in ("missing", "nonexecutable", "broken", "invalid_version"):
            with self.subTest(state=state):
                saved = Path(self.temp_dir.name) / (state + "-aidp")
                if state == "nonexecutable":
                    saved.write_text("not executable")
                elif state != "missing":
                    _executable(saved, "#!/bin/sh\n" + (
                        "exit 1\n" if state == "broken" else "echo unknown\n"))
                self.remember(saved)
                summary = self.run_check("--skip-latest")
                self.assertEqual(summary["prerequisites"]["aidp_cli"]["path"], str(self.bin_dir / "aidp"))
                self.assertEqual(summary["prerequisites"]["aidp_cli"]["source"], "aidp")

    def test_failed_saved_package_probe_blocks_validation_without_claiming_packages_missing(self) -> None:
        self.install_aidp()
        saved_cli = self.bin_dir / "aidp"
        broken_python = self.bin_dir / "broken-python"
        for body, expected_detail in (
            ("echo interpreter-failed >&2; exit 1", "interpreter-failed"),
            ("echo invalid-json", "package probe returned unreadable output"),
        ):
            with self.subTest(body=body):
                _executable(broken_python, "#!/bin/sh\n" + body + "\n")
                self.remember(saved_cli, broken_python)
                summary = self.run_check("--skip-latest", expected=1)
                self.assertFalse(summary["ok"])
                self.assertEqual(summary["blocking"], ["aidp_python_client"])
                self.assertEqual(summary["prerequisites"]["aidp_python_client"], {
                    "status": "unknown", "detail": expected_detail})
                self.assertFalse(summary["prerequisites"]["aidp_cli"]["validated"])
                self.assertEqual(summary["prerequisites"]["aidp_cli"]["source"], "context")
                self.assertEqual(summary["actions"], [])
        # A successful probe in the saved environment still passes normally.
        self.remember(saved_cli)
        recovered = self.run_check("--skip-latest")
        self.assertTrue(recovered["ok"])
        self.assertEqual(recovered["blocking"], [])
        self.assertTrue(recovered["prerequisites"]["aidp_cli"]["validated"])

    def test_invalid_context_is_nonfatal_and_not_rewritten(self) -> None:
        self.install_aidp()
        self.context_file.write_text("invalid json")
        summary = self.run_check("--skip-latest")
        self.assertIsNone(summary["context"])
        self.assertIsNotNone(summary["context_error"])
        self.assertEqual(self.context_file.read_text(), "invalid json")
        self.assertTrue(summary["ok"])

    def test_typescript_is_skipped_without_executing_it(self) -> None:
        marker = Path(self.temp_dir.name) / "typescript-ran"
        _executable(self.bin_dir / "aidp", '#!/usr/bin/env node\ninvalid typescript')
        # The mock node executable would mark any accidental invocation.
        _executable(self.bin_dir / "node", '#!/bin/sh\ntouch "%s"\necho 99.0.0\n' % marker)
        candidate = self.new_candidate("later bin")
        log = Path(self.temp_dir.name) / "versions.log"
        summary = self.run_check("--skip-latest",
            PATH=os.pathsep.join((str(self.bin_dir), str(candidate.parent), str(candidate.parent), "/usr/bin", "/bin")),
            FAKE_VERSION_LOG=str(log))
        self.assertFalse(marker.exists())
        self.assertEqual(summary["prerequisites"]["aidp_cli"]["path"], str(candidate))
        self.assertEqual(log.read_text().splitlines(), [str(candidate)])
        self.assertTrue(summary["prerequisites"]["aidp_cli"]["path_adjustment_required"])

    def test_typescript_only_offers_isolated_install(self) -> None:
        _executable(self.bin_dir / "aidp", "#!/usr/bin/env node\ninvalid")
        summary = self.run_check("--python", str(self.fake_python),
            expected=1, FAKE_CLI="", FAKE_CLIENT="")
        self.assertIsNone(summary["prerequisites"]["aidp_cli"]["path"])
        [action] = summary["actions"]
        self.assertEqual(action["kind"], "install_aidp_packages")
        self.assertEqual(action["install_method"], "virtualenv")
        self.assertNotIn("--break-system-packages", action["command"])

    def test_current_path_equivalent_symlink_needs_no_adjustment(self) -> None:
        saved = self.new_candidate("pipx venv/bin")
        (self.bin_dir / "aidp").symlink_to(saved)
        self.remember(saved)
        summary = self.run_check("--skip-latest")
        self.assertFalse(summary["prerequisites"]["aidp_cli"]["path_adjustment_required"])
        self.assertEqual(summary["actions"], [])

    def test_scoped_path_is_inherited_by_child_without_changing_parent(self) -> None:
        candidate = self.new_candidate("directory with spaces and ' quote")
        summary = self.run_check("--skip-latest", "--python", str(self.fake_python),
            FAKE_SCRIPT_DIR=str(candidate.parent))
        [action] = summary["actions"]
        environment = os.environ.copy()
        environment.update(PATH=str(self.bin_dir) + ":/usr/bin:/bin", FAKE_CLI="5.2.1")
        # A helper invoking aidp inherits the scoped setting.
        helper = Path(self.temp_dir.name) / "helper.sh"
        helper.write_text("#!/bin/sh\naidp --version\n")
        completed = subprocess.run(["/bin/sh", "-c", action["command"] + "; /bin/sh " + shlex.quote(str(helper))],
            env=environment, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("5.2.1", completed.stdout)
        self.assertNotIn(str(candidate.parent), environment["PATH"])

    def test_weekly_lookup_is_decided_inside_script(self) -> None:
        self.install_aidp()
        self.remember(self.bin_dir / "aidp", latestVersionCheck={
            "checkedAt": datetime.now(timezone.utc).isoformat()})
        summary = self.run_check()
        self.assertEqual(summary["versions"]["latest_detail"], "skipped")
        self.assertIsNone(summary["versions"]["latest"]["aidp-cli"])
        forced = self.run_check("--check-latest")
        self.assertEqual(forced["versions"]["latest"]["aidp-cli"], "5.2.1")

    def test_discovery_is_nonrecursive_and_deduplicates_failed_candidates(self) -> None:
        module = self.load_module()
        candidate = self.new_candidate("path-bin")
        hidden = self.new_candidate("path-bin/nested")
        environment = {"PATH": str(candidate.parent) + os.pathsep + str(candidate.parent)}
        with mock.patch.dict(os.environ, environment), mock.patch.object(module, "VENV_DIR", "/not-present"), mock.patch.object(
            module, "_tool", return_value={"status": "invalid"}) as version, mock.patch.object(
            module, "_probe_packages", return_value=({}, None)):
            result, _, _, _ = module._select_cli({})
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(version.call_count, 1)
        self.assertEqual(version.call_args.args[2], str(candidate))
        self.assertNotEqual(version.call_args.args[2], str(hidden))

    def test_discovery_timeout_is_shared_across_candidates(self) -> None:
        module = self.load_module()
        first = self.new_candidate("first")
        second = self.new_candidate("second")
        clock = [0.0]
        def slow_version(*args):
            clock[0] += module.VERSION_TIMEOUT_SECONDS
            return {"status": "invalid"}
        with mock.patch.dict(os.environ, {"PATH": os.pathsep.join((str(first.parent), str(second.parent)))}), mock.patch.object(
            module, "VENV_DIR", "/not-present"), mock.patch.object(module.time, "monotonic", side_effect=lambda: clock[0]), mock.patch.object(
            module, "_tool", side_effect=slow_version) as version:
            result, _, _, _ = module._select_cli({})
        self.assertEqual(version.call_count, 1)
        self.assertIn("time limit", result["detail"])

    def test_package_probe_returns_all_nonrecursive_script_directories(self) -> None:
        module = self.load_module()
        facts, error = module._probe_packages(sys.executable)
        self.assertIsNone(error)
        self.assertTrue(facts["script_dirs"])
        self.assertTrue(all(os.path.isabs(path) for path in facts["script_dirs"]))

    def test_saved_python_interpreter_symlink_is_not_resolved_to_base_python(self) -> None:
        module = self.load_module()
        saved = self.new_candidate("venv/bin")
        interpreter = saved.parent / "python"
        interpreter.symlink_to(self.fake_python)
        context = {"pythonCli": {"path": str(saved), "pythonPath": str(interpreter)}}
        with mock.patch.object(module, "_tool", return_value={"status": "installed", "version": "5.2.1", "path": str(saved)}):
            _, selected_python, source, _ = module._select_cli(context)
        self.assertEqual(source, "context")
        self.assertEqual(selected_python, str(interpreter))
        self.assertNotEqual(selected_python, str(interpreter.resolve()))

    def test_saved_version_failure_is_not_repeated_during_discovery(self) -> None:
        module = self.load_module()
        saved = self.new_candidate("saved-bin")
        context = {"pythonCli": {"path": str(saved), "pythonPath": str(self.fake_python)}}
        with mock.patch.dict(os.environ, {"PATH": str(saved.parent)}), mock.patch.object(
            module, "VENV_DIR", "/not-present"), mock.patch.object(module, "_tool", return_value={"status": "invalid"}) as version, mock.patch.object(
            module, "_probe_packages", return_value=({}, None)):
            module._select_cli(context)
        self.assertEqual(version.call_count, 1)

    def test_claude_and_codex_resources_are_identical(self) -> None:
        for relative_path in (
            "SKILL.md",
            "references/installation.md",
            "references/troubleshooting.md",
            "references/aidp-target-selection.md",
            "scripts/check_prerequisites.py",
        ):
            self.assertEqual(
                (CODEX_SKILL / relative_path).read_bytes(),
                (CLAUDE_SKILL / relative_path).read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
