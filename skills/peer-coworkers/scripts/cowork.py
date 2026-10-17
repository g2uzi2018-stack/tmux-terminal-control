#!/usr/bin/env python3
"""Bound work packages to tmux sessions; validate handoffs before primary acceptance."""
import argparse
from contextlib import contextmanager, nullcontext
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import uuid

from common import Tmux, ToolError
import profiles
import session

SCRIPTS = Path(__file__).resolve().parent
FIELDS = {'STATUS', 'RESULT', 'EVIDENCE', 'VALIDATION', 'REMAINING_WORK', 'RISKS'}
TERMINAL = {'accepted', 'partial', 'blocked', 'failed', 'cancelled'}


def nonblank(value, label):
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise ToolError(label + ' must be nonblank text')
    return value


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ToolError('duplicate JSON field: ' + key)
        result[key] = value
    return result


def read_json(path, limit=4 * 1024 * 1024):
    # O_NOFOLLOW prevents accidental result/record symlink traversal on Linux/WSL.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ToolError('JSON must be a bounded regular file')
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ToolError('JSON exceeds byte limit')
    return json.loads(data.decode('utf-8'), object_pairs_hook=no_duplicates)


def atomic_json(path, value):
    fd, temporary = tempfile.mkstemp(prefix='.write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def locked(directory):
    with (directory / '.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def git(cwd, *args):
    process = subprocess.run(['git', '-C', str(cwd), *args], capture_output=True, timeout=10)
    if process.returncode:
        raise ToolError('Git query failed: ' + process.stderr.decode('utf-8', 'replace').strip())
    return process.stdout


def snapshot(cwd):
    """Detect ordinary scope drift, including same-status edits; not a security sandbox."""
    paths = set(git(cwd, 'ls-files', '-z', '--cached', '--others', '--exclude-standard').split(b'\0')) - {b''}
    if len(paths) > 10000:
        raise ToolError('workspace exceeds 10000 files; use a smaller worktree')
    files, total = {}, 0
    for raw in sorted(paths):
        name = raw.decode('utf-8', 'strict')
        path = cwd / name
        if not path.exists() and not path.is_symlink():
            continue
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            data = os.fsencode(os.readlink(path))
        elif stat.S_ISREG(info.st_mode):
            total += info.st_size
            if total > 64 * 1024 * 1024:
                raise ToolError('workspace exceeds 64 MiB; use a smaller worktree')
            data = path.read_bytes()
        else:
            raise ToolError('unsupported workspace entry: ' + name)
        files[name] = [info.st_mode, hashlib.sha256(data).hexdigest()]
    head = subprocess.run(['git', '-C', str(cwd), 'rev-parse', '--verify', 'HEAD'],
                          capture_output=True, timeout=5)
    branch = subprocess.run(['git', '-C', str(cwd), 'symbolic-ref', '--quiet', 'HEAD'],
                            capture_output=True, timeout=5)
    if branch.returncode not in (0, 1):
        raise ToolError('Git branch query failed')
    return dict(files=files, head=head.stdout.decode().strip(),
                branch=branch.stdout.decode().strip(),
                # Compare staged entries, not mutable index stat caches refreshed by git status.
                index=hashlib.sha256(git(cwd, 'ls-files', '--stage', '-z')).hexdigest())


def normalized_scope(cwd, value):
    nonblank(value, 'scope')
    path = Path(value)
    if path.is_absolute() or '..' in path.parts or '.git' in path.parts:
        raise ToolError('scope must be repository-relative without .. or .git')
    normalized = path.as_posix()
    try:
        (cwd / path).resolve().relative_to(cwd)
    except ValueError as exc:
        raise ToolError('scope escapes workspace through a symlink') from exc
    return normalized


def scope_report(record):
    current = snapshot(Path(record['cwd']))
    baseline = record['baseline']
    changed = sorted(path for path in baseline['files'].keys() | current['files'].keys()
                     if baseline['files'].get(path) != current['files'].get(path))
    owned = record['owned_paths']
    violations = [path for path in changed if not any(
        scope == '.' or path == scope or path.startswith(scope + '/') for scope in owned)]
    git_changed = any(baseline[field] != current[field] for field in ('head', 'branch', 'index'))
    return dict(changed_paths=changed, scope_violations=violations,
                git_state_changed=git_changed,
                scope_check_exclusions=record.get('scope_check_exclusions', [])), current


def validate_result(value, record):
    if not isinstance(value, dict) or set(value) != {'task_id', 'attempt_id', 'handoff'}:
        raise ToolError('result requires exactly task_id, attempt_id, handoff')
    if any(value[key] != record[key] for key in ('task_id', 'attempt_id')):
        raise ToolError('result belongs to another task or attempt')
    handoff = value['handoff']
    if not isinstance(handoff, dict) or set(handoff) != FIELDS:
        raise ToolError('handoff requires exactly the six documented fields')
    if handoff['STATUS'] not in ('DONE', 'PARTIAL', 'BLOCKED'):
        raise ToolError('invalid handoff STATUS')
    for key in FIELDS - {'STATUS'}:
        array = handoff[key]
        if not isinstance(array, list) or len(array) > 12 or any(
                not isinstance(item, str) or not item.strip() or len(item) > 2000 for item in array):
            raise ToolError(key + ' requires at most 12 nonblank strings of at most 2000 characters')
    if len(json.dumps(handoff, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) > 8192:
        raise ToolError('handoff exceeds 8 KiB')
    if (handoff['STATUS'] == 'DONE') != (not handoff['REMAINING_WORK']):
        raise ToolError('DONE requires no remaining work; PARTIAL/BLOCKED require remaining work')
    return value


def root_directory(value=None):
    root = Path(value) if value else Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'peer-coworkers'
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def workspace_registry(cwd):
    root = root_directory() / 'workspaces' / hashlib.sha256(cwd.encode('utf-8')).hexdigest()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def prepare(args):
    cwd = Path(args.cwd).resolve(strict=True)
    if not cwd.is_dir() or Path(os.fsdecode(git(cwd, 'rev-parse', '--show-toplevel')).strip()).resolve() != cwd:
        raise ToolError('cwd must be the Git worktree root')
    if args.profile == 'opencode' and not args.enable_opencode:
        raise ToolError('OpenCode is compatibility-only; explicit --enable-opencode is required')
    model = profiles.validate_model(getattr(args, 'model', None))
    if args.budget_seconds <= 0:
        raise ToolError('budget must be positive')
    owned = [normalized_scope(cwd, path) for path in args.owned_path]
    if args.role in ('review', 'research') and owned:
        raise ToolError('read-only roles cannot own write paths')
    if args.role in ('implement', 'test') and not owned:
        raise ToolError('write roles require --owned-path')
    for item in (args.goal, *args.acceptance):
        nonblank(item, 'goal/acceptance')
    baseline = snapshot(cwd)
    root = root_directory(args.runs_dir)
    try:
        root.relative_to(cwd)
    except ValueError:
        pass
    else:
        raise ToolError('runs directory must be outside the worktree')
    task_id, attempt_id = 'task-' + uuid.uuid4().hex, uuid.uuid4().hex
    run = root / task_id
    run.mkdir(mode=0o700)
    record = dict(version=1, task_id=task_id, attempt_id=attempt_id, goal=args.goal,
                  cwd=str(cwd), role=args.role, profile=args.profile, model=model, owned_paths=owned,
                  acceptance=args.acceptance, baseline=baseline, state='prepared',
                  budget_seconds=args.budget_seconds, created_at=time.time(),
                  scope_check_exclusions=['Git-ignored untracked files', 'paths outside the worktree'],
                  opencode_enabled=args.enable_opencode, closed=False,
                  result_path=str(run / 'result.json'))
    example = dict(task_id=task_id, attempt_id=attempt_id,
                   handoff=dict(STATUS='DONE', RESULT=[], EVIDENCE=[], VALIDATION=[], REMAINING_WORK=[], RISKS=[]))
    prompt = ('Complete this bounded work package. Do not delegate, commit, stage, change branches, '
              'or modify CLI permissions. Treat allowed paths as a work contract, not sandbox enforcement. '
              'Write only your owned paths and the result file; review/research roles may write only the result file. '
              'Report real validation, and use PARTIAL/BLOCKED with concrete REMAINING_WORK if unfinished. '
              'Each handoff array allows up to 12 nonblank strings of at most 2000 characters; '
              'the compact handoff must be at most 8 KiB. '
              'Scope checks exclude the categories listed in scope_check_exclusions; the primary must '
              'independently verify any relevant excluded artifacts. '
              'Write the exact JSON envelope (no extra fields) to result_path, then stop working. '
              + json.dumps({key: record[key] for key in ('task_id', 'attempt_id', 'goal', 'cwd', 'role', 'model',
                                                       'owned_paths', 'acceptance', 'result_path',
                                                       'scope_check_exclusions')}, ensure_ascii=False)
              + ' Result envelope template: ' + json.dumps(example, ensure_ascii=False))
    if len(prompt.encode('utf-8')) > 32768:
        raise ToolError('task prompt exceeds 32 KiB')
    (run / 'prompt.txt').write_text(prompt, encoding='utf-8')
    (run / 'prompt.txt').chmod(0o600)
    atomic_json(run / 'task.json', record)
    return dict(run=str(run), task_id=task_id, state='prepared', prompt=str(run / 'prompt.txt'))


def check_session(record):
    tmux = Tmux(record['socket'])
    # Resolve to a session ID: tmux 3.4 display-message does not resolve =name
    # consistently with list-panes, even though it returns a zero exit status.
    targets = [line.split('|', 1)[0] for line in
               tmux.run('list-sessions', '-F', '#{session_id}|#{session_name}').splitlines()
               if line.split('|', 1)[1] == record['session']]
    if len(targets) != 1:
        raise ToolError('exact session not found')
    info = session.describe(tmux, targets[0])
    if (not info['owned'] or info['task'] != record['task_id'] or info['cwd'] != record['cwd']
            or [pane['pane'] for pane in info['panes']] != [record['pane']]):
        raise ToolError('session does not match this work package')


def save(run, record):
    atomic_json(run / 'task.json', record)


@contextmanager
def launch_environment(values):
    """Apply proxy settings only while creating this task's new tmux server."""
    if values:
        bypass = ['localhost', '127.0.0.1', '::1']
        for key in ('NO_PROXY', 'no_proxy'):
            bypass.extend(filter(None, os.environ.get(key, '').split(',')))
        values = dict(values, NO_PROXY=','.join(dict.fromkeys(bypass)),
                      no_proxy=','.join(dict.fromkeys(bypass)))
    previous = {key: os.environ.get(key) for key in values}
    try:
        os.environ.update(values)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def start(run, record, proxy_url=None):
    if record['state'] != 'prepared':
        raise ToolError('start is single-attempt; inspect the existing session instead')
    environment = profiles.proxy_environment(proxy_url)
    command = profiles.command(record['profile'], record['opencode_enabled'], model=record.get('model'))
    registry = workspace_registry(record['cwd'])
    with locked(registry):
        for candidate in registry.glob('*.json'):
            lease = read_json(candidate, 16384)
            other = read_json(Path(lease['run']) / 'task.json')
            if lease['task_id'] != other['task_id']:
                raise ToolError('workspace registry identity mismatch; inspect before proceeding')
            if other['task_id'] == record['task_id'] or other['cwd'] != record['cwd']:
                continue
            if not other['closed'] and other['state'] != 'prepared' and (
                    record['role'] in ('implement', 'test') or other['role'] in ('implement', 'test')):
                raise ToolError('workspace already has a live writer/reader; close it or use an isolated worktree')
        # Capture immediately before launching, rather than when the task was planned.
        record['baseline'] = snapshot(Path(record['cwd']))
        record.update(state='launch_uncertain', command=command, started_at=time.time(),
                      socket='ai-tui-' + record['attempt_id'], session='cli',
                      proxy_url=proxy_url,
                      workspace_lease=str(registry / (record['task_id'] + '.json')))
        save(run, record)
        atomic_json(Path(record['workspace_lease']), dict(run=str(run), task_id=record['task_id']))
        with launch_environment(environment):
            result = session.new(SimpleNamespace(socket=record['socket'], task=record['task_id'],
                                 cwd=record['cwd'], session='cli', command=command,
                                 history_limit=50000, width=140, height=45))
        record.update(pane=result['pane'], state='started')
        save(run, record)
    return dict(run=str(run), state=record['state'], **result)


def within_budget(record):
    if record.get('started_at') is None or time.time() >= record['started_at'] + record['budget_seconds']:
        raise ToolError('task execution budget exhausted or task not started; inspect/collect/close instead')


def run_script(name, *args, input=None, timeout=30):
    return subprocess.run([sys.executable, str(SCRIPTS / name), *args], input=input,
                          capture_output=True, timeout=timeout)


def paste(run, record, evidence=None):
    if record['state'] != 'started':
        raise ToolError('paste is single-attempt and requires a started task')
    within_budget(record)
    check_session(record)
    # A short pointer stays visible instead of becoming a collapsed paste widget.
    # The complete contract remains in a private, task-specific UTF-8 file.
    prompt = ('Read the complete bounded work package at '
              + json.dumps(str(run / 'prompt.txt'), ensure_ascii=False)
              + '. Follow that contract, write only the permitted artifacts and its result_path, '
              'do not delegate or change permissions, then stop.').encode('utf-8')
    if (b'\n' in prompt or b'\r' in prompt) and not (evidence or '').strip():
        raise ToolError('multiline requires verified CLI/version/interface evidence')
    record['state'] = 'paste_uncertain'
    save(run, record)
    options = ['--multiline-verified', evidence] if evidence else []
    result = run_script('input.py', 'paste', '--socket', record['socket'], '--pane', record['pane'],
                        *options, input=prompt)
    if result.returncode:
        raise ToolError(result.stderr.decode('utf-8', 'replace').strip())
    record['state'] = 'pasted'
    save(run, record)
    return dict(state=record['state'], terminal=result.stdout.decode().strip())


def observe(run, record, submit=False, confirmed=False, timeout_ms=20000):
    if submit and (record['state'] != 'pasted' or not confirmed):
        raise ToolError('submit requires pasted state and --received-confirmed; never submit twice')
    if not submit and record['state'] != 'running':
        raise ToolError('observe requires a submitted task; use screen for startup inspection')
    within_budget(record)
    check_session(record)
    remaining = int((record['started_at'] + record['budget_seconds'] - time.time()) * 1000)
    timeout_ms = min(timeout_ms, remaining, 20000)
    if timeout_ms <= 0:
        raise ToolError('wait timeout must be positive')
    mode = 'submit-and-wait' if submit else 'resume'
    if submit:
        record['state'] = 'submit_uncertain'
        save(run, record)  # A crash or failed tmux call must never enable an automatic second Enter.
    flags = ['--received-confirmed'] if submit else []
    result = run_script('wait.py', mode, '--socket', record['socket'], '--pane', record['pane'],
                        '--timeout-ms', str(timeout_ms), '--shell-timeout-ms', '30000', *flags)
    if result.returncode not in (0, 3):
        raise ToolError(result.stderr.decode('utf-8', 'replace').strip() or 'wait failed; inspect submission')
    record['state'] = 'running'
    record['last_observation'] = result.stdout.decode('utf-8', 'replace').splitlines()[0]
    save(run, record)
    return dict(state=record['state'], observation=record['last_observation'],
                screen=result.stdout.decode('utf-8', 'replace').partition('\n')[2])


def collect(run, record):
    if record['state'] not in ('running', 'submit_uncertain', 'awaiting_acceptance', 'partial', 'blocked'):
        raise ToolError('collect requires a submitted task')
    value = validate_result(read_json(Path(record['result_path']), 16384), record)
    report, current = scope_report(record)
    if report['scope_violations'] or report['git_state_changed']:
        raise ToolError('scope check failed: ' + json.dumps(report, ensure_ascii=False))
    status = value['handoff']['STATUS']
    record.update(state={'DONE': 'awaiting_acceptance', 'PARTIAL': 'partial', 'BLOCKED': 'blocked'}[status],
                  result=value, scope=report, collected_snapshot=current)
    save(run, record)
    return dict(state=record['state'], result=value, scope=report)


def accept(run, record, evidence):
    nonblank(evidence, 'independent acceptance evidence')
    if record['state'] != 'awaiting_acceptance':
        raise ToolError('accept requires a validated DONE handoff')
    current_result = validate_result(read_json(Path(record['result_path']), 16384), record)
    if current_result != record['result'] or snapshot(Path(record['cwd'])) != record['collected_snapshot']:
        raise ToolError('artifacts changed since collection; collect and inspect again')
    record.update(state='accepted', acceptance_evidence=evidence, accepted_at=time.time())
    save(run, record)
    return dict(state='accepted', evidence=evidence)


def close(run, record, allow_active=False):
    lease = Path(record['workspace_lease']) if record.get('workspace_lease') else None
    result = None
    # Acquire before killing the session. Contention leaves the task intact and retryable.
    with locked(lease.parent) if lease else nullcontext():
        if not record['closed']:
            if 'socket' not in record or 'pane' not in record:
                raise ToolError('no confirmed session to clean; inspect any launch_uncertain socket manually')
            check_session(record)
            result = session.cleanup(SimpleNamespace(socket=record['socket'], session=record['session'],
                                      task=record['task_id'], allow_active=allow_active))
            if record['state'] not in TERMINAL:
                record['state'] = 'cancelled'
            record['closed'] = True
            save(run, record)
        # A failed unlink after cleanup must remain retryable even with closed=True.
        if lease and lease.exists():
            if read_json(lease, 16384)['task_id'] != record['task_id']:
                raise ToolError('refusing to release another task workspace lease')
            lease.unlink()
    return dict(state=record['state'], closed=True, cleanup=result)


def parser():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('doctor')
    init = commands.add_parser('init')
    init.add_argument('--cwd', required=True)
    init.add_argument('--goal', required=True)
    init.add_argument('--role', choices=('implement', 'test', 'review', 'research'), required=True)
    init.add_argument('--profile', choices=tuple(profiles.PROFILES), default='codex')
    init.add_argument('--model', help='explicit CLI model ID for this task; omitted preserves CLI defaults')
    init.add_argument('--enable-opencode', action='store_true')
    init.add_argument('--owned-path', action='append', default=[])
    init.add_argument('--acceptance', action='append', required=True)
    init.add_argument('--budget-seconds', type=int, default=600)
    init.add_argument('--runs-dir')
    for name in ('start', 'show', 'screen', 'paste', 'submit', 'observe', 'collect', 'accept', 'close'):
        cmd = commands.add_parser(name)
        cmd.add_argument('--run', type=Path, required=True)
        if name == 'start':
            cmd.add_argument('--proxy-url', help='HTTP(S) proxy endpoint inherited by this worker; no credentials')
        if name == 'paste':
            cmd.add_argument('--multiline-verified')
        if name == 'submit':
            cmd.add_argument('--received-confirmed', action='store_true')
        if name in ('submit', 'observe'):
            cmd.add_argument('--timeout-ms', type=int, default=20000)
        if name == 'accept':
            cmd.add_argument('--evidence', required=True)
        if name == 'close':
            cmd.add_argument('--allow-active', action='store_true')
    return parser


def main():
    args = parser().parse_args()
    try:
        if args.action == 'doctor':
            result = profiles.doctor()
        elif args.action == 'init':
            result = prepare(args)
        else:
            run = args.run.expanduser().resolve(strict=True)
            with locked(run):
                record = read_json(run / 'task.json')
                if args.action == 'show':
                    result = {key: value for key, value in record.items()
                              if key not in ('baseline', 'collected_snapshot')}
                elif args.action == 'screen':
                    check_session(record)
                    result = dict(screen=Tmux(record['socket']).capture(record['pane']))
                elif args.action == 'start':
                    result = start(run, record, args.proxy_url)
                elif args.action == 'paste':
                    result = paste(run, record, args.multiline_verified)
                elif args.action in ('submit', 'observe'):
                    result = observe(run, record, args.action == 'submit',
                                     getattr(args, 'received_confirmed', False), args.timeout_ms)
                elif args.action == 'collect':
                    result = collect(run, record)
                elif args.action == 'accept':
                    result = accept(run, record, args.evidence)
                else:
                    result = close(run, record, args.allow_active)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ToolError, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print('error: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
