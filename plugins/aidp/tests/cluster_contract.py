"""Offline drift gate for the cluster creation skill's SDK and CLI contract."""
from __future__ import annotations

import ast
import json
from pathlib import Path

from sensitive_contract import REPO, collect_contract, differences, source_function_contract


BASELINE = Path(__file__).with_name("contracts") / "cluster-create-contract.json"
CLIENTS = {"cluster": ("cluster_client.py", ("create_cluster",))}


def collect_cluster_contract(repo=REPO):
    # Reuse the existing recursive extraction of fields, types, requiredness,
    # defaults, inheritance, enums and discriminator variants (including maps).
    contract = collect_contract(repo, clients=CLIENTS)
    contract.pop("catalogPropertyEnums")
    client = repo / "aidp-python-client/src/aidp_python_client/aidataplatform_dp/cluster_client.py"
    tree = ast.parse(client.read_text(encoding="utf-8"))
    methods = [node for owner in tree.body if isinstance(owner, ast.ClassDef)
               for node in owner.body if isinstance(node, ast.FunctionDef)
               and node.name == "create_cluster"]
    if len(methods) != 1:
        raise ValueError("Cannot extract an unambiguous create_cluster method")
    method = methods[0]
    if ast.get_docstring(method) is not None:
        method.body.pop(0)
    contract["sdkCreateImplementation"] = ast.dump(method, include_attributes=False)
    versions = [ast.literal_eval(value) for node in ast.walk(tree) if isinstance(node, ast.Dict)
                for key, value in zip(node.keys, node.values)
                if isinstance(key, ast.Constant) and key.value == "base_path"]
    if len(versions) != 1:
        raise ValueError("Cannot extract an unambiguous cluster API base path")
    contract["sdkBasePath"] = versions[0]
    contract["cliNaming"] = source_function_contract(
        repo / "aidp-cli/aidp-py-cli/scripts/generate_manifest.py",
        ("build_command_groups", "command_group_name", "apply_short_command_names",
         "command_name_from_sdk_method"),
    )
    return contract


def check_cluster_contract(repo=REPO):
    actual = collect_cluster_contract(repo)
    changes = differences(json.loads(BASELINE.read_text(encoding="utf-8")), actual)
    if changes:
        raise AssertionError(
            "Cluster creation SDK/CLI contract drift. Review and update the cluster creation "
            "skill in BOTH plugins/aidp/codex and plugins/aidp/claude, plus affected tests, "
            "before accepting a new baseline. Do not auto-refresh the baseline or weaken "
            "this test just to make it pass.\n" + "\n".join(changes)
        )
    return actual
