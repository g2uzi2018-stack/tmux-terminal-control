#!/usr/bin/env python3
"""Deterministic raw-terminal fixture. Logs belong to a test temp directory."""
import argparse
import base64
import json
import os
import select
import signal
import sys
import termios
import time
import tty

START, END = b'\x1b[200~', b'\x1b[201~'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--log', required=True)
    parser.add_argument('--bracketed-paste', choices=('on', 'off'), default='on')
    parser.add_argument('--mode', choices=('unchanged', 'still', 'animation', 'approval', 'body', 'quote', 'stale', 'busy', 'exit'), default='still')
    parser.add_argument('--receive-delay-ms', type=int, default=0)
    parser.add_argument('--response-delay-ms', type=int, default=0)
    parser.add_argument('--ignore-submit', action='store_true')
    parser.add_argument('--exit-code', type=int, default=0)
    parser.add_argument('--initial-prompt', default='READY')
    args = parser.parse_args()
    log = open(args.log, 'a', encoding='utf-8', buffering=1)
    fd = sys.stdin.fileno()
    original = termios.tcgetattr(fd)
    tty.setraw(fd)
    enabled = args.bracketed_paste == 'on'
    current = bytearray()
    pending = bytearray()
    paste = None
    count = 0
    body, status = 'FAKE TUI', args.initial_prompt
    scheduled = None
    animated = False
    tick = 0
    next_tick = 0.0
    read_at = time.monotonic() + args.receive_delay_ms / 1000

    def event(kind, **values):
        log.write(json.dumps(dict(event=kind, **values), ensure_ascii=False) + '\n')

    def render():
        size = os.get_terminal_size(fd)
        text = current.decode('utf-8', 'replace')
        shown = json.dumps(text, ensure_ascii=False)
        # Fixed rows: body near top, prompt at physical bottom.
        screen = '\x1b[2J\x1b[HFAKE TUI\x1b[3;1H' + body
        screen += '\x1b[5;1HINPUT: ' + shown[:max(0, size.columns - 9)]
        screen += '\x1b[6;1HSUBMITS: ' + str(count)
        screen += '\x1b[' + str(size.lines) + ';1H' + status[:size.columns - 1]
        os.write(1, screen.encode('utf-8'))

    def response():
        nonlocal body, status, animated, next_tick
        if args.mode == 'unchanged' or args.ignore_submit:
            return None
        if args.mode == 'exit' or bytes(current).startswith(b'/exit'):
            os.write(1, b'\r\nEXIT\r\n')
            event('exit', code=args.exit_code)
            return args.exit_code
        if args.mode == 'approval':
            body, status = 'REQUESTED ACTION', 'APPROVAL: allow action?'
        elif args.mode == 'body':
            body, status = 'APPROVAL: quoted in body', 'WAITING'
        elif args.mode == 'quote':
            body, status = 'ANSWER', 'Quoted: APPROVAL: allow action?'
        elif args.mode == 'stale':
            body, status = 'ANSWER CHANGED', args.initial_prompt
        elif args.mode == 'busy':
            body, status = 'ANSWER', 'BUSY: working'
        elif args.mode == 'animation':
            animated, next_tick = True, time.monotonic()
            body, status = 'ANSWER', 'BUSY: animation 0'
        else:
            body, status = 'ANSWER CHANGED', 'WAITING'
        render()
        event('response', mode=args.mode)
        return None

    def submit():
        nonlocal count, scheduled
        count += 1
        event('submit', count=count, text_b64=base64.b64encode(current).decode())
        if args.mode != 'unchanged' and not args.ignore_submit:
            scheduled = time.monotonic() + args.response_delay_ms / 1000

    try:
        os.write(1, b'\x1b[?2004h' if enabled else b'\x1b[?2004l')
        render()
        event('ready', bracketed_paste=enabled, term=os.environ.get('TERM'))
        while True:
            now = time.monotonic()
            if scheduled is not None and now >= scheduled:
                scheduled = None
                exit_code = response()
                if exit_code is not None:
                    return exit_code
            if animated and now >= next_tick:
                tick += 1
                status = 'BUSY: animation ' + str(tick)
                render()
                next_tick = now + 0.04
            if now < read_at:
                time.sleep(min(0.01, read_at - now))
                continue
            readable, _, _ = select.select([fd], [], [], 0.01)
            if not readable:
                continue
            chunk = os.read(fd, 65536)
            if not chunk:
                return 0
            event('raw', data_b64=base64.b64encode(chunk).decode())
            pending.extend(chunk)
            while pending:
                if paste is not None:
                    pos = pending.find(END)
                    if pos == -1:
                        # Keep a suffix that may be part of a split delimiter.
                        keep = min(len(pending), len(END) - 1)
                        paste.extend(pending[:-keep] if keep else pending)
                        if keep:
                            del pending[:-keep]
                        else:
                            pending.clear()
                        break
                    paste.extend(pending[:pos])
                    del pending[:pos + len(END)]
                    current.extend(paste)
                    event('paste', text_b64=base64.b64encode(paste).decode())
                    paste = None
                    render()
                    continue
                if enabled and pending.startswith(START):
                    del pending[:len(START)]
                    paste = bytearray()
                    continue
                if enabled and START.startswith(pending):
                    break
                byte = pending.pop(0)
                if byte in (10, 13):
                    submit()
                elif byte == 3:
                    event('exit', code=130)
                    return 130
                else:
                    current.append(byte)
                    render()
    finally:
        os.write(1, b'\x1b[?2004l')
        termios.tcsetattr(fd, termios.TCSANOW, original)
        log.close()


if __name__ == '__main__':
    sys.exit(main())
