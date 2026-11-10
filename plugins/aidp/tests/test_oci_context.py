"""OCI path persistence and discovery without cloud access or package installs."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / 'codex/skills/aidp-setup-local'


def load():
    spec = importlib.util.spec_from_file_location('oci_context_prerequisites', SETUP / 'scripts/check_prerequisites.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OciContextTests(unittest.TestCase):
    def test_context_round_trip_between_assistants_preserves_python_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            context = Path(directory) / 'context.json'
            environment = dict(os.environ, AIDP_CONTEXT_FILE=str(context), PYTHONDONTWRITEBYTECODE='1')

            def run(host, *arguments):
                script = ROOT / host / 'skills/aidp-setup-local/scripts/aidp_context.py'
                result = subprocess.run([sys.executable, str(script), *arguments], env=environment,
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)

            run('codex', 'set', 'pythonCli', '--path', sys.executable, '--python-path', sys.executable)
            receipt = run('codex', 'set', 'ociCli', '--path', sys.executable)
            self.assertTrue(receipt['saved'])
            self.assertEqual(receipt['value'], {'path': sys.executable})
            self.assertEqual(run('claude', 'get', 'ociCli'), {'path': sys.executable})
            self.assertEqual(run('claude', 'get', 'all')['pythonCli']['pythonPath'], sys.executable)
            run('claude', 'remove', 'ociCli')
            self.assertIsNone(run('codex', 'get', 'ociCli'))
            self.assertIsNotNone(run('codex', 'get', 'pythonCli'))

    def test_relative_path_is_rejected_without_writing_context(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'context.json'
            result = subprocess.run([sys.executable, str(SETUP / 'scripts/aidp_context.py'),
                                     'set', 'ociCli', '--path', 'relative-oci'],
                                    env=dict(os.environ, AIDP_CONTEXT_FILE=str(path)),
                                    capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(path.exists())

    def test_remembered_off_path_oci_is_revalidated_and_preferred(self):
        module = load()
        saved = os.path.abspath('saved/oci')
        path_oci = os.path.abspath('other/oci')
        with mock.patch.object(module.shutil, 'which', return_value=path_oci), \
             mock.patch.object(module, '_executable_file', return_value=True), \
             mock.patch.object(module, '_tool', return_value={'status': 'installed', 'path': saved, 'version': '3.96.0'}) as tool:
            result = module._initial_oci(saved)
        self.assertEqual(result['path'], saved)
        self.assertTrue(result['path_adjustment_required'])
        tool.assert_called_once_with('oci', ['--version'], path=saved)

    def test_validated_saved_selection_is_not_probed_twice(self):
        module = load()
        saved = os.path.abspath('saved/oci')
        with mock.patch.object(module, '_executable_file', return_value=True), \
             mock.patch.object(module, '_tool', return_value={
                 'status': 'installed', 'path': saved, 'version': '3.96.0'}) as tool, \
             mock.patch.object(module.shutil, 'which') as discovery:
            initial = module._initial_oci(saved)
            result = module._oci_cli(initial, None, sys.executable)
        self.assertEqual(result['path'], saved)
        self.assertTrue(result['path_adjustment_required'])
        tool.assert_called_once_with('oci', ['--version'], path=saved)
        discovery.assert_not_called()

    def test_oci_in_selected_custom_environment_is_reused(self):
        module = load()
        directory = os.path.abspath('custom-environment')
        oci = os.path.join(directory, module.VENV_BIN, module.OCI_EXE)
        with mock.patch.object(module.shutil, 'which', return_value=None), \
             mock.patch.object(module, '_executable_file', side_effect=lambda path: path == oci), \
             mock.patch.object(module, '_tool', return_value={'status': 'installed', 'path': oci, 'version': '3.96.0'}):
            result = module._oci_cli({'status': 'missing'}, os.path.abspath('old/aidp'),
                                     os.path.abspath('old/python'), venv_dir=directory)
        self.assertEqual(result['path'], oci)
        self.assertTrue(result['path_adjustment_required'])

    def test_explicit_path_overrides_saved_selection_and_is_retained_when_off_path(self):
        module = load()
        explicit = os.path.abspath('explicit/oci')
        saved = os.path.abspath('saved/oci')
        python = sys.executable
        facts = {'python': '3.13.17', 'virtualenv': True, 'pip': True, 'ensurepip': True,
                 'packages': {'aidp-cli': '5.1.1', 'aidp-python-client': '5.1.1'}}
        calls = []

        def tool(name, arguments, path=None, **kwargs):
            calls.append(path)
            return {'status': 'installed', 'path': path, 'version': '3.96.0'}

        with mock.patch.object(module, '_read_context', return_value=({'schemaVersion': 2, 'ociCli': {'path': saved}}, None)), \
             mock.patch.object(module, '_select_cli', return_value=(
                 {'status': 'installed', 'path': python, 'version': '5.1.1'}, python, 'context', {python: (facts, None)})), \
             mock.patch.object(module, '_pip', return_value={'status': 'installed', 'version': '26.2.2'}), \
             mock.patch.object(module, '_tool', side_effect=tool), \
             mock.patch.object(module.shutil, 'which', return_value=None):
            summary = module.check(True, 20, oci=explicit)
        self.assertEqual(summary['prerequisites']['oci_cli']['path'], explicit)
        self.assertTrue(summary['prerequisites']['oci_cli']['path_adjustment_required'])
        self.assertEqual(calls, [explicit])

    def test_saved_context_skips_path_discovery_in_complete_check(self):
        module = load()
        saved = os.path.abspath('saved/oci')
        python = sys.executable
        facts = {'python': '3.13.17', 'virtualenv': True, 'pip': True, 'ensurepip': True,
                 'packages': {'aidp-cli': '5.1.1', 'aidp-python-client': '5.1.1'}}

        def which(name):
            if name == 'aidp':
                return python
            raise AssertionError('Unexpected discovery for ' + name)

        with mock.patch.object(module, '_read_context', return_value=({'schemaVersion': 2, 'ociCli': {'path': saved}}, None)), \
             mock.patch.object(module, '_select_cli', return_value=(
                 {'status': 'installed', 'path': python, 'version': '5.1.1'}, python, 'context', {python: (facts, None)})), \
             mock.patch.object(module, '_pip', return_value={'status': 'installed', 'version': '26.2.2'}), \
             mock.patch.object(module, '_executable_file', return_value=True), \
             mock.patch.object(module, '_tool', return_value={'status': 'installed', 'path': saved, 'version': '3.96.0'}) as tool, \
             mock.patch.object(module.shutil, 'which', side_effect=which):
            summary = module.check(True, 20)
        self.assertTrue(summary['ok'])
        self.assertEqual(summary['prerequisites']['oci_cli']['path'], saved)
        tool.assert_called_once_with('oci', ['--version'], path=saved)

    def test_initial_discovery_runs_only_after_saved_path_fails(self):
        module = load()
        saved = os.path.abspath('saved/oci')
        fallback = os.path.abspath('path/oci')
        results = [{'status': 'invalid', 'path': saved, 'detail': 'broken'},
                   {'status': 'installed', 'path': fallback, 'version': '3.96.0'}]
        with mock.patch.object(module, '_executable_file', return_value=True), \
             mock.patch.object(module, '_tool', side_effect=results) as tool:
            result = module._initial_oci(saved)
        self.assertEqual(result['path'], fallback)
        self.assertEqual(tool.call_args_list, [mock.call('oci', ['--version'], path=saved),
                                               mock.call('oci', ['--version'])])

    def test_missing_saved_executable_goes_straight_to_discovery(self):
        module = load()
        with mock.patch.object(module, '_executable_file', return_value=False), \
             mock.patch.object(module, '_tool', return_value={'status': 'missing'}) as tool:
            result = module._initial_oci(os.path.abspath('removed/oci'))
        self.assertEqual(result['status'], 'missing')
        tool.assert_called_once_with('oci', ['--version'])



if __name__ == '__main__':
    unittest.main()
