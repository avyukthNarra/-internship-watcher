import json
import unittest

from site_export import (EXPORT_FIELDS, MAX_SITE_EXPORT_JOBS,
                         build_jobs_export)


class SiteExportTests(unittest.TestCase):
    def test_allowlist_and_private_marker_leak_check(self):
        markers = {
            "profile_id": "PROFILE-PRIVATE-9281",
            "webhook": "https://discord.com/api/webhooks/PRIVATE-WEBHOOK",
            "notion": "NOTION-PAGE-PRIVATE-9912",
            "applied": "https://example.com/applied?member=PRIVATE-APPLIED-778",
            "error": "PRIVATE-ERROR-Traceback-secret-value",
        }
        posting = {
            "id": "simplify:public-job-1", "company": "Fictional Labs",
            "title": "Software Engineer Intern", "location": "Remote",
            "url": "https://example.com/jobs/one?token=PRIVATE-APPLIED-778&utm_source=PRIVATE",
            "terms": ["Summer 2027"], "discord_user_id": markers["profile_id"],
            "message_id": markers["profile_id"], "channel_id": markers["profile_id"],
            "webhook_name": markers["webhook"], "pin": markers["profile_id"],
            "applied_url": markers["applied"], "applied": True,
            "notion_page_id": markers["notion"], "dead_letter": markers["error"],
            "error": markers["error"], "source_url": markers["webhook"],
        }
        state = {"jobs": [{"id": "old-private-id", "first_seen": "2026-11-23T00:00:00Z",
                           "applied_url": markers["applied"], "error": markers["error"]}],
                 "message_map": {markers["profile_id"]: markers["notion"]},
                 "dead": [markers["error"]], "pins": [markers["profile_id"]]}
        cfg = {
            "companies": [], "simplify": {"company_keywords": []},
            "profiles": {markers["profile_id"]: {"webhook_url": markers["webhook"]}},
            "notion_parent_page_id": markers["notion"], "last_error": markers["error"],
        }
        result = build_jobs_export([posting], state["jobs"], cfg,
                                   now="2026-11-24T12:00:00Z")
        serialized = json.dumps(result, sort_keys=True)

        self.assertEqual(len(result), 1)
        self.assertEqual(set(result[0]), EXPORT_FIELDS)
        for marker in markers.values():
            self.assertNotIn(marker, serialized)
        self.assertEqual(result[0]["url"], "https://example.com/jobs/one")
        self.assertEqual(result, build_jobs_export(
            [posting], state["jobs"], {"companies": [], "simplify": {}},
            now="2026-11-24T12:00:00Z"))

    def test_first_seen_is_preserved_and_retention_is_newest_first(self):
        current = {"id": "greenhouse:fictional:1", "company": "Fictional",
                   "title": "Research Intern", "location": "Remote",
                   "url": "https://example.com/jobs/1", "terms": ["Spring 2027"]}
        first_id = build_jobs_export([current], [], now="2026-11-24T12:00:00Z")[0]["id"]
        result = build_jobs_export(
            [current, {**current, "id": "vanshb03:2", "url": "https://example.com/jobs/2"}],
            [{"id": first_id, "first_seen": "2026-11-01T10:00:00Z", "private": "drop"},
             {"id": "expired", "first_seen": "2026-10-01T10:00:00Z"}],
            now="2026-11-24T12:00:00Z",
        )
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1]["id"], first_id)
        self.assertEqual(result[1]["first_seen"], "2026-11-01T10:00:00Z")
        self.assertEqual([job["first_seen"] for job in result],
                         ["2026-11-24T12:00:00Z", "2026-11-01T10:00:00Z"])

    def test_export_is_capped(self):
        postings = [{"id": f"vanshb03:{i}", "company": f"Fictional {i}",
                     "title": "Engineering Intern", "location": "Remote",
                     "url": f"https://example.com/jobs/{i}"}
                    for i in range(MAX_SITE_EXPORT_JOBS + 1)]
        result = build_jobs_export(postings, [], now="2026-11-24T12:00:00Z")
        self.assertEqual(len(result), MAX_SITE_EXPORT_JOBS)

    def test_only_public_http_urls_are_kept(self):
        postings = [
            {"id": "job:one", "title": "Intern", "url": "javascript:alert(1)"},
            {"id": "job:two", "title": "Intern", "url": "https:missing-host"},
        ]
        result = build_jobs_export(postings, [], now="2026-11-24T12:00:00Z")
        self.assertEqual([job["url"] for job in result], ["", ""])


if __name__ == "__main__":
    unittest.main()
