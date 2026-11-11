# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
"""Portable integration checks; the same cases exercise native Windows in CI."""
from __future__ import annotations

import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'codex/skills/aidp-cli/scripts'
SETUP = ROOT / 'codex/skills/aidp-setup-local/scripts'
sys.path.insert(0, str(CLI))
import platform_support as files


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PlatformSupportTests(unittest.TestCase):
    def test_private_file_creation_read_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'private.json'
            with os.fdopen(files.private_open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL), 'wb') as stream:
                stream.write(b'private sample')
            with os.fdopen(files.readonly_open(path, private=True), 'rb') as stream:
                self.assertEqual(stream.read(), b'private sample')
            with self.assertRaises(FileExistsError):
                files.private_open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)

    def test_other_user_access_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'private.json'
            os.close(files.private_open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL))
            if os.name == 'nt':
                subprocess.run(['icacls', str(path), '/grant', '*S-1-1-0:R'], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            else:
                path.chmod(0o644)
            with self.assertRaises(PermissionError):
                files.readonly_open(path, private=True)

    def test_private_directory_inheritance_and_cleanup(self):
        with files.private_directory() as directory:
            path = Path(directory) / 'child'
            # Windows child files must inherit only the user's access from the
            # directory even when created by an external program.
            path.write_bytes(b'sample')
            if os.name != 'nt':
                path.chmod(0o600)
            os.close(files.readonly_open(path, private=True))
        self.assertFalse(Path(directory).exists())

    def test_native_context_round_trip_and_concurrent_writers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'context' / 'context.json'
            env = dict(os.environ, AIDP_CONTEXT_FILE=str(path))
            commands = [
                [sys.executable, str(SETUP / 'aidp_context.py'), 'set', 'lastUsedAuth',
                 '--auth-type', 'api_key', '--profile', 'DEFAULT'],
                [sys.executable, str(SETUP / 'aidp_context.py'), 'set', 'pythonCli',
                 '--path', sys.executable, '--python-path', sys.executable],
            ]
            # Establish the context directory first; concurrent writes exercise
            # file locking, not directory creation on an absent parent.
            path.parent.mkdir()
            processes = [subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                         for command in commands]
            for process in processes:
                output, error = process.communicate(timeout=30)
                self.assertEqual(process.returncode, 0, error.decode())
            result = subprocess.run([sys.executable, str(SETUP / 'aidp_context.py'), 'get', 'all'],
                                    env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertIn('lastUsedAuth', data)
            self.assertIn('pythonCli', data)

    def test_protected_handoff_with_native_python_child(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template, attachment, result = root / 'body.json', root / 'sample.txt', root / 'result.json'
            attachment.write_text('synthetic secret', encoding='utf-8')
            template.write_text(json.dumps({'value': '{textof:' + str(attachment) + '}'}))
            child = ('import json,sys; from pathlib import Path; p=Path(sys.argv[-1][1:]); '
                     'print(json.dumps({"data":json.loads(p.read_text()),"actualPath":str(p)}))')
            completed = subprocess.run([sys.executable, str(CLI / 'protected_aidp.py'),
                '--output-file', str(result), '--', sys.executable, '-c', child, '--body', '@' + str(template)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertNotIn('synthetic secret', completed.stdout + completed.stderr)
            consumed = subprocess.run([sys.executable, str(CLI / 'read-protected-result.py'), str(result)],
                                     capture_output=True, text=True, timeout=30)
            self.assertEqual(consumed.returncode, 0, consumed.stdout + consumed.stderr)
            payload = json.loads(json.loads(consumed.stdout)['stdout'])
            self.assertEqual(payload['data']['value'], 'synthetic secret')
            self.assertFalse(Path(payload['actualPath']).exists())
            self.assertFalse(result.exists())
            self.assertTrue(template.exists())

    def test_windows_launcher_detection_does_not_execute_unknown_exe(self):
        module = load('windows_prerequisites', SETUP / 'check_prerequisites.py')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'aidp.exe'
            with path.open('wb') as stream:
                stream.write(b'MZ' + b'0' * 2048 + ('#!"' + sys.executable + '"\r\n').encode())
            with zipfile.ZipFile(path, 'a') as archive:
                archive.writestr('__main__.py', 'from aidp_cli.main import main\nmain()')
            with patch.object(module, 'WINDOWS', True):
                self.assertEqual(module.interpreter_from_script(path), os.path.abspath(sys.executable))
                path.write_bytes(b'MZ-not-a-python-launcher')
                self.assertIsNone(module.interpreter_from_script(path))

    def test_protected_output_uses_utf8_despite_inherited_legacy_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template, result = root / 'body.json', root / 'result.json'
            template.write_text('{}', encoding='utf-8')
            child = ('import sys; print("caf\\u00e9 \\u6771\\u4eac"); '
                     'print("caf\\u00e9 \\u6771\\u4eac", file=sys.stderr)')
            completed = subprocess.run([sys.executable, str(CLI / 'protected_aidp.py'),
                '--output-file', str(result), '--', sys.executable, '-c', child,
                '--body', '@' + str(template)], capture_output=True, text=True,
                env=dict(os.environ, PYTHONIOENCODING='cp1252', PYTHONUTF8='0'), timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            payload = json.loads(result.read_text(encoding='utf-8'))
            self.assertEqual(payload['stdout'].strip(), 'caf\u00e9 \u6771\u4eac')
            self.assertEqual(payload['stderr'].strip(), 'caf\u00e9 \u6771\u4eac')

    def test_context_read_allows_concurrent_replace_and_clear(self):
        module = load('context_concurrent_read', SETUP / 'aidp_context.py')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'context.json'
            env = dict(os.environ, AIDP_CONTEXT_FILE=str(path))

            def run(*arguments):
                result = subprocess.run([sys.executable, str(SETUP / 'aidp_context.py'),
                    *arguments], env=env, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            run('set', 'lastUsedAuth', '--auth-type', 'api_key', '--profile', 'before')
            migrate = module._migrate_document

            def replace_while_reader_is_open(document):
                run('set', 'lastUsedAuth', '--auth-type', 'api_key', '--profile', 'after')
                return migrate(document)

            with patch.object(module, '_migrate_document', side_effect=replace_while_reader_is_open):
                snapshot = module._load(path)
            self.assertEqual(snapshot['lastUsedAuth']['profile'], 'before')
            self.assertEqual(module._load(path)['lastUsedAuth']['profile'], 'after')

            def clear_while_reader_is_open(document):
                run('clear')
                return migrate(document)

            with patch.object(module, '_migrate_document', side_effect=clear_while_reader_is_open):
                snapshot = module._load(path)
            self.assertEqual(snapshot['lastUsedAuth']['profile'], 'after')
            self.assertFalse(path.exists())
            self.assertEqual(module._load(path), module._empty_context())

    def test_windows_install_commands_quote_paths_and_stop_on_failure(self):
        module = load('windows_install_commands', SETUP / 'check_prerequisites.py')
        with patch.object(module, 'WINDOWS', True), patch.object(module, 'VENV_BIN', 'Scripts'), \
             patch.object(module, 'PYTHON_EXE', 'python.exe'), \
             patch.object(module, 'VENV_DIR', "C:/Users/O'Brien/.aidp-venv"):
            command = module._venv_command("C:/Program Files/Python/python.exe", '5.2.1')
            self.assertIn("& 'C:/Program Files/Python/python.exe'", command)
            self.assertIn("O''Brien", command)
            self.assertIn('Scripts', command)
            self.assertIn('if ($LASTEXITCODE -ne 0)', command)
            self.assertNotIn('&&', command)

    def test_identity_local_ocid_and_tenancy_never_need_oci(self):
        module = load('portable_whoami', CLI / 'oci-whoami.py')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config'
            path.write_text('[DEFAULT]\nuser=ocid1.user.example\ntenancy=ocid1.tenancy.example\n')
            args = SimpleNamespace(profile='DEFAULT', config_file=str(path), output='ocid',
                                   auth='api_key', tenancy_only=False, oci='never-run')
            with patch.object(module.subprocess, 'run') as remote:
                self.assertEqual(module.resolve(args), {'ocid': 'ocid1.user.example'})
                args.tenancy_only = True
                self.assertEqual(module.resolve(args), {'tenancy': 'ocid1.tenancy.example'})
                remote.assert_not_called()

    def test_generated_shell_chain_stops_before_second_command(self):
        module = load('native_shell_commands', SETUP / 'check_prerequisites.py')
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "quoted's marker.txt"
            first = module._shell([sys.executable, '-c', 'raise SystemExit(7)'])
            second = module._shell([sys.executable, '-c',
                'from pathlib import Path; Path(' + repr(str(marker)) + ').write_text("unexpected")'])
            command = module._chain(first, second)
            shell = ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command'] if os.name == 'nt' else ['/bin/sh', '-c']
            completed = subprocess.run(shell + [command], capture_output=True, text=True, timeout=30)
            self.assertEqual(completed.returncode, 7, completed.stderr)
            self.assertFalse(marker.exists())

    def test_identity_token_discovery_exposes_only_requested_subject(self):
        module = load('portable_whoami_token', CLI / 'oci-whoami.py')
        with tempfile.TemporaryDirectory() as directory:
            path, token = Path(directory) / 'config', Path(directory) / 'token'
            payload = base64.urlsafe_b64encode(json.dumps({
                'sub': 'ocid1.user.example', 'unrequested': 'CANARY_PRIVATE_CLAIM',
            }).encode()).decode().rstrip('=')
            token.write_text('header.' + payload + '.signature')
            path.write_text('[DEFAULT]\nsecurity_token_file=' + str(token) + '\n')
            args = SimpleNamespace(profile='DEFAULT', config_file=str(path), output='ocid',
                                   auth='security_token', tenancy_only=False, oci='never-run')
            with patch.object(module.subprocess, 'run') as remote:
                self.assertEqual(module.resolve(args), {'ocid': 'ocid1.user.example'})
                remote.assert_not_called()

    def test_identity_allowlist_and_custom_config_are_preserved(self):
        module = load('portable_whoami_remote', CLI / 'oci-whoami.py')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'custom config'
            path.write_text('[selected]\nuser=ocid1.user.example\n')
            args = SimpleNamespace(profile='selected', config_file=str(path), output='email',
                                   auth='api_key', tenancy_only=False, oci='selected-oci')
            with patch.object(module.subprocess, 'run', return_value=SimpleNamespace(
                    returncode=0, stdout='{"email":"example@example.com"}')) as remote:
                self.assertEqual(module.resolve(args), {'email': 'example@example.com'})
                command = remote.call_args.args[0]
                self.assertEqual(command[0], 'selected-oci')
                self.assertIn(str(path), command)
                self.assertIn('data.{email:email}', command)
                args.output = 'token'
                with self.assertRaises(ValueError):
                    module.resolve(args)

    def test_packaged_platform_helpers_match(self):
        original = (CLI / 'platform_support.py').read_bytes()
        for variant in ('codex', 'claude'):
            for skill in ('aidp-cli', 'aidp-setup-local'):
                self.assertEqual(original, (ROOT / variant / 'skills' / skill / 'scripts/platform_support.py').read_bytes())


if __name__ == '__main__':
    unittest.main()
