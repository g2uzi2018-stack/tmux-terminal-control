"""Local CLI profiles. Availability does not establish authentication or compatibility."""
import shutil
import subprocess
import re
from urllib.parse import urlsplit

from common import ToolError

PROFILES = {
    'codex': {'enabled': True, 'args': ['--no-alt-screen', '--sandbox', 'workspace-write']},
    'agy': {'enabled': True, 'args': ['--sandbox']},
    'cursor': {'enabled': True, 'args': ['--sandbox', 'enabled'],
               'executables': ('cursor-agent', 'agent')},
    'opencode': {'enabled': False, 'args': []},
}


def resolve_executable(profile):
    for name in PROFILES[profile].get('executables', (profile,)):
        executable = shutil.which(name)
        if executable:
            return executable
    return None


def proxy_environment(url):
    """Validate an explicit proxy endpoint without retaining credentials in task records."""
    if url is None:
        return {}
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
    validate_model(model)
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
