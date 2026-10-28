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

    def menu(self, selected=1, expanded=False, edit=False, incomplete=False):
        self.record['profile'] = 'agy'
        self.log = self.run / 'decisions.txt'
        command = [sys.executable, str(fixtures.ROOT / 'tests/fake_approval.py'),
                   '--log', str(self.log), '--selected', str(selected)]
        if expanded:
            command += ['--expanded']
        if edit:
            command += ['--edit', str(self.cwd / 'existing.txt')]
            self.record.update(role='implement', owned_paths=['existing.txt'])
        if incomplete:
            command += ['--incomplete']
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

    def test_file_edit_wait_returns_target_complete_diff_and_approval_budget(self):
        pending = self.menu(edit=True)
        self.assertEqual(pending['dialog']['kind'], 'agy_file_edit')
        self.assertEqual(pending['dialog']['path'], str(self.cwd / 'existing.txt'))
        self.assertTrue(pending['dialog']['diff_fully_visible'])
        self.assertEqual(self.record['last_wait']['budget']['phase'], 'approval')
        events = tasks.read_json(self.run / 'terminal-events.json')
        self.assertIn('Accept this file edit?', events[-1]['screen'])
        self.assertEqual(events[-1]['reason'], 'approval')
        self.assertFalse(self.log.exists())

    def test_captured_agy_149_card_is_recognized_with_all_changes(self):
        screen = (fixtures.ROOT / 'tests/fixtures/agy-1.4.9-pending-edit.txt').read_text()
        dialog = approvals.file_edit_dialog('agy', screen)
        self.assertIsNotNone(dialog)
        self.assertEqual((dialog['additions'], dialog['deletions']), (6, 2))
        self.assertTrue(dialog['diff_fully_visible'])
        self.assertNotIn('shift+tab', dialog['diff'])
        clipped = screen.replace("   6  +                  if code != 200:\n", '')
        self.assertFalse(approvals.file_edit_dialog('agy', clipped)['diff_fully_visible'])

    def test_file_edit_allow_once_from_reject_selection_and_replay_refused(self):
        pending = self.menu(edit=True, selected=2)
        self.decide(pending)
        deadline = time.monotonic() + 1
        while not self.log.exists():
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.01)
        self.assertEqual(self.log.read_text(), '1\n')
        with self.assertRaises(tasks.ToolError):
            self.decide(pending)
        self.assertEqual(self.log.read_text(), '1\n')
        self.assertEqual(self.record['interventions'][-1]['dialog_kind'], 'agy_file_edit')

    def test_file_edit_deny_uses_second_option(self):
        self.decide(self.menu(edit=True), 'deny')
        deadline = time.monotonic() + 1
        while not self.log.exists():
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.01)
        self.assertEqual(self.log.read_text(), '2\n')

    def test_incomplete_file_diff_can_only_be_rejected(self):
        pending = self.menu(edit=True, incomplete=True)
        self.assertEqual(pending['dialog']['decisions'], ['deny'])
        with self.assertRaisesRegex(tasks.ToolError, 'incomplete/truncated'):
            self.decide(pending)
        self.assertFalse(self.log.exists())
        self.decide(pending, 'deny')

    def test_file_edit_outside_scope_or_changed_symlink_is_not_accepted(self):
        pending = self.menu(edit=True)
        self.record['owned_paths'] = ['other.txt']
        with self.assertRaisesRegex(tasks.ToolError, 'outside owned'):
            self.decide(pending)
        self.record['owned_paths'] = ['existing.txt']
        target = self.cwd / 'existing.txt'
        target.unlink()
        target.symlink_to(self.root / 'outside.txt')
        with self.assertRaisesRegex(tasks.ToolError, 'outside owned'):
            self.decide(pending)
        self.assertFalse(self.log.exists())

    def test_file_edit_different_patch_after_submit_is_new_approval(self):
        pending = self.menu(edit=True)
        screen = approvals.Tmux(self.record['socket']).capture(self.record['pane'])
        self.decide(pending)
        self.assertEqual(approvals.observe_approval(self.record, screen)['approval_id'], pending['approval_id'])
        other = approvals.observe_approval(self.record, screen.replace('updated', 'different'))
        self.assertNotEqual(other['approval_id'], pending['approval_id'])
        self.assertEqual(other['status'], 'waiting')

    def test_file_edit_changed_screen_and_unknown_menu_send_nothing(self):
        pending = self.menu(edit=True)
        screen = approvals.Tmux(self.record['socket']).capture(self.record['pane'])
        with patch.object(approvals.Tmux, 'capture', return_value=screen.replace('updated', 'different')):
            with self.assertRaisesRegex(tasks.ToolError, 'screen changed'):
                self.decide(pending)
        for candidate in (screen + '\n> explain this example\n',
                          screen.replace('2. No, reject this change', '2. Always accept'),
                          screen.replace('Pending edit', 'Example edit'),
                          screen.replace('> 1.', '  1.')):
            self.assertIsNone(approvals.file_edit_dialog('agy', candidate))
        self.assertIsNone(approvals.file_edit_dialog('cursor', screen))
        self.assertFalse(self.log.exists())

    def test_current_control_file_edits_allowed_but_old_archives_refused(self):
        for name in ('ready.json', 'ready.json.tmp', 'result.json', 'question.json.tmp'):
            approvals.check_edit_scope(self.record, str(self.run / name))
        for name in ('task.json', 'prompt.txt', 'reply-1.md', 'result.round0.json', 'terminal-events.json'):
            with self.assertRaises(tasks.ToolError):
                approvals.check_edit_scope(self.record, str(self.run / name))

    def test_external_symlink_alias_to_owned_file_is_not_an_owned_edit(self):
        self.record['owned_paths'] = ['existing.txt']
        alias = self.root / 'external-alias.txt'
        alias.symlink_to(self.cwd / 'existing.txt')
        with self.assertRaisesRegex(tasks.ToolError, 'outside owned'):
            approvals.check_edit_scope(self.record, str(alias))

    def test_closing_retains_final_file_edit_screen(self):
        self.menu(edit=True)
        tasks.close(self.run, self.record, allow_active=True)
        event = tasks.read_json(self.run / 'terminal-events.json')[-1]
        self.assertEqual(event['reason'], 'close')
        self.assertIn('Accept this file edit?', event['screen'])

    def test_broken_diagnostics_do_not_disable_wait_or_exact_cleanup(self):
        self.menu(edit=True)
        path = self.run / 'terminal-events.json'
        path.write_text('{broken')
        result = wait_event(self.run, self.record, timeout_ms=500)
        self.assertEqual(result['reason'], 'approval')
        self.assertIn('terminal_event_diagnostic', result)
        result = tasks.close(self.run, self.record, allow_active=True)
        self.assertTrue(result['closed'])
        self.assertIn('terminal_event_diagnostic', result)
        self.assertEqual(path.read_text(), '{broken')

    def test_final_capture_failure_does_not_disable_exact_cleanup(self):
        self.menu(edit=True)
        with patch.object(tasks.Tmux, 'capture', side_effect=tasks.ToolError('transient capture failure')):
            result = tasks.close(self.run, self.record, allow_active=True)
        self.assertTrue(result['closed'])
        self.assertIn('closing screen unavailable', result['terminal_event_diagnostic'])
