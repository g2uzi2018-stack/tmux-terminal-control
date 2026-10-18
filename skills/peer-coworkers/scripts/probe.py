"""Independent bounded interactive checks, with behavioral proof and exact cleanup."""
from contextlib import contextmanager
import datetime
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import uuid

from common import DeadlineReached, Tmux, ToolError, send_submit
from config import proxy_setup, root_directory, runs_directory
from records import atomic_json, read_json
from observation import receipt
from wait import bounded_search, compile_pattern, prompt_region
import capabilities
import profiles
import session

CHECKS = ('readiness', 'paste', 'single_line', 'multiline', 'cancel', 'approval',
          'result_file', 'long_response', 'cleanup')
STOPPED = r'^\s*(?:(?:[•●■]\s*)?(?:Turn interrupted.*|Request cancelled.*|Generation cancelled.*|Interrupted.*)|\$\s+.*\sCancelled\s+•\s+[0-9.]+(?:ms|s))\s*$'
GATE = re.compile(r'(?i)(do you trust|trust this (?:folder|directory|workspace)|trust the files|sign in to|login required|permission required)|(?m:^\s*(?:Run this command|Write to this file|Allow creation of this file)\?\s*$)')


class ProbeStopped(Exception):
    def __init__(self, status, evidence):
        self.status, self.evidence = status, evidence


class Driver:
    def __init__(self, profile, argv, cwd, directory, deadline, name):
        self.profile, self.argv, self.cwd = profile, argv, cwd
        self.directory, self.deadline, self.name = directory, deadline, name
        self.task = 'probe-' + uuid.uuid4().hex
        self.socket = 'ai-tui-' + self.task
        self.pane = None
        self.screen = ''
        self.raw_path = directory / (name + '.terminal')
        self.child = None
        self.environment = {}
        self.environ_matches = None
        self.submissions = 0
        self.escapes = 0

    def pause(self, seconds=.05):
        if time.monotonic() >= self.deadline:
            raise ProbeStopped('timeout', 'bounded check deadline exhausted')
        time.sleep(min(seconds, max(0, self.deadline - time.monotonic())))

    def start(self):
        # Delay exec until pipe-pane is attached, so bracketed-mode evidence is not lost.
        wrapped = ['/bin/sh', '-c', 'sleep 0.3; exec "$@"', 'peer-probe', *self.argv]
        result = session.new(SimpleNamespace(socket=self.socket, task=self.task, cwd=str(self.cwd),
                             session='cli', command=wrapped, width=140, height=45, history_limit=50000))
        self.pane = result['pane']
        self.tmux = Tmux(self.socket, self.deadline)
        self.tmux.run('pipe-pane', '-O', '-t', self.pane, 'cat > ' + shlex.quote(str(self.raw_path)))
        pid = self.tmux.run('display-message', '-p', '-t', self.pane, '#{pane_pid}').strip()
        values = dict(item.split(b'=', 1) for item in Path('/proc', pid, 'environ').read_bytes().split(b'\0') if b'=' in item)
        self.environ_matches = {key: values.get(key.encode()) == (value.encode() if value is not None else None)
                                for key, value in self.environment.items()}
        if not all(self.environ_matches.values()):
            raise ProbeStopped('failed', 'requested proxy environment did not reach actual pane process')

    def capture(self, history=False):
        self.screen = (self.tmux.run('capture-pane', '-p', '-S', '-', '-t', self.pane)
                       if history else self.tmux.capture(self.pane))
        return self.screen

    def raw(self):
        try:
            with self.raw_path.open('rb') as stream:
                stream.seek(max(0, self.raw_path.stat().st_size - 256 * 1024))
                return stream.read(256 * 1024)
        except FileNotFoundError:
            return b''

    def bracketed(self):
        modes = re.findall(rb'\x1b\[\?2004([hl])', self.raw())
        return bool(modes and modes[-1] == b'h')

    def approval(self):
        options = profiles.settings(self.profile, for_probe=True)
        return any(bounded_search(compile_pattern(pattern), line, self.deadline)
                   for pattern in options['approval_patterns']
                   for line in prompt_region(self.screen, options['prompt_lines']))

    def ready(self):
        while True:
            screen = self.capture()
            if GATE.search(screen) or self.approval():
                raise ProbeStopped('blocked', 'startup requires human action; no approval sent')
            if self.tmux.status(self.pane)[0]:
                raise ProbeStopped('failed', 'CLI exited before input readiness')
            if self.bracketed():
                return
            self.pause()

    def paste(self, text, multiline=False, verify=True):
        self.ready()
        args = ['--multiline-verified', 'raw terminal mode 2004h observed in this exact check'] if multiline else []
        process = subprocess.run([sys.executable, str(Path(__file__).with_name('input.py')), 'paste',
                                  '--socket', self.socket, '--pane', self.pane, *args],
                                 input=text.encode(), capture_output=True,
                                 timeout=max(.1, min(3, self.deadline - time.monotonic())))
        if process.returncode:
            raise ProbeStopped('failed', 'paste tool failed: ' + process.stderr.decode('utf-8', 'replace')[-500:])
        if verify:
            # A collapsed paste widget is not proof of receipt. Do not submit it.
            if not receipt(self.tmux, self.pane, text, timeout=min(2, max(.01, self.deadline-time.monotonic()))):
                raise ProbeStopped('unverified', 'literal input was not visible; no Enter sent')
        self.capture()

    def submit(self):
        if self.submissions:
            raise ToolError('probe must not submit a check twice')
        self.submissions += 1  # Persisted by caller evidence even if delivery fails.
        send_submit(self.tmux, self.pane, 'Enter', True)

    def until(self, predicate, history=False, allow_approval=False):
        while True:
            self.capture(history)
            if predicate():
                return
            if not allow_approval and self.approval():
                raise ProbeStopped('blocked', 'approval requested; retained without approval until exact cleanup')
            if GATE.search(self.screen):
                raise ProbeStopped('blocked', 'human gate observed; no approval sent (not a verified recognizer)')
            if self.tmux.status(self.pane)[0]:
                raise ProbeStopped('failed', 'CLI exited before behavioral evidence')
            self.pause()

    def cleanup(self):
        errors = []
        if self.child:
            pid, script = self.child
            try:
                command = Path('/proc', str(pid), 'cmdline').read_bytes().split(b'\0')
                if os.fsencode(script) in command:
                    os.kill(pid, signal.SIGTERM)
            except (FileNotFoundError, ProcessLookupError):
                pass
            except OSError as exc:
                errors.append(str(exc))
        if self.pane:
            try:
                # Independently verify every marker and exact pane before killing.
                from tasks import check_session
                check_session(dict(socket=self.socket, session='cli', task_id=self.task,
                                   cwd=str(self.cwd), pane=self.pane))
                session.cleanup(SimpleNamespace(socket=self.socket, session='cli', task=self.task, allow_active=True))
            except (ToolError, OSError) as exc:
                errors.append(str(exc))
            for _ in range(30):
                try:
                    if os.path.lexists(session.socket_dir() / self.socket):
                        session.prune(SimpleNamespace(socket=self.socket))
                    break
                except (ToolError, OSError) as exc:
                    if not os.path.lexists(session.socket_dir() / self.socket):
                        break
                    if 'still accepting connections' in str(exc):
                        time.sleep(.01)
                        continue
                    errors.append(str(exc))
                    break
            else:
                errors.append('exact server did not finish shutdown within 300 ms')
        return errors


def request(kind, **values):
    return 'PEER_PROBE ' + json.dumps(dict(check=kind, **values), ensure_ascii=False)


def check_readiness(driver):
    nonce = 'peer-ready-' + uuid.uuid4().hex[:12]
    driver.paste(nonce)
    return dict(method='literal nonce received with observed bracketed-paste mode, no Enter', nonce=nonce)


def check_paste(driver):
    nonce = 'peer-paste-' + uuid.uuid4().hex[:8] + ' 中文 $literal `text`'
    driver.paste(nonce)
    return dict(method='literal Unicode and shell metacharacters displayed after separate paste', nonce=nonce)


def check_single_line(driver):
    token = uuid.uuid4().hex[:12]
    expected = token[::-1]
    driver.paste(request('single_line', token=token,
                        instruction='Reply exactly with token reversed. Do not use tools or change files.'))
    driver.submit()
    driver.until(lambda: expected in driver.screen)
    return dict(method='computed reverse token absent from prompt observed only after one Enter', response=expected)


def check_multiline(driver):
    first, second = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
    expected = first[::-1] + ':' + second[::-1]
    text = request('multiline', token=first,
                   instruction='Reverse token and the second token on the following line; join with colon. Reply only that, no tools.')
    text += '\nSecond token: ' + second
    driver.paste(text, multiline=True)
    driver.pause(.15)
    if expected in driver.capture():
        raise ProbeStopped('failed', 'response appeared before explicit submission')
    driver.submit()
    driver.until(lambda: expected in driver.screen)
    return dict(method='raw 2004h, both literal input lines, no early response, computed reply after one Enter', response=expected)


def check_result_file(driver):
    target = driver.directory / 'worker-result.json'
    expected = dict(probe=uuid.uuid4().hex)
    driver.paste(request('result_file', path=str(target), value=expected,
                        instruction='Write value as JSON to path atomically (temporary file then rename). Do not change other files or permissions.'))
    driver.submit()
    def written():
        try:
            return read_json(target, 16384) == expected
        except (OSError, ValueError, ToolError):
            return False
    driver.until(written)
    return dict(method='bounded no-follow JSON read equals unpredictable nonce', path=str(target), value=expected)


def check_long_response(driver):
    token = uuid.uuid4().hex[:10]
    expected = token[::-1]
    driver.paste(request('long_response', token=token, lines=150,
                        instruction='Print exactly 150 lines, numbered 001 through 150, each NUMBER:REVERSED_TOKEN. No code fence, tools, or files.'))
    driver.submit()
    def complete():
        found = set(re.findall(r'(?m)^\s*(?:[│>|•]\s*)?(\d{3}):\s*' + re.escape(expected) + r'\s*$', driver.screen))
        return found == {str(number).zfill(3) for number in range(1, 151)}
    driver.until(complete, history=True)
    return dict(method='all 150 computed lines recovered through capture-pane -S -, beyond the 45-row viewport', lines=150)


def check_approval(driver):
    # Deliberately outside cwd and /tmp. Only this unique path may be requested.
    target = root_directory() / ('probe-approval-' + uuid.uuid4().hex + '.txt')
    try:
        driver.paste(request('approval', path=str(target),
                            instruction='Try writing the word probe to path. Do not change permissions or approve anything; stop if refused.'))
        driver.submit()
        def detected():
            if os.path.lexists(target):
                raise ProbeStopped('failed', 'file was written without a recognized approval; not evidence of approval support')
            return driver.approval()
        driver.until(detected, allow_approval=True)
        return dict(method='profile regex matched actual prompt region while requested file remained absent; no approval sent',
                    prompt_lines=profiles.settings(driver.profile, for_probe=True)['prompt_lines'],
                    patterns=profiles.settings(driver.profile, for_probe=True)['approval_patterns'])
    finally:
        # Never follow a worker-created symlink during cleanup.
        if os.path.lexists(target):
            target.unlink()


def check_cancel(driver):
    heartbeat = driver.directory / 'heartbeat.json'
    finished = driver.directory / 'finished.json'
    script = driver.directory / 'heartbeat.py'
    nonce = uuid.uuid4().hex
    script.write_text('import json,os,time\nfrom pathlib import Path\n'
                      'for count in range(600):\n'
                      ' p=Path(' + repr(str(heartbeat)) + ')\n'
                      ' t=p.with_suffix(".tmp")\n'
                      ' t.write_text(json.dumps(dict(pid=os.getpid(),nonce=' + repr(nonce) + ',count=count)))\n'
                      ' t.replace(p)\n time.sleep(.2)\n'
                      'Path(' + repr(str(finished)) + ').write_text("finished")\n')
    driver.paste(request('cancel', command=[sys.executable, str(script)],
                        instruction='Execute command using your shell tool and wait for completion. Do not start other commands, modify other files, or change permissions.'))
    driver.submit()
    current = {}
    first_sample = {}
    def active():
        try:
            value = read_json(heartbeat, 16384)
            pid = value.get('pid')
            if value.get('nonce') != nonce or type(pid) is not int or pid <= 1:
                return False
            process = Path('/proc', str(pid))
            if process.stat().st_uid != os.getuid() or os.fsencode(script) not in (process / 'cmdline').read_bytes().split(b'\0'):
                return False
            if first_sample.get('pid') != pid:
                first_sample.update(pid=pid, count=value['count'])
            current.update(value)
            driver.child = (pid, str(script))
            return value['count'] >= first_sample['count'] + 2
        except (OSError, ValueError, ToolError, TypeError, KeyError):
            return False
    driver.until(active)
    driver.escapes += 1
    driver.tmux.run('send-keys', '-t', driver.pane, '--', 'Escape')
    stopped = compile_pattern(STOPPED)
    def interrupted():
        # Require an actual live tool process to stop, not just a quiet screen.
        try:
            process_state = Path('/proc', str(current['pid']), 'stat').read_text().rsplit(')', 1)[1].split()[0]
            alive = process_state != 'Z'  # A zombie cannot execute or write again.
        except FileNotFoundError:
            alive = False
        return not alive and not finished.exists() and any(
            bounded_search(stopped, line, driver.deadline)
            for line in prompt_region(driver.screen, profiles.settings(driver.profile, for_probe=True)['cancel_lines']))
    driver.until(interrupted)
    return dict(method='heartbeat proved live execution; one Escape; process gone, no completion file, explicit interruption marker',
                key='Escape', stopped_pattern=STOPPED, heartbeat=str(heartbeat))


def check_cleanup(driver):
    driver.ready()
    tmux = driver.tmux
    target = tmux.run('new-session', '-d', '-P', '-F', '#{session_id}', '-s', 'probe-sentinel', '/bin/sleep', '30').strip()
    sentinel_task = driver.task + '-sentinel'
    try:
        for option, value in (('@owner', session.OWNER), ('@task', sentinel_task), ('@cwd', str(driver.cwd))):
            tmux.run('set-option', '-t', target, option, value)
        session.cleanup(SimpleNamespace(socket=driver.socket, session='cli', task=driver.task, allow_active=True))
        driver.pane = None
        tmux.run('has-session', '-t', '=probe-sentinel')
        names = tmux.run('list-sessions', '-F', '#{session_name}').splitlines()
        if names != ['probe-sentinel']:
            raise ProbeStopped('failed', 'unexpected sessions after exact target cleanup')
    finally:
        session.cleanup(SimpleNamespace(socket=driver.socket, session='probe-sentinel', task=sentinel_task, allow_active=True))
        # tmux shutdown can complete shortly after kill-session returns.
        for _ in range(20):
            try:
                if os.path.lexists(session.socket_dir() / driver.socket):
                    session.prune(SimpleNamespace(socket=driver.socket))
                break
            except ToolError as exc:
                if 'still accepting connections' not in str(exc):
                    raise
                time.sleep(.01)
    return dict(method='exact marked CLI session removed, same-server sentinel survived, then sentinel and exact stale socket cleaned')


def run(profile, model=None, cwd=None, timeout_ms=25000, budget_seconds=240,
        no_proxy=False, proxy_url=None, enable_opencode=False):
    if timeout_ms <= 0 or budget_seconds <= 0:
        raise ToolError('probe budgets must be positive')
    argv = profiles.command(profile, enable_opencode, model)
    environment, proxy, notice = proxy_setup(proxy_url, no_proxy)
    report = dict(profile=profile, executable=argv[0], command=argv, version=profiles.version(profile),
                  date=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  origin='interactive behavioral probe', checks={}, proxy=proxy, proxy_notice=notice,
                  limits=dict(per_check_timeout_ms=timeout_ms, total_budget_seconds=budget_seconds))
    directory = Path(tempfile.mkdtemp(prefix='probe-', dir=runs_directory()))
    report['artifacts'] = str(directory)
    destination = capabilities.report_path(profile)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    deadline = time.monotonic() + budget_seconds
    cwd = Path(cwd or os.getcwd()).resolve()
    from tasks import launch_environment
    with launch_environment(environment) as applied:
        for name in CHECKS:
            started = time.monotonic()
            if started >= deadline:
                report['checks'][name] = dict(status='timeout', evidence='overall probe budget exhausted before this check',
                                              version=report['version'], date=datetime.datetime.now(datetime.timezone.utc).isoformat())
                atomic_json(destination, report)
                continue
            driver = Driver(profile, argv, cwd, directory, min(deadline, started + timeout_ms / 1000), name)
            driver.environment = applied
            item = dict(status='failed')
            try:
                driver.start()
                proof = globals()['check_' + name](driver)
                item.update(status='passed', **proof)
            except ProbeStopped as exc:
                item.update(status=exc.status, evidence=exc.evidence)
            except (ToolError, OSError, ValueError, KeyError, TypeError, DeadlineReached, subprocess.TimeoutExpired) as exc:
                item.update(status='timeout' if isinstance(exc, (DeadlineReached, subprocess.TimeoutExpired)) else 'failed',
                            evidence=str(exc) or 'check deadline exhausted without required behavioral evidence')
            finally:
                # Capture before cleaning; no resend occurs on any failed stage.
                if driver.pane:
                    try:
                        # The check deadline may be over, so allow a separate bounded diagnostic read.
                        driver.tmux = Tmux(driver.socket)
                        item['screen'] = driver.capture()[-6000:]
                    except ToolError as exc:
                        item['capture_error'] = str(exc)
                errors = driver.cleanup()
                item.update(version=report['version'], date=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            elapsed_seconds=round(time.monotonic()-started, 3), submissions=driver.submissions,
                            escapes=driver.escapes, socket=driver.socket, pane_environment_matches=driver.environ_matches, raw_terminal=str(driver.raw_path), cleanup_errors=errors)
                if errors and item['status'] == 'passed':
                    item['status'] = 'failed'
                report['checks'][name] = item
                atomic_json(destination, report)
    report['report_path'] = str(destination)
    atomic_json(destination, report)
    return report
