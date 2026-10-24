import unittest
from unittest.mock import patch
import sys
from support import SCRIPTS

sys.path.insert(0, str(SCRIPTS))

from timing import budget_status, finish_approval


class TimingTests(unittest.TestCase):
    def record(self, **extra):
        return dict(started_at=100, budget_origin='submission', startup_budget_seconds=300,
                    approval_budget_seconds=30, budget_seconds=60, **extra)

    def test_startup_does_not_consume_work_budget_and_remains_bounded(self):
        record = self.record()
        self.assertFalse(budget_status(record, 350)['exhausted'])
        self.assertTrue(budget_status(record, 400)['exhausted'])
        record['execution_started_at'] = 350
        self.assertEqual(budget_status(record, 360)['remaining_seconds'], 50)

    def test_observed_approval_grace_is_capped_and_settled_once(self):
        record = self.record(execution_started_at=100,
                             pending_approval=dict(status='waiting', observed_at=120))
        self.assertEqual(budget_status(record, 145)['remaining_seconds'], 40)
        self.assertEqual(budget_status(record, 190)['remaining_seconds'], 0)
        with patch('timing.time.time', return_value=150):
            finish_approval(record, 'submitted')
            finish_approval(record, 'submitted')
        self.assertEqual(record['approval_wait_seconds'], 30)
        self.assertEqual(budget_status(record, 155)['remaining_seconds'], 35)

    def test_legacy_records_keep_launch_based_budget(self):
        record = dict(started_at=100, budget_seconds=60)
        self.assertEqual(budget_status(record, 150)['remaining_seconds'], 10)
        self.assertTrue(budget_status(record, 160)['exhausted'])
        self.assertEqual(budget_status({})['phase'], 'prepared')
