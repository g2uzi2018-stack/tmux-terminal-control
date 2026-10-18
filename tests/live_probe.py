"""Explicit live compatibility run. Invoke separately with PEER_LIVE=1."""
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/peer-coworkers/scripts'))
import probe


class LiveProbe(unittest.TestCase):
    def test_selected_profile(self):
        self.assertEqual(os.environ.get('PEER_LIVE'), '1', 'PEER_LIVE=1 is required')
        profile = os.environ.get('PEER_PROFILE', 'cursor')
        report = probe.run(profile, cwd=ROOT, timeout_ms=int(os.environ.get('PEER_TIMEOUT_MS', '90000')),
                           budget_seconds=int(os.environ.get('PEER_PROBE_BUDGET', '540')))
        report['invocation_limits'] = dict(per_check_timeout_ms=int(os.environ.get('PEER_TIMEOUT_MS', '90000')),
                                           total_budget_seconds=int(os.environ.get('PEER_PROBE_BUDGET', '540')))
        path = ROOT / 'docs/local' / ('probe-' + profile + '.json')
        path.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({name: item['status'] for name, item in report['checks'].items()}), flush=True)
        # Unknown/blocked capabilities are evidence, not fabricated test failures or passes.
        self.assertEqual(set(report['checks']), set(probe.CHECKS))
        self.assertTrue(all(not item.get('cleanup_errors') for item in report['checks'].values()), report)
