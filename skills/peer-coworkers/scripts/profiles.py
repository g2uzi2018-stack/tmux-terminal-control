"""Headless CLI profiles, command builders, and stream-json log parsers."""
import json, os, shutil, subprocess
from pathlib import Path

PROFILES = {'codex': ('codex',), 'agy': ('agy',), 'cursor': ('cursor-agent', 'agent')}

def resolve_executable(profile):
    if profile not in PROFILES:
        raise RuntimeError(f'unknown profile: {profile}')
    for name in PROFILES[profile]:
        found = shutil.which(name) or str(Path.home() / '.local' / 'bin' / name)
        if Path(found).is_file() and os.access(found, os.X_OK):
            return found
    return None

def doctor():
    out = []
    for name in PROFILES:
        exe, ver = resolve_executable(name), None
        if exe:
            try:
                p = subprocess.run([exe, '--version'], capture_output=True, text=True, timeout=5)
                ver = p.stdout.strip().splitlines()[0][:200] if p.returncode == 0 and p.stdout.strip() else None
            except (OSError, subprocess.TimeoutExpired):
                pass
        out.append({'profile': name, 'executable': exe, 'available': bool(exe), 'version': ver})
    return out

def build_command(profile, cwd, prompt, writable, model=None, effort=None, session_id=None, result_path=None):
    exe = resolve_executable(profile)
    if not exe:
        raise RuntimeError(f'{profile} CLI executable not found')
    if profile == 'codex':
        cmd = [exe, 'exec', '-C', str(cwd), '-s', 'workspace-write' if writable else 'read-only']
        cmd += (['-m', model] if model else []) + (['-c', f'model_reasoning_effort={effort}'] if effort else [])
        cmd += ['resume', session_id] if session_id else []
        return cmd + ['--json', '-o', str(result_path), '--', prompt]
    if profile == 'agy':
        # Phase 0: --mode accept-edits denies Bash and --mode auto is unavailable; -p takes prompt as value.
        cmd = [exe, '--sandbox', '--dangerously-skip-permissions', '--output-format', 'stream-json']
        cmd += (['--model', model] if model else []) + (['--effort', effort] if effort else [])
        return cmd + (['--conversation', session_id] if session_id else []) + [f'--print={prompt}']
    # Phase 0: cursor --force bypasses sandbox outside workspace; -p --sandbox enabled runs tools safely.
    if effort:
        if not model or '[' in model:
            raise RuntimeError('cursor --effort requires --model without bracket parameters')
        model = f'{model}[effort={effort}]'
    cmd = [exe, '-p', '--output-format', 'stream-json', '--sandbox', 'enabled', '--trust', '--workspace', str(cwd)]
    return cmd + (['--model', model] if model else []) + (['--resume', session_id] if session_id else []) + ['--', prompt]

def _iter_events(profile, log_path):
    if not Path(log_path).is_file():
        return
    for raw in Path(log_path).read_text('utf-8', 'replace').splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line) if line.startswith('{') else None
        except ValueError:
            obj = None
        if not isinstance(obj, dict):
            yield ('info', f'[raw] {line}')
        elif profile == 'codex':
            kind, item = obj.get('type'), obj.get('item') or {}
            if kind == 'thread.started' and obj.get('thread_id'):
                yield ('session', obj['thread_id'])
            elif kind == 'item.completed' and item.get('type') == 'agent_message':
                yield ('block', item.get('text', ''))
            elif kind == 'item.completed' and item.get('type') == 'command_execution':
                yield ('info', f"[cmd exit={item.get('exit_code')}] {item.get('command', '')}")
            elif kind in ('error', 'turn.failed'):
                yield ('info', f"[error] {obj.get('message') or (obj.get('error') or {}).get('message', '')}")
        elif profile == 'agy':
            ev, su, res = obj.get('event'), obj.get('step_update') or {}, obj.get('result') or {}
            if (cid := obj.get('conversation_id') or su.get('conversation_id') or res.get('conversation_id')):
                yield ('session', cid)
            if ev == 'init':
                yield ('info', f"[init] model={(obj.get('init') or {}).get('model')}")
            elif ev == 'step_update' and su.get('step_type') == 'agent_response':
                yield ('delta', su.get('step_index', 0), su.get('text_delta', ''), su.get('state') == 'DONE')
            elif ev == 'step_update' and su.get('step_type') == 'tool' and su.get('state') == 'DONE':
                yield ('info', f"[tool] {su.get('tool_name')}")
            elif ev == 'result':
                yield ('fallback', res.get('response', ''))
                yield ('info', f"[result] status={res.get('status')}")
        elif profile == 'cursor':
            if obj.get('session_id'):
                yield ('session', obj['session_id'])
            kind = obj.get('type')
            if kind == 'system' and obj.get('subtype') == 'init':
                yield ('info', f"[init] model={obj.get('model')}")
            elif kind == 'assistant':
                parts = ((obj.get('message') or {}).get('content')) or []
                yield ('block', ''.join(p.get('text', '') for p in parts if isinstance(p, dict) and p.get('type') == 'text'))
            elif kind == 'tool_call' and obj.get('subtype') == 'completed':
                yield ('info', f"[tool] {next(iter(obj.get('tool_call') or {}), 'tool')}")
            elif kind == 'result':
                if not obj.get('is_error') and isinstance(obj.get('result'), str):
                    yield ('fallback', obj['result'])
                yield ('info', f"[result] is_error={obj.get('is_error')} duration_ms={obj.get('duration_ms')}")

def parse_log(profile, log_path):
    session_id, blocks, steps, fallback = None, [], {}, None
    for ev in _iter_events(profile, log_path):
        if ev[0] == 'session':
            session_id = ev[1]
        elif ev[0] == 'block' and ev[1].strip():
            blocks.append(ev[1].strip())
        elif ev[0] == 'delta' and ev[2]:
            steps[ev[1]] = steps.get(ev[1], '') + ev[2]
        elif ev[0] == 'fallback' and ev[1].strip():
            fallback = ev[1].strip()
    if profile == 'agy':
        blocks = [steps[k].strip() for k in sorted(steps) if steps[k].strip()]
    if not blocks and fallback:
        blocks = [fallback]
    return session_id, (blocks[-1] if blocks else ''), '\n\n'.join(blocks)

def format_log(profile, log_path, tail=50):
    lines, buf = [], {}
    for ev in _iter_events(profile, log_path):
        if ev[0] in ('info', 'block') and ev[1].strip():
            lines.append(ev[1].strip())
        elif ev[0] == 'delta':
            buf[ev[1]] = buf.get(ev[1], '') + ev[2]
            if ev[3] and buf.get(ev[1], '').strip():
                lines.append(buf.pop(ev[1]).strip())
    lines.extend(buf[k].strip() for k in sorted(buf) if buf[k].strip())
    return '\n'.join(lines[-tail:] if tail > 0 else lines)
