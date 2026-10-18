#!/usr/bin/env python3
"""Task-bound tmux lifecycle commands with explicit submissions and acceptance."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from common import Tmux, ToolError
from observation import wait_event
import interactions
import profiles
import tasks

def parser():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    doctor_cmd = commands.add_parser('doctor')
    doctor_cmd.add_argument('--probe', action='store_true')
    doctor_cmd.add_argument('--profile', choices=tuple(profiles.PROFILES), default='codex')
    doctor_cmd.add_argument('--no-proxy', action='store_true')
    probe_cmd = commands.add_parser('probe')
    probe_cmd.add_argument('--profile', choices=tuple(profiles.PROFILES), required=True)
    probe_cmd.add_argument('--cwd', type=Path, default=Path.cwd())
    probe_cmd.add_argument('--model')
    probe_cmd.add_argument('--timeout-ms', type=int, default=25000)
    probe_cmd.add_argument('--budget-seconds', type=int, default=240)
    probe_cmd.add_argument('--no-proxy', action='store_true')
    probe_cmd.add_argument('--proxy-url')
    probe_cmd.add_argument('--enable-opencode', action='store_true')
    reaper = commands.add_parser('reap')
    reaper.add_argument('--task')
    reaper.add_argument('--force', action='store_true')
    init = commands.add_parser('init')
    init.add_argument('--cwd', required=True)
    init.add_argument('--goal', required=True)
    init.add_argument('--role', choices=('implement', 'test', 'review', 'research'), required=True)
    init.add_argument('--profile', choices=tuple(profiles.PROFILES), default='codex')
    init.add_argument('--model', help='explicit CLI model ID for this task; omitted preserves CLI defaults')
    init.add_argument('--enable-opencode', action='store_true')
    init.add_argument('--owned-path', action='append', default=[])
    init.add_argument('--acceptance', action='append', required=True)
    init.add_argument('--budget-seconds', type=int, default=600)
    init.add_argument('--runs-dir')
    init.add_argument('--max-replies', type=int, default=2)
    for name in ('start', 'show', 'screen', 'paste', 'submit', 'observe', 'wait', 'keys', 'cancel', 'reply', 'collect', 'accept', 'close'):
        cmd = commands.add_parser(name)
        cmd.add_argument('--run', type=Path, required=True)
        if name == 'keys':
            from common import KEYS
            cmd.add_argument('--key', choices=sorted(KEYS), action='append', required=True)
        if name == 'reply':
            cmd.add_argument('--message-file', type=Path, required=True)
        if name == 'start':
            cmd.add_argument('--no-proxy', action='store_true')
            cmd.add_argument('--proxy-url', help='HTTP(S) proxy endpoint inherited by this worker; no credentials')
        if name == 'paste':
            cmd.add_argument('--multiline-verified')
        if name == 'submit':
            cmd.add_argument('--received-confirmed', action='store_true')
        if name in ('submit', 'observe', 'wait', 'cancel'):
            cmd.add_argument('--timeout-ms', type=int, default=25000 if name == 'wait' else 2000 if name == 'cancel' else 20000)
        if name == 'accept':
            cmd.add_argument('--evidence', required=True)
        if name == 'close':
            cmd.add_argument('--allow-active', action='store_true')
    term = commands.add_parser('term', help='task-bound terminal operations')
    terminal = term.add_subparsers(dest='terminal_action', required=True)
    for name in ('screen', 'history', 'status', 'paste', 'submit', 'wait', 'keys'):
        cmd = terminal.add_parser(name)
        cmd.add_argument('--run', type=Path, required=True)
        if name == 'keys':
            from common import KEYS
            cmd.add_argument('--key', choices=sorted(KEYS), action='append', required=True)
        if name == 'paste':
            cmd.add_argument('--multiline-verified')
        if name == 'submit':
            cmd.add_argument('--received-confirmed', action='store_true')
        if name in ('submit', 'wait'):
            cmd.add_argument('--timeout-ms', type=int, default=25000 if name == 'wait' else 20000)
    return parser


def main():
    args = parser().parse_args()
    if args.action == 'term':
        args.action = args.terminal_action
    try:
        if args.action == 'doctor':
            result = profiles.doctor()
            import capabilities
            for item in result:
                item.update(capabilities.comparison(item['profile'], item['version']) if item['enabled'] else
                            dict(warning='compatibility-only profile not executed'))
            if args.probe:
                import probe
                result = dict(profiles=result, probe=probe.run(args.profile, no_proxy=args.no_proxy))
        elif args.action == 'probe':
            import probe
            result = probe.run(args.profile, args.model, args.cwd, args.timeout_ms,
                               args.budget_seconds, args.no_proxy, args.proxy_url, args.enable_opencode)
        elif args.action == 'reap':
            result = tasks.reap(args.task, args.force)
        elif args.action == 'init':
            result = tasks.prepare(args)
        else:
            run = args.run.expanduser().resolve(strict=True)
            with tasks.locked(run):
                record = tasks.read_json(run / 'task.json')
                if args.action == 'show':
                    result = {key: value for key, value in record.items()
                              if key not in ('baseline', 'collected_snapshot')}
                elif args.action == 'history':
                    tasks.check_session(record)
                    result = dict(screen=Tmux(record['socket']).run('capture-pane', '-p', '-S', '-', '-t', record['pane']))
                elif args.action == 'status':
                    tasks.check_session(record)
                    dead, code = Tmux(record['socket']).status(record['pane'])
                    result = dict(dead=dead, exit_code=code or None)
                elif args.action == 'screen':
                    tasks.check_session(record)
                    result = dict(screen=Tmux(record['socket']).capture(record['pane']))
                elif args.action == 'start':
                    result = tasks.start(run, record, args.proxy_url, args.no_proxy)
                elif args.action == 'paste':
                    result = tasks.paste(run, record, args.multiline_verified)
                elif args.action in ('submit', 'observe'):
                    result = tasks.observe(run, record, args.action == 'submit',
                                     getattr(args, 'received_confirmed', False), args.timeout_ms)
                elif args.action == 'keys':
                    result = interactions.keys(run, record, args.key)
                elif args.action == 'cancel':
                    result = interactions.cancel(run, record, args.timeout_ms)
                elif args.action == 'reply':
                    result = interactions.reply(run, record, args.message_file)
                elif args.action == 'wait':
                    result = wait_event(run, record, args.timeout_ms, verify_session=True)
                elif args.action == 'collect':
                    result = tasks.collect(run, record)
                elif args.action == 'accept':
                    result = tasks.accept(run, record, args.evidence)
                else:
                    result = tasks.close(run, record, args.allow_active)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except (ToolError, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print('error: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
