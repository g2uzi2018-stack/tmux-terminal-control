#!/usr/bin/env python3
"""Create, discover, prune and clean only explicitly marked task sessions."""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import stat
import sys
import uuid
from common import Tmux, ToolError, validate_socket

OWNER = 'tmux-tui/v1'

def socket_dir():
    return Path(os.environ.get('TMUX_TMPDIR') or '/tmp') / ('tmux-' + str(os.getuid()))

def socket_name(value):
    validate_socket(value)
    if not value.startswith('ai-tui-') or value == 'ai-tui-':
        raise ToolError('socket must start with ai-tui- and identify a task')
    return value

def text_option(value, label):
    if not value.strip() or any(c in value for c in '\x00\r\n'):
        raise ToolError(label + ' must be a nonempty single line')
    return value

def describe(tmux, target):
    name = tmux.run('display-message', '-p', '-t', target, '#{session_name}').rstrip('\n')
    task = tmux.run('show-options', '-qv', '-t', target, '@task').rstrip('\n')
    cwd = tmux.run('show-options', '-qv', '-t', target, '@cwd').rstrip('\n')
    owner = tmux.run('show-options', '-qv', '-t', target, '@owner').rstrip('\n')
    panes = []
    for line in tmux.run('list-panes', '-t', target, '-F', '#{pane_id}|#{pane_dead}|#{pane_dead_status}|#{pane_current_command}').splitlines():
        pane, dead, status, command = line.split('|', 3)
        panes.append(dict(pane=pane, dead=dead == '1', exit_code=int(status) if re.fullmatch(r'-?[0-9]+', status) else None, command=command))
    return dict(socket=tmux.socket, session=name, task=task, cwd=cwd,
                owner=owner, owned=owner == OWNER, panes=panes)

def new(args):
    socket = socket_name(args.socket or 'ai-tui-' + uuid.uuid4().hex)
    if os.path.lexists(socket_dir() / socket):
        raise ToolError('socket already exists; inspect/list and resume instead')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.session):
        raise ToolError('session must be a simple exact name')
    task = text_option(args.task, 'task')
    cwd = Path(args.cwd).resolve(strict=True)
    if not cwd.is_dir():
        raise ToolError('cwd must be a directory')
    text_option(str(cwd), 'cwd')
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command or not os.path.isabs(command[0]) or not os.access(command[0], os.X_OK) or not Path(command[0]).is_file():
        raise ToolError('target must be an executable absolute path')
    if min(args.history_limit, args.width, args.height) <= 0:
        raise ToolError('history-limit, width, height must be positive')
    tmux = Tmux(socket)
    target = None
    try:
        # One command queue keeps the empty server alive until session creation.
        result = tmux.batch([
            ['-f', '/dev/null', 'start-server'],
            ['set-option', '-g', 'history-limit', str(args.history_limit)],
            ['new-session', '-d', '-P', '-F', '#{session_id}|#{pane_id}', '-s', args.session,
             '-x', str(args.width), '-y', str(args.height), '-c', str(cwd), '/bin/sh'],
        ]).strip()
        target, pane = result.split('|')
        tmux.run('set-option', '-p', '-t', pane, 'remain-on-exit', 'on')
        for option, value in (('@task', task), ('@cwd', str(cwd)), ('@owner', OWNER),
                              ('@command', json.dumps(command, ensure_ascii=False))):
            tmux.run('set-option', '-t', target, option, value)
        # tmux treats a single program argument as shell-command text. An argv-only
        # Python exec launcher also handles executable names with spaces/semicolons.
        tmux.run('respawn-pane', '-k', '-t', pane, '-c', str(cwd), sys.executable,
                 '-c', 'import os,sys; os.execv(sys.argv[1],sys.argv[1:])', *command)
        return dict(socket=socket, session=args.session, pane=pane, cwd=str(cwd),
                    task=task, owner=OWNER, command=command)
    except (ToolError, ValueError):
        if target is not None:
            try:
                tmux.run('kill-session', '-t', target)
            except ToolError:
                pass
        raise

def list_sessions():
    result = []
    directory = socket_dir()
    if not directory.exists():
        return result
    for path in sorted(directory.iterdir()):
        if not path.name.startswith('ai-tui-'):
            continue
        info = path.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            continue
        try:
            tmux = Tmux(socket_name(path.name))
            targets = tmux.run('list-sessions', '-F', '#{session_id}').splitlines()
            result.extend(describe(tmux, target) for target in targets)
        except ToolError as exc:
            result.append(dict(socket=path.name, error=str(exc), owned=False))
    return result

def prune(args):
    name = socket_name(args.socket)
    path = socket_dir() / name
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ToolError('socket does not exist') from exc
    if not stat.S_ISSOCK(info.st_mode):
        raise ToolError('socket path is not a socket')
    if info.st_uid != os.getuid():
        raise ToolError('refusing to remove a socket owned by another user')
    client = socket.socket(socket.AF_UNIX)
    try:
        try:
            client.connect(os.fspath(path))
        except ConnectionRefusedError:
            pass
        except OSError as exc:
            raise ToolError('socket connect failed: ' + str(exc)) from exc
        else:
            raise ToolError('socket is still accepting connections; use cleanup')
    finally:
        client.close()
    try:
        current = path.lstat()
    except FileNotFoundError as exc:
        raise ToolError('socket disappeared before removal') from exc
    if current.st_ino != info.st_ino:
        raise ToolError('socket changed before removal')
    path.unlink()
    return dict(socket=name, removed=True)

def cleanup(args):
    tmux = Tmux(socket_name(args.socket))
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.session):
        raise ToolError('cleanup requires a simple exact session name')
    target = None
    for candidate in tmux.run('list-sessions', '-F', '#{session_id}').splitlines():
        name = tmux.run('display-message', '-p', '-t', candidate, '#{session_name}').rstrip('\n')
        if name == args.session:
            target = candidate
            break
    if target is None:
        raise ToolError('exact session not found')
    info = describe(tmux, target)
    if not info['owned'] or info['task'] != args.task or not info['cwd']:
        raise ToolError('refusing cleanup: owner/task/cwd markers do not match')
    if not args.allow_active and any(not pane['dead'] for pane in info['panes']):
        raise ToolError('active session retained; explicit --allow-active required to end task')
    tmux.run('kill-session', '-t', target)
    return dict(socket=tmux.socket, session=args.session, task=args.task, cleaned=True)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest='mode', required=True)
    create = commands.add_parser('new')
    create.add_argument('--socket')
    create.add_argument('--session', default='cli')
    create.add_argument('--task', required=True)
    create.add_argument('--cwd', required=True)
    create.add_argument('--history-limit', type=int, default=50000)
    create.add_argument('--width', type=int, default=120)
    create.add_argument('--height', type=int, default=40)
    create.add_argument('command', nargs=argparse.REMAINDER)
    commands.add_parser('list')
    remove = commands.add_parser('cleanup')
    remove.add_argument('--socket', required=True)
    remove.add_argument('--session', required=True)
    remove.add_argument('--task', required=True)
    remove.add_argument('--allow-active', action='store_true')
    drop = commands.add_parser('prune')
    drop.add_argument('--socket', required=True)
    args = p.parse_args()
    try:
        if args.mode == 'new':
            result = new(args)
        elif args.mode == 'cleanup':
            result = cleanup(args)
        elif args.mode == 'prune':
            result = prune(args)
        else:
            result = list_sessions()
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ToolError, OSError, ValueError) as exc:
        print('error: ' + str(exc), file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
