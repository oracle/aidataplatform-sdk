from __future__ import annotations

import ast
from contextlib import contextmanager
from pathlib import Path
import shutil
import tempfile
import unittest

from cluster_contract import REPO, check_cluster_contract, collect_cluster_contract
from sensitive_contract import validate_body


SDK = "aidp-python-client/src/aidp_python_client/aidataplatform_dp/"
MODELS = SDK + "models/"


class ClusterCreationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.repo = Path(cls.directory.name)
        # Source-only extraction; no SDK imports, credentials or network calls.
        for relative in ("aidp-python-client/src", "aidp-cli/aidp-py-cli/scripts",
                         "aidp-cli/aidp-py-cli/src", "aidp-typescript-client/lib/model",
                         "aidp-typescript-client/lib/response"):
            shutil.copytree(REPO / relative, cls.repo / relative,
                            ignore=shutil.ignore_patterns("__pycache__"))

    @contextmanager
    def changed(self, relative, old, new):
        path = self.repo / relative
        original = path.read_text(encoding="utf-8")
        self.assertIn(old, original, "Mutation target moved; review this scenario")
        try:
            path.write_text(original.replace(old, new, 1), encoding="utf-8")
            yield
        finally:
            path.write_text(original, encoding="utf-8")

    def assert_drift(self, relative, old, new, diagnostic):
        with self.changed(relative, old, new):
            with self.assertRaisesRegex(AssertionError, "Cluster creation SDK/CLI contract drift") as error:
                check_cluster_contract(self.repo)
            self.assertIn(diagnostic, str(error.exception))
            self.assertIn("BOTH plugins/aidp/codex and plugins/aidp/claude", str(error.exception))

    def test_reviewed_cluster_creation_contract_has_no_drift(self):
        check_cluster_contract()

    def test_ai_autoscaling_accepts_reviewed_metrics_and_rejects_invalid_targets(self):
        models = collect_cluster_contract()["models"]
        for metric in ("API_REQUESTS_PER_SECOND", "CPU_UTILIZATION", "MEMORY_UTILIZATION"):
            body = {"type": "AI_COMPUTE", "displayName": "chosen", "driverConfig": {},
                    "autoScaleConfiguration": {"cooldownPeriodInMinutes": 10,
                        "metrics": [{"name": metric, "targetAverageValue": "80"}]}}
            validate_body(models, "CreateClusterDetails", body)
        for metric, diagnostic in (({"name": "FUTURE_METRIC", "targetAverageValue": "80"}, "unsupported enum"),
                                   ({"name": "CPU_UTILIZATION", "targetAverageValue": 80}, "expected str"),
                                   ({"name": "CPU_UTILIZATION"}, "targetAverageValue")):
            with self.subTest(metric=metric), self.assertRaisesRegex(AssertionError, diagnostic):
                validate_body(models, "AutoScaleConfiguration", {"metrics": [metric]})

    def test_ai_autoscaling_nested_target_type_change_fails(self):
        self.assert_drift(MODELS + "auto_scale_metric_configuration.py",
                          "'target_average_value': 'str'", "'target_average_value': 'int'",
                          "contract.models.AutoScaleMetricConfiguration.fields.targetAverageValue.type")

    def test_sdk_default_retry_change_fails(self):
        path = self.repo / (SDK + "cluster_client.py")
        source = path.read_text()
        method = next(node for node in ast.walk(ast.parse(source))
                      if isinstance(node, ast.FunctionDef) and node.name == "create_cluster")
        original = ast.get_source_segment(source, method)
        old = "retry_strategy = retry.DEFAULT_RETRY_STRATEGY"
        self.assertIn(old, original)
        self.assert_drift(SDK + "cluster_client.py", original,
                          original.replace(old, "retry_strategy = None", 1),
                          "contract.sdkCreateImplementation")

    def test_added_spark_payload_field_fails(self):
        # Add to both generated field maps, as a real SDK generation would.
        relative = MODELS + "create_spark_cluster_details.py"
        with self.changed(relative, "'worker_config': 'WorkerConfig',",
                          "'worker_config': 'WorkerConfig',\n            'new_option': 'bool',"):
            self.assert_drift(relative, "'worker_config': 'workerConfig',",
                              "'worker_config': 'workerConfig',\n            'new_option': 'newOption',",
                              "ADDED contract.models.CreateSparkClusterDetails.fields.newOption")

    def test_removed_ai_payload_field_fails(self):
        relative = MODELS + "create_ai_compute_details.py"
        with self.changed(relative, "            'description': 'str',\n", ""):
            self.assert_drift(relative, "            'description': 'description',\n", "",
                              "REMOVED contract.models.CreateAiComputeDetails.fields.description")

    def test_wire_field_rename_fails(self):
        self.assert_drift(MODELS + "worker_config.py", "'worker_shape': 'workerShape'",
                          "'worker_shape': 'shape'", "REMOVED contract.models.WorkerConfig.fields.workerShape")

    def test_nested_field_type_change_fails(self):
        self.assert_drift(MODELS + "replica_config.py", "'min_replica': 'int'",
                          "'min_replica': 'str'", "contract.models.ReplicaConfig.fields.minReplica.type")

    def test_nested_container_structure_change_fails(self):
        self.assert_drift(MODELS + "spark_runtime_config.py", "'init_scripts': 'list[InitScriptPath]'",
                          "'init_scripts': 'dict(str, InitScriptPath)'",
                          "contract.models.SparkRuntimeConfig.fields.initScripts.type")

    def test_requiredness_change_fails(self):
        self.assert_drift(MODELS + "create_cluster_details.py",
                          "**[Required]** Gets the driver_config", "Gets the driver_config",
                          "contract.models.CreateClusterDetails.fields.driverConfig.required")

    def test_enum_addition_and_removal_fail_independently(self):
        for values in ('["USER", "AI_COMPUTE", "FUTURE_COMPUTE"]', '["USER"]'):
            with self.subTest(values=values):
                self.assert_drift(MODELS + "create_cluster_details.py",
                                  'allowed_values = ["USER", "AI_COMPUTE"]',
                                  'allowed_values = ' + values,
                                  "contract.models.CreateClusterDetails.fields.type.enum")

    def test_nested_enum_change_fails(self):
        self.assert_drift(MODELS + "cluster_runtime_config.py", 'allowed_values = ["SPARK"]',
                          'allowed_values = ["SPARK", "FUTURE_RUNTIME"]',
                          "contract.models.ClusterRuntimeConfig.fields.type.enum")

    def test_default_change_fails(self):
        self.assert_drift(MODELS + "create_spark_cluster_details.py", "self._type = 'USER'",
                          "self._type = 'FUTURE_COMPUTE'",
                          "contract.models.CreateSparkClusterDetails.defaults.type")

    def test_discriminator_variant_change_fails(self):
        self.assert_drift(MODELS + "create_cluster_details.py", "if type == 'DFL':",
                          "if type == 'FUTURE_COMPUTE':",
                          "contract.models.CreateClusterDetails.variants")

    def test_new_subtype_and_its_nested_fields_fail(self):
        relative = MODELS + "create_future_compute_details.py"
        template = (self.repo / (MODELS + "create_ai_compute_details.py")).read_text()
        (self.repo / relative).write_text(template.replace("CreateAiComputeDetails", "CreateFutureComputeDetails"))
        try:
            self.assert_drift(MODELS + "create_cluster_details.py", "        if type == 'DFL':",
                              "        if type == 'FUTURE_COMPUTE':\n"
                              "            return 'CreateFutureComputeDetails'\n\n"
                              "        if type == 'DFL':",
                              "ADDED contract.models.CreateFutureComputeDetails")
        finally:
            (self.repo / relative).unlink()

    def test_creation_command_option_change_fails(self):
        self.assert_drift(SDK + "cluster_client.py",
                          "def create_cluster(self, ai_data_platform_id, workspace_key, create_cluster_details, **kwargs):",
                          "def create_cluster(self, ai_data_platform_id, workspace_key, create_cluster_details, new_create_option=None, **kwargs):",
                          "contract.sdkCreateImplementation")

    def test_creation_route_change_fails(self):
        self.assert_drift(SDK + "cluster_client.py",
                          'resource_path = "/aiDataPlatforms/{aiDataPlatformId}/workspaces/{workspaceKey}/clusters"',
                          'resource_path = "/aiDataPlatforms/{aiDataPlatformId}/workspaces/{workspaceKey}/futureClusters"',
                          "contract.operations.cluster.operations.create_cluster.path")

    def test_api_version_change_fails(self):
        self.assert_drift(SDK + "cluster_client.py", "'base_path': '/20260430'",
                          "'base_path': '/20990101'", "contract.sdkBasePath")

    def test_removed_creation_operation_fails(self):
        with self.changed(SDK + "cluster_client.py", "def create_cluster(", "def future_create_cluster("):
            with self.assertRaisesRegex(ValueError, "SDK operation missing: create_cluster"):
                check_cluster_contract(self.repo)

    def test_cli_option_enum_change_fails(self):
        self.assert_drift("aidp-cli/aidp-py-cli/src/aidp_cli/main.py",
                          'AUTH_CHOICES = ("api_key",', 'AUTH_CHOICES = ("future_auth", "api_key",',
                          "contract.cli.AUTH_CHOICES")

    def test_cli_command_naming_change_fails(self):
        self.assert_drift("aidp-cli/aidp-py-cli/scripts/generate_manifest.py",
                          'def command_group_name(default_name: str) -> str:',
                          'def command_group_name(default_name: str) -> str:\n    return "future-group"',
                          "contract.cliNaming.command_group_name")

    def test_prose_and_comment_changes_do_not_fail(self):
        with self.changed(MODELS + "create_cluster_details.py", "Cluster name.", "Compute display name."):
            with self.changed(SDK + "cluster_client.py", "# Don't accept unknown kwargs",
                              "# Validate keyword arguments"):
                check_cluster_contract(self.repo)


if __name__ == "__main__":
    unittest.main()
