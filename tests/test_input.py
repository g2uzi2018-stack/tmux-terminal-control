import base64
import time
from support import TmuxCase

class InputTests(TmuxCase):
    def assert_transfer(self, text):
        self.start()
        data = text.encode()
        flags = ['--multiline-verified', 'fake_tui/v1 raw input, paste on'] if '\n' in text or '\r' in text else []
        result = self.input_script('paste', *flags, input=data)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.until(lambda: self.pasted() == data)
        self.assertEqual(self.raw(), b'\x1b[200~' + data + b'\x1b[201~')
        self.assertEqual(self.submits(), [])
        self.assertEqual(result.stdout, ('reason=pasted bytes=' + str(len(data)) + '\n').encode())
        self.assertEqual(self.tmux('list-buffers').stdout, b'')

    def test_unknown_multiline_rejected_before_any_bytes_or_buffers(self):
        self.start()
        p = self.input_script('paste', input=b'first\nsecond')
        self.assertEqual(p.returncode, 1)
        self.assertIn(b'multiline rejected', p.stderr)
        time.sleep(0.03)
        self.assertEqual(self.raw(), b'')
        self.assertEqual(self.submits(), [])
        self.assertEqual(self.tmux('list-buffers').stdout, b'')

    def test_disabled_multiline_rejected_before_sending(self):
        self.start('--bracketed-paste', 'off')
        self.assertEqual(self.input_script('paste', input=b'first\nsecond\n').returncode, 1)
        self.assertEqual(self.raw(), b'')
        self.assertEqual(self.submits(), [])

    def test_single_line_works_with_paste_disabled(self):
        self.start('--bracketed-paste', 'off')
        p = self.input_script('paste', input=b'-plain;')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.until(lambda: self.raw() == b'-plain;')
        self.assertEqual(self.submits(), [])

    def test_delayed_receive_does_not_submit_and_confirmation_is_required(self):
        self.start('--receive-delay-ms', '300')
        self.assertEqual(self.input_script('paste', input=b'delayed').returncode, 0)
        self.assertEqual(self.submits(), [])
        self.assertEqual(self.input_script('submit').returncode, 2)
        self.assertEqual(self.submits(), [])
        self.until(lambda: self.pasted() == b'delayed')
        self.assertEqual(self.input_script('submit', '--received-confirmed').returncode, 0)
        self.until(lambda: len(self.submits()) == 1)
        self.assertEqual(base64.b64decode(self.submits()[0]['text_b64']), b'delayed')

    def test_unconfirmed_target_submission_is_not_repeated(self):
        self.start('--ignore-submit')
        self.input_script('paste', input=b'once')
        self.until(lambda: self.pasted() == b'once')
        self.assertEqual(self.input_script('submit', '--received-confirmed').returncode, 0)
        self.until(lambda: len(self.submits()) == 1)
        time.sleep(0.08)
        self.assertEqual(len(self.submits()), 1)

    def test_keys_are_not_text_or_enter(self):
        self.start()
        for key in ('Enter', 'C-j', 'C-m', '-danger', 'hello;', 'literal text'):
            self.assertEqual(self.input_script('keys', '--key', key).returncode, 2)
        self.assertEqual(self.raw(), b'')
        self.assertEqual(self.input_script('keys', '--key', 'Escape').returncode, 0)
        self.until(lambda: self.raw() == b'\x1b')

    def test_invalid_utf8_rejected(self):
        self.start()
        self.assertEqual(self.input_script('paste', input=b'\xff').returncode, 1)
        self.assertEqual(self.raw(), b'')

    def test_missing_pane_is_error(self):
        self.start()
        p = self.script('input.py', 'paste', '--socket', self.socket, '--pane', '%999', input=b'x')
        self.assertEqual(p.returncode, 1)
        self.assertEqual(self.raw(), b'')

    def test_tmux_35a_has_no_paste_format_query(self):
        self.start()
        self.assertEqual(self.tmux('display-message', '-p', '-t', self.pane,
                                  '#{bracket_paste_flag}').stdout, b'\n')

    def test_send_keys_trailing_semicolon_regression(self):
        self.start('--bracketed-paste', 'off')
        self.tmux('send-keys', '-l', '-t', self.pane, 'literal;')
        self.until(lambda: self.raw() == b'literal')

    def test_send_keys_double_dash_does_not_save_semicolon(self):
        self.start('--bracketed-paste', 'off')
        self.tmux('send-keys', '-l', '-t', self.pane, '--', 'literal;')
        self.until(lambda: self.raw() == b'literal')

    def test_send_keys_leading_dash_is_option_regression(self):
        self.start('--bracketed-paste', 'off')
        self.assertNotEqual(self.tmux('send-keys', '-l', '-t', self.pane, '--not-a-key', check=False).returncode, 0)
        self.assertEqual(self.raw(), b'')

CASES = {
    'trailing_semicolon': 'literal;',
    'leading_dash': '-not-an-option;',
    'dollars': '$HOME $' + '{VALUE} $(printf unsafe);',
    'backticks': 'literal ' + chr(96) + 'uname' + chr(96) + ' and backslash \\;',
    'chinese': '你好，原样传输；',
    'blank_lines': 'first\n\nthird',
    'trailing_newline': 'first\n',
    'carriage_return': 'first\rsecond',
    'long_input': '中文-$HOME;' * 2000,
}
for label, value in CASES.items():
    def test(self, text=value):
        self.assert_transfer(text)
    setattr(InputTests, 'test_verbatim_' + label, test)
