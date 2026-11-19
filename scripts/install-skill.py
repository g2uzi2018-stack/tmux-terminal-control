#!/usr/bin/env python3
"""Install peer-coworkers skill to Codex skills directory, overwriting any existing copy."""
import argparse, os, shutil, sys, tempfile, uuid
from pathlib import Path

REQUIRED = ('LICENSE', 'NOTICE', 'SKILL.md', 'references/model-selection.md',
            'scripts/cowork.py', 'scripts/profiles.py', 'scripts/audit.py')

def install(destination):
    root, dest = Path(__file__).resolve().parents[1], destination.expanduser().absolute()
    dest.parent.mkdir(parents=True, exist_ok=True)
    old, staging = None, Path(tempfile.mkdtemp(prefix='.peer-coworkers-install-', dir=dest.parent))
    try:
        shutil.copytree(root / 'skills' / 'peer-coworkers', staging, dirs_exist_ok=True, symlinks=False,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for name in ('LICENSE', 'NOTICE'):
            shutil.copyfile(root / name, staging / name)
        for rel in REQUIRED:
            if not (staging / rel).is_file():
                raise RuntimeError(f'missing package file: {rel}')
        if dest.exists() or dest.is_symlink():
            old = dest.parent / f'.peer-coworkers-old-{uuid.uuid4().hex[:8]}'
            dest.rename(old)
        try:
            staging.rename(dest)
        except OSError:
            if old is not None and not (dest.exists() or dest.is_symlink()):
                old.rename(dest)
            raise
        return dest
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if old is not None:
            old.unlink() if old.is_symlink() else (shutil.rmtree(old) if old.exists() else None)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dest', type=Path, default=Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'skills' / 'peer-coworkers')
    try:
        print(f'Installed: {install(p.parse_args().dest)}')
        return 0
    except (OSError, RuntimeError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
