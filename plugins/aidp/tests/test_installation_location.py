"""Installation destination selection stays read-only and preserves existing tools."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(host='codex'):
    spec = importlib.util.spec_from_file_location('location_prerequisites_' + host, ROOT / host / 'skills/aidp-setup-local/scripts/check_prerequisites.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InstallationLocationTests(unittest.TestCase):
    def fresh_check(self, module, **kwargs):
        facts = {'python': '3.13.17', 'virtualenv': False, 'pip': True,
                 'ensurepip': True, 'packages': {'aidp-cli': None, 'aidp-python-client': None}}
        index = {'latest': '5.1.1', 'available': ['5.1.1']}
        with mock.patch.object(module, '_read_context', return_value=({'schemaVersion': 2}, None)), \
             mock.patch.object(module, '_select_cli', return_value=(
                 {'status': 'missing'}, sys.executable, 'option', {sys.executable: (facts, None)})), \
             mock.patch.object(module, '_tool', return_value={'status': 'installed', 'version': '3.96.0'}), \
             mock.patch.object(module, '_python', return_value={'status': 'installed', 'version': '3.13.17'}), \
             mock.patch.object(module, '_pip', return_value={'status': 'installed', 'version': '26.2.2'}), \
             mock.patch.object(module, '_index_versions', return_value=index), \
             mock.patch.object(module.shutil, 'which', return_value=None):
            return module.check(False, 20, **kwargs)

    def test_custom_destination_controls_action_without_creating_directory(self):
        module = load()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'custom aidp'
            summary = self.fresh_check(module, venv_dir=str(target))
            [action] = summary['actions']
            self.assertEqual(action['install_method'], 'virtualenv')
            self.assertEqual(action['verify_aidp'], str(target / module.VENV_BIN / module.AIDP_EXE))
            self.assertEqual(action['path_hint'], str(target / module.VENV_BIN))
            self.assertIn(str(target), action['command'])
            self.assertIn('aidp-cli==5.1.1', action['command'])
            self.assertFalse(target.exists(), 'The prerequisite checker must stay read-only')

    def test_omitted_destination_keeps_existing_default(self):
        module = load()
        summary = self.fresh_check(module)
        [action] = summary['actions']
        self.assertEqual(action['verify_aidp'], os.path.join(module.VENV_DIR, module.VENV_BIN, module.AIDP_EXE))

    def test_custom_directory_can_be_discovered_without_path_changes(self):
        module = load()
        with tempfile.TemporaryDirectory() as directory:
            candidate = os.path.join(directory, module.VENV_BIN, module.AIDP_EXE)
            with mock.patch.object(module.os, 'get_exec_path', return_value=[]), \
                 mock.patch.object(module, '_executable_file', side_effect=lambda path: path == candidate), \
                 mock.patch.object(module, 'interpreter_from_script', return_value=sys.executable), \
                 mock.patch.object(module, '_tool', return_value={'status': 'installed', 'path': candidate}):
                result, interpreter, _, _ = module._select_cli({}, venv_dir=directory)
            self.assertEqual(result['path'], candidate)
            self.assertEqual(interpreter, sys.executable)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_saved_working_selection_is_not_relocated(self):
        module = load()
        saved = {'path': os.path.abspath('saved-aidp'), 'pythonPath': sys.executable}
        with mock.patch.object(module, '_executable_file', return_value=True), \
             mock.patch.object(module, '_tool', return_value={'status': 'installed', 'path': saved['path']}), \
             mock.patch.object(module, 'interpreter_from_script') as ownership:
            result, interpreter, source, _ = module._select_cli({'pythonCli': saved}, venv_dir=os.path.abspath('new-location'))
        self.assertEqual(result['path'], saved['path'])
        self.assertEqual(interpreter, sys.executable)
        self.assertEqual(source, 'context')
        ownership.assert_not_called()

    def test_relative_destination_is_rejected_before_checks(self):
        module = load()
        with mock.patch.object(sys, 'argv', ['checker', '--venv-dir', 'relative-directory']), \
             mock.patch.object(module, 'check') as check, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(module.main(), 2)
        check.assert_not_called()

    def test_posix_environment_command_keeps_existing_behavior(self):
        module = load()
        with mock.patch.object(module, 'WINDOWS', False), mock.patch.object(module, 'VENV_BIN', 'bin'), \
             mock.patch.object(module, 'PYTHON_EXE', 'python'):
            command = module._venv_command('/usr/bin/python3', '5.1.1', '/home/user/.aidp-venv')
        self.assertTrue(command.startswith('/usr/bin/python3 -m venv /home/user/.aidp-venv && '))
        self.assertNotIn('Test-Path', command)

    @unittest.skipUnless(os.name == 'nt', 'PowerShell execution requires Windows')
    def test_prepared_environment_is_reused_and_failed_creation_stops_install(self):
        module = load()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'prepared environment'
            python = target / 'Scripts/python.exe'
            python.parent.mkdir(parents=True)
            python.write_bytes(b'existing-environment-marker')
            marker = Path(directory) / 'pip-command-ran'
            install = module._shell([sys.executable, '-c', 'from pathlib import Path; Path(' + repr(str(marker)) + ').touch()'])
            fail = module._shell([sys.executable, '-c', 'raise SystemExit(7)'])
            with mock.patch.object(module, '_pip_install', return_value=install), \
                 mock.patch.object(module, '_shell', return_value=fail):
                command = module._venv_command(sys.executable, '5.1.1', str(target))
            result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(marker.exists())
            self.assertEqual(python.read_bytes(), b'existing-environment-marker')
            python.unlink()
            marker.unlink()
            result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 7, result.stderr)
            self.assertFalse(marker.exists())


    def test_system_drive_oci_is_found_beside_separate_user_aidp(self):
        drive = 'D:' if os.name == 'nt' else '/test-os-drive'
        for host in ('codex', 'claude'):
            with self.subTest(host=host):
                module = load(host)
                expected = os.path.join(drive + os.sep, 'oci-cli', module.VENV_BIN, module.OCI_EXE)
                with mock.patch.object(module, 'WINDOWS', True), \
                     mock.patch.dict(os.environ, {'SystemDrive': drive}), \
                     mock.patch.object(module.shutil, 'which', return_value=None), \
                     mock.patch.object(module, '_executable_file', side_effect=lambda p: p == expected), \
                     mock.patch.object(module, '_tool', return_value={
                         'status': 'installed', 'path': expected, 'version': '3.96.0'}) as tool:
                    result = module._oci_cli({'status': 'missing'},
                        os.path.join(module.VENV_DIR, module.VENV_BIN, module.AIDP_EXE),
                        sys.executable, venv_dir=module.VENV_DIR)
                self.assertEqual(result['path'], expected)
                self.assertTrue(result['path_adjustment_required'])
                tool.assert_called_once_with('oci', ['--version'], path=expected)

    def test_posix_discovery_does_not_search_windows_oci_destination(self):
        module = load('codex')
        with mock.patch.object(module, 'WINDOWS', False), \
             mock.patch.dict(os.environ, {'SystemDrive': 'D:'}), \
             mock.patch.object(module.shutil, 'which', return_value=None), \
             mock.patch.object(module, '_executable_file') as executable:
            result = module._oci_cli({'status': 'missing'}, None, None)
        self.assertEqual(result['status'], 'missing')
        executable.assert_not_called()

    def test_new_windows_aidp_action_keeps_user_profile_destination(self):
        for host in ('codex', 'claude'):
            with self.subTest(host=host):
                module = load(host)
                with mock.patch.object(module, 'WINDOWS', True):
                    summary = self.fresh_check(module)
                [action] = [a for a in summary['actions'] if a['kind'] == 'install_aidp_packages']
                self.assertEqual(action['verify_aidp'],
                    os.path.join(os.path.expanduser('~'), '.aidp-venv', module.VENV_BIN, module.AIDP_EXE))
                self.assertIn(module._shell([os.path.join(module.VENV_DIR, module.VENV_BIN, module.PYTHON_EXE), '-m', 'pip', 'install']), action['command'])


if __name__ == '__main__':
    unittest.main()
