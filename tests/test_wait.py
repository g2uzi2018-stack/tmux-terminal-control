import base64
import re
import subprocess
import threading
import time
from support import PYTHON, SCRIPTS, TmuxCase

class WaitTests(TmuxCase):
    def prepare(self, *args):
        self.start(*args)
        result = self.input_script('paste', input=b'one round')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.until(lambda: self.pasted() == b'one round')

    def assert_result(self, result, reason, changed=None):
        lines = result.stdout.decode().splitlines()
        self.assertTrue(lines, result.stderr)
        self.assertRegex(lines[0], r'^reason=(prompt|still|exited|timeout|error) elapsed_ms=[0-9]+ changed=[01]( match=[A-Za-z0-9_-]+| exit_code=-?[0-9]+)?$')
        self.assertTrue(lines[0].startswith('reason=' + reason + ' '), result.stdout)
        self.assertEqual(result.returncode, {'timeout': 3, 'error': 1}.get(reason, 0), result.stderr)
        if changed is not None:
            self.assertIn('changed=' + str(changed), lines[0])
        self.assertLessEqual(len(lines[1:]), 24)
        return lines[0]

    def test_unchanged_after_submit_never_returns_still(self):
        self.prepare('--mode', 'unchanged')
        self.assert_result(self.wait_script(), 'timeout', 0)
        self.assertEqual(len(self.submits()), 1)

    def test_changed_then_quiet_returns_still(self):
        self.prepare('--mode', 'still')
        result = self.wait_script()
        self.assert_result(result, 'still', 1)
        self.assertEqual(result.stdout.decode().split('\n', 1)[1], self.tmux('capture-pane', '-p', '-t', self.pane).stdout.decode())

    def test_animation_without_events_returns_timeout(self):
        self.prepare('--mode', 'animation')
        self.assert_result(self.wait_script(), 'timeout', 1)

    def test_new_approval_prompt_returns_match(self):
        self.prepare('--mode', 'approval')
        first = self.assert_result(self.wait_script('submit-and-wait', '--prompt', 'approval=^APPROVAL: .+$'), 'prompt', 1)
        self.assertIn('match=approval', first)

    def test_real_exit_has_code_and_last_screen(self):
        self.prepare('--mode', 'exit', '--exit-code', '7')
        result = self.wait_script()
        self.assertIn('exit_code=7', self.assert_result(result, 'exited', 1))
        self.assertIn(b'EXIT', result.stdout)

    def test_static_busy_is_not_quiet_candidate(self):
        self.prepare('--mode', 'busy')
        self.assert_result(self.wait_script('submit-and-wait', '--busy-regex', '^BUSY'), 'timeout', 1)

    def test_old_prompt_residual_is_excluded(self):
        self.prepare('--mode', 'stale', '--initial-prompt', 'APPROVAL: old request')
        result = self.wait_script('submit-and-wait', '--prompt', 'approval=^APPROVAL: .+$')
        self.assert_result(result, 'still', 1)
        self.assertNotIn(b'match=approval', result.stdout.split(b'\n')[0])

    def test_body_prompt_outside_region_does_not_match(self):
        self.prepare('--mode', 'body')
        self.assert_result(self.wait_script('submit-and-wait', '--prompt-lines', '4', '--prompt', 'approval=^APPROVAL: .+$'), 'still', 1)

    def test_quoted_prompt_in_region_does_not_match_anchored_regex(self):
        self.prepare('--mode', 'quote')
        self.assert_result(self.wait_script('submit-and-wait', '--prompt', 'approval=^APPROVAL: .+$'), 'still', 1)

    def test_resume_preserves_baseline_and_observed_change(self):
        self.prepare('--mode', 'still')
        first = self.wait_script(timeout_ms=70)
        self.assert_result(first, 'timeout', 1)
        baseline = self.tmux('show-options', '-pqv', '-t', self.pane, '@aitui_baseline').stdout
        self.assertEqual(self.tmux('show-options', '-pqv', '-t', self.pane, '@aitui_changed').stdout.strip(), b'1')
        result = self.wait_script('resume')
        self.assert_result(result, 'still', 1)
        self.assertEqual(self.tmux('show-options', '-pqv', '-t', self.pane, '@aitui_baseline').stdout, baseline)
        self.assertEqual(len(self.submits()), 1)
        self.assertNotEqual(base64.b64decode(baseline), result.stdout.split(b'\n', 1)[1])

    def test_resume_detects_change_that_arrives_after_first_timeout(self):
        self.prepare('--mode', 'approval', '--response-delay-ms', '200')
        self.assert_result(self.wait_script(timeout_ms=70), 'timeout', 0)
        result = self.wait_script('resume', '--prompt', 'approval=^APPROVAL: .+$')
        self.assert_result(result, 'prompt', 1)
        self.assertEqual(len(self.submits()), 1)

    def test_resume_without_round_is_error(self):
        self.start()
        self.assert_result(self.wait_script('resume'), 'error', 0)
        self.assertEqual(self.submits(), [])

    def test_begin_does_not_submit(self):
        self.start()
        self.assert_result(self.wait_script('begin', timeout_ms=50), 'timeout', 0)
        self.assertEqual(self.submits(), [])

    def test_no_screen_outputs_only_header_within_shell_timeout(self):
        self.prepare('--mode', 'unchanged')
        started = time.monotonic()
        result = self.wait_script('submit-and-wait', '--no-screen', timeout_ms=100)
        self.assert_result(result, 'timeout', 0)
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertLess(time.monotonic() - started, 0.6)

    def test_invalid_limits_or_regex_error_before_submission(self):
        self.prepare()
        for options in (['--timeout-ms', '1900'], ['--timeout-ms', '0'], ['--prompt', 'approval=['], ['--poll-ms', '0']):
            self.assert_result(self.wait_script('submit-and-wait', *options), 'error', 0)
        self.assertEqual(self.submits(), [])

    def test_no_receipt_confirmation_is_error_before_submission(self):
        self.prepare()
        result = self.script('wait.py', 'submit-and-wait', '--socket', self.socket, '--pane', self.pane,
                             '--timeout-ms', '100', '--shell-timeout-ms', '2000')
        self.assert_result(result, 'error', 0)
        self.assertEqual(self.submits(), [])

    def test_missing_pane_is_error_not_exited(self):
        self.start()
        result = self.script('wait.py', 'begin', '--socket', self.socket, '--pane', '%999',
                             '--timeout-ms', '100', '--shell-timeout-ms', '2000')
        self.assert_result(result, 'error', 0)

    def test_socket_disappears_during_wait_is_error(self):
        self.prepare('--mode', 'unchanged')
        timer = threading.Timer(0.1, lambda: self.tmux('kill-server', check=False))
        timer.start()
        try:
            self.assert_result(self.wait_script(timeout_ms=500), 'error')
        finally:
            timer.join()

    def test_live_pane_capture_failure_is_error(self):
        import os
        import shutil
        from pathlib import Path
        self.prepare()
        shim = Path(self.temp.name) / 'tmux'
        shim.write_text('#!' + PYTHON + '\nimport os, sys\nif "capture-pane" in sys.argv:\n    sys.exit(23)\nos.execv(' + repr(shutil.which('tmux')) + ', [' + repr(shutil.which('tmux')) + '] + sys.argv[1:])\n')
        shim.chmod(0o700)
        env = dict(os.environ, PATH=self.temp.name + ':' + os.environ['PATH'])
        self.assert_result(self.wait_script('begin', env=env), 'error', 0)
        self.assertEqual(self.tmux('display-message', '-p', '-t', self.pane, '#{pane_dead}').stdout.strip(), b'0')

    def test_hung_capture_is_bounded_and_reported_as_error(self):
        import os
        import shutil
        from pathlib import Path
        self.prepare()
        shim = Path(self.temp.name) / 'tmux'
        shim.write_text('#!' + PYTHON + '\nimport os, sys, time\nif "capture-pane" in sys.argv:\n    time.sleep(5)\nos.execv(' + repr(shutil.which('tmux')) + ', [' + repr(shutil.which('tmux')) + '] + sys.argv[1:])\n')
        shim.chmod(0o700)
        env = dict(os.environ, PATH=self.temp.name + ':' + os.environ['PATH'])
        started = time.monotonic()
        self.assert_result(self.wait_script('begin', timeout_ms=80, env=env), 'error', 0)
        self.assertLess(time.monotonic() - started, 0.6)

    def test_resumed_old_prompt_still_excluded(self):
        self.prepare('--mode', 'stale', '--initial-prompt', 'APPROVAL: old request')
        self.assert_result(self.wait_script('submit-and-wait', '--prompt', 'approval=^APPROVAL: .+$', timeout_ms=70), 'timeout', 1)
        self.assert_result(self.wait_script('resume', '--prompt', 'approval=^APPROVAL: .+$'), 'still', 1)
        self.assertEqual(len(self.submits()), 1)

    def test_pathological_regex_cannot_exceed_wait_budget(self):
        self.start('--initial-prompt', 'a' * 70)
        started = time.monotonic()
        result = self.wait_script('begin', '--busy-regex', '(a+)+b', timeout_ms=100)
        self.assert_result(result, 'timeout', 0)
        self.assertLess(time.monotonic() - started, 0.6)
        self.assertEqual(self.submits(), [])

    def test_observed_change_survives_regex_timeout_then_resume(self):
        self.prepare('--mode', 'stale', '--initial-prompt', 'a' * 70)
        first = self.wait_script('submit-and-wait', '--busy-regex', '(a+)+b', timeout_ms=120)
        self.assert_result(first, 'timeout', 1)
        self.assertEqual(self.tmux('show-options', '-pqv', '-t', self.pane, '@aitui_changed').stdout.strip(), b'1')
        self.assert_result(self.wait_script('resume'), 'still', 1)
        self.assertEqual(len(self.submits()), 1)

    def test_new_ready_prompt_uses_configured_label(self):
        self.prepare('--mode', 'still')
        result = self.wait_script('submit-and-wait', '--prompt', 'ready=^WAITING$')
        self.assertIn('match=ready', self.assert_result(result, 'prompt', 1))

    def test_pane_disappears_while_socket_remains_is_error(self):
        self.prepare('--mode', 'unchanged')
        self.tmux('new-session', '-d', '-s', 'keep-server', '/bin/sh')
        timer = threading.Timer(0.1, lambda: self.tmux('kill-pane', '-t', self.pane, check=False))
        timer.start()
        try:
            self.assert_result(self.wait_script(timeout_ms=500), 'error')
            self.assertEqual(self.tmux('has-session', '-t', '=keep-server').returncode, 0)
        finally:
            timer.join()

    def test_corrupt_round_state_is_error_without_submit(self):
        self.start()
        self.tmux('set-option', '-p', '-t', self.pane, '@aitui_baseline', 'not base64!')
        self.assert_result(self.wait_script('resume'), 'error', 0)
        self.assertEqual(self.submits(), [])
