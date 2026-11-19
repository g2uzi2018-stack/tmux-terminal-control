#!/usr/bin/env python3
"""Headless peer coworker runner with lock-derived state and git-tree audit."""
import argparse, fcntl, hashlib, json, os, re, shutil, signal, subprocess, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path
import audit, profiles

def _now(): return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def _runs_root():
    ov = os.environ.get('PEER_RUNS_DIR')
    root = Path(ov).expanduser().resolve() if ov else Path(f'/tmp/peer-coworkers-{os.getuid()}/runs')
    root.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root

def _save_run(run_dir, data):
    tmp = run_dir / f'.run.json.{os.getpid()}.tmp'
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(tmp, run_dir / 'run.json')

def _open_run(arg):
    d = Path(arg).expanduser().resolve(strict=True)
    return d, json.loads((d / 'run.json').read_text(encoding='utf-8'))

def _try_flock(path):
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd, None
    except BlockingIOError:
        holder = Path(path).read_text('utf-8', 'replace').strip() if Path(path).exists() else ''
        os.close(fd)
        return None, holder

def _is_running(run_dir):
    fd, _ = _try_flock(Path(run_dir) / 'run.lock')
    if fd is None: return True
    os.close(fd)
    return False

def _derive_status(run_dir, run, rnum):
    if _is_running(run_dir): return 'running'
    info = run.get('rounds', {}).get(str(rnum), {})
    if 'exit_code' not in info: return 'killed'
    if info.get('timed_out'): return 'timed_out'
    res = Path(run_dir) / f'result-{rnum}.md'
    return 'done' if res.is_file() and res.read_text('utf-8', 'replace').strip() else 'failed'

def _acquire_locks(run_dir, cwd, writable, rnum):
    run_fd, _ = _try_flock(run_dir / 'run.lock')
    if run_fd is None:
        raise RuntimeError('previous round is still running')
    if not writable:
        return run_fd, None
    locks = _runs_root().parent / 'locks'
    locks.mkdir(parents=True, exist_ok=True, mode=0o700)
    ws_fd, holder = _try_flock(locks / f"{hashlib.sha256(str(cwd).encode()).hexdigest()[:16]}.lock")
    if ws_fd is None:
        os.close(run_fd)
        raise RuntimeError(f'workspace already locked by another writable run: {holder or "unknown"}')
    os.ftruncate(ws_fd, 0)
    os.lseek(ws_fd, 0, os.SEEK_SET)
    os.write(ws_fd, json.dumps({'run': str(run_dir), 'cwd': str(cwd), 'round': rnum}, ensure_ascii=False).encode())
    return run_fd, ws_fd

def _spawn_runner(run_dir, rnum, run_data, run_fd, ws_fd):
    ready_r, ready_w = os.pipe()
    fds = (run_fd, ready_r) if ws_fd is None else (run_fd, ws_fd, ready_r)
    cmd = [sys.executable, str(Path(__file__).resolve()), '_runner', '--run', str(run_dir), '--round', str(rnum), '--ready-fd', str(ready_r)]
    proc = subprocess.Popen(cmd, start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, pass_fds=fds)
    run_data.update(round=rnum, pgid=proc.pid)
    run_data.setdefault('rounds', {})[str(rnum)] = {'started_at': _now()}
    _save_run(run_dir, run_data)
    os.write(ready_w, b'1')  # Release _runner only after pgid and round metadata are persisted.
    for fd in (ready_w, ready_r, run_fd, ws_fd):
        if fd is not None:
            os.close(fd)
    return proc.pid

def cmd_start(args):
    cwd = Path(args.cwd).expanduser().resolve(strict=True)
    if Path(audit.git(cwd, 'rev-parse', '--show-toplevel').strip()).resolve() != cwd:
        raise RuntimeError('cwd must be the Git worktree root')
    if not profiles.resolve_executable(args.profile) or args.timeout <= 0:
        raise RuntimeError('CLI executable not found or --timeout <= 0')
    write_paths = [audit.normalize_write_path(cwd, p) for p in args.write]
    body = Path(args.task_file).expanduser().read_text('utf-8').strip()
    if not body or (args.name and not re.fullmatch(r'[A-Za-z0-9_.-]+', args.name)):
        raise RuntimeError('task file is empty or --name is invalid')
    root = _runs_root()
    if root == cwd or cwd in root.parents:
        raise RuntimeError('runs directory must be outside the workspace')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    run_id = f'{stamp}-{args.name}-{uuid.uuid4().hex[:6]}' if args.name else f'{stamp}-{uuid.uuid4().hex[:8]}'
    run_dir = root / run_id
    run_dir.mkdir(mode=0o700)
    try:
        run_fd, ws_fd = _acquire_locks(run_dir, cwd, bool(write_paths), 1)
    except Exception:
        shutil.rmtree(run_dir, ignore_errors=True)
        raise
    scope = f'可写路径: {", ".join(write_paths)}。不要执行 git add/commit。' if write_paths else '本任务为只读调研/审查：严禁修改、创建或删除工作区任何文件，也不要改 git 状态。'
    (run_dir / 'task.md').write_text(f'{body}\n\n---\n工作目录: {cwd}\n{scope}\n完整报告必须写在最终回复中，以 DONE/PARTIAL/BLOCKED/QUESTION 开头。\n', 'utf-8')
    base = audit.baseline(run_dir, cwd)
    run_data = {'id': run_id, 'name': args.name, 'profile': args.profile, 'model': args.model, 'effort': args.effort, 'cwd': str(cwd), 'write_paths': write_paths,
                'timeout': args.timeout, 'session_id': None, 'pgid': None, 'round': 1, 'round_trees': {'1': base['base_tree']}, 'rounds': {}, 'created_at': _now(), **base}
    return {'run': str(run_dir), 'id': run_id, 'round': 1, 'pgid': _spawn_runner(run_dir, 1, run_data, run_fd, ws_fd), 'status': 'running'}

def cmd_send(args):
    run_dir, run_data = _open_run(args.run)
    msg = Path(args.file).expanduser().read_text('utf-8').strip()
    if not msg or _is_running(run_dir) or not run_data.get('session_id'):
        raise RuntimeError('empty message, previous round still running, or missing session_id')
    cwd, next_round = Path(run_data['cwd']), run_data['round'] + 1
    run_fd, ws_fd = _acquire_locks(run_dir, cwd, bool(run_data.get('write_paths')), next_round)
    run_data.setdefault('round_trees', {})[str(next_round)] = audit.worktree_tree(run_dir, cwd)
    (run_dir / f'prompt-{next_round}.md').write_text(msg + '\n', 'utf-8')
    return {'run': str(run_dir), 'id': run_data['id'], 'round': next_round, 'pgid': _spawn_runner(run_dir, next_round, run_data, run_fd, ws_fd), 'status': 'running'}

def _term_group():
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    try: os.killpg(0, signal.SIGTERM)
    except ProcessLookupError: pass

def cmd_runner(args):
    if not os.read(args.ready_fd, 1):
        return 1
    os.close(args.ready_fd)
    run_dir, run_data = _open_run(args.run)
    rnum = args.round
    prompt = (run_dir / ('task.md' if rnum == 1 else f'prompt-{rnum}.md')).read_text('utf-8')
    result_path, log_path = run_dir / f'result-{rnum}.md', run_dir / f'round-{rnum}.log'
    cmd = profiles.build_command(run_data['profile'], run_data['cwd'], prompt, bool(run_data.get('write_paths')),
                                 model=run_data.get('model'), effort=run_data.get('effort'),
                                 session_id=run_data.get('session_id') if rnum > 1 else None, result_path=result_path)
    timed_out = False
    with log_path.open('w', encoding='utf-8') as log_f:
        try:
            proc = subprocess.Popen(cmd, cwd=run_data['cwd'], stdin=subprocess.DEVNULL, stdout=log_f, stderr=subprocess.STDOUT, close_fds=True)
            try:
                exit_code = proc.wait(timeout=run_data.get('timeout', 2700))
            except subprocess.TimeoutExpired:
                timed_out = True
                _term_group()
                try: exit_code = proc.wait(timeout=5)
                except subprocess.TimeoutExpired: proc.kill(); exit_code = proc.wait()
            finally:
                _term_group()
        except OSError as exc:
            log_f.write(f'launch error: {exc}\n')
            exit_code = 127
    session_id, last_text, transcript = profiles.parse_log(run_data['profile'], log_path)
    if transcript:
        (run_dir / f'transcript-{rnum}.md').write_text(transcript + '\n', 'utf-8')
    if timed_out or exit_code != 0:
        result_path.unlink(missing_ok=True)
    elif not (result_path.is_file() and result_path.read_text('utf-8', 'replace').strip()):
        result_path.write_text(last_text + '\n', 'utf-8') if last_text else result_path.unlink(missing_ok=True)
    if session_id:
        run_data['session_id'] = session_id
    run_data.setdefault('rounds', {}).setdefault(str(rnum), {}).update(exit_code=exit_code, finished_at=_now(), timed_out=timed_out)
    _save_run(run_dir, run_data)
    return 0

def cmd_wait(args):
    run_dir, _ = _open_run(args.run)
    deadline = time.monotonic() + max(0, args.timeout)
    while _is_running(run_dir) and time.monotonic() < deadline:
        time.sleep(min(1.0, max(0.05, deadline - time.monotonic())))
    run_dir, run_data = _open_run(args.run)
    rnum = run_data['round']
    status, log_path = _derive_status(run_dir, run_data, rnum), run_dir / f'round-{rnum}.log'
    out = {'run': str(run_dir), 'id': run_data['id'], 'round': rnum, 'status': status, 'profile': run_data['profile'], 'session_id': run_data.get('session_id')}
    if status == 'running':
        return {**out, 'pgid': run_data.get('pgid'), 'log_path': str(log_path)}
    info, tpath = run_data.get('rounds', {}).get(str(rnum), {}), run_dir / f'transcript-{rnum}.md'
    out['exit_code'] = info.get('exit_code')
    if tpath.is_file():
        out['transcript_path'] = str(tpath)
    if status == 'done':
        rpath = run_dir / f'result-{rnum}.md'
        text = rpath.read_text('utf-8', 'replace')
        out.update(result_path=str(rpath), first_line=next((ln.strip() for ln in text.splitlines() if ln.strip()), '')[:160])
        if len(text.strip()) < 200:
            out['hint'] = '完整内容见 transcript'
    else:
        lines = log_path.read_text('utf-8', 'replace').splitlines() if log_path.is_file() else []
        out.update(timed_out=info.get('timed_out', False), log_path=str(log_path), log_tail='\n'.join(lines[-30:]))
    return {**out, 'audit': audit.report(run_dir, run_data)}

def cmd_log(args):
    run_dir, run_data = _open_run(args.run)
    rnum = run_data['round']
    log_path = run_dir / f'round-{rnum}.log'
    return {'run': str(run_dir), 'round': rnum, 'status': _derive_status(run_dir, run_data, rnum),
            'log_path': str(log_path), 'text': profiles.format_log(run_data['profile'], log_path, tail=args.tail)}

def cmd_diff(args):
    run_dir, run_data = _open_run(args.run)
    trees = run_data.get('round_trees', {})
    since = trees.get(str(args.round)) if args.round is not None else None
    if args.round is not None and not since:
        raise RuntimeError(f'round {args.round} tree not found')
    until = trees.get(str(args.round + 1)) if args.round is not None else None
    return {'run': str(run_dir), 'round': args.round or 'all', **audit.report(run_dir, run_data, since, until)}

def cmd_stop(args):
    run_dir, run_data = _open_run(args.run)
    if not _is_running(run_dir):
        return {'run': str(run_dir), 'stopped': False, 'status': _derive_status(run_dir, run_data, run_data['round'])}
    pgid = run_data.get('pgid')
    if pgid:
        for sig, span in ((signal.SIGTERM, 5.0), (signal.SIGKILL, 2.0)):
            if not _is_running(run_dir):
                break
            try:
                os.killpg(pgid, sig)
            except ProcessLookupError:
                break
            end = time.monotonic() + span
            while _is_running(run_dir) and time.monotonic() < end:
                time.sleep(0.05)
    return {'run': str(run_dir), 'stopped': True, 'status': _derive_status(run_dir, run_data, run_data['round'])}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('doctor')
    st = sub.add_parser('start')
    for arg, kw in (('--cwd', {'required': True}), ('--profile', {'choices': tuple(profiles.PROFILES), 'required': True}),
                    ('--model', {}), ('--effort', {}), ('--task-file', {'required': True}),
                    ('--write', {'action': 'append', 'default': []}), ('--name', {}), ('--timeout', {'type': int, 'default': 2700})):
        st.add_argument(arg, **kw)
    for name, extra in (('wait', ('--timeout', {'type': int, 'default': 120})), ('send', ('--file', {'required': True})),
                        ('log', ('--tail', {'type': int, 'default': 50})), ('diff', ('--round', {'type': int})), ('stop', None)):
        c = sub.add_parser(name)
        c.add_argument('--run', required=True)
        if extra:
            c.add_argument(extra[0], **extra[1])
    rn = sub.add_parser('_runner')
    for arg, kw in (('--run', {'required': True}), ('--round', {'type': int, 'required': True}), ('--ready-fd', {'type': int, 'required': True})):
        rn.add_argument(arg, **kw)
    args = p.parse_args()
    if args.cmd == '_runner':
        return cmd_runner(args)
    try:
        handlers = {'doctor': lambda _: {'profiles': profiles.doctor()}, 'start': cmd_start, 'wait': cmd_wait,
                    'send': cmd_send, 'log': cmd_log, 'diff': cmd_diff, 'stop': cmd_stop}
        print(json.dumps(handlers[args.cmd](args), ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
