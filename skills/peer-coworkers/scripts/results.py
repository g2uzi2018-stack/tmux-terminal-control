"""Validate the bounded task result envelope."""
import json

from common import ToolError

FIELDS = {'STATUS', 'RESULT', 'EVIDENCE', 'VALIDATION', 'REMAINING_WORK', 'RISKS'}


def validate_ready(value, record):
    if not isinstance(value, dict) or set(value) != {'task_id', 'attempt_id', 'round', 'STATUS'}:
        raise ToolError('ready requires exactly task_id, attempt_id, round, STATUS')
    if (any(value[key] != record[key] for key in ('task_id', 'attempt_id'))
            or type(value['round']) is not int or value['round'] != record['round']
            or value['STATUS'] != 'READY'):
        raise ToolError('ready must be READY for this task, attempt and round')
    return value


def validate_result(value, record):
    if not isinstance(value, dict) or set(value) != {'task_id', 'attempt_id', 'round', 'handoff'}:
        raise ToolError('result requires exactly task_id, attempt_id, round, handoff')
    if any(value[key] != record[key] for key in ('task_id', 'attempt_id')):
        raise ToolError('result belongs to another task or attempt')
    if type(value['round']) is not int or value['round'] != record['round']:
        raise ToolError('result belongs to another round')
    handoff = value['handoff']
    if not isinstance(handoff, dict) or set(handoff) != FIELDS:
        raise ToolError('handoff requires exactly the six documented fields')
    if handoff['STATUS'] not in ('DONE', 'PARTIAL', 'BLOCKED'):
        raise ToolError('invalid handoff STATUS')
    for key in FIELDS - {'STATUS'}:
        array = handoff[key]
        if not isinstance(array, list) or len(array) > 12 or any(
                not isinstance(item, str) or not item.strip() or len(item) > 2000 for item in array):
            raise ToolError(key + ' requires at most 12 nonblank strings of at most 2000 characters')
    if len(json.dumps(handoff, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) > 8192:
        raise ToolError('handoff exceeds 8 KiB')
    if (handoff['STATUS'] == 'DONE') != (not handoff['REMAINING_WORK']):
        raise ToolError('DONE requires no remaining work; PARTIAL/BLOCKED require remaining work')
    return value



def validate_question(value, record):
    if not isinstance(value, dict) or set(value) != {'task_id', 'attempt_id', 'round', 'QUESTION', 'OPTIONS', 'BLOCKING'}:
        raise ToolError('question requires task_id, attempt_id, round, QUESTION, OPTIONS, BLOCKING')
    if any(value[key] != record[key] for key in ('task_id', 'attempt_id')):
        raise ToolError('question belongs to another task or attempt')
    if type(value['round']) is not int or value['round'] != record['round']:
        raise ToolError('question belongs to another round')
    from records import nonblank
    nonblank(value['QUESTION'], 'QUESTION')
    if len(value['QUESTION']) > 2000 or type(value['BLOCKING']) is not bool:
        raise ToolError('question text exceeds limit or BLOCKING is not boolean')
    options = value['OPTIONS']
    if not isinstance(options, list) or len(options) > 12 or any(
            not isinstance(item, str) or not item.strip() or len(item) > 2000 for item in options):
        raise ToolError('OPTIONS requires at most 12 bounded nonblank strings')
    if len(json.dumps(value, ensure_ascii=True).encode()) > 16384:
        raise ToolError('question exceeds 16 KiB')
    return value
