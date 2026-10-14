"""Shared, bounded tmux argv operations."""
import re
import subprocess
import time

class ToolError(Exception):
    pass

class DeadlineReached(Exception):
    pass

def validate_socket(value):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', value):
        raise ToolError('socket must be a simple tmux -L name')
    return value

def validate_pane(value):
    if not re.fullmatch(r'%[0-9]+', value):
        raise ToolError('pane must be an explicit %number ID')
    return value

def literal_arg(value):
    # tmux's client interprets trailing semicolons even in subprocess argv.
    value = str(value)
    return value[:-1] + r'\;' if value.endswith(';') else value

class Tmux:
    def __init__(self, socket, deadline=None):
        self.socket = validate_socket(socket)
        self.deadline = deadline

    def run(self, *args, input=None):
        return self._run(list(map(literal_arg, args)), input=input)

    def batch(self, commands):
        args = []
        for command in commands:
            if args:
                args.append(";")
            args.extend(map(literal_arg, command))
        return self._run(args)

    def _run(self, args, input=None):
        timeout = 3.0 if self.deadline is None else self.deadline - time.monotonic()
        if timeout <= 0.01:
            raise DeadlineReached()
        try:
            p = subprocess.run(['tmux', '-L', self.socket, *args], input=input,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise ToolError('tmux command timed out within its allowed limit') from exc
        except OSError as exc:
            raise ToolError(str(exc)) from exc
        if p.returncode:
            raise ToolError(p.stderr.decode('utf-8', 'replace').strip() or 'tmux failed')
        return p.stdout.decode('utf-8', 'replace')

    def capture(self, pane):
        return self.run('capture-pane', '-p', '-t', validate_pane(pane))

    def status(self, pane):
        parts = self.run('display-message', '-p', '-t', validate_pane(pane),
                         '#{pane_id}|#{pane_dead}|#{pane_dead_status}').strip().split('|')
        if len(parts) != 3 or parts[0] != pane or parts[1] not in ('0', '1'):
            raise ToolError('pane missing or invalid status')
        return parts[1] == '1', parts[2]

    def alive(self, pane):
        if self.status(pane)[0]:
            raise ToolError('cannot send to exited pane')

    def set_pane_option(self, pane, name, value):
        self.run('set-option', '-p', '-t', pane, name, value)

    def pane_option(self, pane, name):
        return self.run('show-options', '-pqv', '-t', pane, name).rstrip('\n')

KEYS = {'Escape', 'Tab', 'BTab', 'Up', 'Down', 'Left', 'Right', 'Home', 'End',
        'PageUp', 'PageDown', 'BSpace', 'DC'} | {'C-' + c for c in 'abcdefghijklmnopqrstuvwxyz' if c not in 'jm'}
SUBMIT_KEYS = {'Enter', 'C-j', 'C-m'}

def send_submit(tmux, pane, key, confirmed):
    if not confirmed:
        raise ToolError('submission requires --received-confirmed after read-screen verification')
    if key not in SUBMIT_KEYS:
        raise ToolError('unsupported submit key')
    tmux.alive(pane)
    tmux.run('send-keys', '-t', pane, '--', key)
