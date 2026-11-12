"""Advisory dialog recognition and explicit, screen-bound single decisions.

Recognition is never authorization or a current-version compatibility claim.
Observed agy menus and Cursor one-time shell menus support explicit decisions.
"""
import hashlib
from pathlib import Path
import re
import time
import uuid

from common import Tmux, ToolError, send_submit
from records import nonblank, save, terminal_event
from snapshot import within_scope
from timing import finish_approval


def screen_hash(screen):
    return hashlib.sha256(screen.encode('utf-8')).hexdigest()


def cursor_command_dialog(screen):
    """Recognize the observed Cursor one-time shell approval, without granting it."""
    lines = screen.rstrip().splitlines()
    if lines and lines[-1].strip() == 'ctrl+r to review changed files':
        lines.pop()
    questions = [i for i, line in enumerate(lines) if line.strip() == 'Run this command?']
    if not questions:
        return None
    question = questions[-1]
    tail = [line.strip() for line in lines[question + 1:] if line.strip()]
    if (len(tail) != 5 or not tail[0].startswith('Not in allowlist:')
            or tail[1] != '→ Run (once) (y)'
            or not re.fullmatch(r'Add Shell\(.+\) to allowlist\? \(tab\)', tail[2])
            or tail[3] != 'Run Everything (shift+tab)'
            or tail[4] != 'Skip & tell the agent what to do instead (esc or n)'):
        return None
    # The card separator starts in column one. Continuation rows in the
    # preview are indented even when the command contains its own rule line.
    separators = [i for i, line in enumerate(lines[:question]) if re.fullmatch(r'─+', line)]
    if not separators:
        return None
    body = lines[separators[-1] + 1:question]
    while body and not body[0].strip():
        body.pop(0)
    first = re.fullmatch(r' \$ +(.+)', body[0]) if body else None
    if first is None:
        return None
    while not body[-1].strip():
        body.pop()
    command = '\n'.join([first[1], *body[1:]])
    visible = (all(not row.strip() or row.startswith('    ') for row in body[1:])
               and re.search(r' in \S[^\n]*$', command) is not None
               and not re.search(r'(?i)(\d+ (?:input )?lines? hidden|truncated|[⋯…]|\.\.\.)', command))
    return dict(kind='cursor_command', command=command, selected=1, choices=tail,
                source='observed_dialog', compatibility_verified=False,
                command_fully_visible=visible,
                decisions=['allow-once', 'deny'] if visible else ['deny'])


def numbered_menu(rows, wrapped=()):
    choices, selected, number = {}, [], None
    for row in rows:
        match = re.fullmatch(r'\s*(>)?\s*(\d+)\.\s+(.+?)\s*', row)
        if not match:
            if number not in wrapped:
                return {}, None
            choices[number] += '\n' + row
            continue
        number = int(match[2])
        if number != len(choices) + 1:
            return {}, None
        choices[number] = match[3]
        if match[1]:
            selected.append(number)
    return choices, selected[0] if len(selected) == 1 else None


def command_dialog(profile, screen):
    if profile == 'cursor':
        return cursor_command_dialog(screen)
    if profile != 'agy':
        return None
    lines = screen.rstrip().splitlines()
    # Bound to a current dialog ending at the CLI footer. Text in scrollback or
    # a task quoting a lone approval phrase is insufficient.
    if not lines or not re.match(r'^esc to cancel\s+', lines[-1]):
        return None
    region = lines[-40:]
    tail = [line.strip() for line in lines if line.strip()]
    if (lines[0] == 'Expanded Tool Permission Editor' and len(tail) >= 2
            and tail[-2].startswith('enter confirm · esc back')):
        try:
            start = next(i for i, line in enumerate(lines) if line.strip() == 'Full Command:') + 1
            end = next(i for i in range(start, len(lines)) if re.fullmatch(r'─+', lines[i]))
        except StopIteration:
            return None
        command = '\n'.join(line[4:] if line.startswith('    ') else line for line in lines[start:end]).strip()
        if not command:
            return None
        # The native Full Command pane can paginate without a "hidden" label.
        # Its visible slice is not the full command, even inside this editor.
        visible = (not re.search(r'(?i)(lines? hidden|truncated|[⋯…])', command)
                   and not re.search(r'(?m)^\s*\(\d+[–-]\d+ of \d+ lines?\)\s*$', command))
        return dict(kind='agy_expanded_command', command=command, source='observed_dialog',
                    command_fully_visible=visible, compatibility_verified=False,
                    decisions=['allow-once', 'deny'] if visible else ['deny'])
    starts = [i for i, line in enumerate(region) if line.strip() == 'Requesting permission for:']
    if not starts:
        return None
    region = region[starts[-1]:]
    try:
        question = next(i for i, line in enumerate(region) if line.strip() == 'Run this command?')
    except StopIteration:
        return None
    command_rows = region[1:question]
    while command_rows and not command_rows[-1].strip():
        command_rows.pop()
    command = '\n'.join(command_rows).strip()
    if not command:
        return None
    tail = [line.strip() for line in region[question + 1:-1] if line.strip()]
    if not tail or tail[-1] != '↑/↓ Navigate · tab Amend · ctrl+g edit/expand command':
        return None
    choices, selected = numbered_menu(tail[:-1], wrapped=(2, 3))
    if (set(choices) != {1, 2, 3, 4} or selected is None
            or choices[1] != 'Yes, run command' or choices[4] != 'No, cancel'
            or not choices[2].startswith('Yes, and always allow in this conversation')
            or not choices[3].startswith('Yes, and always allow for commands')):
        return None
    visible = not re.search(r'(?i)(lines? hidden|truncated)', command)
    return dict(kind='agy_command', command=command, command_rows=command_rows, selected=selected,
                choices={str(key): label for key, label in choices.items()}, source='observed_dialog', compatibility_verified=False,
                command_fully_visible=visible, expansion_key=None if visible else 'C-g',
                decisions=['allow-once', 'deny'] if visible else ['deny'])


def agy_returned_command_matches(expanded, menu, original_menu=None):
    """Check the preview prefix and, when recorded, the exact pre-expansion card."""
    if original_menu is not None and menu != dict(original_menu, selected=menu['selected']):
        return False
    rows = menu['command_rows']
    logical_lines = expanded['command'].split('\n')
    marker = re.fullmatch(r'   ⋯ \(([1-9][0-9]*) lines? hidden\)', rows[-1])
    if marker:
        rows = rows[:-1]
        if expanded['command_fully_visible'] and original_menu is None:
            hidden = int(marker[1])
            if hidden >= len(logical_lines):
                return False
            logical_lines = logical_lines[:-hidden]
    elif not menu['command_fully_visible']:
        return False
    row = 0
    for logical in logical_lines:
        if row == len(rows):
            return bool(rows) and bool(marker) and (original_menu is not None or not expanded['command_fully_visible'])
        # tmux captures agy's blank logical line without the display padding.
        if rows[row] == logical == '':
            row += 1
            continue
        if not rows[row].startswith('   '):
            return False
        displayed = rows[row][3:]
        row += 1
        while displayed != logical:
            # agy prefixes logical lines with three spaces, but puts a wrapped
            # word on an unindented row and omits the single space at the break.
            if (not displayed or not logical.startswith(displayed + ' ') or row == len(rows)
                    or not rows[row] or rows[row][0].isspace()):
                return False
            displayed += ' ' + rows[row]
            row += 1
    return bool(rows) and row == len(rows)


def file_edit_dialog(profile, screen):
    """Recognize the observed two-choice edit card, including incomplete diffs.

    A missing/truncated diff may be rejected but must never be accepted. Counts
    bind approval to all changed lines, not just the visible tail of a large edit.
    """
    if profile != 'agy':
        return None
    lines = screen.rstrip().splitlines()
    if not lines or not re.match(r'^esc to cancel\s+', lines[-1]):
        return None
    starts = [i for i, line in enumerate(lines) if line in ('Pending edit', 'Create file')]
    if not starts:
        return None
    region = lines[starts[-1]:]
    creating = region[0] == 'Create file'
    try:
        question = region.index('Allow creation of this file?' if creating else 'Accept this file edit?')
    except ValueError:
        return None
    header_pattern = r'(/.+?)\s+\+(\d+)' if creating else r'(/.+?)\s+\+(\d+)\s+-(\d+)'
    headers = [(i, re.fullmatch(header_pattern, line))
               for i, line in enumerate(region[1:question], 1)]
    headers = [(i, match) for i, match in headers if match]
    if len(headers) != 1:
        return None
    header, match = headers[0]
    path, additions, deletions = match[1], int(match[2]), 0 if creating else int(match[3])
    if '..' in Path(path).parts or '\x00' in path:
        return None
    tail = [line.strip() for line in region[question + 1:-1] if line.strip()]
    footer = '↑/↓ Navigate · tab Amend · f full diff'
    if len(tail) != 3 or (tail[-1] != footer and not (creating and tail[-1] == '↑/↓ Navigate · f full diff')):
        return None
    choices, selected = numbered_menu(tail[:-1])
    expected = {1: 'Yes, allow creation', 2: 'No, deny creation'} if creating else {
        1: 'Yes, accept this change', 2: 'No, reject this change'}
    if choices != expected or selected is None:
        return None
    diff = '\n'.join(region[header + 1:question]).strip()
    # The shortcut hint isn't part of the patch identity.
    diff = diff.removesuffix('shift+tab to auto-approve file edits').rstrip()
    markers = re.findall(r'^\s*\d+\s+([+-])(?:\s|$)', diff, re.MULTILINE)
    complete = (len(diff.encode('utf-8')) <= 32768 and additions + deletions > 0
                and markers.count('+') == additions and markers.count('-') == deletions
                and not re.search(r'(?im)^\s*(?:[⋯…].*|.*\(\d+ lines? hidden\)|.*\btruncated\b)\s*$', diff))
    if creating and complete:
        rows = [re.fullmatch(r'\s*(\d+)\s+\+(?:[ \t]+.*)?', row) for row in diff.splitlines()]
        complete = len(rows) == additions and all(
            row and int(row[1]) == number for number, row in enumerate(rows, 1))
    return dict(kind='agy_file_create' if creating else 'agy_file_edit', path=path, diff=diff,
                diff_sha256=screen_hash(diff), additions=additions, deletions=deletions,
                diff_fully_visible=complete, selected=selected, choices={str(key): label for key, label in choices.items()},
                source='observed_dialog', compatibility_verified=False,
                inspection_command=None if complete else 'inspect-diff',
                decisions=['allow-once', 'deny'] if complete else ['deny'])


def file_read_dialog(profile, screen):
    """Recognize the observed agy one-file, outside-workspace Read card."""
    if profile != 'agy':
        return None
    lines = [line.strip() for line in screen.splitlines() if line.strip()]
    starts = [i for i, line in enumerate(lines) if line == 'File access']
    if not starts:
        return None
    card = lines[starts[-1]:]
    if (len(card) != 10 or not re.fullmatch(r'─+', card[1])
            or card[3:5] != ['Reason: outside workspace', 'Allow access to this file?']
            or card[8] != '↑/↓ Navigate' or not re.match(r'^esc to cancel\s+', card[9])):
        return None
    path = card[2].removeprefix('Read: ')
    if (not card[2].startswith('Read: /') or '…' in path or '⋯' in path or '...' in path
            or any(ord(char) < 32 or ord(char) == 127 for char in path)):
        return None
    choices = {1: 'Yes, allow access', 2: 'Yes, and always allow non-workspace access', 3: 'No, deny access'}
    selected = []
    for number, line in enumerate(card[5:8], 1):
        if line.removeprefix('> ') != f'{number}. {choices[number]}':
            return None
        if line.startswith('> '):
            selected.append(number)
    if len(selected) != 1:
        return None
    return dict(kind='agy_file_read', path=path, selected=selected[0], choices={str(key): label for key, label in choices.items()},
                source='observed_dialog', compatibility_verified=False,
                decisions=['allow-once', 'deny'])


def check_read_path(path):
    target = Path(path)
    if str(target.resolve(strict=True)) != path or not target.is_file():
        raise ToolError('file read allowance requires a canonical path to one regular file')


def approval_dialog(profile, screen):
    return file_read_dialog(profile, screen) or file_edit_dialog(profile, screen) or command_dialog(profile, screen)


def same_operation(first, second):
    if first.get('kind') == second.get('kind') == 'agy_file_read':
        return first['path'] == second['path']
    if first.get('kind') == second.get('kind') and first.get('kind') in ('agy_file_edit', 'agy_file_create'):
        return (first['path'], first['diff_sha256']) == (second['path'], second['diff_sha256'])
    command_kinds = {'agy_command', 'agy_expanded_command', 'cursor_command'}
    return (first.get('kind') in command_kinds and second.get('kind') in command_kinds
            and first['command'] == second['command'])


def check_edit_scope(record, path):
    """Check the current target again before acceptance; never broaden CLI grants."""
    target = Path(path)
    if not target.is_absolute() or '..' in target.parts:
        raise ToolError('edit path must be absolute and contain no parent traversal')
    result = Path(record['result_path'])
    run = result.parent.resolve()
    controls = {result.name, result.name + '.tmp'}
    root = Path(record['cwd'])
    for candidate in (target, target.resolve()):
        if candidate.name in controls and candidate.parent.resolve() == run:
            continue
        if (not candidate.is_relative_to(root) or '.git' in candidate.relative_to(root).parts
                or not within_scope(candidate.relative_to(root).as_posix(), record['owned_paths'])):
            raise ToolError('file edit is outside the handoff and owned workspace paths')


def observe_approval(record, screen, configured=False):
    dialog = approval_dialog(record['profile'], screen)
    if dialog is None and not configured:
        # An unrecognized/transient paint is not proof that an uncertain Enter
        # was processed. Keep that delivery evidence until explicit closure.
        if record.get('pending_approval', {}).get('status') != 'uncertain':
            finish_approval(record, 'screen_changed')
        return None
    pending = record.get('pending_approval')
    # An explicit cancellation followed by a different, complete command card
    # can establish a new approval. Keep the original uncertain attempt intact.
    if pending and pending['status'] == 'uncertain':
        attempts = [item for item in record.get('interventions', [])
                    if item.get('action') == 'approval' and item.get('approval_id') == pending['approval_id']]
        cancelled = attempts and any(item.get('action') == 'keys' and item.get('keys') == ['Escape']
                                    and item.get('status') == 'sent' and item['at'] > attempts[-1]['at']
                                    for item in record.get('interventions', []))
        if not (cancelled and dialog and pending['dialog']['kind'] == 'agy_expanded_command'
                and dialog['kind'] == 'agy_command' and dialog['command_fully_visible']
                and not agy_returned_command_matches(pending['dialog'], dialog, pending.get('original_menu'))):
            return pending
    if (pending and pending['status'] == 'submitted' and dialog
            and same_operation(pending['dialog'], dialog)):
        return pending
    dialog = dialog or dict(kind='configured_pattern', decisions=[])
    if not pending or pending['status'] != 'waiting' or pending['dialog'] != dialog:
        original_menu = None
        if (pending and pending['status'] == 'waiting' and pending['dialog']['kind'] == 'agy_command'
                and dialog['kind'] == 'agy_expanded_command'
                and agy_returned_command_matches(dialog, pending['dialog'], pending['dialog'])):
            original_menu = pending['dialog']
        finish_approval(record, 'screen_changed')
        pending = dict(approval_id=uuid.uuid4().hex, screen_sha256=screen_hash(screen),
                       observed_at=time.time(), status='waiting', dialog=dialog)
        if original_menu is not None:
            pending['original_menu'] = original_menu
        record['pending_approval'] = pending
    return pending


def reviewed_dialog(record, approval_id):
    from tasks import check_session, within_budget
    pending = record.get('pending_approval', {})
    if record['closed'] or pending.get('status') != 'waiting' or pending.get('approval_id') != approval_id:
        raise ToolError('no matching unanswered approval; inspect wait and never replay')
    within_budget(record)
    check_session(record)
    tmux = Tmux(record['socket'])
    tmux.alive(record['pane'])
    screen = tmux.capture(record['pane'])
    dialog = approval_dialog(record['profile'], screen)
    if dialog is None or dialog != pending['dialog']:
        raise ToolError('approval changed or unsupported; inspect wait again')
    return tmux, screen, dialog, pending


def inspect_diff(run, record, approval_id):
    """Open the read-only viewer once and return a larger approval card."""
    tmux, before, dialog, _ = reviewed_dialog(record, approval_id)
    if dialog['kind'] not in ('agy_file_edit', 'agy_file_create'):
        raise ToolError('inspect-diff requires an agy file approval')
    check_edit_scope(record, dialog['path'])
    if dialog['diff_fully_visible']:
        raise ToolError('diff is already fully visible; review the current approval')
    finish_approval(record, 'uncertain')
    entry = dict(action='inspect_diff', approval_id=approval_id, screen_sha256=screen_hash(before),
                 path=dialog['path'], status='uncertain', at=time.time())
    record.setdefault('interventions', []).append(entry)
    save(run, record)
    if approval_dialog(record['profile'], tmux.capture(record['pane'])) != dialog:
        raise ToolError('file approval changed; inspection remains uncertain')
    tmux.run('send-keys', '-t', record['pane'], '-l', '--', 'f')

    def capture_until(predicate, diagnostic):
        deadline = time.monotonic() + 2
        while True:
            current = tmux.capture(record['pane'])
            if predicate(current):
                return current
            if time.monotonic() >= deadline:
                raise ToolError(diagnostic + '; inspection remains uncertain, do not resend')
            time.sleep(.02)

    def viewer(screen):
        lines = screen.rstrip().splitlines()
        return (len(lines) >= 3 and re.search(r'\s+change 1/1$', lines[0])
                and lines[-2].strip() == 'n/N next/prev diff · / search · ←/→ cycle file · c comment · d delete comment · esc back'
                and re.match(r'^esc to cancel\s+', lines[-1]))

    capture_until(viewer, 'full diff viewer not confirmed')
    tmux.run('resize-window', '-t', record['pane'], '-y', '200')
    # Wait for the repaint, not merely the resize command's exit status.
    previous = None
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        current = tmux.capture(record['pane'])
        if viewer(current) and current == previous:
            break
        previous = current
        time.sleep(.08)
    else:
        raise ToolError('expanded viewer repaint unconfirmed; inspection remains uncertain')
    terminal_event(run, record, 'full_diff_inspection', current)
    entry['viewer_sha256'] = screen_hash(current)
    save(run, record)
    tmux.run('send-keys', '-t', record['pane'], '--', 'Escape')
    after = capture_until(lambda s: file_edit_dialog(record['profile'], s) is not None,
                          'return to file approval not confirmed')
    returned = file_edit_dialog(record['profile'], after)
    if any(returned[key] != dialog[key] for key in ('kind', 'path', 'additions', 'deletions')):
        raise ToolError('file target changed during inspection; inspection remains uncertain')
    prefix = re.split(r'(?m)^\s*… \d+ more lines \(f for full diff\)\s*$', dialog['diff'])[0].rstrip()
    if not returned['diff'].startswith(prefix):
        raise ToolError('visible patch changed during inspection; inspection remains uncertain')
    entry['status'] = 'inspected'
    # Retire the old token even when a repaint has an identical screen hash.
    record.pop('pending_approval')
    approval = observe_approval(record, after)
    path = terminal_event(run, record, 'approval', after)
    save(run, record)
    return dict(approval=approval, screen=after, terminal_events_path=path,
                next_action='Review the returned full card and use its new token for decision; '
                            'if still clipped, only deny is supported. The task window remains 200 rows.')


def decide(run, record, approval_id, decision, evidence):
    from tasks import within_budget
    nonblank(evidence, 'authorization evidence')
    tmux, before, dialog, pending = reviewed_dialog(record, approval_id)
    editing = dialog['kind'] in ('agy_file_edit', 'agy_file_create')
    reading = dialog['kind'] == 'agy_file_read'
    if decision == 'allow-once':
        if reading:
            check_read_path(dialog['path'])
        elif editing:
            if not dialog['diff_fully_visible']:
                raise ToolError('file diff is incomplete/truncated; inspect full diff before allowing')
            check_edit_scope(record, dialog['path'])
        elif not dialog['command_fully_visible']:
            raise ToolError('approval command is collapsed/truncated; expand and inspect it before allowing')
    target = 1 if decision == 'allow-once' else (3 if reading else 2 if editing else 4)
    # Persist before the first terminal side effect, including navigation. A
    # partial failure must not turn a second Enter into a second tool call.
    finish_approval(record, 'uncertain')
    entry = dict(action='approval', approval_id=approval_id, screen_sha256=pending['screen_sha256'],
                 decision=decision, evidence=evidence, status='uncertain', at=time.time())
    record.setdefault('interventions', []).append(entry)
    entry['dialog_kind'] = dialog['kind']
    if editing:
        entry.update(path=dialog['path'], diff_sha256=dialog['diff_sha256'])
    if reading:
        entry['path'] = dialog['path']
    terminal_event(run, record, 'approval_decision', before)
    save(run, record)
    if dialog['kind'] == 'cursor_command':
        if approval_dialog(record['profile'], tmux.capture(record['pane'])) != dialog:
            raise ToolError('Cursor approval changed; decision remains uncertain')
        if decision == 'allow-once':
            tmux.run('send-keys', '-t', record['pane'], '-l', '--', 'y')
        else:
            tmux.run('send-keys', '-t', record['pane'], '--', 'Escape')
        pending['status'] = 'submitted'
        entry['status'] = 'submitted'
        save(run, record)
        return dict(state=record['state'], approval_id=approval_id, decision=decision, sent=True)
    expanded_review = None
    if dialog['kind'] == 'agy_expanded_command':
        expanded_review = dialog
        entry['reviewed_command_sha256'] = screen_hash(dialog['command'])
        save(run, record)
        tmux.run('send-keys', '-t', record['pane'], '--', 'Escape')
        deadline = time.monotonic() + 1
        while True:
            before = tmux.capture(record['pane'])
            menu = command_dialog(record['profile'], before)
            if menu and menu['kind'] == 'agy_command':
                if not agy_returned_command_matches(dialog, menu, pending.get('original_menu')):
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
        current_dialog = approval_dialog(record['profile'], current)
        if current_dialog and current_dialog['selected'] == target:
            if expanded_review and (current_dialog['kind'] != 'agy_command'
                                    or not agy_returned_command_matches(expanded_review, current_dialog, pending.get('original_menu'))):
                raise ToolError('reviewed command changed during navigation; decision remains uncertain')
            if current_dialog != dict(dialog, selected=target):
                raise ToolError('approval content changed during navigation; decision remains uncertain')
            break
        if time.monotonic() >= deadline:
            raise ToolError('approval navigation unconfirmed; decision remains uncertain, do not resend')
        time.sleep(.02)
    if decision == 'allow-once':
        if reading:
            check_read_path(current_dialog['path'])
        elif editing:
            check_edit_scope(record, current_dialog['path'])
    within_budget(record)
    send_submit(tmux, record['pane'], 'Enter', True)
    pending['dialog'] = current_dialog
    pending['status'] = 'submitted'
    entry['status'] = 'submitted'
    save(run, record)
    return dict(state=record['state'], approval_id=approval_id, decision=decision, sent=True)
