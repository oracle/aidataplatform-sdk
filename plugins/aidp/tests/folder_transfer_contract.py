# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
"""Offline SDK/CLI contracts for workspace and volume folder transfers only."""
from __future__ import annotations

import ast
from importlib import metadata
import json
from pathlib import Path

from sensitive_contract import REPO, collect_contract, collect_installed_contract, differences


BASELINE = Path(__file__).with_name("contracts") / "folder-transfer-contract.json"
INSTALLED_BASELINE = BASELINE.with_name("folder-transfer-contract-installed.json")
CLIENTS = {
    "workspace-object": ("workspace_object_client.py", (
        "upload_and_extract_workspace_zip", "zip_and_download_workspace_folder")),
    "volume": ("volume_client.py", (
        "upload_and_extract_volume_zip", "zip_and_download_volume_folder")),
    "async-operations": ("async_operations_client.py", ("get_async_operation",)),
}


def collect_folder_transfer_contract(repo=REPO, *, installed=False):
    if installed:
        contract, _ = collect_installed_contract(repo, clients=CLIENTS)
        sdk_root = Path(metadata.distribution("aidp-python-client").locate_file(""))
    else:
        contract = collect_contract(repo, clients=CLIENTS)
        sdk_root = repo / "aidp-python-client/src"
    # Scope this gate to the five transfer/polling operations. Changes to
    # unrelated workspace/volume operations or catalog enums are separate work.
    contract.pop("catalogPropertyEnums")
    for group in contract["operations"].values():
        group.pop("operationInventory")
    package = sdk_root / "aidp_python_client/aidataplatform_dp"
    versions = {}
    for group, (filename, _) in CLIENTS.items():
        tree = ast.parse((package / filename).read_text(encoding="utf-8"))
        paths = {ast.literal_eval(value) for node in ast.walk(tree) if isinstance(node, ast.Dict)
                 for key, value in zip(node.keys, node.values)
                 if isinstance(key, ast.Constant) and key.value == "base_path"}
        if len(paths) != 1:
            raise ValueError(f"Cannot extract unambiguous folder-transfer API version: {filename}")
        versions[group] = paths.pop()
    contract["sdkBasePaths"] = versions
    return contract


def check_folder_transfer_contract(repo=REPO, *, installed=False, actual=None):
    baseline = INSTALLED_BASELINE if installed else BASELINE
    if actual is None:
        actual = collect_folder_transfer_contract(repo, installed=installed)
    changes = differences(json.loads(baseline.read_text(encoding="utf-8")), actual)
    if changes:
        raise AssertionError(
            "Folder-transfer SDK/CLI contract drift. Review request/response fields, "
            "CLI commands, async statuses and PAR handling in BOTH plugins/aidp/codex "
            "and plugins/aidp/claude, plus affected tests, before accepting a new baseline. "
            "Do not auto-refresh baselines or weaken assertions.\n" + "\n".join(changes))
    return actual
