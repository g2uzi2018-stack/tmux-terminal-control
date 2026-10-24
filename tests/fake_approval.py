"""Observed agy command-menu layout; no model service or real tool execution."""
import argparse
import os
from pathlib import Path
import sys
import termios
import tty

parser = argparse.ArgumentParser()
parser.add_argument('--log', type=Path, required=True)
parser.add_argument('--selected', type=int, default=1)
parser.add_argument('--expanded', action='store_true')
args = parser.parse_args()
selected = args.selected
expanded = args.expanded


def draw():
    choices = ['Yes, run command',
               "Yes, and always allow in this conversation for commands that start with 'git status'",
               "Yes, and always allow for commands that start with 'git status' (Persist to settings.json)",
               'No, cancel']
    if expanded:
        lines = ['Expanded Tool Permission Editor', '─' * 100, '', '  Full Command:',
                 "    python3 -c '", '    print(391)', "    '", '', '─' * 100,
                 '  Requested Permission (Editable):', '  > python3', '',
                 '  enter confirm · esc back · pgup/pgdown scroll Full Command',
                 'esc to cancel                                  Gemini 3.8 Flash · high']
        os.write(1, ('\x1b[2J\x1b[H' + '\r\n'.join(lines) + '\r\n').encode())
        return
    command = "   python3 -c '\r\n   ⋯ (2 lines hidden)" if args.expanded else '   git status'
    lines = ['Command', '', 'Requesting permission for:', command, '', 'Run this command?']
    lines += [('> ' if number == selected else '  ') + str(number) + '. ' + text
              for number, text in enumerate(choices, 1)]
    lines += ['', '  ↑/↓ Navigate · tab Amend · ctrl+g edit/expand command',
              'esc to cancel                                  Gemini 3.8 Flash · high']
    os.write(1, ('\x1b[2J\x1b[H' + '\r\n'.join(lines) + '\r\n').encode())


previous = termios.tcgetattr(0)
tty.setraw(0)
try:
    draw()
    pending = b''
    while True:
        pending += os.read(0, 1024)
        while pending:
            if expanded and pending.startswith(b'\x1b'):
                expanded = False
                pending = pending[1:]
                draw()
            elif pending.startswith(b'\x1b[A'):
                selected = max(1, selected - 1)
                pending = pending[3:]
                draw()
            elif pending.startswith(b'\x1b[B'):
                selected = min(4, selected + 1)
                pending = pending[3:]
                draw()
            elif b'\x1b[A'.startswith(pending) or b'\x1b[B'.startswith(pending):
                break
            else:
                char, pending = pending[0], pending[1:]
                if char in (10, 13):
                    with args.log.open('a') as stream:
                        stream.write(str(selected) + '\n')
                    os.write(1, b'\x1b[2J\x1b[HDECISION RECEIVED\r\n')
finally:
    termios.tcsetattr(0, termios.TCSANOW, previous)
