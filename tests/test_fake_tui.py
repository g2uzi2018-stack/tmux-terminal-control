import base64
import time
from support import TmuxCase


class FakeTuiTests(TmuxCase):
    def test_bracketed_paste_logs_exact_bytes_and_separate_submit(self):
        self.start()
        text = '中文\n\n-$HOME;\n'.encode()
        self.direct_paste(text)
        self.until(lambda: bool(self.pasted()))
        self.assertEqual(self.pasted(), text)
        self.assertEqual(self.submits(), [])
        self.assertEqual(self.raw(), b'\x1b[200~' + text + b'\x1b[201~')
        self.tmux('send-keys', '-t', self.pane, 'Enter')
        self.until(lambda: len(self.submits()) == 1)
        self.assertEqual(base64.b64decode(self.submits()[0]['text_b64']), text)
        expected_term = self.tmux('show-option', '-gqv', 'default-terminal').stdout.decode().strip()
        self.assertEqual(self.events()[0]['term'], expected_term)

    def test_disabled_paste_exposes_early_submission(self):
        self.start('--bracketed-paste', 'off')
        self.direct_paste(b'first\nsecond\n')
        self.until(lambda: len(self.submits()) == 2)
        self.assertEqual(self.raw(), b'first\nsecond\n')

    def test_delayed_receiver_does_not_record_submission_before_enter(self):
        self.start('--receive-delay-ms', '250')
        self.direct_paste(b'pending')
        time.sleep(0.06)
        self.assertEqual(self.raw(), b'')
        self.assertEqual(self.submits(), [])
        self.until(lambda: self.pasted() == b'pending')
        self.assertEqual(self.submits(), [])

    def test_exit_command_preserves_exit_status(self):
        self.start('--exit-code', '7')
        self.direct_paste(b'/exit')
        self.until(lambda: self.pasted() == b'/exit')
        self.tmux('send-keys', '-t', self.pane, 'Enter')
        self.until(lambda: any(e['event'] == 'exit' for e in self.events()))
        self.until(lambda: self.tmux('display-message', '-p', '-t', self.pane,
                                    '#{pane_dead}|#{pane_dead_status}').stdout.strip() == b'1|7')
