"""Workspace snapshots and scope reporting."""
import hashlib
import os
from pathlib import Path
import stat
import subprocess

from common import ToolError
from records import nonblank


def git(cwd, *args):
    process = subprocess.run(['git', '-C', str(cwd), *args], capture_output=True, timeout=10)
    if process.returncode:
        raise ToolError('Git query failed: ' + process.stderr.decode('utf-8', 'replace').strip())
    return process.stdout



def snapshot(cwd, previous=None, limits=None):
    """Opaque submodules and special entries; stat caching is an optimization, not a sandbox."""
    if limits is None:
        from config import load_config
        limits = load_config().get('snapshot', {})
    max_files = limits.get('max_files', 50000)
    max_bytes = limits.get('max_bytes', 256 * 1024 * 1024)
    paths = set(git(cwd, 'ls-files', '-z', '--cached', '--others', '--exclude-standard').split(b'\0')) - {b''}
    if len(paths) > max_files:
        raise ToolError('workspace file limit exceeded; adjust snapshot.max_files in config.json')
    gitlinks = {}
    for entry in git(cwd, 'ls-files', '--stage', '-z').split(b'\0'):
        if not entry:
            continue
        metadata, raw = entry.split(b'\t', 1)
        mode, commit, stage = metadata.split()
        if mode == b'160000':
            gitlinks[raw] = commit.decode('ascii')
    # Git omits untracked FIFOs and sockets. Discover those without opening them,
    # respecting ignored directories and treating submodules as opaque.
    ignored_dirs = {os.fsdecode(raw).rstrip('/') for raw in
                    git(cwd, 'ls-files', '--others', '--ignored', '--exclude-standard',
                        '--directory', '-z').split(b'\0') if raw.endswith(b'/')}
    special = set()
    for directory, directories, names in os.walk(cwd, followlinks=False):
        relative = Path(directory).relative_to(cwd)
        directories[:] = [name for name in directories if name != '.git'
                          and (relative / name).as_posix() not in ignored_dirs
                          and os.fsencode((relative / name).as_posix()) not in gitlinks]
        for name in names:
            path = Path(directory) / name
            try:
                mode = path.lstat().st_mode
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(mode) and not stat.S_ISLNK(mode):
                special.add(os.fsencode(path.relative_to(cwd)))
    if special:
        ignored = subprocess.run(['git', '-C', str(cwd), 'check-ignore', '-z', '--stdin'],
                                 input=b'\0'.join(special) + b'\0', capture_output=True, timeout=10)
        if ignored.returncode not in (0, 1):
            raise ToolError('Git special-entry ignore query failed')
        paths.update(special - set(ignored.stdout.split(b'\0')))
        if len(paths) > max_files:
            raise ToolError('workspace file limit exceeded; adjust snapshot.max_files in config.json')
    files, stamps, total = {}, {}, 0
    previous = previous or {}
    for raw in sorted(paths):
        name = os.fsdecode(raw)
        path = cwd / name
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if raw in gitlinks:
            if (path / '.git').exists():
                status = git(path, 'status', '--porcelain', '-z', '--untracked-files=normal')
                head = git(path, 'rev-parse', 'HEAD').decode('ascii').strip()
                files[name] = [0o160000, gitlinks[raw], head, hashlib.sha256(status).hexdigest()]
            else:
                files[name] = [0o160000, gitlinks[raw], 'uninitialized']
            continue
        stamp = [info.st_size, info.st_mtime_ns, info.st_ino, info.st_ctime_ns, info.st_dev, info.st_mode]
        if stat.S_ISREG(info.st_mode):
            total += info.st_size
            if total > max_bytes:
                raise ToolError('workspace byte limit exceeded; adjust snapshot.max_bytes in config.json')
        if previous.get('stats', {}).get(name) == stamp and name in previous.get('files', {}):
            files[name] = previous['files'][name]
        elif stat.S_ISLNK(info.st_mode):
            files[name] = [info.st_mode, hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()]
        elif stat.S_ISREG(info.st_mode):
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
            # Refuse a torn snapshot instead of caching content under stale metadata.
            after = path.lstat()
            if (after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_ino) != (
                    info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_ino):
                raise ToolError('workspace changed during snapshot; retry inspection')
            files[name] = [info.st_mode, digest.hexdigest()]
        else:
            files[name] = [stat.S_IFMT(info.st_mode), 'special']
        stamps[name] = stamp
    head = subprocess.run(['git', '-C', str(cwd), 'rev-parse', '--verify', 'HEAD'],
                          capture_output=True, timeout=5)
    branch = subprocess.run(['git', '-C', str(cwd), 'symbolic-ref', '--quiet', 'HEAD'],
                            capture_output=True, timeout=5)
    if branch.returncode not in (0, 1):
        raise ToolError('Git branch query failed')
    return dict(files=files, stats=stamps, head=head.stdout.decode().strip(),
                branch=branch.stdout.decode().strip(),
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
    baseline = record['baseline']
    current = snapshot(Path(record['cwd']), previous=baseline)
    changed = sorted(path for path in baseline['files'].keys() | current['files'].keys()
                     if baseline['files'].get(path) != current['files'].get(path))
    owned = record['owned_paths']
    violations = [path for path in changed if not any(
        scope == '.' or path == scope or path.startswith(scope + '/') for scope in owned)]
    git_changed = any(baseline[field] != current[field] for field in ('head', 'branch', 'index'))
    return dict(changed_paths=changed, scope_violations=violations,
                git_state_changed=git_changed,
                scope_check_exclusions=record.get('scope_check_exclusions', [])), current
