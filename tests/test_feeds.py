import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import watcher


class FeedFetcherTests(unittest.TestCase):
    def test_ats_fetchers_map_native_fields_and_ids(self):
        greenhouse = {
            "jobs": [{"id": 17, "title": "Summer SWE Intern",
                       "location": {"name": "Dublin, OH"},
                       "absolute_url": "https://boards.greenhouse.io/acme/jobs/17"}]
        }
        lever = [{"id": "l-2", "text": "Backend Intern",
                  "categories": {"location": "Austin, TX"},
                  "hostedUrl": "https://jobs.lever.co/acme/l-2"}]
        ashby = {"jobs": [{"id": "a-3", "title": "Data Intern",
                            "location": "New York, NY", "jobUrl": "https://jobs.ashbyhq.com/acme/a-3"}]}
        with patch.object(watcher, "get", side_effect=[greenhouse, lever, ashby]):
            self.assertEqual(watcher.fetch_greenhouse("acme"), [{
                "id": "greenhouse:acme:17", "title": "Summer SWE Intern",
                "location": "Dublin, OH",
                "url": "https://boards.greenhouse.io/acme/jobs/17"}])
            self.assertEqual(watcher.fetch_lever("acme"), [{
                "id": "lever:acme:l-2", "title": "Backend Intern",
                "location": "Austin, TX", "url": "https://jobs.lever.co/acme/l-2"}])
            self.assertEqual(watcher.fetch_ashby("acme"), [{
                "id": "ashby:acme:a-3", "title": "Data Intern",
                "location": "New York, NY", "url": "https://jobs.ashbyhq.com/acme/a-3"}])

    def test_simplify_filters_visibility_age_and_company_word_boundaries(self):
        now = datetime.now(timezone.utc).timestamp()
        feed = [
            {"id": "keep", "active": True, "is_visible": True,
             "date_posted": now, "company_name": "Acme",
             "title": "Summer SWE Intern", "locations": ["Austin, TX"], "url": "u"},
            {"id": "substring", "active": True, "is_visible": True,
             "date_posted": now, "company_name": "Acme Labs",
             "title": "Summer SWE Intern", "locations": ["Austin, TX"], "url": "u2"},
            {"id": "hidden", "active": True, "is_visible": False,
             "date_posted": now, "company_name": "Acme", "title": "Intern", "locations": [], "url": "u3"},
            {"id": "old", "active": True, "is_visible": True,
             "date_posted": now - 15 * 86400, "company_name": "Acme", "title": "Intern", "locations": [], "url": "u4"},
        ]
        cfg = {"simplify": {"url": "feed", "company_keywords": ["Acme"], "max_age_days": 7}}
        with patch.object(watcher, "get", return_value=feed):
            jobs = watcher.fetch_simplify(cfg)
        self.assertEqual([j["id"] for j in jobs], ["simplify:keep", "simplify:substring"])
        self.assertEqual(jobs[0]["location"], "Austin, TX")

    def test_jobright_inherits_company_and_ignores_malformed_date(self):
        today = datetime.now(timezone.utc).strftime("%b %d")
        text = "\n".join([
            "| **[Acme](https://acme.example)** | **[Summer SWE Intern](https://jobright.ai/jobs/info/abc123)** | Dublin, OH | x | " + today + " |",
            "| ↳ | **[Backend Intern](https://jobright.ai/jobs/info/def456)** | Austin, TX | x | " + today + " |",
            "| **[Acme](https://acme.example)** | **[Bad Date Intern](https://jobright.ai/jobs/info/deadbeef)** | Austin, TX | x | Foo 99 |",
        ])
        cfg = {"jobright": {"repos": ["synthetic"], "max_age_days": 2}}
        with patch.object(watcher, "get_text", return_value=text):
            jobs = watcher.fetch_jobright(cfg)
        self.assertEqual([j["id"] for j in jobs], ["jobright:abc123", "jobright:def456"])
        self.assertEqual([j["company"] for j in jobs], ["Acme", "Acme"])
        self.assertEqual(jobs[1]["url"], "https://jobright.ai/jobs/info/def456")


class FilteringAndRoutingTests(unittest.TestCase):
    def test_discover_applies_same_title_term_and_location_filters_to_every_source(self):
        good = lambda source: {"id": source + ":good", "title": "Summer SWE Intern",
                               "location": "Dublin, OH", "url": "https://example.test/" + source}
        bad_title = lambda source: {"id": source + ":bad-title", "title": "Summer Marketing Intern",
                                    "location": "Austin, TX", "url": "https://example.test/" + source + "-m"}
        bad_term = lambda source: {"id": source + ":bad-term", "title": "Summer 2026 SWE Intern",
                                   "location": "Austin, TX", "url": "https://example.test/" + source + "-t"}
        bad_location = lambda source: {"id": source + ":bad-location", "title": "Summer SWE Intern",
                                       "location": "Dublin, Ireland", "url": "https://example.test/" + source + "-l"}
        cfg = {
            "companies": [{"name": "GH", "ats": "greenhouse", "board": "gh"},
                          {"name": "Lever", "ats": "lever", "board": "lever"},
                          {"name": "Ashby", "ats": "ashby", "board": "ashby"}],
            "include_keywords": ["intern"], "exclude_keywords": ["marketing"],
            "exclude_locations": ["dublin", "ireland"], "terms": ["Summer 2027"],
            "simplify": {"enabled": True}, "jobright": {"enabled": True},
        }
        sources = ["greenhouse", "lever", "ashby", "simplify", "jobright"]
        def feed(name):
            return [good(name), bad_title(name), bad_term(name), bad_location(name)]
        with patch.object(watcher, "ATS_FETCHERS", {name: (lambda org, n=name: feed(n))
                                                       for name in ("greenhouse", "lever", "ashby")}), \
             patch.object(watcher, "fetch_simplify", side_effect=lambda c: feed("simplify")), \
             patch.object(watcher, "fetch_jobright", side_effect=lambda c: feed("jobright")):
            found = watcher.discover(cfg)
        self.assertEqual({j["id"] for j in found}, {name + ":good" for name in sources})

    def test_location_exclusion_keeps_us_city_with_same_name(self):
        self.assertFalse(watcher.location_excluded("Dublin, OH", ["dublin", "ireland"]))
        self.assertTrue(watcher.location_excluded("Dublin, Ireland", ["dublin", "ireland"]))

    def test_profile_webhook_routes_only_matching_profile_and_no_substring_company_match(self):
        cfg = {"companies": [{"name": "Acme", "ats": "greenhouse", "board": "acme"}],
               "simplify": {"company_keywords": ["arm"]},
               "profiles": {"u": {"roles": ["SWE"], "companies": ["Acme"],
                                    "locations": ["Austin"], "webhook_env": "DISCORD_WEBHOOK_PROFILE"}}}
        acme = {"id": "jobright:1", "company": "Acme", "title": "SWE Intern",
                "location": "Austin, TX", "url": "u"}
        farmers = {**acme, "id": "jobright:2", "company": "Farmers"}
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "default", "DISCORD_WEBHOOK_URL_TOP": "top",
                                     "DISCORD_WEBHOOK_PROFILE": "profile"}, clear=True):
            self.assertEqual(watcher.destinations(acme, cfg),
                             ["discord:DISCORD_WEBHOOK_URL_TOP", "discord:DISCORD_WEBHOOK_PROFILE"])
            self.assertEqual(watcher.destinations(farmers, cfg), ["discord:DISCORD_WEBHOOK_URL"])


if __name__ == "__main__":
    unittest.main()
