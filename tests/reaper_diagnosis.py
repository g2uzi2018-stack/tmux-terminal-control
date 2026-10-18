"""Explicit bounded reproduction of startup/respawn reaping, not a CLI compatibility test."""
import json
from pathlib import Path
import time
import uuid
from support import ROOT, SCRIPTS, TmuxCase
import sys
sys.path.insert(0, str(SCRIPTS))


class StartupReaping(TmuxCase):
    def test_startup_reaping(self):
        executable = Path(self.temp.name) / 'unstartable'
        executable.write_text('#!/missing/interpreter\n')
        executable.chmod(0o700)
        samples = []
        for _ in range(80):
            self.socket = 'ai-tui-test-' + uuid.uuid4().hex
            result = self.script('session.py', 'new', '--socket', self.socket, '--task', 'diagnose',
                                 '--cwd', self.temp.name, '--', str(executable))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.pane = json.loads(result.stdout)['pane']
            deadline = time.monotonic() + .4
            seen = []
            while time.monotonic() < deadline:
                value = self.tmux('display-message', '-p', '-t', self.pane,
                                  '#{pane_pid}|#{pane_dead}|#{pane_dead_status}|#{pane_dead_signal}').stdout.decode().strip()
                if not seen or seen[-1] != value:
                    seen.append(value)
                if value.split('|')[1:3] == ['1', '1']:
                    break
                time.sleep(.005)
            from common import Tmux
            repaired = Tmux(self.socket).status(self.pane)
            native = self.tmux('display-message', '-p', '-t', self.pane,
                               '#{pane_pid}|#{pane_dead}|#{pane_dead_status}|#{pane_dead_signal}').stdout.decode().strip()
            if seen[-1] != native:
                seen.append(native)
            screen = self.tmux('capture-pane', '-p', '-t', self.pane).stdout.decode('utf-8', 'replace')
            pid=seen[-1].split('|')[0]
            proc=Path('/proc',pid)
            try:
                process_info=(proc/'status').read_text()
                command=(proc/'cmdline').read_bytes().decode('utf-8','replace')
            except FileNotFoundError:
                process_info,command='gone','gone'
            samples.append(dict(states=seen, traceback='FileNotFoundError' in screen, process=process_info,command=command))
            self.destroy()
        (ROOT / 'docs/local/reaper-diagnosis.json').write_text(json.dumps(samples, indent=2) + '\n')
        bad = [s for s in samples if s['states'][-1].split('|')[1:3] != ['1', '1'] or not s['traceback']]
        print('startup reaping anomalies:', json.dumps(bad))
        self.assertEqual(bad, [])
