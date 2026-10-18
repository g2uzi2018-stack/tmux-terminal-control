from pathlib import Path
import time
import unittest
from unittest.mock import patch
import test_cowork as fixtures
import tasks as cowork
import interactions
import capabilities


class InteractionTests(unittest.TestCase):
    setUp = fixtures.CoworkTests.setUp
    init = fixtures.CoworkTests.init
    result = fixtures.CoworkTests.result
    write_result = fixtures.CoworkTests.write_result
    start_fake = fixtures.CoworkTests.start_fake
    cleanup_session = fixtures.CoworkTests.cleanup_session

    def running(self):
        self.start_fake()
        self.record['state'] = 'running'
        self.record['started_at'] = time.time()
        cowork.save(self.run, self.record)
        self.message = self.run / 'message.txt'
        self.message.write_text('Answer the outstanding question and check the result.')

    def wait_result(self):
        until = time.monotonic() + 2
        while not Path(self.record['result_path']).exists():
            if time.monotonic() > until:
                self.fail('peer did not write result')
            time.sleep(.01)

    def test_reply_round_archive_and_maximum_with_real_tmux(self):
        self.running()
        self.write_result()
        interactions.reply(self.run, self.record, self.message)
        self.assertEqual(self.record['round'], 1)
        self.assertTrue((self.run / 'result.round0.json').exists())
        self.wait_result()
        cowork.collect(self.run, self.record)
        interactions.reply(self.run, self.record, self.message)
        self.wait_result()
        self.assertEqual(self.record['round'], 2)
        with self.assertRaisesRegex(cowork.ToolError, 'max_replies'):
            interactions.reply(self.run, self.record, self.message)
        self.assertEqual((self.run / 'submits.txt').read_text(), '2')
        self.assertEqual((self.run / 'reply-1.md').stat().st_mode & 0o777, 0o600)

    def test_reply_submit_failure_cannot_resend(self):
        self.running()
        self.write_result()
        with patch.object(interactions, 'send_submit', side_effect=cowork.ToolError('failed')) as submit:
            with self.assertRaises(cowork.ToolError):
                interactions.reply(self.run, self.record, self.message)
            self.assertEqual(cowork.read_json(self.run / 'task.json')['state'], 'reply_uncertain')
            with self.assertRaises(cowork.ToolError):
                interactions.reply(self.run, self.record, self.message)
            self.assertEqual(submit.call_count, 1)
        with self.assertRaises(cowork.ToolError):
            cowork.validate_result(self.result(round=0), self.record)

    def test_key_failure_is_recorded_before_sending(self):
        self.running()
        with patch.object(cowork, 'check_session'), patch.object(interactions.Tmux, 'run', side_effect=cowork.ToolError('failed')):
            with self.assertRaises(cowork.ToolError):
                interactions.keys(self.run, self.record, ['Escape'])
        entry = cowork.read_json(self.run / 'task.json')['interventions'][-1]
        self.assertEqual(entry['status'], 'uncertain')
        self.assertEqual(entry['keys'], ['Escape'])
        with self.assertRaises(cowork.ToolError):
            interactions.keys(self.run, self.record, ['Enter'])

    def test_unsupported_cancel_cannot_send_anything(self):
        self.running()
        with patch.object(capabilities, 'comparison', return_value={'probe': None, 'version_matches': False}), \
                patch.object(interactions.Tmux, 'run') as send:
            with self.assertRaisesRegex(cowork.ToolError, 'unverified'):
                interactions.cancel(self.run, self.record)
            send.assert_not_called()
        self.assertEqual(self.record['state'], 'running')

    def test_supported_cancel_is_confirmed_and_idempotent(self):
        import sys
        import profiles
        from probe import STOPPED
        with patch.object(profiles, 'command', return_value=[sys.executable, str(fixtures.ROOT / 'tests/fake_probe.py')]):
            cowork.start(self.run, self.record)
        self.addCleanup(self.cleanup_session, self.record, self.run)
        end = time.monotonic() + 2
        while 'READY' not in cowork.Tmux(self.record['socket']).capture(self.record['pane']):
            self.assertLess(time.monotonic(), end)
            time.sleep(.01)
        self.record['state'] = 'running'
        with patch.object(capabilities, 'cancellation', return_value=dict(key='Escape', stopped_pattern=STOPPED)):
            value = interactions.cancel(self.run, self.record, 1500)
            self.assertEqual(value['state'], 'cancelled')
            self.assertTrue(value['sent'])
            self.assertFalse(interactions.cancel(self.run, self.record)['sent'])
        self.assertEqual(len(self.record['interventions']), 1)

    def test_cancel_uncertain_resume_does_not_send_escape_twice(self):
        from probe import STOPPED
        self.running()
        original = interactions.Tmux.run
        sends = []
        def tracked(tmux, *args, **kwargs):
            if args[0] == 'send-keys' and args[-1] == 'Escape':
                sends.append(args)
            return original(tmux, *args, **kwargs)
        with patch.object(capabilities, 'cancellation', return_value=dict(key='Escape', stopped_pattern=STOPPED)), \
                patch.object(interactions.Tmux, 'run', tracked):
            self.assertEqual(interactions.cancel(self.run, self.record, 180)['state'], 'cancelling')
            self.assertFalse(interactions.cancel(self.run, self.record, 180)['sent'])
        self.assertEqual(len(sends), 1)

    def test_question_is_archived_when_reply_advances_round(self):
        self.running()
        self.record['state'] = 'awaiting_reply'
        cowork.atomic_json(self.run / 'question.json', dict(task_id=self.record['task_id'],
            attempt_id=self.record['attempt_id'], round=0, QUESTION='Choose?', OPTIONS=['A', 'B'], BLOCKING=True))
        interactions.reply(self.run, self.record, self.message)
        self.assertTrue((self.run / 'question.round0.json').exists())
        self.assertFalse((self.run / 'question.json').exists())
        self.assertEqual(self.record['round'], 1)

    def test_question_cannot_rearm_single_attempt_cancellation(self):
        from observation import wait_event
        from probe import STOPPED
        self.running()
        cowork.atomic_json(self.run / 'question.json', dict(task_id=self.record['task_id'],
            attempt_id=self.record['attempt_id'], round=0, QUESTION='Choose?', OPTIONS=['A', 'B'], BLOCKING=True))
        original = interactions.Tmux.run
        sends = []
        def tracked(tmux, *args, **kwargs):
            if args[0] == 'send-keys' and args[-1] == 'Escape':
                sends.append(args)
            return original(tmux, *args, **kwargs)
        with patch.object(capabilities, 'cancellation', return_value=dict(key='Escape', stopped_pattern=STOPPED)), \
                patch.object(interactions.Tmux, 'run', tracked):
            self.assertEqual(interactions.cancel(self.run, self.record, 180)['state'], 'cancelling')
            self.assertEqual(wait_event(self.run, self.record, 300)['reason'], 'question')
            self.assertEqual(self.record['state'], 'cancelling')
            self.record = cowork.read_json(self.run / 'task.json')
            # Even an independently changed state cannot clear delivery evidence.
            self.record['state'] = 'awaiting_reply'
            cowork.save(self.run, self.record)
            self.assertFalse(interactions.cancel(self.run, self.record, 180)['sent'])
        self.assertEqual(len(sends), 1)
