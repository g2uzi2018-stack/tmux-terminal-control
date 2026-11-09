"""Observe the current handoff, terminal approval or queued reply."""
import time

from common import DeadlineReached, Tmux, ToolError
from records import reconcile_submission, save, terminal_event
from results import HANDOFF_ERRORS, read_handoff
from wait import bounded_search, compile_pattern, prompt_region
from approvals import observe_approval
from timing import budget_status, finish_approval
import profiles


def terminal_flags(profile):
    options = profiles.settings(profile)
    flags = ['--prompt-lines', str(options['prompt_lines'])]
    for pattern in options['approval_patterns']:
        flags += ['--prompt', 'approval=' + pattern]
    if options.get('busy_regex'):
        flags += ['--busy-regex', options['busy_regex']]
    return flags


def wait_event(run, record, timeout_ms=25000):
    from lease import session_gone
    from tasks import check_session
    if timeout_ms <= 0:
        raise ToolError('wait interval must be positive')
    if record['closed'] or record['state'] not in ('running', 'submit_uncertain', 'reply_uncertain',
                                                   'partial', 'blocked', 'awaiting_acceptance', 'cancelling'):
        raise ToolError('wait requires an open submitted task')
    started = time.monotonic()
    deadline = started + min(timeout_ms, 25000) / 1000
    options = profiles.settings(record['profile'], deadline=deadline)
    patterns = [compile_pattern(pattern) for pattern in options['approval_patterns']]
    busy = compile_pattern(options['busy_regex']) if options.get('busy_regex') else None
    tmux = Tmux(record['socket'], deadline)
    screen, previous, quiet, pending, pending_since = '', None, None, None, None
    result = dict(reason='timeout')
    invalid = None
    try:
        session_missing = session_gone(record, deadline=deadline) is True
        if not session_missing:
            check_session(record, deadline=deadline)
        while time.monotonic() < deadline:
            if session_missing:
                dead, code = True, None
                finish_approval(record, 'session_gone')
            else:
                dead, code = tmux.status(record['pane'])
                screen = tmux.capture(record['pane'])
                if not dead:
                    region = prompt_region(screen, options['prompt_lines'])
                    configured = any(bounded_search(pattern, line, deadline) for pattern in patterns for line in region)
                    approval = observe_approval(record, screen, configured=configured)
                    if approval:
                        reason = 'approval' if approval['status'] == 'waiting' else 'attention'
                        result = dict(reason=reason, approval=approval)
                        break
            now = time.monotonic()
            try:
                handoff = read_handoff(record['result_path'])
                invalid = None
            except FileNotFoundError:
                handoff, invalid = None, None
            except HANDOFF_ERRORS as exc:
                handoff, invalid = None, str(exc)
            if handoff != pending:
                pending, pending_since = handoff, now
            if pending and now - pending_since >= .12:
                reconciliation = reconcile_submission(run, record, handoff)
                reason = 'question' if handoff['status'] == 'QUESTION' else 'result_ready'
                result = dict(reason=reason, result=handoff)
                if reconciliation:
                    result['submission_reconciliation'] = reconciliation
                break
            if not pending:
                if dead:
                    result = dict(reason='exited', exit_code=code or None, session_gone=session_missing)
                    break
                if budget_status(record)['exhausted']:
                    result = dict(reason='budget_exhausted')
                    break
                is_busy = bool(busy and bounded_search(busy, screen, deadline))
                if screen != previous or is_busy:
                    previous, quiet = screen, now if not is_busy else None
                elif quiet is None:
                    quiet = now
                if quiet is not None and now - quiet >= .6:
                    result = dict(reason='attention')
                    break
            time.sleep(max(0, min(.05, deadline - time.monotonic())))
    except DeadlineReached:
        pass
    result.update(screen=screen, elapsed_ms=int((time.monotonic() - started) * 1000), budget=budget_status(record))
    if result['reason'] in ('timeout', 'attention') and 'approval' not in result:
        from followups import observe_reply_queue
        result.update(observe_reply_queue(record, screen))
    if invalid:
        result['result_diagnostic'] = invalid
    result['terminal_events_path'] = terminal_event(run, record, result['reason'], screen)
    if record.get('terminal_event_diagnostic'):
        result['terminal_event_diagnostic'] = record['terminal_event_diagnostic']
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
