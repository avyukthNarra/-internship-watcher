import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

import notion_sync as notion
from job_utils import job_identity


def job():
    return {"id": "ashby:example:job", "company": "Example", "title": "SWE Intern",
            "url": "https://jobs.ashbyhq.com/example/job", "location": "Austin, TX"}


class NotionSyncTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        paths = patch.multiple(notion, ROOT=self.root, STATE_PATH=self.root / "state.json",
                               MSG_MAP_PATH=self.root / "messages.json")
        paths.start()
        self.addCleanup(paths.stop)
        env = patch.dict(os.environ, {"NOTION_TOKEN": "test", "NOTION_PARENT_PAGE_ID": "parent"}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        notion._PAGE_CACHE.clear()
        notion.SYNC_ERRORS.clear()
        self.addCleanup(notion._PAGE_CACHE.clear)
        self.addCleanup(notion.SYNC_ERRORS.clear)

    def test_recovered_network_and_server_errors_do_not_fail_sync(self):
        good = Mock(status_code=200)
        good.json.return_value = {"results": []}
        with patch.object(notion.requests, "request", side_effect=[requests.Timeout(), Mock(status_code=503), good]) as api, \
             patch.object(notion.time, "sleep"):
            self.assertEqual(notion._notion("POST", "/databases/db/query"), {"results": []})
        self.assertEqual(api.call_count, 3)
        self.assertEqual(notion.SYNC_ERRORS, [])

    def test_exhausted_rate_limit_is_reported_once(self):
        with patch.object(notion.requests, "request", return_value=Mock(status_code=429, headers={})) as api, \
             patch.object(notion.time, "sleep"):
            self.assertIsNone(notion._notion("PATCH", "/pages/page", {}))
        self.assertEqual(api.call_count, 3)
        self.assertEqual(len(notion.SYNC_ERRORS), 1)
        self.assertIn("429", notion.SYNC_ERRORS[0])

    def test_ambiguous_server_error_on_create_is_not_retried(self):
        with patch.object(notion.requests, "request", return_value=Mock(status_code=503)) as api:
            self.assertIsNone(notion._notion("POST", "/pages", {}))
        self.assertEqual(api.call_count, 1)
        self.assertEqual(notion.SYNC_ERRORS, ["Notion HTTP 503"])

    def test_pin_failure_is_durable_and_retries_after_message_disappears(self):
        j = job()
        notion.MSG_MAP_PATH.write_text(json.dumps({"message": {"cid": "channel", "job": j}}))
        state = {"users": {}}

        def ensure(user, parent, days):
            user["db"] = "db"
            return True

        with patch.object(notion, "_pinned_message_ids", return_value={"message"}), \
             patch.object(notion, "_pin_reactors", return_value=[{"id": "u", "username": "member"}]), \
             patch.object(notion, "_ensure_tracker", side_effect=ensure), \
             patch.object(notion, "_upsert_row", return_value=None):
            notion._sync_pins(state, "token", "parent", {})
        saved = notion._state()
        self.assertIn("u:" + j["id"], saved["pending_pins"])
        self.assertEqual(saved["users"]["u"]["jobs"], [])

        notion.MSG_MAP_PATH.write_text("{}")
        with patch.object(notion, "_ensure_tracker", side_effect=ensure), \
             patch.object(notion, "_upsert_row", return_value={"id": "page"}) as upsert:
            notion._sync_pins(saved, "token", "parent", {})
            notion._sync_pins(saved, "token", "parent", {})
        upsert.assert_called_once()
        saved = notion._state()
        self.assertEqual(saved["pending_pins"], {})
        self.assertEqual(saved["users"]["u"]["jobs"], [j["id"]])
        self.assertEqual(saved["users"]["u"]["pages"][job_identity(j)], "page")

    def test_allowlist_ignores_other_pin_reactors_and_empty_allowlist_allows_all(self):
        j = job()
        notion.MSG_MAP_PATH.write_text(json.dumps({"message": {"cid": "channel", "job": j}}))
        reactors = [{"id": "stranger", "username": "x"}, {"id": "friend", "username": "y"}]

        def ensure(user, parent, days):
            user["db"] = "db"
            return True

        for allowed, expected in ((["friend"], {"friend"}), ([], {"stranger", "friend"})):
            state = {"users": {}}
            with patch.object(notion, "_pinned_message_ids", return_value={"message"}), \
                 patch.object(notion, "_pin_reactors", return_value=reactors), \
                 patch.object(notion, "_ensure_tracker", side_effect=ensure), \
                 patch.object(notion, "_upsert_row", return_value={"id": "page"}):
                notion._sync_pins(state, "token", "parent", {"allowed_user_ids": allowed})
            self.assertEqual(set(state["users"]), expected)

    def collect(self, messages, cfg=None):
        state = {"users": {}, "applied_after": "0"}
        with patch.object(notion, "_channel_messages", return_value=messages), \
             patch.object(notion, "_react") as react:
            notion._collect_applied(state, "token", "channel", cfg)
        return state, react

    def test_applied_channel_ignores_users_outside_the_allowlist(self):
        messages = [{"id": "1", "author": {"id": "stranger"}, "content": "https://example.com/jobs/1"},
                    {"id": "2", "author": {"id": "friend"}, "content": "https://example.com/jobs/2"}]
        state, react = self.collect(messages, {"allowed_user_ids": ["friend"]})
        self.assertEqual(list(state["pending_applied"]), ["2:0"])
        react.assert_not_called()
        self.assertEqual(state["applied_after"], "2")

    def test_applied_links_are_capped_per_message_and_per_run(self):
        many = " ".join(f"https://example.com/jobs/{i}" for i in range(8))
        state, react = self.collect([{"id": "1", "author": {"id": "u"}, "content": many}])
        self.assertEqual(len(state["pending_applied"]), notion.MAX_LINKS_PER_MESSAGE)
        react.assert_called_once_with("token", "channel", "1", notion.WARN_EMOJI)

        flood = [{"id": str(i), "author": {"id": "u"}, "content": f"https://example.com/jobs/{i}"}
                 for i in range(1, 31)]
        state, react = self.collect(flood)
        self.assertEqual(len(state["pending_applied"]), notion.MAX_APPLIED_LINKS_PER_RUN)
        react.assert_not_called()
        # The cursor stops after the last queued message, so the rest is read next run.
        self.assertEqual(state["applied_after"], str(notion.MAX_APPLIED_LINKS_PER_RUN))

    def test_applied_message_is_acknowledged_only_after_every_link_succeeds(self):
        state = {"users": {}, "applied_after": "1"}
        message = {"id": "2", "author": {"id": "u"},
                   "content": "https://example.com/jobs/1 https://example.com/jobs/2"}

        def ensure(user, parent, days):
            user["db"] = "db"
            return True

        with patch.dict(os.environ, {"APPLIED_CHANNEL_ID": "channel"}), \
             patch.object(notion, "_channel_messages", return_value=[message]), \
             patch.object(notion, "_ensure_tracker", side_effect=ensure), \
             patch.object(notion, "_parse_job_from_url", return_value=("Example", "Intern", "TX")), \
             patch.object(notion, "_upsert_row", side_effect=[{"id": "page-1"}, None]), \
             patch.object(notion, "_react") as react:
            notion._sync_applied(state, "token", "parent", {})
        react.assert_not_called()
        saved = notion._state()
        self.assertEqual(list(saved["pending_applied"]), ["2:1"])
        with patch.dict(os.environ, {"APPLIED_CHANNEL_ID": "channel"}), \
             patch.object(notion, "_channel_messages", return_value=[]), \
             patch.object(notion, "_ensure_tracker", side_effect=ensure), \
             patch.object(notion, "_upsert_row", return_value={"id": "page-2"}), \
             patch.object(notion, "_react") as react:
            notion._sync_applied(saved, "token", "parent", {})
        react.assert_called_once_with("token", "channel", "2", notion.CHECK_EMOJI)
        self.assertEqual(notion._state()["pending_applied"], {})

    def test_explicit_empty_configuration_is_respected(self):
        (self.root / "config.json").write_text("not valid JSON")
        notion.run([], cfg={})
        self.assertTrue(notion.STATE_PATH.exists())

    def test_each_sync_starts_with_fresh_page_cache(self):
        notion._PAGE_CACHE["db"] = [{"id": "old-page"}]

        def log_master(j):
            self.assertEqual(notion._PAGE_CACHE, {})
            return True

        with patch.object(notion, "log_master", side_effect=log_master):
            notion.run([job()], cfg={})
