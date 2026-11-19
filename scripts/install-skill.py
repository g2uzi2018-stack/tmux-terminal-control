#!/usr/bin/env python3
"""Install peer-coworkers skill by backing up any existing installation and copying files."""
import argparse, os, shutil, sys, tempfile, uuid
from datetime import datetime, timezone
from pathlib import Path

REQUIRED = ('LICENSE', 'NOTICE', 'SKILL.md', 'references/model-selection.md',
            'scripts/cowork.py', 'scripts/profiles.py', 'scripts/audit.py')

def install(destination):
    root, dest = Path(__file__).resolve().parents[1], destination.expanduser().absolute()
    dest.parent.mkdir(parents=True, exist_ok=True)
    backup, staging = None, Path(tempfile.mkdtemp(prefix='.peer-coworkers-install-', dir=dest.parent))
    try:
        shutil.copytree(root / 'skills' / 'peer-coworkers', staging, dirs_exist_ok=True, symlinks=False,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for name in ('LICENSE', 'NOTICE'):
            shutil.copyfile(root / name, staging / name)
        for rel in REQUIRED:
            if not (staging / rel).is_file():
                raise RuntimeError(f'missing package file: {rel}')
        if dest.exists() or dest.is_symlink():
            backups = dest.parent / '.peer-coworkers-backups'
            backups.mkdir(exist_ok=True)
            backup = backups / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8])
            dest.rename(backup)
        try:
            staging.rename(dest)
        except OSError:
            if backup is not None:
                backup.rename(dest)
            raise
        return dest, backup
    finally:
        if staging.exists():
            shutil.rmtree(staging)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dest', type=Path, default=Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'skills' / 'peer-coworkers')
    try:
        dest, backup = install(p.parse_args().dest)
        print(f'Installed: {dest}' + (f'\nBacked up previous: {backup}' if backup else ''))
        return 0
    except (OSError, RuntimeError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
