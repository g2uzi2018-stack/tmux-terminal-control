#!/usr/bin/env python3
"""Bound work packages to tmux sessions; validate handoffs before primary acceptance."""
from contextlib import contextmanager, nullcontext
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid

from common import Tmux, ToolError
from config import runs_directory, proxy_setup, load_config
from lease import locked, workspace_registry, session_gone, prune_dead, inspect_lease, reap
from records import atomic_json, nonblank, read_json, save
from results import FIELDS, validate_result
from snapshot import git, normalized_scope, scope_report, snapshot
import profiles
from observation import terminal_flags
import session
from timing import budget_status

SCRIPTS = Path(__file__).resolve().parent
TERMINAL = {'accepted', 'partial', 'blocked', 'failed', 'cancelled'}


def prepare(args):
    cwd = Path(args.cwd).resolve(strict=True)
    if not cwd.is_dir() or Path(os.fsdecode(git(cwd, 'rev-parse', '--show-toplevel')).strip()).resolve() != cwd:
        raise ToolError('cwd must be the Git worktree root')
    if args.profile == 'opencode' and not args.enable_opencode:
        raise ToolError('OpenCode is compatibility-only; explicit --enable-opencode is required')
    model = getattr(args, 'model', None)
    if model is None:
        model = load_config().get('profiles', {}).get(args.profile, {}).get('model')
    model = profiles.validate_model(model)
    if type(getattr(args, 'max_replies', 2)) is not int or getattr(args, 'max_replies', 2) < 0:
        raise ToolError('max_replies must be a nonnegative integer')
    if args.budget_seconds <= 0:
        raise ToolError('budget must be positive')
    for name, default in (('startup_budget_seconds', 300), ('approval_budget_seconds', 300)):
        value = getattr(args, name, default)
        if type(value) is not int or value < (1 if name == 'startup_budget_seconds' else 0):
            raise ToolError(name + ' must be a valid nonnegative budget (startup must be positive)')
    owned = [normalized_scope(cwd, path) for path in args.owned_path]
    if args.role in ('review', 'research') and owned:
        raise ToolError('read-only roles cannot own write paths')
    if args.role in ('implement', 'test') and not owned:
        raise ToolError('write roles require --owned-path')
    for item in (args.goal, *args.acceptance):
        nonblank(item, 'goal/acceptance')
    baseline = snapshot(cwd)
    root = runs_directory(args.runs_dir)
    try:
        root.relative_to(cwd)
    except ValueError:
        pass
    else:
        raise ToolError('runs directory must be outside the worktree')
    task_id, attempt_id = 'task-' + uuid.uuid4().hex, uuid.uuid4().hex
    run = root / task_id
    run.mkdir(mode=0o700)
    record = dict(version=2, round=0, reply_count=0, max_replies=getattr(args, 'max_replies', 2), interventions=[], task_id=task_id, attempt_id=attempt_id, goal=args.goal,
                  cwd=str(cwd), role=args.role, profile=args.profile, model=model, owned_paths=owned,
                  acceptance=args.acceptance, baseline=baseline, state='prepared',
                  budget_seconds=args.budget_seconds, created_at=time.time(),
                  budget_origin='submission', startup_budget_seconds=getattr(args, 'startup_budget_seconds', 300),
                  approval_budget_seconds=getattr(args, 'approval_budget_seconds', 300),
                  readiness_required=True,
                  scope_check_exclusions=['Git-ignored untracked files', 'paths outside the worktree'],
                  opencode_enabled=args.enable_opencode, closed=False,
                  result_path=str(run / 'result.json'))
    example = dict(task_id=task_id, attempt_id=attempt_id, round=0,
                   handoff=dict(STATUS='DONE', RESULT=[], EVIDENCE=[], VALIDATION=[], REMAINING_WORK=[], RISKS=[]))
    prompt = ('Complete this bounded work package. Do not delegate, commit, stage, change branches, '
              'or modify CLI permissions. Treat allowed paths as a work contract, not sandbox enforcement. '
              'Write only your owned paths and the run-directory result/question/ready JSON (including temporary files for atomic publication); '
              'review/research roles may write only those control artifacts. '
              'Before reading project materials or doing substantive work, verify the control directory is writable: '
              'atomically publish ready.json alongside prompt.txt with exactly task_id, attempt_id, round, STATUS="READY" '
              '(use the actual task identity below). This is a control artifact permitted for every role. '
              'Prefer direct file tools. If they cannot rename files atomically, a narrowly scoped local command '
              'that only publishes this run\'s control files is permitted, subject to normal CLI approval. '
              'Do not enumerate the run parent or create unrelated directories. '
              'If control-file publication is refused, stop and report the exact restriction in the terminal; '
              'do not spend the task budget planning a result that cannot be delivered. '
              'Save a usable owned-artifact draft early and refine it, instead of only describing planned work. '
              'The execution budget is ' + str(args.budget_seconds) + ' seconds from initial submission; '
              'publish PARTIAL/BLOCKED with concrete remaining work if unable to finish. '
              'Report real validation, and use PARTIAL/BLOCKED with concrete REMAINING_WORK if unfinished. '
              'Each handoff array allows up to 12 nonblank strings of at most 2000 characters; '
              'the compact handoff must be at most 8 KiB. '
              'Scope checks exclude the categories listed in scope_check_exclusions; the primary must '
              'independently verify any relevant excluded artifacts. '
              'Publish JSON atomically: write a temporary file in the run directory, then rename it to result_path. '
              'For a blocking question, atomically publish question.json in the same directory with exactly '
              'task_id, attempt_id, round, QUESTION (text), OPTIONS (array of text), BLOCKING (boolean), then wait. '
              'Do not spawn or dispatch other work processes. Follow the current round in any reply file. '
              'Write the exact JSON envelope (no extra fields) to result_path, then stop working. '
              + json.dumps({key: record[key] for key in ('task_id', 'attempt_id', 'round', 'goal', 'cwd', 'role', 'model',
                                                       'owned_paths', 'acceptance', 'result_path',
                                                       'scope_check_exclusions')}, ensure_ascii=True)
              + ' Result envelope template: ' + json.dumps(example, ensure_ascii=True))
    if len(prompt.encode('utf-8')) > 32768:
        raise ToolError('task prompt exceeds 32 KiB')
    (run / 'prompt.txt').write_text(prompt, encoding='utf-8')
    (run / 'prompt.txt').chmod(0o600)
    save(run, record)
    return dict(run=str(run), task_id=task_id, state='prepared', prompt=str(run / 'prompt.txt'))


def check_session(record, deadline=None):
    tmux = Tmux(record['socket'], deadline)
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


@contextmanager
def launch_environment(values):
    """Apply proxy settings only while creating this task's new tmux server."""
    values = dict(values)
    if any(value is not None for key, value in values.items()
           if key.lower() in ('http_proxy', 'https_proxy', 'all_proxy')):
        bypass = ['localhost', '127.0.0.1', '::1']
        for key in ('NO_PROXY', 'no_proxy'):
            inherited = values[key] if key in values else os.environ.get(key)
            bypass.extend(filter(None, (inherited or '').split(',')))
        values = dict(values, NO_PROXY=','.join(dict.fromkeys(bypass)),
                      no_proxy=','.join(dict.fromkeys(bypass)))
    previous = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield values
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def start(run, record, proxy_url=None, no_proxy=False):
    if record['state'] != 'prepared':
        raise ToolError('start is single-attempt; inspect the existing session instead')
    environment, proxy, proxy_notice = proxy_setup(proxy_url, no_proxy)
    command = profiles.command(record['profile'], record['opencode_enabled'], model=record.get('model'))
    registry = workspace_registry(record['cwd'])
    reclaimed = []
    with locked(registry):
        for candidate in registry.glob('*.json'):
            item, other = inspect_lease(candidate)
            if item['status'] == 'unknown':
                raise ToolError('unresolved workspace lease; inspect reap report and use --task ID --force if appropriate')
            if other['cwd'] != record['cwd']:
                raise ToolError('workspace lease cwd mismatch')
            if item['status'] == 'gone':
                prune_dead(other)
                candidate.unlink()
                reclaimed.append(item['task_id'])
                continue
            if other['task_id'] == record['task_id']:
                continue
            if (record['role'] in ('implement', 'test') or other['role'] in ('implement', 'test')):
                raise ToolError('workspace already has a live writer/reader; close it or use an isolated worktree')
        # Capture immediately before launching, rather than when the task was planned.
        record['baseline'] = snapshot(Path(record['cwd']))
        record.update(state='launch_uncertain', command=command, started_at=time.time(),
                      socket='ai-tui-' + record['attempt_id'], session='cli',
                      proxy_url=proxy_url, proxy=proxy,
                      workspace_lease=str(registry / (record['task_id'] + '.json')))
        record['cli_version'] = profiles.version(record['profile'])
        import capabilities
        compatibility = capabilities.comparison(record['profile'], record['cli_version'], check_version=False)
        record['cli_capabilities'] = {key: compatibility[key] for key in ('version_matches', 'warning', 'passed', 'failed')}
        save(run, record)
        atomic_json(Path(record['workspace_lease']), dict(run=str(run), task_id=record['task_id']))
        with launch_environment(environment):
            result = session.new(SimpleNamespace(socket=record['socket'], task=record['task_id'],
                                 cwd=record['cwd'], session='cli', command=command,
                                 history_limit=50000, width=140, height=45))
        record.update(pane=result['pane'], state='started')
        save(run, record)
    return dict(run=str(run), state=record['state'], reclaimed_leases=reclaimed, proxy=proxy, proxy_notice=proxy_notice,
                cli_version=record['cli_version'], cli_capabilities=record['cli_capabilities'], **result)


def within_budget(record):
    status = budget_status(record)
    if status['phase'] == 'prepared' or status['exhausted']:
        raise ToolError('task ' + status['phase'] + ' budget exhausted or task not started; inspect/collect/close instead')


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
    remaining = int(budget_status(record)['remaining_seconds'] * 1000)
    timeout_ms = min(timeout_ms, record['budget_seconds'] * 1000 if submit else remaining, 20000)
    if timeout_ms <= 0:
        raise ToolError('wait timeout must be positive')
    mode = 'submit-and-wait' if submit else 'resume'
    if submit:
        if record.get('budget_origin') == 'submission':
            record['execution_started_at'] = time.time()
        record['state'] = 'submit_uncertain'
        save(run, record)  # A crash or failed tmux call must never enable an automatic second Enter.
    flags = ['--received-confirmed'] if submit else []
    result = run_script('wait.py', mode, '--socket', record['socket'], '--pane', record['pane'],
                        '--timeout-ms', str(timeout_ms), '--shell-timeout-ms', '30000',
                        *terminal_flags(record['profile']), *flags)
    if result.returncode not in (0, 3):
        raise ToolError(result.stderr.decode('utf-8', 'replace').strip() or 'wait failed; inspect submission')
    record['state'] = 'running'
    record['last_observation'] = result.stdout.decode('utf-8', 'replace').splitlines()[0]
    screen = result.stdout.decode('utf-8', 'replace').partition('\n')[2]
    from approvals import observe_approval
    approval = observe_approval(record, screen, configured='match=approval' in record['last_observation'])
    save(run, record)
    return dict(state=record['state'], observation=record['last_observation'],
                screen=screen, approval=approval, budget=budget_status(record))


def collect(run, record):
    if record['state'] not in ('running', 'awaiting_reply', 'reply_uncertain', 'submit_uncertain', 'awaiting_acceptance', 'partial', 'blocked'):
        raise ToolError('collect requires a submitted task')
    value = validate_result(read_json(Path(record['result_path']), 16384), record)
    report, current = scope_report(record)
    if report['scope_violations'] or report['git_state_changed']:
        raise ToolError('scope check failed: ' + json.dumps(report, ensure_ascii=True))
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
    result, gone = None, False
    # Acquire before killing the session. Contention leaves the task intact and retryable.
    with locked(lease.parent) if lease else nullcontext():
        if lease and lease.exists() and read_json(lease, 16384)['task_id'] != record['task_id']:
            raise ToolError('refusing to release another task workspace lease')
        if not record['closed']:
            if 'socket' not in record or 'pane' not in record:
                raise ToolError('no confirmed session to clean; inspect any launch_uncertain socket manually')
            gone = session_gone(record)
            if gone:
                result = prune_dead(record)
                record['state'] = 'closed'
            else:
                check_session(record)
                result = session.cleanup(SimpleNamespace(socket=record['socket'], session=record['session'],
                                          task=record['task_id'], allow_active=allow_active))
            if record['state'] not in TERMINAL | {'closed'}:
                record['state'] = 'cancelled'
            record['closed'] = True
            from timing import finish_approval
            finish_approval(record, 'closed')
            save(run, record)
        # A failed unlink after cleanup must remain retryable even with closed=True.
        if lease and lease.exists():
            if read_json(lease, 16384)['task_id'] != record['task_id']:
                raise ToolError('refusing to release another task workspace lease')
            lease.unlink()
    return dict(state=record['state'], closed=True, cleanup=result, session_gone=bool(gone))
