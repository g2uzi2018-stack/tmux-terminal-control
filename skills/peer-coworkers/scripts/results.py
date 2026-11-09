"""Read the current task handoff and bind its bytes to acceptance."""
import hashlib
from pathlib import Path

from common import ToolError
from records import read_bytes, read_json

HANDOFF_ERRORS = (OSError, ValueError, KeyError, TypeError, ToolError)


def handoff_instructions(path):
    return (
        f'Write your handoff to {path} as UTF-8 Markdown (up to 1 MiB). Use exactly one of DONE, '
        'PARTIAL, BLOCKED, or QUESTION on the first line, followed by your report or question. '
        'Include the outcome, relevant evidence and remaining work. For a review, state the '
        'assessment separately from whether you finished the review. Publish the finished file '
        f'in one write, or rename {path}.tmp into place, then stop.'
    )


def read_handoff(path):
    path = Path(path)
    data = read_bytes(path, 1024 * 1024, 'handoff exceeds 1 MiB')
    status, _, body = data.decode('utf-8').partition('\n')
    status = status.strip()
    if status not in ('DONE', 'PARTIAL', 'BLOCKED', 'QUESTION') or not body.strip():
        raise ToolError('handoff needs a status line (DONE, PARTIAL, BLOCKED or QUESTION) and a body')
    return dict(status=status, path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def historical_result(record):
    """Read a closed run's original JSON without reopening its lifecycle."""
    if 'result' in record:
        return record['result']
    value = read_json(Path(record['result_path']), 16384)
    if any(value[key] != record[key] for key in ('task_id', 'attempt_id', 'round')):
        raise ToolError('historical result belongs to a different submission')
    if value['handoff']['STATUS'] not in ('DONE', 'PARTIAL', 'BLOCKED'):
        raise ToolError('invalid historical result status')
    return value
