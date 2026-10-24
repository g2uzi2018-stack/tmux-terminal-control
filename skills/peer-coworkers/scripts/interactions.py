"""Explicit single-attempt keys, cancellation, and bounded follow-up rounds."""
import json
import os
from pathlib import Path
import stat
import time

from common import KEYS, Tmux, ToolError, send_submit
from observation import receipt
from records import read_json, save
from results import validate_question, validate_result
from wait import compile_pattern, prompt_region, bounded_search
import capabilities
import profiles


def intervention(run, record, action, **data):
    entry = dict(action=action, status='uncertain', at=time.time(), round=record['round'], **data)
    record.setdefault('interventions', []).append(entry)
    save(run, record)
    return entry


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


def cancel(run, record, timeout_ms=2000):
    if record['state'] == 'cancelled':
        return dict(state='cancelled', sent=False)
    if record['state'] not in ('running', 'awaiting_reply', 'cancelling'):
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
    prior_cancel = any(item.get('action') == 'cancel' and item.get('round') == record['round']
                       for item in record.get('interventions', []))
    sent = record['state'] != 'cancelling' and not prior_cancel
    if sent:
        record['state'] = 'cancelling'
        record['cancel_baseline'] = before
        entry = intervention(run, record, 'cancel', key='Escape')
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


def read_message(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 32768:
            raise ToolError('reply message must be a regular UTF-8 file of at most 32 KiB')
        content = stream.read(32769)
    if len(content) > 32768:
        raise ToolError('reply message exceeds 32 KiB')
    text = content.decode('utf-8')
    if not text.strip() or '\x00' in text:
        raise ToolError('reply message must be nonblank text without NUL')
    return text


def reply(run, record, message_file):
    from tasks import check_session, within_budget, run_script
    if record['state'] not in ('running', 'awaiting_reply', 'partial', 'blocked', 'awaiting_acceptance'):
        raise ToolError('reply requires a submitted task; reply_uncertain must never be retried')
    if record['reply_count'] >= record['max_replies']:
        raise ToolError('max_replies reached; create a new task')
    within_budget(record)
    check_session(record)
    if record.get('pending_approval', {}).get('status') in ('waiting', 'uncertain'):
        raise ToolError('resolve the pending approval before replying; never paste a task into an approval menu')
    text = read_message(message_file)
    old_round = record['round']
    result_path, question_path = Path(record['result_path']), run / 'question.json'
    if os.path.lexists(result_path):
        validate_result(read_json(result_path, 16384), record)
    if os.path.lexists(question_path):
        validate_question(read_json(question_path, 16384), record)
    # Persist before *any* side effect. Neither paste nor Enter can be retried.
    record.update(state='reply_uncertain', round=old_round + 1, reply_count=record['reply_count'] + 1)
    entry = intervention(run, record, 'reply')
    for path, label in ((result_path, 'result'), (question_path, 'question')):
        if os.path.lexists(path):
            archive = run / (label + '.round' + str(old_round) + '.json')
            if os.path.lexists(archive):
                raise ToolError('round archive already exists; inspect uncertain reply')
            os.replace(path, archive)
    example = dict(task_id=record['task_id'], attempt_id=record['attempt_id'], round=record['round'],
                   handoff=dict(STATUS='DONE', RESULT=[], EVIDENCE=[], VALIDATION=[], REMAINING_WORK=[], RISKS=[]))
    target = run / ('reply-' + str(record['round']) + '.md')
    instructions = ('Continue the original bounded task for round ' + str(record['round']) + '. Do not delegate or change permissions. '
                    'Write the current-round result atomically to ' + str(result_path) + '. Old rounds are invalid. '
                    'You may atomically write a current-round question.json as documented in prompt.txt.\n'
                    'First publish ready.json with the current task_id, attempt_id, round and STATUS="READY".\n'
                    'Result envelope: ' + json.dumps(example) + '\n\n' + text + '\n')
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(instructions)
    pointer = 'Read ' + json.dumps(str(target)) + ' and follow the current-round instructions.'
    process = run_script('input.py', 'paste', '--socket', record['socket'], '--pane', record['pane'],
                         input=pointer.encode('utf-8'))
    if process.returncode:
        raise ToolError('reply paste failed; inspect reply_uncertain, never resend automatically')
    tmux = Tmux(record['socket'])
    if not receipt(tmux, record['pane'], pointer):
        raise ToolError('reply receipt is unconfirmed; inspect reply_uncertain, never resend automatically')
    from wait import encode
    baseline = tmux.capture(record['pane'])
    for name, value in (('@aitui_baseline', encode(baseline)), ('@aitui_changed', '0'),
                        ('@aitui_previous', encode(baseline)), ('@aitui_quiet_since', '')):
        tmux.set_pane_option(record['pane'], name, value)
    send_submit(tmux, record['pane'], 'Enter', True)
    record['state'] = 'running'
    for key in ('result', 'scope', 'collected_snapshot', 'last_wait', 'worker_ready_round'):
        record.pop(key, None)
    entry['status'] = 'submitted'
    save(run, record)
    return dict(state='running', round=record['round'], reply_file=str(target))
