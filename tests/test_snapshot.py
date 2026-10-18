import json
import os
from pathlib import Path
import socket
import subprocess
import time
import unittest
from unittest.mock import patch
import test_cowork as fixtures
import tasks as cowork
import snapshot


class SnapshotTests(unittest.TestCase):
    setUp = fixtures.CoworkTests.setUp
    init = fixtures.CoworkTests.init
    result = fixtures.CoworkTests.result
    write_result = fixtures.CoworkTests.write_result

    def git(self, *args, cwd=None):
        return subprocess.run(['git', '-C', str(cwd or self.cwd), *args], check=True,
                              capture_output=True)

    def commit_fixture(self, cwd):
        self.git('add', '.', cwd=cwd)
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                 'commit', '-qm', 'fixture', cwd=cwd)

    def test_submodule_init_collect_accept_and_dirty_digest(self):
        source = self.root / 'module'
        source.mkdir()
        self.git('init', '-q', cwd=source)
        (source / 'file').write_text('one')
        self.commit_fixture(source)
        self.git('-c', 'protocol.file.allow=always', 'submodule', 'add', str(source), 'sub')
        self.commit_fixture(self.cwd)
        prepared = self.init(role='implement', owned_path=['sub'])
        self.run = Path(prepared['run'])
        self.record = cowork.read_json(self.run / 'task.json')
        before = self.record['baseline']['files']['sub']
        self.assertEqual(before[0], 0o160000)
        (self.cwd / 'sub/file').write_text('two')
        self.write_result()
        self.assertEqual(cowork.collect(self.run, self.record)['scope']['changed_paths'], ['sub'])
        cowork.accept(self.run, self.record, 'checked opaque dirty digest')
        self.assertNotEqual(before, self.record['collected_snapshot']['files']['sub'])

    def test_non_utf8_path_survives_persistence_and_scope_check(self):
        name = os.fsdecode(b'odd-\xff')
        (self.cwd / name).write_bytes(b'before')
        prepared = self.init(role='implement', owned_path=['.'])
        self.run = Path(prepared['run'])
        self.record = cowork.read_json(self.run / 'task.json')
        (self.cwd / name).write_bytes(b'after')
        self.write_result()
        self.assertEqual(cowork.collect(self.run, self.record)['scope']['changed_paths'], [name])
        cowork.accept(self.run, self.record, 'non UTF-8 roundtrip')

    def test_fifo_and_socket_never_read(self):
        os.mkfifo(self.cwd / 'fifo')
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(self.cwd / 'socket'))
            value = snapshot.snapshot(self.cwd)
        self.assertEqual(value['files']['fifo'][1], 'special')
        self.assertEqual(value['files']['socket'][1], 'special')

    def test_stat_cache_reuses_only_unchanged_content(self):
        first = snapshot.snapshot(self.cwd)
        with patch.object(Path, 'open', side_effect=AssertionError('unchanged files must not be read')):
            cached = snapshot.snapshot(self.cwd, previous=first)
        self.assertEqual(cached, first)
        (self.cwd / 'existing.txt').write_text('new data')
        second = snapshot.snapshot(self.cwd, previous=first)
        self.assertNotEqual(first['files'], second['files'])

    def test_configurable_limits_report_adjustment(self):
        with self.assertRaisesRegex(cowork.ToolError, 'snapshot.max_bytes'):
            snapshot.snapshot(self.cwd, limits={'max_bytes': 1})
        with self.assertRaisesRegex(cowork.ToolError, 'snapshot.max_files'):
            snapshot.snapshot(self.cwd, limits={'max_files': 0})

    def test_large_snapshot_benchmark_and_cache(self):
        for index in range(1500):
            (self.cwd / ('file-' + str(index))).write_text('content')
        start = time.monotonic()
        first = snapshot.snapshot(self.cwd)
        full = time.monotonic() - start
        start = time.monotonic()
        second = snapshot.snapshot(self.cwd, previous=first)
        cached = time.monotonic() - start
        self.assertEqual(first, second)
        print('snapshot benchmark 1501 files: full=%.4fs cached=%.4fs' % (full, cached))

    def test_large_task_remains_readable_after_collect_and_accept(self):
        for index in range(10000):
            (self.cwd / ('empty-%05d.txt' % index)).touch()
        prepared = self.init()
        self.run = Path(prepared['run'])
        self.record = cowork.read_json(self.run / 'task.json')
        self.write_result()
        cowork.collect(self.run, self.record)
        self.assertGreater((self.run / 'task.json').stat().st_size, 4 * 1024 * 1024)
        self.record = cowork.read_json(self.run / 'task.json')
        cowork.accept(self.run, self.record, 'large task reloaded and snapshot verified')
        self.assertEqual(cowork.read_json(self.run / 'task.json')['state'], 'accepted')

    def test_record_limit_rejects_write_without_stranding_previous_record(self):
        path = self.run / 'task.json'
        previous = cowork.read_json(path)
        config_path = Path(os.environ['PEER_CONFIG'])
        settings = json.loads(config_path.read_text())
        limit = path.stat().st_size + 32
        settings['snapshot'] = {'max_record_bytes': limit}
        config_path.write_text(json.dumps(settings))
        self.record['goal'] += 'x' * 1000
        with self.assertRaisesRegex(cowork.ToolError, 'snapshot.max_record_bytes'):
            cowork.save(self.run, self.record)
        self.assertEqual(cowork.read_json(path), previous)
        settings['snapshot']['max_record_bytes'] = limit + 2000
        config_path.write_text(json.dumps(settings))
        cowork.save(self.run, self.record)
        self.assertEqual(cowork.read_json(path)['goal'], self.record['goal'])
