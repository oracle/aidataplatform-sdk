"""Bootstrap Python may lack pip while the selected environment provides it."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import venv

ROOT = Path(__file__).resolve().parents[1]


class BootstrapPipTests(unittest.TestCase):
    def test_context_get_all_runs_with_real_pip_free_python(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / 'bootstrap'
            venv.EnvBuilder(with_pip=False).create(runtime)
            python = runtime / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
            environment = dict(os.environ, AIDP_CONTEXT_FILE=str(Path(directory) / 'context.json'))
            pip = subprocess.run([str(python), '-m', 'pip', '--version'], capture_output=True, timeout=30)
            self.assertNotEqual(pip.returncode, 0)
            for host in ('codex', 'claude'):
                helper = ROOT / host / 'skills/aidp-setup-local/scripts/aidp_context.py'
                result = subprocess.run([str(python), str(helper), 'get', 'all'],
                                        env=environment, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIsInstance(json.loads(result.stdout), dict)

    def test_saved_pip_satisfies_prerequisite_and_performs_latest_lookup(self):
        for host in ('codex', 'claude'):
            with self.subTest(host=host):
                script = ROOT / host / 'skills/aidp-setup-local/scripts/check_prerequisites.py'
                spec = importlib.util.spec_from_file_location('bootstrap_checker_' + host, script)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                saved = os.path.abspath('saved-environment/python.exe')
                cli = os.path.abspath('saved-environment/aidp.exe')
                facts = {'python': '3.13.17', 'virtualenv': True, 'pip': True, 'ensurepip': True,
                         'packages': {'aidp-cli': '5.1.1', 'aidp-python-client': '5.1.1'}}
                context = {'schemaVersion': 2, 'pythonCli': {'path': cli, 'pythonPath': saved}}
                index = {'latest': '5.1.1', 'available': ['5.1.1']}
                with mock.patch.object(module, '_read_context', return_value=(context, None)), \
                     mock.patch.object(module, '_select_cli', return_value=(
                         {'status': 'installed', 'path': cli, 'version': '5.1.1'},
                         saved, 'context', {saved: (facts, None)})) as selection, \
                     mock.patch.object(module, '_pip', side_effect=[
                         {'status': 'missing', 'detail': 'No module named pip'},
                         {'status': 'installed', 'version': '26.2.2'}]) as pip, \
                     mock.patch.object(module, '_initial_oci', return_value={
                         'status': 'installed', 'path': sys.executable,
                         'version': '3.96.0', 'path_adjustment_required': False}), \
                     mock.patch.object(module, '_index_versions', return_value=index) as lookup, \
                     mock.patch.object(module.shutil, 'which', return_value=cli):
                    summary = module.check(False, 20)
                self.assertTrue(summary['ok'], summary['blocking'])
                self.assertEqual(summary['prerequisites']['pip']['status'], 'installed')
                self.assertEqual(summary['versions']['index_python'], saved)
                self.assertEqual(pip.call_args_list, [mock.call(), mock.call(saved)])
                self.assertEqual(selection.call_args.args[0], context)
                self.assertEqual(lookup.call_count, 2)
                self.assertTrue(all(call.args[0] == saved for call in lookup.call_args_list))
                self.assertNotIn('restore_pip', [action['kind'] for action in summary['actions']])


if __name__ == '__main__':
    unittest.main()
