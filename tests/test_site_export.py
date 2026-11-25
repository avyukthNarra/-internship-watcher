import json
import unittest
from pathlib import Path

from site_export import (EXPORT_FIELDS, MAX_SITE_EXPORT_JOBS, ROLE_LABELS,
                         build_jobs_export)

ROOT = Path(__file__).resolve().parent.parent


class SiteExportTests(unittest.TestCase):
    def test_allowlist_and_private_marker_leak_check(self):
        markers = {
            "profile_id": "PROFILE-PRIVATE-9281",
            "webhook": "https://discord.com/api/webhooks/PRIVATE-WEBHOOK",
            "notion": "NOTION-PAGE-PRIVATE-9912",
            "applied": "https://example.com/applied?member=PRIVATE-APPLIED-778",
            "error": "PRIVATE-ERROR-Traceback-secret-value",
            "ref": "PRIVATE-REF-4431",
            "email": "PRIVATE-EMAIL-5512",
        }
        posting = {
            "id": "simplify:public-job-1", "company": "Fictional Labs",
            "title": "Software Engineer Intern", "location": "Remote",
            "url": ("https://example.com/jobs/one?token=PRIVATE-APPLIED-778&utm_source=PRIVATE"
                    "&ref=PRIVATE-REF-4431&email=PRIVATE-EMAIL-5512"),
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
            "alert_channels": [
                {"name": "swe", "webhook_env": "DISCORD_WEBHOOK_PRIVATE_SWE", "roles": ["software"]},
                {"name": markers["profile_id"], "webhook_env": "DISCORD_WEBHOOK_PRIVATE_X",
                 "roles": ["engineer"]},
            ],
        }
        result = build_jobs_export([posting], state["jobs"], cfg,
                                   now="2026-11-24T12:00:00Z")
        serialized = json.dumps(result, sort_keys=True)

        self.assertEqual(len(result), 1)
        self.assertEqual(set(result[0]), EXPORT_FIELDS)
        for marker in markers.values():
            self.assertNotIn(marker, serialized)
        self.assertNotIn("DISCORD_WEBHOOK", serialized)
        self.assertEqual(result[0]["url"], "https://example.com/jobs/one")
        self.assertEqual(result[0]["roles"], ["SWE"])
        self.assertEqual(result, build_jobs_export(
            [posting], state["jobs"], {**cfg, "profiles": {}, "notion_parent_page_id": ""},
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

    def test_job_id_query_survives_and_keeps_distinct_jobs_distinct(self):
        postings = [
            {"id": "greenhouse:custom:123", "company": "Fictional", "title": "Intern",
             "url": "https://careers.example.com/jobs?gh_jid=123"},
            {"id": "greenhouse:custom:456", "company": "Fictional", "title": "Intern",
             "url": "https://careers.example.com/jobs?gh_jid=456"},
        ]
        result = build_jobs_export(postings, [], now="2026-11-24T12:00:00Z")
        self.assertEqual(len(result), 2)
        self.assertEqual({item["url"] for item in result}, {
            "https://careers.example.com/jobs?gh_jid=123",
            "https://careers.example.com/jobs?gh_jid=456",
        })
        self.assertEqual(len({item["id"] for item in result}), 2)

    def test_personal_and_referral_query_keys_are_removed_but_fragment_is_kept(self):
        posting = {"id": "workday:tenant:role", "title": "Intern",
                   "url": ("https://jobs.example.com/role?jobId=abc&ref=friend"
                           "&email=person%40example.com&source=campaign#job-details")}
        result = build_jobs_export([posting], [], now="2026-11-24T12:00:00Z")
        self.assertEqual(result[0]["source"], "workday")
        self.assertEqual(result[0]["url"],
                         "https://jobs.example.com/role?jobId=abc#job-details")


    def test_roles_follow_alert_channel_matching(self):
        cfg = json.loads((ROOT / "config.json").read_text())
        cases = [
            ("Software Engineer Intern", "", ["SWE"]),
            ("Machine Learning Research Intern", "", ["ML/AI", "Research"]),
            ("Embedded Software Intern", "", ["Embedded"]),  # swe excludes embedded
            ("Firmware Engineer Intern", "Hardware", ["Embedded"]),
            ("Mechanical Systems Intern", "Hardware", ["Hardware"]),
            ("PCB Design Intern", "", ["Hardware"]),
            ("Quantitative Trader Intern", "", ["Quant"]),
            ("Summer Analyst", "Quant", ["Data", "Quant"]),
            ("Product Design Intern", "", []),
            ("International Sales Intern", "", []),  # "ai" is whole-word only
            ("Data Science Intern - Mobile", "", ["SWE", "Data"]),
        ]
        postings = [{"id": f"simplify:{i}", "company": "Fictional", "title": title,
                     "category": category, "location": "Remote",
                     "url": f"https://example.com/jobs/{i}"}
                    for i, (title, category, _) in enumerate(cases)]
        result = build_jobs_export(postings, [], cfg, now="2026-11-24T12:00:00Z")
        by_title = {item["title"]: item["roles"] for item in result}
        for title, _, expected in cases:
            self.assertEqual(by_title[title], expected, title)
        for item in result:
            self.assertTrue(set(item["roles"]) <= set(ROLE_LABELS))

    def test_roles_are_empty_without_channels(self):
        result = build_jobs_export(
            [{"id": "lever:x:1", "title": "Software Engineer Intern",
              "url": "https://example.com/jobs/1"}], [], {}, now="2026-11-24T12:00:00Z")
        self.assertEqual(result[0]["roles"], [])

    def test_web_sample_matches_export_schema(self):
        sample = json.loads((ROOT / "web" / "sample-jobs.json").read_text())
        self.assertGreaterEqual(len(sample), 30)
        for item in sample:
            self.assertEqual(set(item), EXPORT_FIELDS)
            self.assertTrue(set(item["roles"]) <= set(ROLE_LABELS))
            self.assertTrue(item["url"] == "" or item["url"].startswith("https://example.com/"))


if __name__ == "__main__":
    unittest.main()
