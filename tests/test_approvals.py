from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

import test_cowork as fixtures
import approvals
from observation import wait_event
import tasks


class ApprovalTests(unittest.TestCase):
    setUp = fixtures.CoworkTests.setUp
    init = fixtures.CoworkTests.init
    cleanup_session = fixtures.CoworkTests.cleanup_session

    def menu(self, selected=1, expanded=False):
        self.record['profile'] = 'agy'
        self.log = self.run / 'decisions.txt'
        command = [sys.executable, str(fixtures.ROOT / 'tests/fake_approval.py'),
                   '--log', str(self.log), '--selected', str(selected)]
        if expanded:
            command += ['--expanded']
        with patch.object(tasks.profiles, 'command', return_value=command), \
                patch.object(tasks.profiles, 'version', return_value='fixture-v1'):
            tasks.start(self.run, self.record)
        self.addCleanup(self.cleanup_session, self.record, self.run)
        self.record.update(state='running', execution_started_at=time.time())
        result = wait_event(self.run, self.record, timeout_ms=2000)
        self.assertEqual(result['reason'], 'approval', result)
        return result['approval']

    def decide(self, pending, decision='allow-once'):
        return approvals.decide(self.run, self.record, pending['approval_id'],
                                pending['screen_sha256'], decision, 'authorized fixture command only')

    def test_dialog_without_probe_interrupts_busy_footer_and_is_not_authorization(self):
        pending = self.menu()
        self.assertEqual(pending['dialog']['command'], 'git status')
        self.assertFalse(pending['dialog']['compatibility_verified'])
        self.assertFalse(self.log.exists())
        again = wait_event(self.run, self.record, timeout_ms=300)
        self.assertEqual(again['approval']['approval_id'], pending['approval_id'])

    def test_allow_once_navigates_from_persistent_option_and_submits_only_once(self):
        pending = self.menu(selected=3)
        self.decide(pending)
        deadline = time.monotonic() + 1
        while not self.log.exists():
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.01)
        self.assertEqual(self.log.read_text(), '1\n')
        with self.assertRaisesRegex(tasks.ToolError, 'unanswered'):
            self.decide(pending)
        self.assertEqual(self.log.read_text(), '1\n')

    def test_deny_navigates_to_cancel_without_persistent_permissions(self):
        pending = self.menu()
        self.decide(pending, 'deny')
        deadline = time.monotonic() + 1
        while not self.log.exists():
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.01)
        self.assertEqual(self.log.read_text(), '4\n')

    def test_changed_screen_or_blank_evidence_sends_nothing(self):
        pending = self.menu()
        with self.assertRaises(tasks.ToolError):
            approvals.decide(self.run, self.record, pending['approval_id'],
                             pending['screen_sha256'], 'allow-once', ' ')
        original = approvals.Tmux.capture
        with patch.object(approvals.Tmux, 'capture', lambda tmux, pane: original(tmux, pane).replace('git status', 'git diff')):
            with self.assertRaisesRegex(tasks.ToolError, 'screen changed'):
                self.decide(pending)
        self.assertFalse(self.log.exists())

    def test_failure_after_persistence_is_uncertain_and_cannot_rearm_on_footer_change(self):
        pending = self.menu(selected=3)
        original = approvals.Tmux.run
        def fail_send(tmux, *args, **kwargs):
            if args[0] == 'send-keys':
                raise tasks.ToolError('injected terminal failure')
            return original(tmux, *args, **kwargs)
        with patch.object(approvals.Tmux, 'run', fail_send):
            with self.assertRaisesRegex(tasks.ToolError, 'injected'):
                self.decide(pending)
        self.record = tasks.read_json(self.run / 'task.json')
        self.assertEqual(self.record['pending_approval']['status'], 'uncertain')
        screen = approvals.Tmux(self.record['socket']).capture(self.record['pane'])
        same = approvals.observe_approval(self.record, screen.replace('high', 'high Tip'))
        self.assertEqual(same['approval_id'], pending['approval_id'])
        self.assertIsNone(approvals.observe_approval(self.record, 'partial terminal repaint'))
        self.assertEqual(self.record['pending_approval']['status'], 'uncertain')
        self.assertEqual(approvals.observe_approval(self.record, screen)['approval_id'], pending['approval_id'])
        with self.assertRaises(tasks.ToolError):
            self.decide(pending)
        self.assertFalse(self.log.exists())

    def test_quoted_or_incomplete_dialog_cannot_be_decided(self):
        self.menu()
        screen = approvals.Tmux(self.record['socket']).capture(self.record['pane'])
        for candidate in ('Run this command?', screen + '\n> explain the example\n',
                          screen.replace('> 1.', '  1.'), screen.replace('4. No, cancel', '4. Always allow'),
                          screen.replace('Requesting permission for:', 'Example:')):
            self.assertIsNone(approvals.command_dialog('agy', candidate))
        self.assertIsNone(approvals.command_dialog('cursor', screen))

    def test_reply_is_blocked_while_menu_is_pending(self):
        import interactions
        self.menu()
        message = self.run / 'answer.txt'
        message.write_text('continue')
        with self.assertRaisesRegex(tasks.ToolError, 'pending approval'):
            interactions.reply(self.run, self.record, message)
        self.assertEqual(self.record['round'], 0)

    def test_hidden_command_cannot_be_allowed(self):
        pending = self.menu()
        original = approvals.Tmux.capture
        screen = original(approvals.Tmux(self.record['socket']), self.record['pane'])
        hidden = screen.replace('   git status', '   python3 -c ... (12 lines hidden)')
        pending = approvals.observe_approval(self.record, hidden)
        with patch.object(approvals.Tmux, 'capture', return_value=hidden):
            with self.assertRaisesRegex(tasks.ToolError, 'collapsed/truncated'):
                self.decide(pending)
        self.assertFalse(self.log.exists())

    def test_expanded_command_returns_to_menu_and_only_allows_once(self):
        pending = self.menu(selected=3, expanded=True)
        self.assertEqual(pending['dialog']['kind'], 'agy_expanded_command')
        self.assertIn('print(391)', pending['dialog']['command'])
        self.decide(pending)
        deadline = time.monotonic() + 1
        while not self.log.exists():
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.01)
        self.assertEqual(self.log.read_text(), '1\n')
        entry = self.record['interventions'][-1]
        self.assertIn('reviewed_command_sha256', entry)

    def test_changed_command_after_expanded_review_is_not_submitted(self):
        pending = self.menu(expanded=True)
        original = approvals.Tmux.capture
        def changed(tmux, pane):
            screen = original(tmux, pane)
            return screen if 'Expanded Tool Permission Editor' in screen else screen.replace('python3', 'different-command')
        with patch.object(approvals.Tmux, 'capture', changed):
            with self.assertRaisesRegex(tasks.ToolError, 'command changed'):
                self.decide(pending)
        self.assertFalse(self.log.exists())
        self.assertEqual(self.record['pending_approval']['status'], 'uncertain')
