import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import test_cowork as fixtures
import config
import tasks as cowork
import profiles


class ConfigTests(unittest.TestCase):
    setUp = fixtures.CoworkTests.setUp
    init = fixtures.CoworkTests.init

    def configure(self, value):
        Path(os.environ['PEER_CONFIG']).write_text(json.dumps(value))

    def test_missing_configuration_uses_safe_defaults(self):
        Path(os.environ['PEER_CONFIG']).unlink()
        self.assertEqual(config.load_config(), {})
        with patch.object(config.subprocess, 'run', return_value=SimpleNamespace(
                returncode=0, stdout='__PEER_PROXY_ABSENT__\n')):
            env, record, notice = config.proxy_setup()
        self.assertEqual(env, {})
        self.assertIn('not enabled', notice)
        self.assertIsNone(record['command_ok'])
        self.assertTrue(str(config.runs_directory()).startswith('/tmp/peer-coworkers-'))

    def test_url_off_and_cli_precedence(self):
        url = 'http://127.0.0.1:18999'
        self.configure({'proxy': {'mode': 'url', 'url': url}})
        self.assertEqual(config.proxy_setup()[0]['HTTPS_PROXY'], url)
        self.assertEqual(config.proxy_setup(no_proxy=True)[1]['mode'], 'off')
        with self.assertRaises(cowork.ToolError):
            config.proxy_setup(proxy_url=url, no_proxy=True)

    def test_real_command_environment_capture_and_failure(self):
        self.configure({'proxy': {'mode': 'command', 'command': 'export HTTPS_PROXY=http://localhost:18999'}})
        env, metadata, _ = config.proxy_setup()
        self.assertEqual(env['HTTPS_PROXY'], 'http://localhost:18999')
        self.assertTrue(metadata['command_ok'])
        self.configure({'proxy': {'mode': 'command', 'command': 'false'}})
        with self.assertRaises(cowork.ToolError):
            config.proxy_setup()
        self.assertEqual(self.record['state'], 'prepared')

    def test_auto_failure_is_not_absence(self):
        self.configure({'proxy': {'mode': 'auto'}})
        with patch.object(config.subprocess, 'run', return_value=SimpleNamespace(returncode=42, stdout='')):
            with self.assertRaises(cowork.ToolError):
                config.proxy_setup()

    def test_start_proxy_failure_has_no_launch_side_effect(self):
        self.configure({'proxy': {'mode': 'command', 'command': 'false'}})
        with patch.object(cowork.session, 'new') as launch:
            with self.assertRaises(cowork.ToolError):
                cowork.start(self.run, self.record)
            launch.assert_not_called()
        self.assertEqual(cowork.read_json(self.run / 'task.json')['state'], 'prepared')

    def test_profile_overrides_and_validation(self):
        self.configure({'profiles': {'codex': {'path': '/bin/echo', 'model': 'fixture-model',
                         'approval_patterns': ['^Approval required$']}}})
        self.assertEqual(profiles.command('codex')[-2:], ['--model', 'fixture-model'])
        self.assertEqual(profiles.resolve_executable('codex'), '/bin/echo')
        self.assertEqual(profiles.settings('codex')['approval_patterns'], ['^Approval required$'])
        for value in ({'snapshot': {'max_files': -1}}, {'snapshot': {'max_record_bytes': 0}}, {'proxy': {'mode': 'bad'}},
                      {'profiles': {'codex': {'approval_patterns': ['[']}}}):
            self.configure(value)
            with self.assertRaises(cowork.ToolError):
                config.load_config()

    def test_configured_model_is_bound_to_task_prompt(self):
        self.configure({'profiles': {'codex': {'model': 'fixture-model'}}})
        prepared = self.init()
        run = Path(prepared['run'])
        self.assertEqual(cowork.read_json(run / 'task.json')['model'], 'fixture-model')
        self.assertIn('fixture-model', (run / 'prompt.txt').read_text())

    def test_corrupt_probe_report_is_only_a_warning(self):
        import capabilities
        destination = capabilities.report_path('codex')
        destination.parent.mkdir(parents=True)
        for value in ([], {'profile': 'codex', 'checks': {'cancel': []}}):
            cowork.atomic_json(destination, value)
            self.assertIsNone(capabilities.latest('codex'))
            with patch.object(profiles, 'version', return_value='fixture'):
                self.assertFalse(capabilities.comparison('codex')['version_matches'])

    def test_proxy_command_removals_reach_real_pane_and_parent_is_restored(self):
        import sys
        keys = ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
                'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy')
        self.configure({'proxy': {'mode': 'command', 'command': 'unset ' + ' '.join(keys)}})
        inherited = {key: 'http://stale.invalid:1234' for key in keys}
        with patch.dict(os.environ, inherited), patch.object(profiles, 'command', return_value=[
                sys.executable, '-c', 'import time; time.sleep(20)']):
            cowork.start(self.run, self.record)
            self.addCleanup(cowork.close, self.run, self.record, True)
            pid = cowork.Tmux(self.record['socket']).run('display-message', '-p', '-t',
                    self.record['pane'], '#{pane_pid}').strip()
            pane_env = dict(item.split(b'=', 1) for item in Path('/proc', pid, 'environ').read_bytes().split(b'\0')
                            if b'=' in item)
            for key in keys:
                self.assertNotIn(key.encode(), pane_env)
                self.assertEqual(os.environ[key], inherited[key])
