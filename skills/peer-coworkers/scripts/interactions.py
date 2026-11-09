"""Explicit terminal actions and feedback."""
import os
import re
import stat
from pathlib import Path
import time
import uuid

from common import KEYS, Tmux, ToolError, send_submit
from observation import receipt
from records import nonblank, read_bytes, save
from results import handoff_instructions
from wait import compile_pattern, prompt_region, bounded_search
import capabilities
import profiles


def intervention(run, record, action, **data):
    entry = dict(action=action, status='uncertain', at=time.time(), **data)
    record.setdefault('interventions', []).append(entry)
    save(run, record)
    return entry


def workspace_trust_dialog(record, screen):
    """Match an observed startup trust menu for this exact task cwd."""
    lines = [line.strip() for line in screen.splitlines() if line.strip()]
    if record['profile'] == 'cursor':
        if (len(lines) < 2 or not re.fullmatch(r'╭─+╮', lines[0])
                or lines[-1] != '╰' + lines[0][1:-1] + '╯'
                or any(not (line.startswith('│') and line.endswith('│')) for line in lines[1:-1])):
            return False
        card = [line[1:-1].strip() for line in lines[1:-1]]
        return [line for line in card if line] == [
            '⚠ Workspace Trust Required',
            'Cursor Agent can execute code and access files in this directory.',
            'Do you trust the contents of this directory?',
            record['cwd'],
            '▶ [a] Trust this workspace',
            '[q] Quit',
            'Use arrow keys to navigate, Enter to select, or press the key shown',
        ]
    if record['profile'] != 'agy':
        return False
    expected = [
        'Accessing workspace:', record['cwd'],
        'Do you trust the contents of this project?',
        'Antigravity CLI requires permission to read, edit, and execute files here.',
        '> Yes, I trust this folder', 'No, exit', '↑/↓ Navigate · enter Confirm',
    ]
    return (lines[:7] == expected and
            (len(lines) == 7 or (len(lines) == 8 and
             re.fullmatch(r'[^<>?]+\s·\s[^<>?]+', lines[7]) is not None)))


def trust_workspace(run, record, digest, evidence):
    """Confirm one explicitly authorized startup trust menu; never submit work."""
    from approvals import screen_hash
    from records import nonblank
    from tasks import check_session, within_budget
    nonblank(evidence, 'workspace trust authorization evidence')
    if record.get('closed') or record['state'] != 'started' or record.get('execution_started_at') is not None:
        raise ToolError('workspace trust requires an open started task before any work submission')
    if any(item.get('action') == 'workspace_trust' for item in record.get('interventions', [])):
        raise ToolError('workspace trust already attempted; inspect, never resend')
    within_budget(record)
    check_session(record)
    tmux = Tmux(record['socket'])
    before = tmux.capture(record['pane'])
    if screen_hash(before) != digest or not workspace_trust_dialog(record, before):
        raise ToolError('workspace trust screen/path/selection changed or unsupported')
    key = 'a' if record['profile'] == 'cursor' else 'Enter'
    entry = intervention(run, record, 'workspace_trust', screen_sha256=digest,
                         cwd=record['cwd'], key=key, evidence=evidence)
    if tmux.capture(record['pane']) != before:
        raise ToolError('workspace trust screen changed; attempt remains uncertain')
    within_budget(record)
    if key == 'a':
        tmux.alive(record['pane'])
        tmux.run('send-keys', '-t', record['pane'], '-l', '--', key)
    else:
        send_submit(tmux, record['pane'], key, True)
    entry['status'] = 'submitted'
    save(run, record)
    return dict(state=record['state'], trust='submitted', cwd=record['cwd'],
                screen_sha256=digest)


def keys(run, record, selected):
    if not selected or any(key not in KEYS for key in selected):
        raise ToolError('unsupported key; Enter is only allowed through a submission command')
    if record.get('closed'):
        raise ToolError('task is closed')
    from tasks import check_session, within_budget
    within_budget(record)
    check_session(record)
    entry = intervention(run, record, 'keys', keys=selected)
    tmux = Tmux(record['socket'])
    tmux.alive(record['pane'])
    tmux.run('send-keys', '-t', record['pane'], '--', *selected)
    entry['status'] = 'sent'
    save(run, record)
    return dict(state=record['state'], intervention=entry)


def steer_reply(run, record, steer_id, evidence):
    """Steer one existing Cursor queue item with one Enter."""
    from followups import cursor_reply_binding, reply_acknowledged, reply_hash, steer_attempted
    from tasks import check_session, within_budget
    nonblank(evidence, 'reply steer authorization evidence')
    if record['closed'] or record['state'] != 'running' or record['profile'] != 'cursor':
        raise ToolError('steer requires an open running Cursor task')
    pending = record.get('pending_steer', {})
    if pending.get('steer_id') != steer_id or steer_attempted(record):
        raise ToolError('no matching unsteered feedback; inspect wait and never resend')
    within_budget(record)
    check_session(record)
    tmux = Tmux(record['socket'])

    def check_queue():
        if (cursor_reply_binding(record, tmux.capture(record['pane'])) != pending['binding']
                or reply_hash(record) != pending['reply_sha256'] or reply_acknowledged(record)):
            raise ToolError('feedback queue or content changed; inspect the pane')

    check_queue()
    entry = intervention(run, record, 'reply_steer', reply_file=record['reply_file'],
                         steer_id=steer_id, screen_sha256=pending['screen_sha256'], evidence=evidence)
    check_queue()
    within_budget(record)
    send_submit(tmux, record['pane'], 'Enter', True)
    entry['status'] = 'submitted'
    record.pop('pending_steer', None)
    save(run, record)
    return dict(state=record['state'], steer='submitted', result_path=record['result_path'])


def cancel(run, record, timeout_ms=2000):
    if record['state'] == 'cancelled':
        return dict(state='cancelled', sent=False)
    if record['state'] not in ('running', 'cancelling'):
        raise ToolError('cancel requires a running task or an existing cancelling state')
    check = capabilities.cancellation(record['profile'])
    pattern = compile_pattern(check['stopped_pattern'])
    options = profiles.settings(record['profile'])
    busy = compile_pattern(options['busy_regex']) if options.get('busy_regex') else None
    if timeout_ms <= 0:
        raise ToolError('cancel timeout must be positive')
    deadline = time.monotonic() + min(timeout_ms, 5000) / 1000
    from tasks import check_session
    check_session(record)
    tmux = Tmux(record['socket'], deadline)
    before = tmux.capture(record['pane'])
    # Delivery uncertainty is durable even if another observation changed state.
    sent = record['state'] != 'cancelling' and not any(
        item['action'] == 'cancel' and item.get('result_path') == record['result_path']
        for item in record.get('interventions', [])
    )
    if sent:
        record['state'] = 'cancelling'
        record['cancel_baseline'] = before
        entry = intervention(run, record, 'cancel', key='Escape', result_path=record['result_path'])
        tmux.alive(record['pane'])
        tmux.run('send-keys', '-t', record['pane'], '--', 'Escape')
        entry['status'] = 'sent'
        save(run, record)
    else:
        record['state'] = 'cancelling'
    baseline_lines = set(record.get('cancel_baseline', '').splitlines())
    screen, quiet = before, None
    from common import DeadlineReached
    try:
        while time.monotonic() < deadline:
            dead, _ = tmux.status(record['pane'])
            screen = tmux.capture(record['pane'])
            stopped = any(line not in baseline_lines and bounded_search(pattern, line, deadline)
                          for line in prompt_region(screen, options.get('cancel_lines', 20)))
            if dead:
                record['state'] = 'cancelled'
                break
            if stopped and not (busy and bounded_search(busy, screen, deadline)):
                quiet = quiet or time.monotonic()
                if time.monotonic() - quiet >= .12:
                    record['state'] = 'cancelled'
                    break
            else:
                quiet = None
            time.sleep(min(.04, max(0, deadline - time.monotonic())))
    except DeadlineReached:
        pass
    save(run, record)
    return dict(state=record['state'], sent=sent, screen=screen)


def reply(run, record, message_file):
    from approvals import observe_approval
    from common import DeadlineReached
    from followups import reply_pointer
    from records import terminal_event
    from tasks import check_session, run_script, within_budget
    if record['closed'] or record['state'] not in ('running', 'partial', 'blocked', 'awaiting_acceptance'):
        raise ToolError('reply requires an open submitted task; inspect uncertain sends before continuing')
    previous = Path(record['result_path'])
    if record.get('reply_file'):
        # A fresh file shows the worker reached this feedback. Malformed prose
        # can be corrected, but an absent handoff cannot acknowledge delivery.
        try:
            info = previous.lstat()
        except FileNotFoundError as exc:
            raise ToolError('wait for the current feedback handoff before replying again') from exc
        if not stat.S_ISREG(info.st_mode) or not info.st_size:
            raise ToolError('current feedback has no nonempty regular handoff')
    text = nonblank(read_bytes(message_file, 32768, 'feedback exceeds 32 KiB').decode('utf-8'),
                    'feedback')
    within_budget(record)
    check_session(record)
    tmux = Tmux(record['socket'])
    tmux.alive(record['pane'])
    options = profiles.settings(record['profile'])
    patterns = [compile_pattern(pattern) for pattern in options['approval_patterns']]

    def check_approval_screen():
        screen = tmux.capture(record['pane'])
        region = prompt_region(screen, options['prompt_lines'])
        deadline = time.monotonic() + 2
        try:
            configured = any(bounded_search(pattern, line, deadline) for pattern in patterns for line in region)
        except DeadlineReached as exc:
            raise ToolError('reply approval check timed out; inspect the current screen') from exc
        if observe_approval(record, screen, configured=configured):
            terminal_event(run, record, 'reply_blocked_by_approval', screen)
            save(run, record)
            raise ToolError('resolve the current approval before replying; use wait to inspect it')
        return screen

    check_approval_screen()
    within_budget(record)
    marker = uuid.uuid4().hex[:12]
    target = run / f'feedback-{marker}.md'
    handoff = run / f'handoff-{marker}.md'
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(f'{text}\n\n{handoff_instructions(handoff)}\n')
    record.update(state='reply_uncertain', reply_file=str(target), result_path=str(handoff))
    for key in ('scope', 'collected_snapshot', 'pending_steer'):
        record.pop(key, None)
    entry = intervention(run, record, 'reply', reply_file=str(target), previous_handoff=str(previous))
    pointer = reply_pointer(record)
    check_approval_screen()
    within_budget(record)
    process = run_script('input.py', 'paste', '--socket', record['socket'], '--pane', record['pane'],
                         input=pointer.encode('utf-8'))
    if process.returncode or not receipt(tmux, record['pane'], pointer):
        raise ToolError('feedback paste receipt unconfirmed; inspect reply_uncertain and never resend')
    from wait import encode
    baseline = check_approval_screen()
    for name, value in (('@aitui_baseline', encode(baseline)), ('@aitui_changed', '0'),
                        ('@aitui_previous', encode(baseline)), ('@aitui_quiet_since', '')):
        tmux.set_pane_option(record['pane'], name, value)
    check_approval_screen()
    within_budget(record)
    send_submit(tmux, record['pane'], 'Enter', True)
    record['state'] = 'running'
    entry['status'] = 'submitted'
    save(run, record)
    return dict(state='running', reply_file=str(target), result_path=str(handoff))
