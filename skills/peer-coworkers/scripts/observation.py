"""Bounded event observation. Only a valid current-round JSON result signals completion."""
import json
from pathlib import Path
import time

from common import DeadlineReached, Tmux, ToolError
from records import read_json, save
from results import validate_question, validate_result
from wait import bounded_search, compile_pattern, prompt_region
import profiles


def terminal_flags(profile):
    options = profiles.settings(profile)
    flags = ['--prompt-lines', str(options['prompt_lines'])]
    for pattern in options['approval_patterns']:
        flags += ['--prompt', 'approval=' + pattern]
    if options.get('busy_regex'):
        flags += ['--busy-regex', options['busy_regex']]
    return flags


def wait_event(run, record, timeout_ms=25000, still_ms=600, poll_ms=50, stable_ms=120, session_missing=False, verify_session=False):
    if timeout_ms <= 0 or min(still_ms, poll_ms, stable_ms) <= 0:
        raise ToolError('wait intervals must be positive')
    if record['state'] not in ('running', 'awaiting_reply', 'submit_uncertain', 'reply_uncertain',
                                'partial', 'blocked', 'awaiting_acceptance', 'cancelling'):
        raise ToolError('wait requires a submitted task')
    started = time.monotonic()
    deadline = started + min(timeout_ms, 25000) / 1000
    # Version checks and regex matching share the same observation deadline.
    options = profiles.settings(record['profile'], deadline=deadline)
    patterns = [compile_pattern(pattern) for pattern in options['approval_patterns']]
    busy = compile_pattern(options['busy_regex']) if options.get('busy_regex') else None
    tmux = Tmux(record['socket'], deadline)
    screen, previous, quiet, pending, pending_since = '', None, None, None, None
    invalid = None
    result = dict(reason='timeout')
    try:
        if verify_session:
            from lease import session_gone
            from tasks import check_session
            session_missing = session_gone(record, deadline=deadline) is True
            if not session_missing:
                check_session(record, deadline=deadline)
        while time.monotonic() < deadline:
            now = time.monotonic()
            try:
                value = validate_result(read_json(Path(record['result_path']), 16384), record)
                signature = json.dumps(value, sort_keys=True, ensure_ascii=True)
                if signature != pending:
                    pending, pending_since = signature, now
                elif (now - pending_since) * 1000 >= stable_ms:
                    result = dict(reason='result_ready', result=value)
                    break
            except (OSError, ValueError, KeyError, TypeError, ToolError) as exc:
                pending, pending_since = None, None
                invalid = str(exc)
            try:
                if pending is not None:
                    raise ToolError('valid result is stabilizing; prefer it over a leftover question')
                question = validate_question(read_json(run / 'question.json', 16384), record)
                if record['state'] != 'cancelling':
                    record['state'] = 'awaiting_reply'
                result = dict(reason='question', question=question)
                break
            except (OSError, ValueError, KeyError, TypeError, ToolError):
                pass
            if session_missing:
                if pending is None:
                    result = dict(reason='exited', exit_code=None, session_gone=True)
                    break
                time.sleep(max(0, min(poll_ms / 1000, deadline-time.monotonic())))
                continue
            dead, code = tmux.status(record['pane'])
            screen = tmux.capture(record['pane'])
            region = prompt_region(screen, options['prompt_lines'])
            if any(bounded_search(pattern, line, deadline) for pattern in patterns for line in region):
                result = dict(reason='approval')
                break
            if dead:
                if not code and getattr(tmux, 'last_exit_signal', '') in ('', '0'):
                    time.sleep(max(0, min(.005, deadline-time.monotonic())))
                    continue
                # A complete JSON may have been published just before exit. Finish
                # its stable window rather than making callers race collect().
                if pending is None:
                    result = dict(reason='exited', exit_code=code or None)
                    break
            is_busy = bool(busy and bounded_search(busy, screen, deadline))
            if screen != previous or is_busy:
                previous, quiet = screen, now if not is_busy else None
            elif quiet is None:
                quiet = now
            if pending is None and quiet is not None and (now - quiet) * 1000 >= still_ms:
                result = dict(reason='attention')
                break
            time.sleep(max(0, min(poll_ms / 1000, deadline - time.monotonic())))
    except DeadlineReached:
        pass
    result.update(screen=screen, elapsed_ms=int((time.monotonic() - started) * 1000))
    if invalid and result['reason'] != 'result_ready':
        result['result_diagnostic'] = invalid
    record['last_wait'] = {key: value for key, value in result.items() if key not in ('screen', 'result')}
    save(run, record)
    return result


def receipt(tmux, pane, pointer, timeout=2):
    """Require the actual short pointer in the input display, including wrapped text."""
    deadline = time.monotonic() + timeout
    expected = ''.join(pointer.split())
    while time.monotonic() < deadline:
        if expected in ''.join(tmux.capture(pane).split()):
            return True
        time.sleep(.05)
    return False
