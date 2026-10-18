"""A deterministic terminal peer for exercising orchestration, never a real model."""
import argparse
import json
import os
from pathlib import Path
import sys
import termios
import tty

parser = argparse.ArgumentParser()
parser.add_argument('--run', type=Path, required=True)
args = parser.parse_args()
record = json.loads((args.run / 'task.json').read_text())
previous = termios.tcgetattr(sys.stdin.fileno())
tty.setraw(sys.stdin.fileno())
try:
    os.write(1, b'\x1b[?2004hREADY\r\n')
    data, paste, submits = bytearray(), False, 0
    pending = bytearray()
    while True:
        raw = os.read(0, 4096)
        if not raw:
            break
        pending.extend(raw)
        while pending:
            marker = b'\x1b[201~' if paste else b'\x1b[200~'
            if pending.startswith(marker):
                del pending[:len(marker)]
                paste = not paste
                if not paste:
                    os.write(1, b'RECEIVED ' + bytes(data) + b'\r\n')
                else:
                    data.clear()
                continue
            if marker.startswith(pending):
                break
            char = pending.pop(0)
            if char in (10, 13) and not paste:
                record = json.loads((args.run / 'task.json').read_text())
                submits += 1
                handoff = dict(STATUS='DONE', RESULT=['deterministic peer completed'],
                               EVIDENCE=['submit_count=' + str(submits)], VALIDATION=['fake peer only'],
                               REMAINING_WORK=[], RISKS=[])
                result = dict(task_id=record['task_id'], attempt_id=record['attempt_id'], round=record['round'], handoff=handoff)
                (args.run / 'temporary-result.json').write_text(json.dumps(result))
                os.replace(args.run / 'temporary-result.json', record['result_path'])
                (args.run / 'submits.txt').write_text(str(submits))
                os.write(1, b'RESULT_READY\r\n')
            else:
                data.append(char)
finally:
    termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, previous)
