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

    def test_unpolled_sources_do_not_remain_stale(self):
        health = self.health({}, {"removed": {"ok": False, "failing_since": 1}})
        self.assertEqual(health["sources"], {})
        self.assertEqual(health_exit_code(health), 0)
