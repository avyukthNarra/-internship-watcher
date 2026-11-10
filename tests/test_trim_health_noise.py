import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import trim_health_noise as trim

BASE = {"last_completed_scan": 100, "matching_jobs": 5, "new_jobs": 0, "pending_deliveries": 0,
        "dead_deliveries": 0, "sync_error": None, "failed_sources": 1, "stale_failed_sources": 0,
        "successful_sources": 2,
        "sources": {"a": {"ok": True, "last_success": 1, "etag": "x", "full_fetch": 1},
                    "b": {"ok": False, "error": "HTTP 404", "failing_since": 50}}}


def run(*args, cwd):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


class TrimHealthNoiseTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        run("git", "init", "-q", cwd=self.root)
        run("git", "config", "user.email", "t@example.com", cwd=self.root)
        run("git", "config", "user.name", "t", cwd=self.root)
        for name in (*trim.STATE_FILES, "health.json"):
            (self.root / name).write_text(json.dumps(BASE if name == "health.json" else {}))
        run("git", "add", ".", cwd=self.root)
        run("git", "commit", "-q", "-m", "init", cwd=self.root)

    def write_health(self, **changes):
        health = json.loads(json.dumps(BASE))
        health.update(changes)
        (self.root / "health.json").write_text(json.dumps(health))

    def dirty(self):
        out = subprocess.run(["git", "status", "--porcelain"], cwd=self.root,
                             capture_output=True, text=True).stdout
        return {line[3:] for line in out.splitlines()}

    def test_timestamp_count_and_cache_noise_is_discarded(self):
        health = json.loads(json.dumps(BASE))
        health.update(last_completed_scan=999, matching_jobs=1, new_jobs=3)
        health["sources"]["a"].update(last_success=999, etag="y", full_fetch=999)
        (self.root / "health.json").write_text(json.dumps(health))
        self.assertEqual(self.dirty(), {"health.json"})
        trim.main(self.root)
        self.assertEqual(self.dirty(), set())

    def test_meaningful_health_changes_are_kept(self):
        for change in ({"pending_deliveries": 2}, {"sync_error": "Timeout"}, {"dead_deliveries": 1}):
            with self.subTest(change=change):
                self.write_health(**change)
                trim.main(self.root)
                self.assertEqual(self.dirty(), {"health.json"})
                run("git", "checkout", "--", "health.json", cwd=self.root)
        health = json.loads(json.dumps(BASE))
        health["sources"]["b"]["failing_since"] = 10  # the 5-hour timer must persist
        (self.root / "health.json").write_text(json.dumps(health))
        trim.main(self.root)
        self.assertEqual(self.dirty(), {"health.json"})

    def test_health_rides_along_when_other_state_changed(self):
        self.write_health(last_completed_scan=999)
        (self.root / "seen.json").write_text(json.dumps(["new"]))
        trim.main(self.root)
        self.assertEqual(self.dirty(), {"health.json", "seen.json"})

    def test_missing_or_corrupt_health_is_left_alone(self):
        (self.root / "health.json").write_text("not json")
        self.assertEqual(trim.main(self.root), 0)
        self.assertEqual(self.dirty(), {"health.json"})


if __name__ == "__main__":
    unittest.main()
