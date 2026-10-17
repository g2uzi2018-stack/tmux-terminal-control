import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills' / 'peer-coworkers' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import cowork
import profiles


class CoworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='peer-coworkers-tests-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        environment = patch.dict(os.environ, {'XDG_STATE_HOME': str(self.root / 'state')})
        environment.start()
        self.addCleanup(environment.stop)
        self.cwd = self.root / 'project'
        self.cwd.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.cwd)], check=True)
        (self.cwd / 'existing.txt').write_text('initial\n')
        self.runs = self.root / 'runs'
        self.prepared = self.init()
        self.run = Path(self.prepared['run'])
        self.record = cowork.read_json(self.run / 'task.json')

    def init(self, **changes):
        args = dict(cwd=str(self.cwd), goal='bounded test', role='research', profile='codex',
                    owned_path=[], acceptance=['observable result'], budget_seconds=60,
                    enable_opencode=False, runs_dir=str(self.runs))
        args.update(changes)
        return cowork.prepare(SimpleNamespace(**args))

    def result(self, **changes):
        value = dict(task_id=self.record['task_id'], attempt_id=self.record['attempt_id'],
                     handoff=dict(STATUS='DONE', RESULT=['done'], EVIDENCE=['evidence'],
                                  VALIDATION=[], REMAINING_WORK=[], RISKS=[]))
        value.update(changes)
        return value

    def write_result(self, value=None):
        (self.run / 'result.json').write_text(json.dumps(value or self.result()))
        self.record['state'] = 'running'

    def test_identity_and_private_files(self):
        second = self.init()
        self.assertNotEqual(second['task_id'], self.record['task_id'])
        self.assertEqual(self.run.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.run / 'task.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.run / 'prompt.txt').stat().st_mode & 0o777, 0o600)

    def test_opencode_requires_explicit_opt_in(self):
        with self.assertRaisesRegex(cowork.ToolError, 'compatibility-only'):
            self.init(profile='opencode')
        with patch.object(profiles.shutil, 'which') as which:
            with self.assertRaisesRegex(cowork.ToolError, 'compatibility-only'):
                profiles.command('opencode')
            which.assert_not_called()

    def test_doctor_does_not_execute_opencode(self):
        with patch.object(profiles.shutil, 'which', side_effect=lambda name: '/fake/' + name), \
                patch.object(profiles.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='v1')) as run:
            profiles.doctor()
            self.assertEqual([call.args[0][0] for call in run.call_args_list],
                             ['/fake/codex', '/fake/agy', '/fake/cursor-agent'])

    def test_cursor_prefers_agent_cli_alias_over_editor(self):
        prepared = self.init(profile='cursor', model='auto')
        record = cowork.read_json(Path(prepared['run']) / 'task.json')
        with patch.object(profiles.shutil, 'which', side_effect=lambda name: '/fake/' + name) as which:
            command = profiles.command(record['profile'], model=record['model'])
        self.assertEqual(command, ['/fake/cursor-agent', '--sandbox', 'enabled', '--model', 'auto'])
        self.assertEqual([call.args[0] for call in which.call_args_list], ['cursor-agent'])

    def test_cursor_falls_back_to_current_agent_command(self):
        with patch.object(profiles.shutil, 'which',
                          side_effect=lambda name: '/fake/agent' if name == 'agent' else None) as which:
            self.assertEqual(profiles.command('cursor'), ['/fake/agent', '--sandbox', 'enabled'])
        self.assertEqual([call.args[0] for call in which.call_args_list], ['cursor-agent', 'agent'])

    def test_cursor_missing_cli_never_launches_editor(self):
        with patch.object(profiles.shutil, 'which', return_value=None) as which:
            with self.assertRaisesRegex(cowork.ToolError, 'cursor executable not found'):
                profiles.command('cursor')
        self.assertEqual([call.args[0] for call in which.call_args_list], ['cursor-agent', 'agent'])

    def test_explicit_model_is_bound_to_task_and_launch_argv(self):
        model = 'claude-sonnet-4-6'
        prepared = self.init(profile='agy', model=model)
        run = Path(prepared['run'])
        record = cowork.read_json(run / 'task.json')
        self.assertEqual(record['model'], model)
        self.assertIn(model, (run / 'prompt.txt').read_text())
        with patch.object(profiles.shutil, 'which', return_value='/fake/agy'):
            command = profiles.command(record['profile'], model=record['model'])
        self.assertEqual(command, ['/fake/agy', '--sandbox', '--model', model])

    def test_omitted_model_preserves_cli_default(self):
        self.assertIsNone(self.record['model'])
        with patch.object(profiles.shutil, 'which', return_value='/fake/agy'):
            self.assertEqual(profiles.command('agy'), ['/fake/agy', '--sandbox'])

    def test_invalid_model_rejected_before_creating_task(self):
        for model in ('', '--skip-permissions', 'claude sonnet', 'model\nname', 'x' * 201):
            with self.subTest(model=model), self.assertRaises(cowork.ToolError):
                self.init(profile='agy', model=model)

    def test_explicit_proxy_reaches_pane_and_parent_environment_is_restored(self):
        proxy = 'http://127.0.0.1:17890'
        before = dict(os.environ)
        with patch.object(profiles, 'command', return_value=[sys.executable, str(ROOT / 'tests/fake_peer.py'),
                                                           '--run', str(self.run)]):
            cowork.start(self.run, self.record, proxy_url=proxy)
        self.addCleanup(self.cleanup_session, self.record, self.run)
        self.assertEqual(dict(os.environ), before)
        pid = cowork.Tmux(self.record['socket']).run('display-message', '-p', '-t',
                                                    self.record['pane'], '#{pane_pid}').strip()
        environment = dict(item.split(b'=', 1) for item in Path('/proc', pid, 'environ').read_bytes().split(b'\0') if b'=' in item)
        for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
            self.assertEqual(environment[key.encode()], proxy.encode())
        self.assertIn(b'127.0.0.1', environment[b'NO_PROXY'])
        self.assertEqual(self.record['proxy_url'], proxy)

    def test_proxy_environment_restored_after_launch_failure(self):
        before = dict(os.environ)
        with self.assertRaises(RuntimeError):
            with cowork.launch_environment(profiles.proxy_environment('http://127.0.0.1:17890')):
                self.assertEqual(os.environ['HTTPS_PROXY'], 'http://127.0.0.1:17890')
                raise RuntimeError('simulated launch failure')
        self.assertEqual(dict(os.environ), before)

    def test_invalid_proxy_rejected_before_launch_or_state_change(self):
        for url in ('socks5://localhost:7890', 'http://user:secret@localhost:7890',
                    'http://localhost:99999', 'http://localhost:7890/path',
                    'http://localhost:7890?secret=x', 'http://localhost:7890\n', ''):
            with self.subTest(url=url), patch.object(cowork.session, 'new') as launch:
                with self.assertRaises((cowork.ToolError, ValueError)):
                    cowork.start(self.run, self.record, proxy_url=url)
                launch.assert_not_called()
                self.assertEqual(self.record['state'], 'prepared')

    def test_ownership_and_escape_rejected(self):
        for args in (dict(role='implement'), dict(owned_path=['existing.txt']),
                     dict(role='implement', owned_path=['../escape']),
                     dict(role='implement', owned_path=['.git/config'])):
            with self.subTest(args=args), self.assertRaises(cowork.ToolError):
                self.init(**args)
        (self.cwd / 'escape').symlink_to(self.root)
        with self.assertRaises(cowork.ToolError):
            self.init(role='implement', owned_path=['escape/result'])

    def test_invalid_handoffs_rejected(self):
        invalid = [self.result(attempt_id='old'), self.result(task_id='other'), self.result(extra='text')]
        for key, value in [('STATUS', 'SUCCESS'), ('RESULT', 'text'), ('RESULT', ['x'] * 13),
                           ('EVIDENCE', ['x' * 2001]), ('RISKS', [' ']), ('REMAINING_WORK', ['unfinished'])]:
            item = self.result()
            item['handoff'][key] = value
            invalid.append(item)
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(cowork.ToolError):
                cowork.validate_result(item, self.record)

    def test_partial_and_blocked_require_remaining_work(self):
        for status in ('PARTIAL', 'BLOCKED'):
            value = self.result()
            value['handoff']['STATUS'] = status
            with self.assertRaises(cowork.ToolError):
                cowork.validate_result(value, self.record)
            value['handoff']['REMAINING_WORK'] = ['concrete missing step']
            self.assertEqual(cowork.validate_result(value, self.record), value)

    def test_byte_limits_and_duplicate_keys(self):
        path = self.run / 'bad.json'
        path.write_text('{"task_id":"first","task_id":"second"}')
        with self.assertRaises(cowork.ToolError):
            cowork.read_json(path)
        path.write_bytes(b'x' * 16385)
        with self.assertRaises(cowork.ToolError):
            cowork.read_json(path, 16384)
        value = self.result()
        value['handoff']['RESULT'] = ['\u4e2d' * 1000] * 3
        with self.assertRaisesRegex(cowork.ToolError, '8 KiB'):
            cowork.validate_result(value, self.record)

    def test_result_symlink_and_fifo_rejected_without_blocking(self):
        target = self.run / 'target.json'
        target.write_text('{}')
        link = self.run / 'link.json'
        link.symlink_to(target)
        with self.assertRaises(OSError):
            cowork.read_json(link)
        fifo = self.run / 'pipe'
        os.mkfifo(fifo)
        with self.assertRaises(cowork.ToolError):
            cowork.read_json(fifo)

    def test_collect_does_not_accept_and_accept_rechecks(self):
        self.write_result()
        self.assertEqual(cowork.collect(self.run, self.record)['state'], 'awaiting_acceptance')
        with self.assertRaises(cowork.ToolError):
            cowork.accept(self.run, self.record, ' ')
        value = self.result()
        value['handoff']['RESULT'] = ['changed after collection']
        self.write_result(value)
        self.record['state'] = 'awaiting_acceptance'
        with self.assertRaisesRegex(cowork.ToolError, 'changed since collection'):
            cowork.accept(self.run, self.record, 'independent check')

    def test_dirty_file_same_status_scope_drift_detected(self):
        (self.cwd / 'existing.txt').write_text('changed without changing git status\n')
        self.write_result()
        with self.assertRaisesRegex(cowork.ToolError, 'scope check failed'):
            cowork.collect(self.run, self.record)

    def test_owned_change_can_be_collected_but_accept_rechecks_artifact(self):
        prepared = self.init(role='implement', owned_path=['existing.txt'])
        self.run = Path(prepared['run'])
        self.record = cowork.read_json(self.run / 'task.json')
        (self.cwd / 'existing.txt').write_text('implementation')
        self.write_result()
        collected = cowork.collect(self.run, self.record)
        self.assertEqual(collected['scope']['changed_paths'], ['existing.txt'])
        (self.cwd / 'existing.txt').write_text('another change')
        with self.assertRaisesRegex(cowork.ToolError, 'changed since collection'):
            cowork.accept(self.run, self.record, 'test passed')

    def test_index_change_rejected_even_inside_owned_paths(self):
        prepared = self.init(role='implement', owned_path=['.'])
        self.run = Path(prepared['run'])
        self.record = cowork.read_json(self.run / 'task.json')
        subprocess.run(['git', '-C', str(self.cwd), 'add', 'existing.txt'], check=True)
        self.write_result()
        with self.assertRaisesRegex(cowork.ToolError, 'git_state_changed'):
            cowork.collect(self.run, self.record)

    def test_git_status_metadata_refresh_is_not_staging(self):
        subprocess.run(['git', '-C', str(self.cwd), 'add', 'existing.txt'], check=True)
        subprocess.run(['git', '-C', str(self.cwd), '-c', 'user.name=Test', '-c', 'user.email=test@localhost',
                        'commit', '-qm', 'fixture'], check=True)
        prepared = self.init()
        self.run = Path(prepared['run'])
        self.record = cowork.read_json(self.run / 'task.json')
        path = self.cwd / 'existing.txt'
        info = path.stat()
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns - 2000000000))
        subprocess.run(['git', '-C', str(self.cwd), 'status', '--porcelain'],
                       check=True, capture_output=True)
        self.write_result()
        self.assertEqual(cowork.collect(self.run, self.record)['state'], 'awaiting_acceptance')

    def test_budget_and_unconfirmed_submit_have_no_side_effects(self):
        self.record['state'] = 'pasted'
        self.record['started_at'] = time.time() - 100
        with patch.object(cowork, 'run_script') as invoke:
            with self.assertRaises(cowork.ToolError):
                cowork.observe(self.run, self.record, submit=True)
            with self.assertRaises(cowork.ToolError):
                cowork.observe(self.run, self.record, submit=True, confirmed=True)
            invoke.assert_not_called()

    def test_submit_failure_is_never_retried(self):
        self.record.update(state='pasted', started_at=time.time(), socket='ai-tui-test', pane='%0')
        with patch.object(cowork, 'check_session'), patch.object(cowork, 'run_script',
                return_value=SimpleNamespace(returncode=1, stderr=b'failed')) as invoke:
            with self.assertRaises(cowork.ToolError):
                cowork.observe(self.run, self.record, submit=True, confirmed=True)
            self.assertEqual(cowork.read_json(self.run / 'task.json')['state'], 'submit_uncertain')
            with self.assertRaises(cowork.ToolError):
                cowork.observe(self.run, self.record, submit=True, confirmed=True)
            self.assertEqual(invoke.call_count, 1)

    def start_fake(self, record=None, run=None):
        record, run = record or self.record, run or self.run
        with patch.object(profiles, 'command', return_value=[sys.executable, str(ROOT / 'tests/fake_peer.py'), '--run', str(run)]):
            cowork.start(run, record)
        self.addCleanup(self.cleanup_session, record, run)
        end = time.monotonic() + 3
        while 'READY' not in cowork.Tmux(record['socket']).capture(record['pane']):
            if time.monotonic() > end:
                self.fail('fake peer did not start')
            time.sleep(0.01)

    def cleanup_session(self, record, run):
        if not record['closed']:
            cowork.close(run, record, allow_active=True)
        try:
            cowork.session.prune(SimpleNamespace(socket=record['socket']))
        except (cowork.ToolError, FileNotFoundError):
            pass

    def test_real_tmux_single_submit_collect_accept_close(self):
        self.start_fake()
        cowork.paste(self.run, self.record)
        end = time.monotonic() + 2
        while 'RECEIVED' not in cowork.Tmux(self.record['socket']).capture(self.record['pane']):
            if time.monotonic() > end:
                self.fail('fake peer did not receive prompt')
            time.sleep(0.01)
        cowork.observe(self.run, self.record, submit=True, confirmed=True, timeout_ms=1200)
        with self.assertRaises(cowork.ToolError):
            cowork.observe(self.run, self.record, submit=True, confirmed=True)
        cowork.collect(self.run, self.record)
        self.assertEqual((self.run / 'submits.txt').read_text(), '1')
        self.assertEqual(cowork.accept(self.run, self.record, 'checked fake peer submit count')['state'], 'accepted')
        with self.assertRaisesRegex(cowork.ToolError, 'active session'):
            cowork.close(self.run, self.record)
        self.assertTrue(cowork.close(self.run, self.record, allow_active=True)['closed'])
        self.assertEqual(self.record['state'], 'accepted')

    def test_writer_conflict_with_live_reader(self):
        self.start_fake()
        prepared = self.init(role='implement', owned_path=['existing.txt'])
        run = Path(prepared['run'])
        record = cowork.read_json(run / 'task.json')
        with patch.object(profiles, 'command', return_value=['/bin/sh']), \
                self.assertRaisesRegex(cowork.ToolError, 'live writer/reader'):
            cowork.start(run, record)
        self.assertEqual(record['state'], 'prepared')

    def test_writer_conflict_across_different_run_directories(self):
        self.start_fake()
        prepared = self.init(role='implement', owned_path=['existing.txt'],
                             runs_dir=str(self.root / 'other-runs'))
        run = Path(prepared['run'])
        record = cowork.read_json(run / 'task.json')
        with patch.object(profiles, 'command', return_value=['/bin/sh']), \
                self.assertRaisesRegex(cowork.ToolError, 'live writer/reader'):
            cowork.start(run, record)
        self.assertEqual(record['state'], 'prepared')

    def test_close_lock_contention_preserves_live_session_and_is_retryable(self):
        self.start_fake()
        lease = Path(self.record['workspace_lease'])
        with cowork.locked(lease.parent):
            with self.assertRaises(BlockingIOError):
                cowork.close(self.run, self.record, allow_active=True)
            self.assertFalse(self.record['closed'])
            self.assertTrue(lease.exists())
            cowork.check_session(self.record)
        cowork.close(self.run, self.record, allow_active=True)
        self.assertFalse(lease.exists())

    def test_close_retries_lease_release_after_unlink_failure(self):
        self.start_fake()
        lease = Path(self.record['workspace_lease'])
        with patch.object(Path, 'unlink', side_effect=PermissionError('simulated unlink failure')):
            with self.assertRaises(PermissionError):
                cowork.close(self.run, self.record, allow_active=True)
        self.assertTrue(self.record['closed'])
        self.assertTrue(lease.exists())
        cowork.close(self.run, self.record, allow_active=True)
        self.assertFalse(lease.exists())

    def test_ignored_file_exclusion_is_explicit_in_contract_and_result(self):
        self.assertIn('Git-ignored untracked files', self.record['scope_check_exclusions'])
        self.assertIn('scope_check_exclusions', (self.run / 'prompt.txt').read_text())
        self.write_result()
        result = cowork.collect(self.run, self.record)
        self.assertEqual(result['scope']['scope_check_exclusions'], self.record['scope_check_exclusions'])

    def test_detached_head_snapshot_supported(self):
        subprocess.run(['git', '-C', str(self.cwd), 'add', 'existing.txt'], check=True)
        subprocess.run(['git', '-C', str(self.cwd), '-c', 'user.name=Test', '-c', 'user.email=test@localhost',
                        'commit', '-qm', 'fixture'], check=True)
        subprocess.run(['git', '-C', str(self.cwd), 'checkout', '--detach', '-q'], check=True)
        self.assertEqual(cowork.snapshot(self.cwd)['branch'], '')


class InstallTests(unittest.TestCase):
    def test_standalone_install_and_recoverable_update(self):
        spec = importlib.util.spec_from_file_location('peer_installer', ROOT / 'scripts/install-skill.py')
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        with tempfile.TemporaryDirectory(prefix='peer-install-test-') as temp:
            dest = Path(temp) / 'peer-coworkers'
            installer.install(dest)
            self.assertFalse(any(path.is_symlink() for path in dest.rglob('*')))
            process = subprocess.run([sys.executable, str(dest / 'scripts/cowork.py'), '--help'], capture_output=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            (dest / 'user-extra.txt').write_text('preserve in backup')
            _, backup = installer.install(dest)
            self.assertEqual((backup / 'user-extra.txt').read_text(), 'preserve in backup')
