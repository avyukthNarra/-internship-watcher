import copy
import unittest

from source_health import SOURCE_ALERT_AFTER, build_health, health_exit_code, health_summary


class SourceHealthTests(unittest.TestCase):
    def health(self, sources, previous=None, **overrides):
        return build_health(sources, previous or {}, **{
            "now": SOURCE_ALERT_AFTER + 100,
            "matching_jobs": 2, "new_jobs": 1,
            "pending_deliveries": 0, "sync_error": None, **overrides,
        })

    def test_only_persistent_failures_exceed_the_grace_period(self):
        sources = {"old": {"ok": False, "error": "HTTP 404"},
                   "new": {"ok": False, "error": "Timeout"},
                   "recovered": {"ok": True, "failing_since": 1}}
        before = copy.deepcopy(sources)
        health = self.health(sources, {"old": {"failing_since": 100}})
        self.assertEqual(health["failed_sources"], 2)
        self.assertEqual(health["stale_failed_sources"], 1)
        self.assertEqual(health["sources"]["old"]["failing_since"], 100)
        self.assertEqual(health["sources"]["new"]["failing_since"], health["last_completed_scan"])
        self.assertNotIn("failing_since", health["sources"]["recovered"])
        self.assertEqual(sources, before)
        self.assertEqual(health_exit_code(health), 1)
        self.assertIn("2 failed (1 down 5h+)", health_summary(health))

    def test_short_outage_succeeds_but_pending_delivery_or_sync_error_fails(self):
        sources = {"new": {"ok": False, "error": "HTTP 503"}}
        self.assertEqual(health_exit_code(self.health(sources)), 0)
        self.assertEqual(health_exit_code(self.health({}, pending_deliveries=1)), 1)
        self.assertEqual(health_exit_code(self.health({}, sync_error="Timeout")), 1)

    def test_one_stale_source_warns_but_a_broad_outage_fails(self):
        def stale(count, total):
            sources = {f"s{i}": {"ok": i >= count} for i in range(total)}
            previous = {f"s{i}": {"failing_since": 1} for i in range(count)}
            return self.health(sources, previous)
        one_of_twenty = stale(1, 20)
        self.assertEqual(one_of_twenty["stale_failed_sources"], 1)
        self.assertEqual(health_exit_code(one_of_twenty), 0)
        self.assertIn("1 failed (1 down 5h+)", health_summary(one_of_twenty))
        self.assertEqual(health_exit_code(stale(2, 20)), 1)
        self.assertEqual(health_exit_code(stale(1, 3)), 1)

    def test_unpolled_sources_do_not_remain_stale(self):
        health = self.health({}, {"removed": {"ok": False, "failing_since": 1}})
        self.assertEqual(health["sources"], {})
        self.assertEqual(health_exit_code(health), 0)
