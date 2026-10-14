import base64
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills' / 'tmux-tui' / 'scripts'
PYTHON = shutil.which('python3')


class TmuxCase(unittest.TestCase):
    def setUp(self):
        if not shutil.which('tmux') or not PYTHON:
            self.fail('tmux and python3 are required; missing dependencies are failures')
        self.temp = tempfile.TemporaryDirectory(prefix='tmux-tui-tests-')
        self.addCleanup(self.temp.cleanup)
        self.socket = 'ai-tui-test-' + uuid.uuid4().hex
        self.addCleanup(self.destroy)
        self.log = Path(self.temp.name) / 'input.jsonl'
        self.pane = None

    def tmux(self, *args, input=None, check=True):
        result = subprocess.run(['tmux', '-L', self.socket, *args], input=input,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
        if check and result.returncode:
            self.fail(result.stderr.decode('utf-8', 'replace'))
        return result

    def start(self, *args):
        result = self.tmux('-f', '/dev/null', 'start-server', ';', 'set-option', '-g',
                           'history-limit', '50000', ';', 'new-session', '-d', '-P',
                           '-F', '#{pane_id}', '-s', 'cli', '-x', '90', '-y', '24', '/bin/sh')
        self.pane = result.stdout.decode().strip()
        self.tmux('set-option', '-p', '-t', self.pane, 'remain-on-exit', 'on')
        self.tmux('respawn-pane', '-k', '-t', self.pane, PYTHON,
                  str(ROOT / 'tests' / 'fake_tui.py'), '--log', str(self.log), *args)
        self.until(lambda: any(e['event'] == 'ready' for e in self.events()))
        return self.pane

    def destroy(self):
        # Always scoped to this test's unique socket, never the default server.
        self.tmux('kill-server', check=False)
        endpoint = Path(os.environ.get('TMUX_TMPDIR') or '/tmp') / ('tmux-' + str(os.getuid())) / self.socket
        try:
            info = endpoint.lstat()
            if stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid():
                # This exact UUID endpoint was created by this test, not found by prefix.
                if self.tmux('has-session', check=False).returncode != 0:
                    if endpoint.lstat().st_ino == info.st_ino:
                        endpoint.unlink()
        except FileNotFoundError:
            pass

    def events(self):
        if not self.log.exists():
            return []
        content = self.log.read_text()
        lines = content.splitlines()
        if not content.endswith('\n'):
            lines = lines[:-1]
        return [json.loads(line) for line in lines if line]

    def until(self, predicate, timeout=2):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if predicate():
                return
            time.sleep(0.01)
        self.fail('timed out waiting for test evidence')

    def raw(self):
        return b''.join(base64.b64decode(e['data_b64']) for e in self.events() if e['event'] == 'raw')

    def pasted(self):
        return b''.join(base64.b64decode(e['text_b64']) for e in self.events() if e['event'] == 'paste')

    def submits(self):
        return [e for e in self.events() if e['event'] == 'submit']

    def direct_paste(self, data, flags=('-p', '-r', '-d')):
        name = 'test-' + uuid.uuid4().hex
        self.tmux('load-buffer', '-b', name, '-', input=data)
        self.tmux('paste-buffer', *flags, '-b', name, '-t', self.pane)

    def script(self, name, *args, input=None, timeout=4, env=None):
        return subprocess.run([PYTHON, str(SCRIPTS / name), *args], input=input,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, env=env)

    def input_script(self, mode, *args, input=None):
        return self.script('input.py', mode, '--socket', self.socket, '--pane', self.pane,
                           *args, input=input)

    def wait_script(self, mode='submit-and-wait', *args, timeout_ms=350, **kwargs):
        confirmed = ['--received-confirmed'] if mode == 'submit-and-wait' else []
        return self.script('wait.py', mode, '--socket', self.socket, '--pane', self.pane,
                           '--timeout-ms', str(timeout_ms), '--shell-timeout-ms', '2000',
                           '--poll-ms', '15', '--still-ms', '100', *confirmed, *args, **kwargs)
