"""Recognize submitted follow-ups still queued in the CLI."""
import hashlib
import json
from pathlib import Path
import re
import uuid

from records import read_bytes
from results import HANDOFF_ERRORS, read_handoff
from approvals import screen_hash

ACTIVITY = re.compile(r'([ \t]*)([\u2800-\u28ff]+)([ \t]+)(Running|Thinking|Reading|Working)([ \t]+)(\d+(?:\.\d+)?[kKmM]?)( tokens[ \t]*)')


def reply_pointer(record):
    return 'Read ' + json.dumps(record['reply_file'], ensure_ascii=False) + ' and follow the feedback.'


def cursor_reply_queue(record, screen):
    if record['profile'] != 'cursor' or not record.get('reply_file'):
        return False
    lines = [line.strip() for line in screen.splitlines() if line.strip()]
    starts = [i for i, line in enumerate(lines) if re.fullmatch(r'┌─ follow-ups ─+┐', line)]
    if not starts:
        return False
    tail = lines[starts[-1]:]
    tail = [line for i, line in enumerate(tail) if i < 4 or not (line.startswith('Tip: ') or re.fullmatch(r'\d+ tasks?', line))]
    pointer = reply_pointer(record)
    cwd_footer = tail[-1]
    if cwd_footer.startswith('~/'):
        cwd_footer = str(Path.home()) + cwd_footer[1:]
    return (len(tail) == 8
            and re.fullmatch(r'│ ○ ' + re.escape(pointer) + r'\s*│', tail[1]) is not None
            and re.fullmatch(r'│ enter steer · ↑ select/edit · esc cancel\s*│', tail[2]) is not None
            and re.fullmatch(r'└─+┘', tail[3]) is not None
            and ACTIVITY.fullmatch(tail[4]) is not None
            and re.fullmatch(r'→ Add a follow-up\s+ctrl\+c to stop', tail[5]) is not None
            and (cwd_footer == record['cwd'] or cwd_footer.startswith(record['cwd'] + ' · ')))


def cursor_reply_binding(record, screen):
    """Ignore only the recognized queue footer's spinner and numeric token count."""
    if not cursor_reply_queue(record, screen):
        return None
    lines = screen.splitlines(keepends=True)
    visible = [(i, line.strip()) for i, line in enumerate(lines) if line.strip()]
    start = max(j for j, (_, line) in enumerate(visible) if re.fullmatch(r'┌─ follow-ups ─+┐', line))
    footer = next(i for i, line in visible[start + 4:]
                  if not (line.startswith('Tip: ') or re.fullmatch(r'\d+ tasks?', line)))
    raw = lines[footer].rstrip('\r\n')
    match = ACTIVITY.fullmatch(raw)
    lines[footer] = (match[1] + '<spinner>' + match[3] + match[4] + match[5]
                     + '<tokens>' + match[7] + lines[footer][len(raw):])
    return screen_hash(''.join(lines))


def reply_acknowledged(record):
    try:
        read_handoff(record['result_path'])
    except HANDOFF_ERRORS:
        return False
    return True


def reply_hash(record):
    return hashlib.sha256(read_bytes(Path(record['reply_file']), 65536)).hexdigest()


def steer_attempted(record):
    return any(item['action'] == 'reply_steer' and item.get('reply_file') == record.get('reply_file')
               for item in record.get('interventions', []))


def observe_reply_queue(record, screen):
    if record['state'] != 'running' or not record.get('reply_file') or reply_acknowledged(record):
        return {}
    if record['profile'] == 'agy':
        lines = screen.rstrip().splitlines()
        prefix = '▸ Read ' + json.dumps(record['reply_file'], ensure_ascii=False)
        if (lines and re.match(r'^\s*Press up to edit queued messages\s+', lines[-1])
                and any(line.startswith(prefix) and '(alt+m to send immediately)' in line for line in lines)):
            return dict(reason='reply_queued')
        return {}
    binding = cursor_reply_binding(record, screen)
    if not binding:
        return {}
    if steer_attempted(record):
        return dict(reason='reply_queued')
    digest, content = screen_hash(screen), reply_hash(record)
    pending = record.get('pending_steer', {})
    if (pending.get('binding'), pending.get('reply_sha256')) != (binding, content):
        pending = dict(steer_id=uuid.uuid4().hex, screen_sha256=digest,
                       binding=binding, reply_sha256=content)
        record['pending_steer'] = pending
        # The caller already holds the run lock; wait persists the token.
    return dict(reason='reply_queued', reply_steer=pending)
