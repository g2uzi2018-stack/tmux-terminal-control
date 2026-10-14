import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from support import PYTHON, ROOT, TmuxCase

class SessionTests(TmuxCase):
    def create(self, *args, cwd=None, task='task', env=None):
        result = self.script('session.py', 'new', '--socket', self.socket,
                             '--task', task, '--cwd', str(cwd or self.temp.name),
                             '--height', '24', '--width', '90', *args,
                             '--', PYTHON, str(ROOT / 'tests' / 'fake_tui.py'), '--log', str(self.log), env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        info = json.loads(result.stdout)
        self.pane = info['pane']
        self.until(lambda: any(e['event'] == 'ready' for e in self.events()))
        return info

    def cleanup_script(self, *args, task='task', session='cli'):
        return self.script('session.py', 'cleanup', '--socket', self.socket,
                           '--session', session, '--task', task, *args)

    def test_creation_history_remain_and_metadata(self):
        info = self.create('--history-limit', '777')
        self.assertEqual(info['socket'], self.socket)
        self.assertEqual(info['owner'], 'tmux-tui/v1')
        self.assertEqual(self.tmux('display-message', '-p', '-t', self.pane, '#{history_limit}').stdout.strip(), b'777')
        self.assertEqual(self.tmux('show-options', '-pqv', '-t', self.pane, 'remain-on-exit').stdout.strip(), b'on')
        for key, value in (('@task', 'task'), ('@cwd', self.temp.name), ('@owner', 'tmux-tui/v1')):
            self.assertEqual(self.tmux('show-options', '-qv', '-t', 'cli', key).stdout.decode().strip(), value)
        expected = self.tmux('show-options', '-gqv', 'default-terminal').stdout.decode().strip()
        self.assertEqual(self.events()[0]['term'], expected)

    def test_history_limit_change_after_creation_does_not_apply(self):
        self.create('--history-limit', '777')
        self.tmux('set-option', '-g', 'history-limit', '999')
        self.assertEqual(self.tmux('display-message', '-p', '-t', self.pane, '#{history_limit}').stdout.strip(), b'777')

    def test_existing_socket_cannot_be_reused_or_respawned(self):
        self.create()
        result = self.script('session.py', 'new', '--socket', self.socket,
                             '--task', 'other', '--cwd', self.temp.name, '--', PYTHON, '--version')
        self.assertEqual(result.returncode, 1)
        self.assertIn(b'already exists', result.stderr)
        self.assertEqual(self.tmux('display-message', '-p', '-t', self.pane, '#{pane_dead}').stdout.strip(), b'0')

    def test_list_reports_owned_task_and_unknown_session(self):
        self.create()
        self.tmux('new-session', '-d', '-s', 'unrelated', '/bin/sh')
        result = self.script('session.py', 'list')
        self.assertEqual(result.returncode, 0, result.stderr)
        items = [item for item in json.loads(result.stdout) if item['socket'] == self.socket]
        self.assertEqual(len(items), 2)
        owned = next(item for item in items if item['session'] == 'cli')
        self.assertTrue(owned['owned'])
        self.assertEqual(owned['task'], 'task')
        self.assertEqual(owned['panes'][0]['pane'], self.pane)
        self.assertFalse(next(item for item in items if item['session'] == 'unrelated')['owned'])

    def test_cleanup_refuses_unmarked_session_even_with_prefix(self):
        self.start()
        self.assertEqual(self.cleanup_script('--allow-active').returncode, 1)
        self.assertEqual(self.tmux('has-session', '-t', '=cli').returncode, 0)

    def test_cleanup_refuses_mismatched_task(self):
        self.create()
        self.assertEqual(self.cleanup_script('--allow-active', task='other').returncode, 1)
        self.assertEqual(self.tmux('has-session', '-t', '=cli').returncode, 0)

    def test_cleanup_preserves_active_without_explicit_flag(self):
        self.create()
        result = self.cleanup_script()
        self.assertEqual(result.returncode, 1)
        self.assertIn(b'active session retained', result.stderr)
        self.assertEqual(self.tmux('has-session', '-t', '=cli').returncode, 0)

    def test_cleanup_exact_target_does_not_kill_other_session(self):
        self.create()
        self.tmux('new-session', '-d', '-s', 'cli-extra', '/bin/sh')
        result = self.cleanup_script('--allow-active')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['cleaned'])
        self.assertEqual(self.tmux('has-session', '-t', '=cli-extra').returncode, 0)
        self.assertNotEqual(self.tmux('has-session', '-t', '=cli', check=False).returncode, 0)

    def test_cleanup_of_exited_owned_session(self):
        self.create()
        self.input_script('paste', input=b'/exit')
        self.until(lambda: self.pasted() == b'/exit')
        self.input_script('submit', '--received-confirmed')
        self.until(lambda: self.tmux('display-message', '-p', '-t', self.pane, '#{pane_dead}').stdout.strip() == b'1')
        self.assertEqual(self.cleanup_script().returncode, 0)
        self.assertNotEqual(self.tmux('has-session', check=False).returncode, 0)

    def test_cwd_and_task_ending_semicolon_are_literal(self):
        cwd = Path(self.temp.name) / 'working space;'
        cwd.mkdir()
        info = self.create(cwd=cwd, task='literal;')
        self.assertEqual(info['cwd'], str(cwd))
        self.assertEqual(self.tmux('show-options', '-qv', '-t', 'cli', '@task').stdout.decode().rstrip(), 'literal;')
        self.assertEqual(self.cleanup_script('--allow-active', task='literal;').returncode, 0)

    def test_no_arguments_executable_with_spaces_is_not_shell_text(self):
        executable = Path(self.temp.name) / 'a program;'
        executable.write_text('#!' + PYTHON + '\nfrom pathlib import Path\nPath(' + repr(str(self.log)) + ').write_text("executed")\n')
        executable.chmod(0o700)
        result = self.script('session.py', 'new', '--socket', self.socket, '--task', 'task',
                             '--cwd', self.temp.name, '--', str(executable))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.pane = json.loads(result.stdout)['pane']
        self.until(lambda: self.log.exists())
        self.assertEqual(self.log.read_text(), 'executed')

    def test_list_uses_custom_tmux_tmpdir(self):
        env = dict(os.environ, TMUX_TMPDIR=self.temp.name)
        self.addCleanup(lambda: subprocess.run(['tmux', '-L', self.socket, 'kill-server'], env=env,
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        self.create(env=env)
        result = self.script('session.py', 'list', env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(item['socket'] == self.socket and item['owned'] for item in json.loads(result.stdout)))

    def test_invalid_program_does_not_create_server(self):
        result = self.script('session.py', 'new', '--socket', self.socket, '--task', 'task',
                             '--cwd', self.temp.name, '--', '/not/installed/cli')
        self.assertEqual(result.returncode, 1)
        self.assertNotEqual(self.tmux('has-session', check=False).returncode, 0)

    def test_failed_target_startup_keeps_diagnostics_and_exit_status(self):
        executable = Path(self.temp.name) / 'unstartable'
        executable.write_text('#!/missing/interpreter\n')
        executable.chmod(0o700)
        result = self.script('session.py', 'new', '--socket', self.socket, '--task', 'task',
                             '--cwd', self.temp.name, '--', str(executable))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.pane = json.loads(result.stdout)['pane']
        self.until(lambda: self.tmux('display-message', '-p', '-t', self.pane, '#{pane_dead}').stdout.strip() == b'1')
        self.assertIn(b'FileNotFoundError', self.tmux('capture-pane', '-p', '-t', self.pane).stdout)
        self.assertEqual(self.tmux('display-message', '-p', '-t', self.pane, '#{pane_dead_status}').stdout.strip(), b'1')
        self.assertEqual(self.cleanup_script().returncode, 0)

    def test_fixture_cleanup_removes_its_exact_socket_endpoint(self):
        self.start()
        endpoint = Path(os.environ.get('TMUX_TMPDIR') or '/tmp') / ('tmux-' + str(os.getuid())) / self.socket
        self.assertTrue(endpoint.exists())
        self.destroy()
        self.assertFalse(endpoint.exists())
