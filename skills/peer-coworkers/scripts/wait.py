#!/usr/bin/env python3
"""Bounded local screen polling with pane-local round state."""
import argparse
import base64
import binascii
import re
import signal
import sys
import time
import warnings
from common import DeadlineReached, SUBMIT_KEYS, Tmux, ToolError, send_submit, validate_pane

class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ToolError(message)

def encode(screen):
    return base64.b64encode(screen.encode('utf-8')).decode('ascii')

def decode(value):
    if not value:
        raise ToolError('no active round; use begin or submit-and-wait')
    try:
        return base64.b64decode(value, validate=True).decode('utf-8')
    except (binascii.Error, UnicodeError) as exc:
        raise ToolError('invalid pane round state') from exc

def compile_pattern(pattern, flags=0):
    """Reject patterns that compile only by ignoring a future-syntax warning."""
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        try:
            return re.compile(pattern, flags)
        except (re.error, Warning) as exc:
            raise ToolError('invalid regular expression: ' + str(exc)) from exc

def prompt_region(screen, count):
    """Last count physical lines after dropping trailing all-whitespace rows."""
    lines = screen.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    return lines[-count:]

def bounded_search(regex, text, deadline):
    """A user-supplied regex must not escape the local wait budget."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise DeadlineReached()
    previous_handler = signal.getsignal(signal.SIGALRM)
    def expired(signum, frame):
        raise DeadlineReached()
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, remaining)
    try:
        return regex.search(text)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)

def parse():
    p = Parser(description=__doc__)
    p.add_argument('mode', choices=('begin', 'resume', 'submit-and-wait'))
    p.add_argument('--socket', required=True)
    p.add_argument('--pane', required=True)
    p.add_argument('--timeout-ms', type=int, required=True)
    p.add_argument('--shell-timeout-ms', type=int, required=True)
    p.add_argument('--poll-ms', type=int, default=50)
    p.add_argument('--still-ms', type=int, default=600)
    p.add_argument('--prompt-lines', type=int, default=4)
    p.add_argument('--prompt', action='append', default=[], metavar='LABEL=REGEX')
    p.add_argument('--busy-regex')
    p.add_argument('--no-screen', action='store_true')
    p.add_argument('--received-confirmed', action='store_true')
    p.add_argument('--key', choices=sorted(SUBMIT_KEYS), default='Enter')
    a = p.parse_args()
    if a.timeout_ms <= 0 or a.shell_timeout_ms - a.timeout_ms < 250:
        raise ToolError('timeout must be positive and leave at least 250ms before Shell timeout')
    if min(a.poll_ms, a.still_ms, a.prompt_lines) <= 0:
        raise ToolError('poll-ms, still-ms and prompt-lines must be positive')
    if a.mode == 'submit-and-wait' and not a.received_confirmed:
        raise ToolError('submission requires --received-confirmed')
    a.patterns = []
    for prompt in a.prompt:
        label, sep, pattern = prompt.partition('=')
        if not sep or not pattern or not re.fullmatch(r'[A-Za-z0-9_-]+', label):
            raise ToolError('prompt must be LABEL=REGEX with a simple label')
        a.patterns.append((label, compile_pattern(pattern)))
    a.busy = compile_pattern(a.busy_regex, re.MULTILINE) if a.busy_regex else None
    validate_pane(a.pane)
    return a

def main():
    started = time.monotonic()
    a = None
    screen = None
    changed = False
    reason, extra = 'error', ''
    try:
        a = parse()
        deadline = started + a.timeout_ms / 1000
        tmux = Tmux(a.socket, deadline)
        pane = a.pane
        if a.mode == 'resume':
            baseline = decode(tmux.pane_option(pane, '@aitui_baseline'))
            flag = tmux.pane_option(pane, '@aitui_changed')
            if flag not in ('0', '1'):
                raise ToolError('invalid round changed flag')
            changed = flag == '1'
            previous = decode(tmux.pane_option(pane, '@aitui_previous'))
            quiet_value = tmux.pane_option(pane, '@aitui_quiet_since')
            try:
                quiet = float(quiet_value) if quiet_value else None
            except ValueError as exc:
                raise ToolError('invalid quiet timestamp') from exc
        else:
            baseline = tmux.capture(pane)
            previous, quiet = baseline, None
            tmux.set_pane_option(pane, '@aitui_baseline', '')
            tmux.set_pane_option(pane, '@aitui_changed', '0')
            tmux.set_pane_option(pane, '@aitui_previous', encode(previous))
            tmux.set_pane_option(pane, '@aitui_quiet_since', '')
            tmux.set_pane_option(pane, '@aitui_baseline', encode(baseline))
            if a.mode == 'submit-and-wait':
                send_submit(tmux, pane, a.key, a.received_confirmed)
        # Entire baseline detects residual lines even if they later move into the prompt area.
        old_lines = {label: {line for line in baseline.splitlines() if bounded_search(regex, line, deadline)}
                     for label, regex in a.patterns}
        reason = 'timeout'
        while time.monotonic() < deadline:
            dead, exit_code = tmux.status(pane)
            screen = tmux.capture(pane)
            now = time.monotonic()
            old_state = changed, previous, quiet
            if screen != baseline and not changed:
                changed = True
                # Persist the observation before a potentially expensive regex.
                tmux.set_pane_option(pane, '@aitui_changed', '1')
            busy = bool(a.busy and bounded_search(a.busy, screen, deadline))
            if screen != previous:
                previous, quiet = screen, now if changed and not busy else None
            elif busy or not changed:
                quiet = None
            elif quiet is None:
                quiet = now
            if old_state != (changed, previous, quiet):
                tmux.set_pane_option(pane, '@aitui_changed', '1' if changed else '0')
                tmux.set_pane_option(pane, '@aitui_previous', encode(previous))
                tmux.set_pane_option(pane, '@aitui_quiet_since', '' if quiet is None else str(quiet))
            if dead:
                if not exit_code and getattr(tmux, 'last_exit_signal', '') in ('', '0'):
                    # PTY closed, but no waitpid outcome yet. Continue under the
                    # same deadline instead of publishing an incomplete exit.
                    time.sleep(max(0, min(.005, deadline-time.monotonic())))
                    continue
                reason = 'exited'
                if re.fullmatch(r'-?[0-9]+', exit_code):
                    extra = ' exit_code=' + exit_code
                break
            region = prompt_region(screen, a.prompt_lines)
            for label, regex in a.patterns:
                if any(bounded_search(regex, line, deadline) and line not in old_lines[label]
                       for line in region):
                    reason, extra = 'prompt', ' match=' + label
                    break
            if reason == 'prompt':
                break
            if changed and not busy and quiet is not None and (now - quiet) * 1000 >= a.still_ms:
                reason = 'still'
                break
            time.sleep(max(0, min(a.poll_ms / 1000, deadline - time.monotonic())))
    except DeadlineReached:
        reason = 'timeout'
    except (ToolError, OSError) as exc:
        reason = 'error'
        print('error: ' + str(exc), file=sys.stderr)
    elapsed = int((time.monotonic() - started) * 1000)
    print('reason=' + reason + ' elapsed_ms=' + str(elapsed) + ' changed=' + str(int(changed)) + extra)
    if screen is not None and not (a and a.no_screen):
        sys.stdout.write(screen)
        if not screen.endswith('\n'):
            sys.stdout.write('\n')
    return 3 if reason == 'timeout' else 1 if reason == 'error' else 0

if __name__ == '__main__':
    sys.exit(main())
