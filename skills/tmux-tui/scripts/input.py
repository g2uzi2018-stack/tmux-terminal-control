#!/usr/bin/env python3
"""Paste stdin verbatim; keys and submission are explicit separate operations."""
import argparse
import os
import sys
import uuid
from common import KEYS, SUBMIT_KEYS, Tmux, ToolError, send_submit, validate_pane

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    for mode in ('paste', 'keys', 'submit'):
        cmd = modes.add_parser(mode)
        cmd.add_argument('--socket', required=True)
        cmd.add_argument('--pane', required=True)
        if mode == 'paste':
            cmd.add_argument('--multiline-verified', metavar='EVIDENCE')
        elif mode == 'keys':
            cmd.add_argument('--key', action='append', choices=sorted(KEYS), required=True)
        else:
            cmd.add_argument('--key', choices=sorted(SUBMIT_KEYS), default='Enter')
            cmd.add_argument('--received-confirmed', action='store_true', required=True)
    args = parser.parse_args()
    try:
        pane, tmux = validate_pane(args.pane), Tmux(args.socket)
        if args.mode == 'paste':
            data = sys.stdin.buffer.read()
            try:
                text = data.decode('utf-8', 'strict')
            except UnicodeDecodeError as exc:
                raise ToolError('stdin must be valid UTF-8') from exc
            if ('\n' in text or '\r' in text) and not (args.multiline_verified or '').strip():
                raise ToolError('multiline rejected before sending: verified target/version/interface evidence required')
            tmux.alive(pane)
            buffer = 'aitui-' + str(os.getpid()) + '-' + uuid.uuid4().hex
            try:
                tmux.run('load-buffer', '-b', buffer, '-', input=data)
                tmux.run('paste-buffer', '-p', '-r', '-d', '-b', buffer, '-t', pane)
            except ToolError:
                try:
                    tmux.run('delete-buffer', '-b', buffer)
                except ToolError:
                    pass
                raise
            print('reason=pasted bytes=' + str(len(data)))
        elif args.mode == 'keys':
            tmux.alive(pane)
            tmux.run('send-keys', '-t', pane, '--', *args.key)
            print('reason=keys')
        else:
            send_submit(tmux, pane, args.key, args.received_confirmed)
            print('reason=submitted')
        return 0
    except ToolError as exc:
        print('error: ' + str(exc), file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
