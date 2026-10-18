"""Local CLI profiles. Availability does not establish authentication or compatibility."""
import shutil
import subprocess
import re
import time
from urllib.parse import urlsplit

from common import ToolError
from config import load_config

PROFILES = {
    'codex': {'enabled': True, 'args': ['--no-alt-screen', '--sandbox', 'workspace-write']},
    'agy': {'enabled': True, 'args': ['--sandbox']},
    'cursor': {'enabled': True, 'args': ['--sandbox', 'enabled'],
               'executables': ('cursor-agent', 'agent')},
    'opencode': {'enabled': False, 'args': []},
}


def resolve_executable(profile):
    path = load_config().get('profiles', {}).get(profile, {}).get('path')
    if path:
        return shutil.which(path)
    for name in PROFILES[profile].get('executables', (profile,)):
        executable = shutil.which(name)
        if executable:
            return executable
    return None


def proxy_environment(url):
    """Validate an explicit proxy endpoint without retaining credentials in task records."""
    if url is None:
        return {}
    if not isinstance(url, str):
        raise ToolError('proxy URL must be text')
    parsed = urlsplit(url)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or
            parsed.username is not None or parsed.password is not None or
            parsed.path not in ('', '/') or parsed.query or parsed.fragment or
            any(char.isspace() for char in url)):
        raise ToolError('proxy URL must be an HTTP(S) endpoint without credentials, path, or query')
    try:
        parsed.port
    except ValueError as exc:
        raise ToolError('invalid proxy port') from exc
    return {key: url for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
                                 'http_proxy', 'https_proxy', 'all_proxy')}


def validate_model(model):
    if model is not None and (not isinstance(model, str) or
            not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}', model)):
        raise ToolError('model must be a CLI model ID of at most 200 characters')
    return model


def command(profile, enable_opencode=False, model=None):
    model = validate_model(model if model is not None else load_config().get('profiles', {}).get(profile, {}).get('model'))
    if profile not in PROFILES:
        raise ToolError('unknown CLI profile')
    if not PROFILES[profile]['enabled'] and not enable_opencode:
        raise ToolError('OpenCode is compatibility-only; explicit --enable-opencode is required')
    executable = resolve_executable(profile)
    if not executable:
        raise ToolError(profile + ' executable not found in this environment')
    selected = ['--model', model] if model is not None else []
    return [executable, *PROFILES[profile]['args'], *selected]


def doctor():
    result = []
    for name, profile in PROFILES.items():
        executable = resolve_executable(name)
        item = dict(profile=name, executable=executable, enabled=profile['enabled'],
                    authentication='not_checked', version=None)
        # Do not execute a compatibility-only profile, including version probes.
        if executable and profile['enabled']:
            try:
                process = subprocess.run([executable, '--version'], capture_output=True,
                                         text=True, timeout=5)
                item['version'] = process.stdout.strip()[:200] if process.returncode == 0 else None
            except (OSError, subprocess.TimeoutExpired):
                pass
        result.append(item)
    return result


def settings(profile, for_probe=False, deadline=None):
    """Normal recognition uses explicit config or a passing version-bound report.

    Probe candidates are hypotheses to exercise, never compatibility assertions.
    """
    defaults = dict(approval_patterns=[], prompt_lines=4, cancel_lines=20,
                    busy_regex=r'(?i)(esc to (interrupt|cancel)|BUSY:)',
                    approval_verified_version=None)
    configured = load_config().get('profiles', {}).get(profile, {})
    if for_probe:
        if profile == 'agy':
            defaults.update(approval_patterns=[r'^Allow creation of this file\?$'], prompt_lines=8,
                            approval_verified_version='candidate from historical 1.3.5; currently under test')
        elif profile == 'cursor':
            defaults.update(approval_patterns=[r'^\s*Write to this file\?$'], prompt_lines=8,
                            approval_verified_version='candidate observed 2026-10-18; currently under test')
    elif 'approval_patterns' not in configured:
        import capabilities
        report = capabilities.latest(profile)
        if report:
            current = version(profile, timeout=min(5, max(.001, deadline-time.monotonic()))) if deadline else version(profile)
            comparison = capabilities.comparison(profile, current, check_version=False)
            check = report['checks'].get('approval', {})
            if comparison['version_matches'] and check.get('status') == 'passed':
                defaults.update(approval_patterns=check.get('patterns', []),
                                prompt_lines=check.get('prompt_lines', 4),
                                approval_verified_version=report['version'])
    defaults.update(configured)
    return defaults


def version(profile, timeout=5):
    executable = resolve_executable(profile)
    if not executable:
        return None
    try:
        process = subprocess.run([executable, '--version'], capture_output=True, text=True, timeout=timeout)
        return process.stdout.strip()[:200] if process.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None
