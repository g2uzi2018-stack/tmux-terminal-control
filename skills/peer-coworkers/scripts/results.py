"""Validate the bounded task result envelope."""
import hashlib
import json
from pathlib import Path

from common import ToolError

FIELDS = {'STATUS', 'RESULT', 'EVIDENCE', 'VALIDATION', 'REMAINING_WORK', 'RISKS'}
VERDICTS = ('PASS', 'CHANGES_REQUESTED', 'INCONCLUSIVE')


def result_template(record):
    value = {key: record[key] for key in ('task_id', 'attempt_id', 'round')}
    value['handoff'] = dict(STATUS='DONE', RESULT=[], EVIDENCE=[], VALIDATION=[], REMAINING_WORK=[], RISKS=[])
    if record['role'] == 'review' and record.get('result_contract_version', 1) >= 2:
        value['review_verdict'] = 'INCONCLUSIVE'
    return value


def result_instructions(record):
    text = ('STATUS describes completion of your assigned work package. REMAINING_WORK lists only unfinished '
            'work assigned to you. DONE requires empty REMAINING_WORK; PARTIAL/BLOCKED require concrete remaining work. '
            'Each handoff array allows at most 12 nonblank strings of at most 2000 characters. '
            'Compact handoff JSON (UTF-8, ensure_ascii=False, separators=(",", ":")) must fit 8192 bytes; '
            'the entire result file must fit 16384 bytes. Do not truncate JSON or omit findings to fit. ')
    if record['role'] == 'review':
        text += ('An assigned review can be DONE even when the reviewed code needs fixes. Put findings in RESULT '
                 'and risks in RISKS, not REMAINING_WORK, unless fixing them was assigned to you. ')
        if record.get('result_contract_version', 1) >= 2:
            text += ('The top-level review_verdict is required: PASS, CHANGES_REQUESTED or INCONCLUSIVE. '
                     'It assesses the reviewed code independently of STATUS. Acceptance accepts the review report, '
                     'not delivery of the reviewed code. ')
    if record.get('report_path'):
        text += ('For a long report, atomically publish UTF-8 text of at most 1 MiB to ' + record['report_path']
                 + ' (temporary path: ' + record['report_path'] + '.tmp). This current-round report is permitted '
                 'for every role. Keep the handoff short and reference the report in EVIDENCE. '
                 'Never edit reports from prior rounds. ')
    return text


def report_metadata(record):
    """Bind the optional current-round report to collection and acceptance."""
    from records import read_bytes
    if not record.get('report_path'):
        return None
    try:
        data = read_bytes(Path(record['report_path']), 1024 * 1024, 'report exceeds 1 MiB')
    except FileNotFoundError:
        return None
    data.decode('utf-8')
    return dict(path=record['report_path'], bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def validate_ready(value, record):
    if not isinstance(value, dict) or set(value) != {'task_id', 'attempt_id', 'round', 'STATUS'}:
        raise ToolError('ready requires exactly task_id, attempt_id, round, STATUS')
    if (any(value[key] != record[key] for key in ('task_id', 'attempt_id'))
            or type(value['round']) is not int or value['round'] != record['round']
            or value['STATUS'] != 'READY'):
        raise ToolError('ready must be READY for this task, attempt and round')
    return value


def validate_result(value, record):
    fields = {'task_id', 'attempt_id', 'round', 'handoff'}
    if record.get('role') == 'review' and record.get('result_contract_version', 1) >= 2:
        fields.add('review_verdict')
    if not isinstance(value, dict) or set(value) != fields:
        raise ToolError('result requires exactly ' + ', '.join(sorted(fields)))
    if 'review_verdict' in fields and value['review_verdict'] not in VERDICTS:
        raise ToolError('review_verdict must be PASS, CHANGES_REQUESTED or INCONCLUSIVE')
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
        raise ToolError('DONE requires no unfinished assigned work; PARTIAL/BLOCKED require remaining work. '
                        'Review findings belong in RESULT/RISKS and review_verdict, not REMAINING_WORK')
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
