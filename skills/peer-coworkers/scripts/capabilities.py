"""Version-bound probe reports. Availability alone never enables cancellation."""
from common import ToolError
from config import root_directory
from records import read_json
import profiles


def report_path(profile):
    return root_directory() / 'probes' / (profile + '.json')


def latest(profile):
    try:
        value = read_json(report_path(profile), 256 * 1024)
        if (not isinstance(value, dict) or value.get('profile') != profile
                or not isinstance(value.get('checks'), dict)
                or any(not isinstance(item, dict) for item in value['checks'].values())):
            return None
        return value
    except (OSError, ValueError, ToolError, TypeError):
        return None


def comparison(profile, current_version=None, check_version=True):
    report = latest(profile)
    if current_version is None and check_version:
        current_version = profiles.version(profile)
    compatible = bool(report and current_version and report.get('version') == current_version
                      and report.get('executable') == profiles.resolve_executable(profile))
    return dict(probe=report, version_matches=compatible,
                warning=None if compatible else 'not retested after upgrade or no matching probe report',
                passed=[name for name, item in (report or {}).get('checks', {}).items() if item.get('status') == 'passed'],
                failed=[name for name, item in (report or {}).get('checks', {}).items() if item.get('status') != 'passed'])


def cancellation(profile):
    status = comparison(profile)
    check = (status['probe'] or {}).get('checks', {}).get('cancel', {})
    if not status['version_matches'] or check.get('status') != 'passed' or check.get('key') != 'Escape' or not check.get('stopped_pattern'):
        raise ToolError('cancellation is unverified for this executable/version; run probe or use close --allow-active')
    return check
