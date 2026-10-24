"""Separate startup/work budgets and cap observed approval waiting grace."""
import time


def budget_status(record, now=None):
    now = time.time() if now is None else now
    launch = record.get('started_at')
    if launch is None:
        return dict(phase='prepared', remaining_seconds=None, exhausted=False)
    modern = record.get('budget_origin') == 'submission'
    execution = record.get('execution_started_at') if modern else launch
    if execution is None:
        remaining = record.get('startup_budget_seconds', 300) - max(0, now - launch)
        return dict(phase='startup', remaining_seconds=max(0, remaining), exhausted=remaining <= 0)
    waiting = record.get('approval_wait_seconds', 0)
    pending = record.get('pending_approval', {})
    if pending.get('status') == 'waiting':
        waiting += max(0, now - pending['observed_at'])
    grace = min(waiting, record.get('approval_budget_seconds', 300)) if modern else 0
    elapsed = max(0, now - execution)
    remaining = record['budget_seconds'] - max(0, elapsed - grace)
    return dict(phase='approval' if pending.get('status') == 'waiting' else 'execution',
                remaining_seconds=max(0, remaining), exhausted=remaining <= 0,
                execution_elapsed_seconds=max(0, elapsed - grace),
                approval_wait_seconds=waiting, approval_grace_seconds=grace)


def finish_approval(record, status):
    pending = record.get('pending_approval', {})
    if pending.get('status') == 'waiting':
        record['approval_wait_seconds'] = (record.get('approval_wait_seconds', 0)
                                           + max(0, time.time() - pending['observed_at']))
    if pending:
        pending['status'] = status
