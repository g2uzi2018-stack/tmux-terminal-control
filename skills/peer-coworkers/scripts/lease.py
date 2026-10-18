"""Short-retry locks and conservative, persistent workspace lease recovery."""
from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import socket
import stat
import time

from common import DeadlineReached, Tmux, ToolError
from config import root_directory
from records import read_json
import session


@contextmanager
def locked(directory, timeout=2.0):
    with (directory / '.lock').open('a') as stream:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(min(0.025, max(0, deadline - time.monotonic())))
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def workspace_registry(cwd):
    root = root_directory() / 'workspaces' / hashlib.sha256(cwd.encode('utf-8', 'surrogateescape')).hexdigest()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def session_gone(record, deadline=None):
    """Only confirmed sessions can be proven gone; unknown launches need manual recovery."""
    if not all(record.get(key) for key in ('socket', 'session', 'pane')):
        return None
    endpoint = session.socket_dir() / session.socket_name(record['socket'])
    try:
        info = endpoint.lstat()
    except FileNotFoundError:
        return True
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
        raise ToolError('session socket is not an owned socket; inspect manually')
    with socket.socket(socket.AF_UNIX) as client:
        remaining = deadline-time.monotonic() if deadline else .5
        if remaining <= 0:
            raise DeadlineReached()
        client.settimeout(min(.5, remaining))
        try:
            client.connect(str(endpoint))
        except FileNotFoundError:
            return True
        except ConnectionRefusedError:
            return True
        except OSError as exc:
            raise ToolError('cannot establish session liveness: ' + str(exc)) from exc
    try:
        names = Tmux(record['socket'], deadline).run('list-sessions', '-F', '#{session_name}').splitlines()
    except ToolError as exc:
        if str(exc).startswith('no server running on ') or str(exc) == 'no sessions':
            return True
        raise
    return record['session'] not in names


def prune_dead(record):
    if record.get('socket'):
        endpoint = session.socket_dir() / session.socket_name(record['socket'])
        if endpoint.exists():
            try:
                return session.prune(type('Args', (), {'socket': record['socket']})())
            except ToolError as exc:
                # A live socket may contain another exact session. Never remove it.
                if 'still accepting connections' not in str(exc):
                    raise
    return None


def inspect_lease(path):
    try:
        lease = read_json(path, 16384)
        record = read_json(Path(lease['run']) / 'task.json')
        if record['task_id'] != lease['task_id'] or lease['task_id'] != path.stem:
            raise ToolError('workspace registry identity mismatch')
        required = ('task_id', 'attempt_id', 'cwd', 'state', 'role', 'closed', 'version')
        if (any(key not in record for key in required) or not isinstance(record['cwd'], str)
                or not Path(record['cwd']).is_absolute() or type(record['closed']) is not bool
                or record['role'] not in ('implement', 'test', 'research', 'review')):
            raise ToolError('damaged task metadata; exact forced reap required')
        gone = session_gone(record)
        status = 'gone' if gone is True else 'active' if gone is False else 'unknown'
        return dict(path=str(path), task_id=lease['task_id'], status=status), record
    except (OSError, ValueError, KeyError, TypeError, ToolError) as exc:
        return dict(path=str(path), task_id=path.stem, status='unknown', error=str(exc)), None


def reap(task=None, force=False):
    if force and not task:
        raise ToolError('--force requires an exact --task ID')
    reports = []
    for directory in sorted((root_directory() / 'workspaces').glob('*')):
        if not directory.is_dir():
            continue
        with locked(directory):
            for path in sorted(directory.glob('*.json')):
                if task and path.stem != task:
                    continue
                item, record = inspect_lease(path)
                remove = item['status'] == 'gone' or (force and task == path.stem and item['status'] == 'unknown')
                if remove:
                    if record and item['status'] == 'gone':
                        prune_dead(record)
                    path.unlink()
                item['removed'] = remove
                reports.append(item)
    return dict(leases=reports)
