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
from config import runs_directory, proxy_setup, load_config, cursor_task_config
from lease import locked, workspace_registry, session_gone, prune_dead, inspect_lease, reap
from records import atomic_json, nonblank, read_json, save, terminal_event
from results import HANDOFF_ERRORS, handoff_instructions, historical_result, read_handoff
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
    model = args.model
    if model is None:
        model = load_config().get('profiles', {}).get(args.profile, {}).get('model')
    model = profiles.validate_model(model, args.profile)
    if args.budget_seconds <= 0:
        raise ToolError('budget must be positive')
    if args.startup_budget_seconds <= 0 or args.approval_budget_seconds < 0:
        raise ToolError('startup budget must be positive and approval grace cannot be negative')
    owned = [normalized_scope(cwd, path) for path in args.owned_path]
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
    task_id = 'task-' + uuid.uuid4().hex
    run = root / task_id
    handoff = run / 'handoff.md'
    record = dict(version=3, task_id=task_id, goal=args.goal, cwd=str(cwd),
                  role=args.role, profile=args.profile, model=model, owned_paths=owned,
                  acceptance=args.acceptance, baseline=baseline, state='prepared',
                  budget_seconds=args.budget_seconds, created_at=time.time(),
                  budget_origin='submission', startup_budget_seconds=args.startup_budget_seconds,
                  approval_budget_seconds=args.approval_budget_seconds,
                  scope_check_exclusions=['Git-ignored untracked files', 'paths outside the worktree'],
                  opencode_enabled=args.enable_opencode, closed=False, result_path=str(handoff))
    acceptance = '\n'.join('- ' + item for item in args.acceptance)
    paths = ', '.join(owned) or 'none'
    prompt = (f'# Task\n\n{args.goal}\n\n## Acceptance criteria\n\n{acceptance}\n\n'
              f'Workspace is {cwd}. Writable workspace paths are {paths}. '
              'The handoff and its temporary file are also writable. Keep existing CLI permissions, '
              'leave Git staging and commits to the primary, and do the work yourself.\n\n'
              f'Work budget is {args.budget_seconds} seconds from submission.\n\n'
              + handoff_instructions(handoff) + '\n')
    if len(prompt.encode('utf-8')) > 32768:
        raise ToolError('task prompt exceeds 32 KiB')
    run.mkdir(mode=0o700)
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
            if record['owned_paths'] or other['owned_paths']:
                raise ToolError('workspace already has a live writer/reader; close it or use an isolated worktree')
        # Capture immediately before launching, rather than when the task was planned.
        record['baseline'] = snapshot(Path(record['cwd']))
        record.update(state='launch_uncertain', command=command, started_at=time.time(),
                      socket='ai-tui-' + record['task_id'][5:], session='cli',
                      proxy_url=proxy_url, proxy=proxy,
                      workspace_lease=str(registry / (record['task_id'] + '.json')))
        record['cli_version'] = profiles.version(record['profile'])
        import capabilities
        compatibility = capabilities.comparison(record['profile'], record['cli_version'], check_version=False)
        record['cli_capabilities'] = {key: compatibility[key] for key in ('version_matches', 'warning', 'passed', 'failed')}
        save(run, record)
        atomic_json(Path(record['workspace_lease']), dict(run=str(run), task_id=record['task_id']))
        if record['profile'] == 'cursor':
            record['cursor_config_dir'] = cursor_task_config(run, record['cwd'])
            environment['CURSOR_CONFIG_DIR'] = record['cursor_config_dir']
            save(run, record)
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
              + ' and follow its instructions.').encode('utf-8')
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
        attempt = dict(action='submit', status='uncertain', initial_state='submit_uncertain',
                       at=time.time(), execution_started_at=record.get('execution_started_at'))
        record.setdefault('interventions', []).append(attempt)
        save(run, record)  # A crash or failed tmux call must never enable an automatic second Enter.
    flags = ['--received-confirmed'] if submit else []
    try:
        result = run_script('wait.py', mode, '--socket', record['socket'], '--pane', record['pane'],
                            '--timeout-ms', str(timeout_ms), '--shell-timeout-ms', '30000',
                            *terminal_flags(record['profile']), *flags)
    except (OSError, subprocess.TimeoutExpired, ToolError) as exc:
        if submit:
            attempt['diagnostic'] = str(exc)[:1000]
            save(run, record)
        raise
    if result.returncode not in (0, 3):
        diagnostic = result.stderr.decode('utf-8', 'replace').strip() or 'wait failed; inspect submission'
        if submit:
            attempt.update(returncode=result.returncode, diagnostic=diagnostic[:1000])
            save(run, record)
        raise ToolError(diagnostic)
    if submit:
        attempt['status'] = 'submitted'
    record['state'] = 'running'
    record['last_observation'] = result.stdout.decode('utf-8', 'replace').splitlines()[0]
    screen = result.stdout.decode('utf-8', 'replace').partition('\n')[2]
    from approvals import observe_approval
    approval = observe_approval(record, screen, configured='match=approval' in record['last_observation'])
    save(run, record)
    return dict(state=record['state'], observation=record['last_observation'],
                screen=screen, approval=approval, budget=budget_status(record))


def collect(run, record):
    if record['closed']:
        if record.get('version', 1) < 3:
            return dict(state=record['state'], result=historical_result(record),
                        scope=record.get('scope'), report=record.get('collected_report'))
        result = record.get('result')
        if not result or result['path'] != record['result_path']:
            result = read_handoff(record['result_path'])
        return dict(state=record['state'], result=result, scope=record.get('scope'))
    if record['state'] not in ('running', 'reply_uncertain', 'submit_uncertain',
                                'awaiting_acceptance', 'partial', 'blocked', 'cancelling', 'cancelled'):
        raise ToolError('collect requires a submitted task')
    from records import reconcile_submission
    value = read_handoff(record['result_path'])
    reconcile_submission(run, record, value)
    report, current = scope_report(record)
    if report['scope_violations'] or report['git_state_changed']:
        raise ToolError('scope check failed: ' + json.dumps(report, ensure_ascii=True))
    if value['status'] != 'QUESTION':
        record.update(state={'DONE': 'awaiting_acceptance', 'PARTIAL': 'partial', 'BLOCKED': 'blocked'}[value['status']],
                      result=value, scope=report, collected_snapshot=current)
        save(run, record)
    return dict(state=record['state'], result=value, scope=report)


def accept(run, record, evidence):
    nonblank(evidence, 'independent acceptance evidence')
    if record['closed'] or record['state'] != 'awaiting_acceptance':
        raise ToolError('accept requires a collected DONE handoff')
    if (read_handoff(record['result_path']) != record['result']
            or snapshot(Path(record['cwd'])) != record['collected_snapshot']):
        raise ToolError('artifacts changed since collection; collect and inspect again')
    record.update(state='accepted', acceptance_evidence=evidence, accepted_at=time.time())
    save(run, record)
    return dict(state='accepted', evidence=evidence)


def unaccepted_done(record):
    """Protect DONE handoffs until a replacement is collected or work is discarded."""
    if record['state'] == 'accepted':
        return False
    collected = record.get('result', {})
    paths = [record['result_path']]
    paths.extend(item['previous_handoff'] for item in reversed(record.get('interventions', []))
                 if item['action'] == 'reply')
    for path in paths:
        if path == collected.get('path') and collected['status'] == 'DONE':
            return True
        try:
            if read_handoff(path)['status'] == 'DONE':
                return True
        except HANDOFF_ERRORS:
            pass
        if path == collected.get('path'):
            break
    return False


def close(run, record, allow_active=False, discard_unaccepted=False):
    lease = Path(record['workspace_lease']) if record.get('workspace_lease') else None
    result, gone = None, False
    # Acquire before killing the session. Contention leaves the task intact and retryable.
    with locked(lease.parent) if lease else nullcontext():
        if lease and lease.exists() and read_json(lease, 16384)['task_id'] != record['task_id']:
            raise ToolError('refusing to release another task workspace lease')
        if not record['closed']:
            unaccepted = unaccepted_done(record)
            if unaccepted and not discard_unaccepted:
                raise ToolError('unaccepted DONE handoff; collect and accept the current handoff, or explicitly --discard-unaccepted')
            if 'socket' not in record or 'pane' not in record:
                raise ToolError('no confirmed session to clean; inspect any launch_uncertain socket manually')
            gone = session_gone(record)
            if gone:
                result = prune_dead(record)
                if record['state'] not in TERMINAL:
                    record['state'] = 'closed'
            else:
                check_session(record)
                # Preserve the actual final wait before destroying this exact session.
                try:
                    screen = Tmux(record['socket']).capture(record['pane'])
                except (OSError, ToolError) as exc:
                    record['terminal_event_diagnostic'] = 'closing screen unavailable: ' + str(exc)[:900]
                else:
                    terminal_event(run, record, 'close', screen)
                result = session.cleanup(SimpleNamespace(socket=record['socket'], session=record['session'],
                                          task=record['task_id'], allow_active=allow_active))
            # The worker may have written a handoff while its session was closing.
            unaccepted = unaccepted_done(record)
            if unaccepted and not discard_unaccepted:
                raise ToolError('session ended while a DONE handoff arrived; collect and accept before closing the run')
            if record['state'] not in TERMINAL | {'closed'}:
                record['state'] = 'cancelled'
            record['closed'] = True
            if unaccepted:
                record.update(state='cancelled', discarded_unaccepted=True)
            from timing import finish_approval
            finish_approval(record, 'closed')
            save(run, record)
        # A failed unlink after cleanup must remain retryable even with closed=True.
        if lease and lease.exists():
            if read_json(lease, 16384)['task_id'] != record['task_id']:
                raise ToolError('refusing to release another task workspace lease')
            lease.unlink()
    result = dict(state=record['state'], closed=True, cleanup=result, session_gone=bool(gone))
    if record.get('terminal_event_diagnostic'):
        result['terminal_event_diagnostic'] = record['terminal_event_diagnostic']
    return result
