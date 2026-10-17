#!/usr/bin/env python3
"""Install a standalone peer-coworkers package without changing global CLI configuration."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid


def install(destination):
    source = Path(__file__).resolve().parents[1] / 'skills' / 'peer-coworkers'
    destination = destination.expanduser().absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    staging = Path(tempfile.mkdtemp(prefix='.peer-coworkers-install-', dir=destination.parent))
    try:
        # Repository transport links are materialized: the installed skill needs no sibling.
        shutil.copytree(source, staging, dirs_exist_ok=True, symlinks=False,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        required = ['SKILL.md', 'scripts/cowork.py', 'scripts/common.py', 'scripts/session.py',
                    'scripts/input.py', 'scripts/wait.py', 'scripts/profiles.py']
        for name in required:
            if not (staging / name).is_file():
                raise RuntimeError('missing package file: ' + name)
        if destination.exists() or destination.is_symlink():
            backups = destination.parent / '.peer-coworkers-backups'
            backups.mkdir(exist_ok=True)
            backup = backups / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex)
            destination.rename(backup)
        try:
            staging.rename(destination)
        except OSError:
            if backup is not None:
                backup.rename(destination)
            raise
        return destination, backup
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dest', type=Path, default=Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'skills' / 'peer-coworkers')
    args = parser.parse_args()
    try:
        destination, backup = install(args.dest)
        print('Installed: ' + str(destination))
        if backup:
            print('Previous installation backed up: ' + str(backup))
        print('Available on the next turn. Global config and legacy tmux-tui were preserved.')
        return 0
    except (OSError, RuntimeError) as exc:
        print('error: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
