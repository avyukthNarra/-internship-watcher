import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import notion_sync
import watcher


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.paths = patch.multiple(
            watcher,
            ROOT=self.root,
            CONFIG_PATH=self.root / "config.json",
            SEEN_PATH=self.root / "seen.json",
            MSG_MAP_PATH=self.root / "message_map.json",
        )
        self.paths.start()
        self.addCleanup(self.paths.stop)
        self.cfg = {
            "companies": [{"name": "Acme", "ats": "greenhouse", "board": "acme"}],
            "include_keywords": ["intern"],
            "exclude_keywords": [],
            "exclude_locations": [],
            "terms": [],
            "simplify": {"enabled": False},
            "jobright": {"enabled": False},
            "max_discord_per_run": 50,
        }
        (self.root / "config.json").write_text(json.dumps(self.cfg))

    @staticmethod
    def response(status=200):
        response = Mock(status_code=status, headers={})
        response.json.return_value = {
            "jobs": [{
                "id": 17,
                "title": "Software Engineering Intern",
                "location": {"name": "Austin, TX"},
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/17",
            }]
        }
        return response

    def run_with_source(self, responses, notify, notion_log, notion_run=None):
        response_iter = iter(responses)

        def get(*args, **kwargs):
            return next(response_iter)

        if notion_run is None:
            notion_run = Mock()
        env = {
            "DISCORD_WEBHOOK_URL": "https://discord.test/hook",
            "NOTION_TOKEN": "token",
            "NOTION_PARENT_PAGE_ID": "parent",
        }
        return patch.dict(os.environ, env, clear=True), patch.object(
            watcher.requests, "get", side_effect=get
        ), patch.object(watcher, "notify_discord", side_effect=notify), patch.object(
            notion_sync, "log_master", side_effect=notion_log
        ), patch.object(notion_sync, "run", notion_run), patch.object(
            watcher.time, "sleep"
        )

    def test_healthy_scan_delivers_once_and_second_scan_dedupes(self):
        posted = [{"mid": "m-17", "cid": "channel", "ts": 1}]
        notify = Mock(return_value=(
            [{**posted[0], "job": {
                "id": "greenhouse:acme:17",
                "company": "Acme",
                "title": "Software Engineering Intern",
                "location": "Austin, TX",
                "url": "https://boards.greenhouse.io/acme/jobs/17",
            }}],
            set(),
        ))
        notion_log = Mock(return_value=True)
        contexts = self.run_with_source(
            [self.response(), self.response()], notify, notion_log
        )
        with contexts[0], contexts[1], contexts[2] as send, contexts[3] as log, contexts[4] as sync, contexts[5]:
            self.assertEqual(watcher.main([]), 0)
            self.assertEqual(watcher.main([]), 0)

        self.assertEqual(send.call_count, 1)
        self.assertEqual(log.call_count, 1)
        self.assertEqual(sync.call_count, 2)
        self.assertEqual(json.loads((self.root / "delivery_state.json").read_text())["pending"], {})
        health = json.loads((self.root / "health.json").read_text())
        self.assertEqual(health["failed_sources"], 0)
        self.assertEqual(health["new_jobs"], 0)

    def test_failed_source_returns_one_after_successful_delivery_is_persisted(self):
        job = {
            "id": "greenhouse:acme:17",
            "company": "Acme",
            "title": "Software Engineering Intern",
            "location": "Austin, TX",
            "url": "https://boards.greenhouse.io/acme/jobs/17",
        }
        notify = Mock(return_value=([{"mid": "m", "cid": "c", "ts": 1, "job": job}], set()))
        notion_log = Mock(return_value=True)
        contexts = self.run_with_source(
            [self.response(), self.response(404), self.response(404), self.response(404)],
            notify,
            notion_log,
        )
        with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4], contexts[5]:
            self.assertEqual(watcher.main([]), 0)
            self.assertEqual(watcher.main([]), 1)

        state = json.loads((self.root / "delivery_state.json").read_text())
        self.assertEqual(state["pending"], {})
        self.assertIn(job["id"], state["known_ids"])
        health = json.loads((self.root / "health.json").read_text())
        self.assertEqual(health["failed_sources"], 1)
        self.assertEqual(health["pending_deliveries"], 0)
        self.assertEqual(notify.call_count, 1)

    def test_mixed_sources_deliver_healthy_jobs_and_report_failed_source(self):
        self.cfg["companies"] = [
            {"name": "GoodCo", "ats": "greenhouse", "board": "good"},
            {"name": "BrokenCo", "ats": "greenhouse", "board": "broken"},
        ]
        (self.root / "config.json").write_text(json.dumps(self.cfg))

        def get(url, **kwargs):
            if "/good/jobs" in url:
                return self.response()
            return self.response(404)

        def post(hook, jobs):
            return ([{"mid": "m-good", "cid": "c", "ts": 1, "job": jobs[0]}], set())

        notify = Mock(side_effect=post)
        notion_log = Mock(return_value=True)
        contexts = (
            patch.dict(os.environ, {
                "DISCORD_WEBHOOK_URL": "https://discord.test/hook",
                "NOTION_TOKEN": "token",
                "NOTION_PARENT_PAGE_ID": "parent",
            }, clear=True),
            patch.object(watcher.requests, "get", side_effect=get),
            patch.object(watcher, "notify_discord", side_effect=notify),
            patch.object(notion_sync, "log_master", side_effect=notion_log),
            patch.object(notion_sync, "run"),
            patch.object(watcher.time, "sleep"),
        )
        with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4], contexts[5]:
            self.assertEqual(watcher.main([]), 1)

        state = json.loads((self.root / "delivery_state.json").read_text())
        self.assertEqual(state["pending"], {})
        health = json.loads((self.root / "health.json").read_text())
        self.assertEqual(health["successful_sources"], 1)
        self.assertEqual(health["failed_sources"], 1)
        self.assertEqual(health["pending_deliveries"], 0)
        self.assertEqual(notify.call_count, 1)
        self.assertEqual(notion_log.call_count, 1)

    def test_sync_failure_keeps_sent_state_and_recovers_without_duplicate(self):
        job = {
            "id": "greenhouse:acme:17",
            "company": "Acme",
            "title": "Software Engineering Intern",
            "location": "Austin, TX",
            "url": "https://boards.greenhouse.io/acme/jobs/17",
        }
        notify = Mock(return_value=([{"mid": "m", "cid": "c", "ts": 1, "job": job}], set()))
        notion_log = Mock(return_value=True)
        sync = Mock(side_effect=[RuntimeError("temporary sync outage"), None])
        contexts = self.run_with_source(
            [self.response(), self.response()], notify, notion_log, sync
        )
        with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4], contexts[5]:
            self.assertEqual(watcher.main([]), 1)
            first_health = json.loads((self.root / "health.json").read_text())
            self.assertEqual(first_health["sync_error"], "RuntimeError")
            self.assertEqual(watcher.main([]), 0)

        state = json.loads((self.root / "delivery_state.json").read_text())
        self.assertEqual(state["pending"], {})
        self.assertEqual(notify.call_count, 1)
        self.assertEqual(sync.call_count, 2)


if __name__ == "__main__":
    unittest.main()
