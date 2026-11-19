"""Git worktree-tree baseline and out-of-scope diff reporting without touching .git."""
import hashlib, os, shutil, subprocess, tempfile
from pathlib import Path

def git(cwd, *args, env=None, text=True, check=True):
    p = subprocess.run(['git', '-C', str(cwd), *args], capture_output=True, text=text, env=env, timeout=30)
    if p.returncode and check:
        raise RuntimeError((p.stderr if text else p.stderr.decode('utf-8', 'replace')).strip() or f'git {args[0]} failed')
    return (p.stdout.strip() if p.returncode == 0 else '') if not check else p.stdout

def normalize_write_path(cwd, raw):
    if not raw or not raw.strip() or '\x00' in raw:
        raise RuntimeError('write path must be nonblank')
    p = Path(raw)
    if p.is_absolute() or '..' in p.parts or '.git' in p.parts:
        raise RuntimeError(f'write path must be repo-relative without .. or .git: {raw}')
    try:
        (cwd / p).resolve().relative_to(cwd)
    except ValueError as exc:
        raise RuntimeError(f'write path escapes workspace via symlink: {raw}') from exc
    return p.as_posix().rstrip('/') or '.'

def git_env(run_dir, cwd, index=None):
    obj_dir = Path(run_dir) / 'objects'
    for sub in ('info', 'pack'):
        (obj_dir / sub).mkdir(parents=True, exist_ok=True)
    alt = os.path.abspath(os.path.join(str(cwd), git(cwd, 'rev-parse', '--git-path', 'objects').strip()))
    env = {**os.environ, 'GIT_OBJECT_DIRECTORY': str(obj_dir), 'GIT_ALTERNATE_OBJECT_DIRECTORIES': alt}
    return {**env, 'GIT_INDEX_FILE': str(index)} if index else env

def worktree_tree(run_dir, cwd):
    """Snapshot tracked + nonignored untracked files via temp index without writing .git."""
    real_idx = os.path.abspath(os.path.join(str(cwd), git(cwd, 'rev-parse', '--git-path', 'index').strip()))
    with tempfile.TemporaryDirectory() as tmp:
        idx = Path(tmp) / 'index'
        if os.path.exists(real_idx):
            shutil.copy2(real_idx, idx)
        env = git_env(run_dir, cwd, idx)
        git(cwd, 'add', '-A', env=env)
        return git(cwd, 'write-tree', env=env).strip()

def index_digest(cwd):
    return hashlib.sha256(git(cwd, 'ls-files', '-s', '-z', text=False)).hexdigest()

def baseline(run_dir, cwd):
    return {'base_tree': worktree_tree(run_dir, cwd), 'base_head': git(cwd, 'rev-parse', '--verify', 'HEAD', check=False),
            'base_branch': git(cwd, 'symbolic-ref', '--quiet', 'HEAD', check=False), 'base_index': index_digest(cwd)}

def report(run_dir, run, since_tree=None, until_tree=None):
    cwd, base_tree = Path(run['cwd']), since_tree or run['base_tree']
    cur_tree, env = until_tree or worktree_tree(run_dir, cwd), git_env(run_dir, cwd)
    raw = git(cwd, 'diff-tree', '-r', '--name-only', '-z', base_tree, cur_tree, env=env, text=False)
    changed = [p for p in raw.decode('utf-8', 'surrogateescape').split('\0') if p]
    write_paths = run.get('write_paths', [])
    outside = [p for p in changed if not any(w == '.' or p == w or p.startswith(w + '/') for w in write_paths)]
    return {'changed': changed, 'outside_write_paths': outside,
            'head_moved': git(cwd, 'rev-parse', '--verify', 'HEAD', check=False) != run['base_head'],
            'branch_changed': git(cwd, 'symbolic-ref', '--quiet', 'HEAD', check=False) != run['base_branch'],
            'index_changed': index_digest(cwd) != run['base_index'], 'base_tree': base_tree,
            'current_tree': cur_tree, 'stat': git(cwd, 'diff-tree', '--stat', base_tree, cur_tree, env=env).strip()}
