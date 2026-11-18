import unittest
from tools.scheduled_daily import completed, hibernate_allowed


class ScheduledDailyTests(unittest.TestCase):
    def state(self):
        return {'collected_date': '2026-11-08', 'mode': 'production', 'status': 'complete',
                'cloud_processing': 'succeeded', 'expected_stores': 1,
                'results': [{'source': 'x', 'store_id': '1', 'status': 'uploaded', 'rows': 3,
                             'category_counts': {'Egg': 1, 'Milk': 1, 'Meat': 1}}]}

    def test_only_complete_confirmed_day_is_skipped(self):
        state = self.state()
        self.assertTrue(completed(state, {('x', '1')}, '2026-11-08'))
        for key, value in [('cloud_processing', 'submitted'), ('mode', 'test'), ('status', 'partial_failure')]:
            changed = dict(state, **{key: value})
            self.assertFalse(completed(changed, {('x', '1')}, '2026-11-08'))
        self.assertFalse(completed(state, {('x', '2')}, '2026-11-08'))
        self.assertFalse(completed(state, {('x', '1')}, '2026-11-09'))

    def test_any_user_activity_or_failure_prevents_hibernation(self):
        self.assertTrue(hibernate_allowed(True, 601, 10, 10))
        self.assertFalse(hibernate_allowed(True, 599, 10, 10))
        self.assertFalse(hibernate_allowed(True, 601, 10, 11))
        self.assertFalse(hibernate_allowed(False, 601, 10, 10))

    def test_incomplete_category_does_not_count_as_daily_success(self):
        state = self.state()
        state['results'][0]['category_counts']['Meat'] = 0
        self.assertFalse(completed(state, {('x', '1')}, '2026-11-08'))
