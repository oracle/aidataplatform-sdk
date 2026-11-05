#!/usr/bin/env python3
"""Release gate for protected AIDP skills against this repository's SDK/CLI."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import unittest

from sensitive_contract import (BASELINE, INSTALLED_BASELINE, REPO, check_contract,
                                collect_contract, collect_installed_contract)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-candidate", type=Path,
                        help="Export a candidate contract for manual review to a NEW file; does not accept it or run the release gate")
    parser.add_argument("--target", choices=("installed", "repository"), default="installed",
                        help="Default: validate the installed release AND repository. Repository-only is an offline development check, not a release pass.")
    args = parser.parse_args(argv)
    try:
        if args.write_candidate:
            protected_baselines = {BASELINE.resolve(), INSTALLED_BASELINE.resolve()}
            protected_baselines.update((BASELINE.parent / name).resolve() for name in (
                "folder-transfer-contract.json", "folder-transfer-contract-installed.json"))
            if args.write_candidate.resolve() in protected_baselines:
                parser.error("Export to a separate file, review the drift and update skills/tests before replacing the approved baseline.")
            contract = collect_installed_contract()[0] if args.target == "installed" else collect_contract()
            with args.write_candidate.open("x", encoding="utf-8") as stream:
                json.dump(contract, stream, indent=2, sort_keys=True)
                stream.write("\n")
            print("Candidate exported for review. This is NOT a release validation pass.")
            return 0
        contract = check_contract()
        print("Repository SDK/CLI source: approved contract matches.", flush=True)
        if args.target == "installed":
            contract, version = collect_installed_contract()
            check_contract(baseline=INSTALLED_BASELINE, actual=contract)
            print(f"Installed SDK/CLI {version}: approved contract matches.", flush=True)
        else:
            print("Repository-only development checks; installed packages are NOT validated and this is NOT a release pass.", flush=True)
        count = sum(len(group["operations"]) for group in contract["operations"].values())
        print(f"SDK/CLI contract matches: {count} operations, {len(contract['models'])} models, "
              f"{len(contract['catalogPropertyEnums'])} catalog property enums.", flush=True)
    except (AssertionError, OSError, ValueError, SyntaxError, RuntimeError, KeyError, TypeError, ImportError) as error:
        print(f"RELEASE BLOCKED: {error}", file=sys.stderr)
        return 1
    suite = unittest.TestSuite()
    folder = REPO / "plugins/aidp/tests"
    patterns = ["test_sensitive_contracts.py", "test_cluster_contract.py", "test_folder_transfer_contract.py", "test_platform_support.py", "test_protected_aidp.py", "test_protected_resource_templates.py",
                "test_external_catalog_inputs.py", "test_additional_catalog_inputs.py", "test_google_bigquery_inputs.py"]
    if args.target == "installed":
        patterns.append("test_installed_sensitive_contracts.py")
        patterns.append("test_installed_folder_transfer_contract.py")
    for pattern in patterns:
        if not (folder / pattern).is_file():
            print(f"RELEASE BLOCKED: required test suite is missing: {pattern}", file=sys.stderr)
            return 1
        tests = unittest.defaultTestLoader.discover(str(folder), pattern=pattern)
        if not tests.countTestCases():
            print(f"RELEASE BLOCKED: required test suite contains no tests: {pattern}", file=sys.stderr)
            return 1
        suite.addTests(tests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful() or result.skipped or not result.testsRun:
        print("RELEASE BLOCKED: contract or protected-input tests failed, were skipped, or did not run.", file=sys.stderr)
        return 1
    label = "Release validation passed" if args.target == "installed" else "Repository development checks passed (not a release pass)"
    print(f"{label}: {result.testsRun} tests; no network or live AIDP calls.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
