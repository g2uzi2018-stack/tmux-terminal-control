"""Bounded JSON records and atomic persistence."""
import json
import os
import stat
import tempfile

from common import ToolError


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



def record_limit():
    # Result/config/report callers keep their own smaller explicit bounds.
    from config import load_config
    return load_config().get('snapshot', {}).get('max_record_bytes', 64 * 1024 * 1024)


def read_json(path, limit=None):
    task_record = limit is None
    limit = record_limit() if task_record else limit
    # O_NOFOLLOW prevents accidental result/record symlink traversal on Linux/WSL.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ToolError('JSON must be a bounded regular file')
        if info.st_size > limit:
            raise ToolError('task record exceeds snapshot.max_record_bytes; adjust it in config.json'
                            if task_record else 'JSON exceeds byte limit')
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ToolError('JSON exceeds byte limit')
    return json.loads(data.decode('utf-8'), object_pairs_hook=no_duplicates)



def atomic_json(path, value, limit=None):
    fd, temporary = tempfile.mkstemp(prefix='.write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=True, indent=2)
            stream.write('\n')
            if limit is not None:
                stream.flush()
                if os.fstat(stream.fileno()).st_size > limit:
                    raise ToolError('task record exceeds snapshot.max_record_bytes; adjust it in config.json')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)



def save(run, record):
    atomic_json(run / 'task.json', record, limit=record_limit())
