import json
import os
from pathlib import Path
import threading
import time
from unittest.mock import patch
from support import TmuxCase
import tasks as cowork
from observation import wait_event
from records import atomic_json
from results import validate_question


class EventTests(TmuxCase):
    def setUp(self):
        super().setUp()
        self.run = Path(self.temp.name)
        config = self.run / 'config.json'
        config.write_text(json.dumps({'profiles': {'codex': {
            'approval_patterns': [r'^APPROVAL: allow action\?$'], 'prompt_lines': 8}}}))
        environment = patch.dict(os.environ, {'PEER_CONFIG': str(config)})
        environment.start()
        self.addCleanup(environment.stop)
        self.record = dict(task_id='test', attempt_id='attempt', round=0, profile='codex',
                           state='running', result_path=str(self.run / 'result.json'))

    def prepare(self, mode):
        self.start('--mode', mode, '--exit-code', '7')
        self.record.update(socket=self.socket, pane=self.pane)
        self.tmux('send-keys', '-t', self.pane, 'Enter')
        self.until(lambda: len(self.submits()) == 1)

    def wait(self, **kwargs):
        return wait_event(self.run, self.record, timeout_ms=400, still_ms=100,
                          poll_ms=15, stable_ms=70, **kwargs)

    def result(self):
        return dict(task_id='test', attempt_id='attempt', round=0,
                    handoff=dict(STATUS='DONE', RESULT=[], EVIDENCE=[], VALIDATION=[], REMAINING_WORK=[], RISKS=[]))

    def test_approval_in_configured_prompt_region(self):
        self.prepare('approval')
        self.assertEqual(self.wait()['reason'], 'approval')
        self.assertEqual(len(self.submits()), 1)

    def test_still_is_attention_and_busy_is_timeout(self):
        self.prepare('still')
        self.assertEqual(self.wait()['reason'], 'attention')
        self.tmux('respawn-pane', '-k', '-t', self.pane, '/bin/sh', '-c', 'printf "BUSY: working"; sleep 2')
        self.assertEqual(self.wait()['reason'], 'timeout')

    def test_exit_returns_real_status(self):
        self.prepare('exit')
        value = self.wait()
        self.assertEqual((value['reason'], value['exit_code']), ('exited', '7'), value)

    def test_half_json_not_ready_and_stable_current_result_is_ready(self):
        self.prepare('busy')
        path = Path(self.record['result_path'])
        path.write_text('{"task_id":')
        self.assertEqual(self.wait()['reason'], 'timeout')
        atomic_json(path, self.result())
        start = time.monotonic()
        self.assertEqual(self.wait()['reason'], 'result_ready')
        self.assertGreaterEqual(time.monotonic() - start, .07)
        self.assertEqual(len(self.submits()), 1)

    def test_stale_round_and_duplicate_json_cannot_signal_completion(self):
        self.prepare('busy')
        value = self.result()
        value['round'] = 1
        atomic_json(Path(self.record['result_path']), value)
        self.assertEqual(self.wait()['reason'], 'timeout')
        Path(self.record['result_path']).write_text('{"round":0,"round":0}')
        self.assertEqual(self.wait()['reason'], 'timeout')

    def test_question_binding_and_symlink_rejection(self):
        self.prepare('busy')
        value = dict(task_id='test', attempt_id='attempt', round=0,
                     QUESTION='Which interface?', OPTIONS=['A', 'B'], BLOCKING=True)
        atomic_json(self.run / 'question.json', value)
        self.assertEqual(self.wait()['reason'], 'question')
        self.assertEqual(self.record['state'], 'awaiting_reply')
        for changes in ({'round': True}, {'round': 1}, {'BLOCKING': 'yes'}, {'extra': 1}):
            with self.assertRaises(cowork.ToolError):
                validate_question(dict(value, **changes), self.record)
        (self.run / 'question.json').unlink()
        atomic_json(self.run / 'other.json', value)
        (self.run / 'question.json').symlink_to(self.run / 'other.json')
        self.assertEqual(self.wait()['reason'], 'timeout')

    def test_valid_result_takes_priority_over_leftover_question(self):
        self.prepare('busy')
        atomic_json(Path(self.record['result_path']), self.result())
        atomic_json(self.run / 'question.json', dict(task_id='test', attempt_id='attempt', round=0,
            QUESTION='Already answered?', OPTIONS=[], BLOCKING=False))
        self.assertEqual(self.wait()['reason'], 'result_ready')

    def test_result_can_be_read_after_confirmed_session_disappearance(self):
        self.prepare('busy')
        self.tmux('kill-server')
        atomic_json(Path(self.record['result_path']), self.result())
        self.assertEqual(wait_event(self.run, self.record, timeout_ms=400, stable_ms=60,
                                   session_missing=True)['reason'], 'result_ready')
