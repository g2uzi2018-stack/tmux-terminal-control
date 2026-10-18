"""Behavioral probe fixture, not evidence for any real CLI."""
import json
import os
import select
import subprocess
import sys
import termios
import time
import tty

if '--version' in sys.argv:
    print('fake-probe-v1')
    sys.exit()
previous = termios.tcgetattr(0)
tty.setraw(0)
pending, text = bytearray(), bytearray()
in_paste = False
child = None
try:
    os.write(1, b'\x1b[?2004hREADY\r\n')
    while True:
        ready, _, _ = select.select([0], [], [], .05)
        if not ready:
            if pending == b'\x1b':
                pending.clear()
                if child and not os.environ.get('PEER_FAKE_FALSE_CANCEL'):
                    child.terminate()
                    child.wait(timeout=2)
                    child = None
                os.write(1, b'\x1b[2J\x1b[HTurn interrupted\r\n')
            continue
        data = os.read(0, 4096)
        if not data:
            break
        pending.extend(data)
        while pending:
            marker = b'\x1b[201~' if in_paste else b'\x1b[200~'
            if pending.startswith(marker):
                del pending[:len(marker)]
                in_paste = not in_paste
                if in_paste:
                    text.clear()
                else:
                    os.write(1, bytes(text).replace(b'\n', b'\r\n') + b'\r\n')
                continue
            if marker.startswith(pending):
                break
            char = pending.pop(0)
            if char in (10, 13) and not in_paste:
                content = text.decode()
                request = json.loads(content.splitlines()[0].removeprefix('PEER_PROBE '))
                kind = request['check']
                if os.environ.get('PEER_FAKE_NO_RESPONSE') == kind:
                    continue
                if kind == 'single_line':
                    os.write(1, (request['token'][::-1] + '\r\n').encode())
                elif kind == 'multiline':
                    second = content.splitlines()[1].split(': ', 1)[1]
                    os.write(1, (request['token'][::-1] + ':' + second[::-1] + '\r\n').encode())
                elif kind == 'long_response':
                    for number in range(1, request['lines'] + (0 if os.environ.get('PEER_FAKE_TRUNCATE') else 1)):
                        os.write(1, ('%03d:%s\r\n' % (number, request['token'][::-1])).encode())
                elif kind == 'result_file':
                    from pathlib import Path
                    path = Path(request['path'])
                    temporary = path.with_suffix('.tmp')
                    temporary.write_text(json.dumps(request['value']))
                    temporary.replace(path)
                elif kind == 'cancel':
                    if os.environ.get('PEER_FAKE_FORGE_HEARTBEAT'):
                        import re
                        from pathlib import Path
                        script = Path(request['command'][-1])
                        nonce = re.search(r"nonce='([0-9a-f]+)'", script.read_text()).group(1)
                        (script.parent / 'heartbeat.json').write_text(json.dumps(dict(pid=os.getpid(), nonce=nonce, count=99)))
                        continue
                    child = subprocess.Popen(request['command'])
                    os.write(1, b'BUSY: tool running\r\n')
                elif kind == 'approval':
                    # Approval text is the seventh physical nontrailing row.
                    os.write(1, b'Allow creation of this file?\r\n1\r\n2\r\n3\r\n4\r\n5\r\n6\r\n')
            else:
                text.append(char)
finally:
    if child:
        child.terminate()
        child.wait(timeout=2)
    termios.tcsetattr(0, termios.TCSANOW, previous)
