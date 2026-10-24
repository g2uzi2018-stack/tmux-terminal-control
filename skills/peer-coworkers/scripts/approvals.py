"""Advisory dialog recognition and explicit, screen-bound single decisions.

Recognition is never authorization or a current-version compatibility claim.
Only the observed agy numbered command dialog supports scripted decisions.
"""
import hashlib
import re
import time
import uuid

from common import Tmux, ToolError, send_submit
from records import nonblank, save
from timing import finish_approval


def screen_hash(screen):
    return hashlib.sha256(screen.encode('utf-8')).hexdigest()


def command_dialog(profile, screen):
    if profile != 'agy':
        return None
    lines = screen.rstrip().splitlines()
    # Bound to a current dialog ending at the CLI footer. Text in scrollback or
    # a task quoting a lone approval phrase is insufficient.
    if not lines or not re.match(r'^esc to cancel\s+', lines[-1]):
        return None
    region = lines[-40:]
    if (lines[0] == 'Expanded Tool Permission Editor'
            and any('enter confirm · esc back' in line for line in lines)):
        try:
            start = next(i for i, line in enumerate(lines) if line.strip() == 'Full Command:') + 1
            end = next(i for i in range(start, len(lines)) if re.fullmatch(r'─+', lines[i]))
        except StopIteration:
            return None
        command = '\n'.join(line[4:] if line.startswith('    ') else line for line in lines[start:end]).strip()
        if not command or re.search(r'(?i)(lines? hidden|truncated|⋯)', command):
            return None
        return dict(kind='agy_expanded_command', command=command, source='observed_dialog',
                    command_fully_visible=True, compatibility_verified=False,
                    decisions=['allow-once', 'deny'])
    starts = [i for i, line in enumerate(region) if line.strip() == 'Requesting permission for:']
    if not starts:
        return None
    region = region[starts[-1]:]
    try:
        question = next(i for i, line in enumerate(region) if line.strip() == 'Run this command?')
    except StopIteration:
        return None
    command = '\n'.join(region[1:question]).strip()
    if not command:
        return None
    choices, selected = {}, []
    for line in region[question + 1:]:
        match = re.fullmatch(r'\s*(>)?\s*([1-4])\.\s+(.+?)\s*', line)
        if match:
            number = int(match[2])
            if number in choices:
                return None
            choices[number] = match[3]
            if match[1]:
                selected.append(number)
    if (set(choices) != {1, 2, 3, 4} or len(selected) != 1
            or choices[1] != 'Yes, run command' or choices[4] != 'No, cancel'
            or not choices[2].startswith('Yes, and always allow in this conversation')
            or not choices[3].startswith('Yes, and always allow for commands')):
        return None
    visible = not re.search(r'(?i)(lines? hidden|truncated)', command)
    return dict(kind='agy_command', command=command, selected=selected[0],
                choices=choices, source='observed_dialog', compatibility_verified=False,
                command_fully_visible=visible, expansion_key=None if visible else 'C-g',
                decisions=['allow-once', 'deny'] if visible else ['deny'])


def observe_approval(record, screen, configured=False):
    dialog = command_dialog(record['profile'], screen)
    if dialog is None and not configured:
        # An unrecognized/transient paint is not proof that an uncertain Enter
        # was processed. Keep that delivery evidence until explicit closure.
        if record.get('pending_approval', {}).get('status') != 'uncertain':
            finish_approval(record, 'screen_changed')
        return None
    digest = screen_hash(screen)
    pending = record.get('pending_approval')
    # A changing footer cannot rearm an uncertain submission. Require evidence
    # that the dialog has gone away before recognizing another decision.
    if pending and pending['status'] == 'uncertain':
        return pending
    if (pending and pending['status'] == 'submitted' and dialog
            and pending['dialog'].get('command') == dialog['command']):
        return pending
    if not pending or pending['screen_sha256'] != digest:
        finish_approval(record, 'screen_changed')
        pending = dict(approval_id=uuid.uuid4().hex, screen_sha256=digest,
                       observed_at=time.time(), status='waiting',
                       dialog=dialog or dict(kind='configured_pattern', decisions=[]))
        record['pending_approval'] = pending
    return pending


def decide(run, record, approval_id, digest, decision, evidence):
    from tasks import check_session, within_budget
    nonblank(evidence, 'authorization evidence')
    if decision not in ('allow-once', 'deny') or record.get('closed'):
        raise ToolError('decision requires an open task and allow-once or deny')
    pending = record.get('pending_approval', {})
    if (pending.get('status') != 'waiting' or pending.get('approval_id') != approval_id
            or pending.get('screen_sha256') != digest):
        raise ToolError('no matching unanswered approval; inspect wait/screen, never replay a decision')
    within_budget(record)
    check_session(record)
    tmux = Tmux(record['socket'])
    tmux.alive(record['pane'])
    before = tmux.capture(record['pane'])
    dialog = command_dialog(record['profile'], before)
    if screen_hash(before) != digest or dialog is None:
        raise ToolError('approval screen changed or unsupported dialog; inspect it before deciding')
    if decision == 'allow-once' and not dialog['command_fully_visible']:
        raise ToolError('approval command is collapsed/truncated; expand and inspect it before allowing')
    target = 1 if decision == 'allow-once' else 4
    # Persist before the first terminal side effect, including navigation. A
    # partial failure must not turn a second Enter into a second tool call.
    finish_approval(record, 'uncertain')
    entry = dict(action='approval', approval_id=approval_id, screen_sha256=digest,
                 decision=decision, evidence=evidence, status='uncertain', at=time.time(), round=record['round'])
    record.setdefault('interventions', []).append(entry)
    save(run, record)
    if dialog['kind'] == 'agy_expanded_command':
        entry['reviewed_command_sha256'] = screen_hash(dialog['command'])
        save(run, record)
        tmux.run('send-keys', '-t', record['pane'], '--', 'Escape')
        deadline = time.monotonic() + 1
        while True:
            before = tmux.capture(record['pane'])
            menu = command_dialog(record['profile'], before)
            if menu and menu['kind'] == 'agy_command':
                prefix = menu['command'].split('⋯', 1)[0].strip()
                normalize_command = lambda text: '\n'.join(line.strip() for line in text.splitlines())
                if not normalize_command(dialog['command']).startswith(normalize_command(prefix)):
                    raise ToolError('command changed after expanded inspection; decision remains uncertain')
                dialog = menu
                break
            if time.monotonic() >= deadline:
                raise ToolError('return from expanded editor unconfirmed; decision remains uncertain')
            time.sleep(.02)
    delta = target - dialog['selected']
    if delta:
        tmux.run('send-keys', '-t', record['pane'], '--', *(['Down' if delta > 0 else 'Up'] * abs(delta)))
    # Confirm navigation rather than assuming a fixed initial selection or that
    # the CLI processed the arrow keys synchronously.
    deadline = time.monotonic() + 1
    while True:
        current = tmux.capture(record['pane'])
        current_dialog = command_dialog(record['profile'], current)
        if current_dialog and current_dialog['selected'] == target:
            expected = before if not delta else None
            if expected is None:
                old_lines, new_lines = before.splitlines(), current.splitlines()
                normalize = lambda lines: [re.sub(r'^(\s*)>\s*([1-4])\.', r'\1  \2.', line).strip() for line in lines]
                if normalize(old_lines) != normalize(new_lines):
                    raise ToolError('approval content changed during navigation; decision remains uncertain')
            elif current != expected:
                raise ToolError('approval content changed; decision remains uncertain')
            break
        if time.monotonic() >= deadline:
            raise ToolError('approval navigation unconfirmed; decision remains uncertain, do not resend')
        time.sleep(.02)
    send_submit(tmux, record['pane'], 'Enter', True)
    pending['status'] = 'submitted'
    entry['status'] = 'submitted'
    save(run, record)
    return dict(state=record['state'], approval_id=approval_id, decision=decision, sent=True)
