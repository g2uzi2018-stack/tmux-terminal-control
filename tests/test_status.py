"""Reaping status can arrive after a tmux pane's PTY closes."""
from unittest.mock import patch
import unittest
from support import SCRIPTS, TmuxCase
import sys
sys.path.insert(0, str(SCRIPTS))
from common import Tmux


class ReaperTests(unittest.TestCase):
    def test_dead_before_waitpid_is_retried(self):
        with patch.object(Tmux, '_notify_reaper', return_value=False), \
                patch.object(Tmux, 'run', side_effect=['%0|1||0', '%0|1|7|0']) as run:
            self.assertEqual(Tmux('ai-tui-test').status('%0'), (True, '7'))
            self.assertEqual(run.call_count, 2)

    def test_signal_exit_does_not_wait_for_numeric_code(self):
        with patch.object(Tmux, 'run', return_value='%0|1||15') as run:
            self.assertEqual(Tmux('ai-tui-test').status('%0'), (True, ''))
            self.assertEqual(run.call_count, 1)

    def test_reaper_notification_never_targets_a_generic_socket(self):
        with patch.object(Tmux, 'run') as query, patch('common.os.kill') as signal:
            self.assertFalse(Tmux('default')._notify_reaper('%0'))
            query.assert_not_called()
            signal.assert_not_called()

    def test_reaper_notification_never_signals_a_live_child(self):
        import os
        with patch.object(Tmux, 'run', return_value=str(os.getppid()) + '|' + str(os.getpid())), \
                patch('common.os.kill') as signal:
            self.assertFalse(Tmux('ai-tui-test')._notify_reaper('%0'))
            signal.assert_not_called()


class RealReaperTests(TmuxCase):
    def test_repeated_real_child_exit_status(self):
        self.start()
        for _ in range(30):
            self.tmux('respawn-pane', '-k', '-t', self.pane, '/bin/sh', '-c', 'exit 7')
            tmux = Tmux(self.socket)
            self.until(lambda: tmux.status(self.pane)[0])
            self.assertEqual(tmux.status(self.pane), (True, '7'))

    def test_real_transient_reaper_format(self):
        import time
        self.start()
        samples = []
        for _ in range(60):
            self.tmux('respawn-pane', '-k', '-t', self.pane, '/bin/sh', '-c', 'exit 7')
            deadline = time.monotonic() + 1
            while True:
                raw = self.tmux('display-message', '-p', '-t', self.pane,
                                '#{pane_id}|#{pane_dead}|#{pane_dead_status}|#{pane_dead_signal}').stdout.decode().strip()
                fields = raw.split('|')
                if fields[1:3] == ['1', '7']:
                    break
                if fields[1] == '1' and not fields[2]:
                    samples.append(raw)
                    Tmux(self.socket).status(self.pane)
                self.assertLess(time.monotonic(), deadline, raw)
        print('actual transient reaper samples:', sorted(set(samples)))

    def test_repeated_failed_launch_keeps_actual_exit_status(self):
        import json
        from pathlib import Path
        import uuid
        executable = Path(self.temp.name) / 'unstartable'
        executable.write_text('#!/missing/interpreter\n')
        executable.chmod(0o700)
        for _ in range(20):
            self.socket = 'ai-tui-test-' + uuid.uuid4().hex
            result = self.script('session.py', 'new', '--socket', self.socket, '--task', 'failed-start',
                                 '--cwd', self.temp.name, '--', str(executable))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.pane = json.loads(result.stdout)['pane']
            tmux = Tmux(self.socket)
            self.until(lambda: tmux.status(self.pane) == (True, '1'))
            self.assertIn('FileNotFoundError', tmux.capture(self.pane))
            self.destroy()

    def test_direct_new_session_exit_status_without_respawn(self):
        import json
        from pathlib import Path
        import time
        import uuid
        from support import PYTHON

        samples = []
        for _ in range(40):
            self.socket = 'ai-tui-test-' + uuid.uuid4().hex
            tmux = Tmux(self.socket)
            # The target is launched directly. No placeholder process, respawn,
            # wait-for gate or inferred exit value participates in this test.
            self.pane = tmux.batch([
                ['-f', '/dev/null', 'start-server'],
                ['set-window-option', '-g', 'remain-on-exit', 'on'],
                ['new-session', '-d', '-P', '-F', '#{pane_id}', '-s', 'cli',
                 '-c', self.temp.name, PYTHON, '-c',
                 'import os; os.execv("/missing/peer-test-executable",["/missing/peer-test-executable"])'],
            ]).strip()
            query = '#{pane_pid}|#{pane_dead}|#{pane_dead_status}|#{pane_dead_signal}'
            deadline = time.monotonic() + .5
            while True:
                before = tmux.run('display-message', '-p', '-t', self.pane, query).strip()
                if before.split('|')[1:3] == ['1', '1'] or time.monotonic() >= deadline:
                    break
                time.sleep(.005)
            notified = []
            original = tmux._notify_reaper
            def notify(pane):
                result = original(pane)
                notified.append(result)
                return result
            with patch.object(tmux, '_notify_reaper', side_effect=notify):
                observed = tmux.status(self.pane)
            after = tmux.run('display-message', '-p', '-t', self.pane, query).strip()
            samples.append(dict(before=before, after=after, observed=observed,
                                re_notifications=sum(notified),
                                traceback='FileNotFoundError' in tmux.capture(self.pane)))
            self.assertEqual(observed, (True, '1'), samples[-1])
            self.assertEqual(after.split('|')[1:3], ['1', '1'], samples[-1])
            self.assertTrue(samples[-1]['traceback'])
            self.destroy()
        pending = sum(sample['before'].split('|')[1:3] == ['1', ''] for sample in samples)
        repaired = sum(sample['re_notifications'] for sample in samples)
        print('direct launch cases=40 native-pending=%d exact-server-notifications=%d native-exit-1=40' % (pending, repaired))
