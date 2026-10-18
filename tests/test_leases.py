import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_cowork as fixtures
import tasks as cowork
import lease
import profiles


class LeaseTests(unittest.TestCase):
    setUp = fixtures.CoworkTests.setUp
    init = fixtures.CoworkTests.init
    start_fake = fixtures.CoworkTests.start_fake
    cleanup_session = fixtures.CoworkTests.cleanup_session

    def test_killed_server_close_releases_and_next_writer_starts(self):
        self.start_fake()
        path = Path(self.record['workspace_lease'])
        cowork.Tmux(self.record['socket']).run('kill-server')
        result = cowork.close(self.run, self.record)
        self.assertTrue(result['session_gone'])
        self.assertFalse(path.exists())
        prepared = self.init(role='implement', owned_path=['.'])
        run = Path(prepared['run'])
        self.start_fake(cowork.read_json(run / 'task.json'), run)

    def test_start_reclaims_only_confirmed_gone(self):
        self.start_fake()
        old = Path(self.record['workspace_lease'])
        cowork.Tmux(self.record['socket']).run('kill-server')
        prepared = self.init(role='implement', owned_path=['.'])
        run = Path(prepared['run'])
        record = cowork.read_json(run / 'task.json')
        self.start_fake(record, run)
        self.assertFalse(old.exists())
        cowork.close(self.run, self.record)

    def test_unknown_launch_requires_exact_force(self):
        registry = cowork.workspace_registry(self.record['cwd'])
        path = registry / (self.record['task_id'] + '.json')
        self.record.update(state='launch_uncertain', socket='ai-tui-missing')
        cowork.save(self.run, self.record)
        cowork.atomic_json(path, dict(run=str(self.run), task_id=self.record['task_id']))
        self.assertFalse(lease.reap()['leases'][0]['removed'])
        with self.assertRaises(cowork.ToolError):
            cowork.close(self.run, self.record)
        with patch.object(profiles, 'command', return_value=['/bin/sh']):
            prepared = self.init(role='implement', owned_path=['.'])
            run = Path(prepared['run'])
            with self.assertRaisesRegex(cowork.ToolError, 'unresolved'):
                cowork.start(run, cowork.read_json(run / 'task.json'))
        with self.assertRaises(cowork.ToolError):
            lease.reap(force=True)
        self.assertTrue(lease.reap(task=self.record['task_id'], force=True)['leases'][0]['removed'])

    def test_missing_record_is_not_stolen(self):
        registry = cowork.workspace_registry(self.record['cwd'])
        path = registry / 'missing.json'
        cowork.atomic_json(path, dict(run=str(self.root / 'missing'), task_id='missing'))
        with patch.object(profiles, 'command', return_value=['/bin/sh']):
            with self.assertRaisesRegex(cowork.ToolError, 'unresolved'):
                cowork.start(self.run, self.record)
        self.assertTrue(path.exists())
        self.assertEqual(lease.reap()['leases'][0]['status'], 'unknown')

    def test_active_mismatched_markers_refuse_close(self):
        self.start_fake()
        cowork.Tmux(self.record['socket']).run('set-option', '-t', 'cli', '@task', 'another-task')
        try:
            with self.assertRaises(cowork.ToolError):
                cowork.close(self.run, self.record, True)
            self.assertTrue(Path(self.record['workspace_lease']).exists())
        finally:
            cowork.Tmux(self.record['socket']).run('set-option', '-t', 'cli', '@task', self.record['task_id'])

    def test_lock_short_contention_is_retried(self):
        import threading
        registry = cowork.workspace_registry(self.record['cwd'])
        held = threading.Event()
        def contender():
            with lease.locked(registry):
                held.set()
                time.sleep(.1)
        thread = threading.Thread(target=contender)
        thread.start()
        held.wait(1)
        with lease.locked(registry):
            self.assertFalse(thread.is_alive())
        thread.join()

    def test_corrupt_metadata_with_missing_socket_is_not_auto_reaped(self):
        registry = cowork.workspace_registry(self.record['cwd'])
        path = registry / (self.record['task_id'] + '.json')
        cowork.atomic_json(path, dict(run=str(self.run), task_id=self.record['task_id']))
        cowork.atomic_json(self.run / 'task.json', dict(task_id=self.record['task_id'],
            socket='ai-tui-absent', session='cli', pane='%0'))
        self.assertEqual(lease.reap()['leases'][0]['status'], 'unknown')
        self.assertTrue(path.exists())

    def test_mismatched_lease_does_not_kill_session(self):
        self.start_fake()
        path = Path(self.record['workspace_lease'])
        original = cowork.read_json(path)
        try:
            cowork.atomic_json(path, dict(run=str(self.run), task_id='another-task'))
            with self.assertRaises(cowork.ToolError):
                cowork.close(self.run, self.record, True)
            cowork.check_session(self.record)
        finally:
            cowork.atomic_json(path, original)

    def test_empty_but_live_server_is_session_gone_without_pruning_live_socket(self):
        self.start_fake()
        tmux = cowork.Tmux(self.record['socket'])
        tmux.run('set-option', '-s', 'exit-empty', 'off')
        def finish_empty_server():
            try:
                tmux.run('kill-server')
            except cowork.ToolError:
                pass
            try:
                cowork.session.prune(SimpleNamespace(socket=self.record['socket']))
            except (cowork.ToolError, FileNotFoundError):
                pass
        self.addCleanup(finish_empty_server)
        tmux.run('kill-session', '-t', '=cli')
        result = cowork.close(self.run, self.record)
        self.assertTrue(result['session_gone'])
        self.assertFalse(Path(self.record['workspace_lease']).exists())
        with self.assertRaisesRegex(cowork.ToolError, 'still accepting connections'):
            cowork.session.prune(SimpleNamespace(socket=self.record['socket']))
