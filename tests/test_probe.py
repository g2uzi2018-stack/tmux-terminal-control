import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import test_cowork as fixtures
import capabilities
import config
import tasks as cowork
import interactions
import probe
import profiles


class ProbeTests(unittest.TestCase):
    setUp = fixtures.CoworkTests.setUp
    init = fixtures.CoworkTests.init
    start_fake = fixtures.CoworkTests.start_fake
    cleanup_session = fixtures.CoworkTests.cleanup_session

    def test_all_checks_execute_behavior_against_fixture_and_version_gate(self):
        wrapper = self.root / 'fixture-cli'
        wrapper.write_text('#!/bin/sh\nexec ' + sys.executable + ' ' + str(fixtures.ROOT / 'tests/fake_probe.py') + ' "$@"\n')
        wrapper.chmod(0o700)
        Path(os.environ['PEER_CONFIG']).write_text(json.dumps(dict(
            runs_dir=str(self.runs), proxy=dict(mode='off'), profiles=dict(codex=dict(
            path=str(wrapper), approval_patterns=[r'^Allow creation of this file\?$'], prompt_lines=8)))))
        report = probe.run('codex', cwd=self.cwd, timeout_ms=4000, budget_seconds=50)
        self.assertEqual(set(report['checks']), set(probe.CHECKS))
        self.assertEqual({key: item['status'] for key, item in report['checks'].items()},
                         {key: 'passed' for key in probe.CHECKS}, json.dumps(report, indent=2))
        for name, item in report['checks'].items():
            self.assertLessEqual(item['submissions'], 1)
            self.assertFalse(item['cleanup_errors'], name)
        self.assertEqual(report['checks']['cancel']['escapes'], 1)
        self.assertEqual(capabilities.cancellation('codex')['key'], 'Escape')
        Path(os.environ['PEER_CONFIG']).write_text(json.dumps(dict(proxy=dict(mode='off'),
            profiles=dict(codex=dict(path=str(wrapper))))))
        self.assertEqual(profiles.settings('codex')['approval_patterns'], [r'^Allow creation of this file\?$'])
        with patch.object(profiles, 'version', return_value='fake-probe-v2'):
            self.assertFalse(capabilities.comparison('codex')['version_matches'])
            self.assertEqual(profiles.settings('codex')['approval_patterns'], [])
            with self.assertRaises(cowork.ToolError):
                capabilities.cancellation('codex')
        # Check prompt-region sensitivity instead of claiming the historical agy version passed.
        self.assertEqual(report['checks']['approval']['prompt_lines'], 8)

    def test_failure_is_isolated_and_later_checks_are_executed(self):
        with patch.object(profiles, 'command', return_value=['/bin/false']), \
                patch.object(profiles, 'version', return_value='fixture-failure'):
            report = probe.run('codex', cwd=self.cwd, timeout_ms=900, budget_seconds=12)
        self.assertEqual(set(report['checks']), set(probe.CHECKS))
        self.assertTrue(all(item['status'] != 'passed' for item in report['checks'].values()))
        self.assertTrue(all('socket' in item for item in report['checks'].values()))
        self.assertTrue(all(item['submissions'] == 0 for item in report['checks'].values()))

    def negative_fixture(self, check, extra_env):
        wrapper = self.root / 'fixture-cli'
        wrapper.write_text('#!/bin/sh\nexec ' + sys.executable + ' ' + str(fixtures.ROOT / 'tests/fake_probe.py') + ' "$@"\n')
        wrapper.chmod(0o700)
        Path(os.environ['PEER_CONFIG']).write_text(json.dumps(dict(
            runs_dir=str(self.runs), proxy=dict(mode='off'), profiles=dict(codex=dict(path=str(wrapper))))))
        with patch.object(probe, 'CHECKS', (check,)), patch.dict(os.environ, extra_env):
            return probe.run('codex', cwd=self.cwd, timeout_ms=1800, budget_seconds=4)['checks'][check]

    def test_echoed_input_is_not_a_single_line_response(self):
        item = self.negative_fixture('single_line', {'PEER_FAKE_NO_RESPONSE': 'single_line'})
        self.assertEqual(item['status'], 'timeout')
        self.assertEqual(item['submissions'], 1)

    def test_partial_long_answer_does_not_pass(self):
        self.assertEqual(self.negative_fixture('long_response', {'PEER_FAKE_TRUNCATE': '1'})['status'], 'timeout')

    def test_interrupted_label_without_stopped_process_does_not_pass(self):
        item = self.negative_fixture('cancel', {'PEER_FAKE_FALSE_CANCEL': '1'})
        self.assertEqual(item['status'], 'timeout')
        self.assertEqual(item['escapes'], 1)
        self.assertFalse(item['cleanup_errors'])

    def test_probe_compares_requested_proxy_to_actual_pane(self):
        wrapper = self.root / 'fixture-cli'
        wrapper.write_text('#!/bin/sh\nexec ' + sys.executable + ' ' + str(fixtures.ROOT / 'tests/fake_probe.py') + ' "$@"\n')
        wrapper.chmod(0o700)
        Path(os.environ['PEER_CONFIG']).write_text(json.dumps(dict(runs_dir=str(self.runs),
            proxy=dict(mode='url', url='http://localhost:18999'), profiles=dict(codex=dict(path=str(wrapper))))))
        with patch.object(probe, 'CHECKS', ('readiness',)):
            item = probe.run('codex', cwd=self.cwd, timeout_ms=1800, budget_seconds=4)['checks']['readiness']
        self.assertEqual(item['status'], 'passed', item)
        self.assertTrue(item['pane_environment_matches']['HTTPS_PROXY'])
        self.assertTrue(item['pane_environment_matches']['NO_PROXY'])

    def test_forged_heartbeat_for_an_unrelated_process_cannot_enable_escape(self):
        item = self.negative_fixture('cancel', {'PEER_FAKE_FORGE_HEARTBEAT': '1'})
        self.assertEqual(item['status'], 'timeout')
        self.assertEqual(item['escapes'], 0)
        self.assertFalse(item['cleanup_errors'])
