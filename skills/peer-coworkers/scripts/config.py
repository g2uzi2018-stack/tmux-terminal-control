"""Bounded JSON configuration, private run directories, and explicit proxy setup."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

from common import ToolError
from records import read_json


def load_config():
    path = Path(os.environ.get('PEER_CONFIG', Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
                               / 'peer-coworkers/config.json')).expanduser()
    try:
        value = read_json(path, 65536)
    except FileNotFoundError:
        return {}
    if not isinstance(value, dict):
        raise ToolError('config.json must be an object')
    for key in ('proxy', 'profiles', 'snapshot'):
        if key in value and not isinstance(value[key], dict):
            raise ToolError(key + ' configuration must be an object')
    if 'runs_dir' in value and (not isinstance(value['runs_dir'], str) or not Path(value['runs_dir']).expanduser().is_absolute()):
        raise ToolError('runs_dir must be an absolute path')
    proxy = value.get('proxy', {})
    if proxy.get('mode', 'auto') not in ('auto', 'command', 'url', 'off'):
        raise ToolError('proxy.mode must be auto, command, url, or off')
    for key in ('max_files', 'max_bytes', 'max_record_bytes'):
        limit = value.get('snapshot', {}).get(key)
        if limit is not None and (type(limit) is not int or limit <= 0):
            raise ToolError('snapshot.' + key + ' must be a positive integer')
    for name, profile in value.get('profiles', {}).items():
        if not isinstance(profile, dict):
            raise ToolError('profile configuration must be an object')
        if 'path' in profile and (not isinstance(profile['path'], str) or not Path(profile['path']).is_absolute()):
            raise ToolError('profile path must be absolute')
        if 'approval_patterns' in profile and (not isinstance(profile['approval_patterns'], list) or
                any(not isinstance(pattern, str) or not pattern for pattern in profile['approval_patterns'])):
            raise ToolError('approval_patterns must be an array of nonempty regex strings')
        for key in ('prompt_lines', 'cancel_lines'):
            if key in profile and (type(profile[key]) is not int or profile[key] <= 0):
                raise ToolError(key + ' must be a positive integer')
        if profile.get('busy_regex') is not None:
            from wait import compile_pattern
            if not isinstance(profile['busy_regex'], str):
                raise ToolError('busy_regex must be text or null')
            compile_pattern(profile['busy_regex'])
        for key in ('approval_patterns',):
            from wait import compile_pattern
            for pattern in profile.get(key, []):
                compile_pattern(pattern)
    return value


def root_directory(value=None):
    root = Path(value) if value else Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'peer-coworkers'
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def runs_directory(value=None):
    if value or load_config().get('runs_dir'):
        return root_directory(value or load_config()['runs_dir'])
    root = Path('/tmp') / ('peer-coworkers-' + str(os.getuid()))
    root.mkdir(mode=0o700, exist_ok=True)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ToolError('default temporary root must be an owned private directory without symlinks')
    runs = root / 'runs'
    runs.mkdir(mode=0o700, exist_ok=True)
    info = runs.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ToolError('runs root must be an owned private directory without symlinks')
    return runs


def proxy_setup(proxy_url=None, no_proxy=False):
    from profiles import proxy_environment
    settings = load_config().get('proxy', {})
    if no_proxy and proxy_url is not None:
        raise ToolError('--no-proxy conflicts with --proxy-url')
    mode = 'off' if no_proxy else 'url' if proxy_url is not None else settings.get('mode', 'auto')
    url = proxy_url if proxy_url is not None else settings.get('url')
    if mode != 'off' and url is not None:
        proxy_environment(url)
    if mode == 'off':
        return {}, dict(mode=mode, command_ok=None, url=None), 'proxy setup disabled; inherited environment retained'
    if mode == 'url':
        if url is None:
            raise ToolError('proxy.url is required for url mode')
        return proxy_environment(url), dict(mode=mode, command_ok=None, url=url), 'explicit proxy environment'
    # Configured command text is trusted local configuration, never worker input.
    command = settings.get('command') if mode == 'command' else 'proxy_on'
    if not isinstance(command, str) or not command.strip() or '\x00' in command:
        raise ToolError('proxy.command must be nonblank Bash code')
    marker = '__PEER_PROXY_ENV__'
    capture = ('import json,os; print(' + repr(marker) + '+json.dumps({k:os.environ.get(k) for k in '
               '("HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","NO_PROXY",'
               '"http_proxy","https_proxy","all_proxy","no_proxy")}))')
    script = ('if ! declare -F proxy_on >/dev/null; then printf "__PEER_PROXY_ABSENT__\\n"; exit 0; fi\n' if mode == 'auto' else '')
    script += command + '\npeer_proxy_status=$?\nif [ "$peer_proxy_status" -ne 0 ]; then exit "$peer_proxy_status"; fi\nexec "$1" -c "$2"'
    result = subprocess.run(['/bin/bash', '-ic', script, 'peer-proxy', sys.executable, capture],
                            capture_output=True, text=True, timeout=15)
    if mode == 'auto' and result.returncode == 0 and '__PEER_PROXY_ABSENT__' in result.stdout.splitlines():
        return {}, dict(mode=mode, command_ok=None, url=None), 'proxy_on absent; automatic proxy not enabled'
    if result.returncode:
        raise ToolError('proxy setup failed; task remains prepared (exit ' + str(result.returncode) + ')')
    line = next((line[len(marker):] for line in reversed(result.stdout.splitlines()) if line.startswith(marker)), None)
    if line is None:
        raise ToolError('proxy command did not return an environment; task remains prepared')
    environment = json.loads(line)
    if url is not None:
        environment.update(proxy_environment(url))
    # Avoid persisting any credentials inherited from the user's shell.
    return environment, dict(mode=mode, command_ok=True, url=url), 'proxy command completed'
