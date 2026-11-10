import os
import unittest
from datetime import datetime, timezone
import time
from unittest.mock import Mock, patch

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


class Vanshb03Tests(unittest.TestCase):
    def listing(self, jid, **overrides):
        return {"id": jid, "active": True, "is_visible": True, "date_posted": time.time(),
                "company_name": "Rockwell", "title": "Firmware Intern", "season": "Summer",
                "locations": ["Austin, TX", "Dallas, TX", "Plano, TX", "Frisco, TX"],
                "url": f"https://go.vansh.nyc/{jid}", **overrides}

    def fetch(self, data, **feed):
        cfg = {"vanshb03": {"enabled": True, **feed}}
        with patch.object(watcher, "source_items", return_value=data):
            return watcher.fetch_vanshb03(cfg)

    def test_maps_fields_and_labels_seasons_like_simplify(self):
        job, = self.fetch([self.listing("a")])
        self.assertEqual(job["id"], "vanshb03:a")
        self.assertEqual(job["terms"], ["Summer 2027"])
        self.assertEqual(job["location"], "Austin, TX, Dallas, TX, Plano, TX")
        self.assertEqual(job["url"], "https://go.vansh.nyc/a")

    def test_fall_belongs_to_the_previous_year_and_slashes_split(self):
        self.assertEqual(watcher.vanshb03_terms("Fall", 2027), ["Fall 2026"])
        self.assertEqual(watcher.vanshb03_terms("Spring/Summer", 2027), ["Spring 2027", "Summer 2027"])
        self.assertEqual(watcher.vanshb03_terms(None, 2027), [])

    def test_inactive_hidden_and_old_listings_are_skipped(self):
        data = [self.listing("ok"), self.listing("off", active=False),
                self.listing("hid", is_visible=False),
                self.listing("old", date_posted=time.time() - 30 * 86400),
                self.listing("undated", date_posted=None)]
        self.assertEqual([j["id"] for j in self.fetch(data)], ["vanshb03:ok"])
        old = self.fetch(data, max_age_days=60)
        self.assertIn("vanshb03:old", [j["id"] for j in old])

    def test_matches_a_simplify_listing_for_cross_feed_dedup(self):
        from job_utils import fingerprint
        simplify = {"company": "Rockwell", "title": "Firmware Intern", "terms": ["Summer 2027"],
                    "location": "Austin, TX, Dallas, TX, Plano, TX"}
        self.assertEqual(fingerprint(self.fetch([self.listing("a")])[0]), fingerprint(simplify))


class CategoryTests(unittest.TestCase):
    def listing(self, jid, company, category):
        return {"id": jid, "active": True, "date_posted": time.time(), "company_name": company,
                "title": "Firmware Intern", "locations": ["Austin, TX"], "url": f"https://x.example/{jid}",
                "terms": ["Summer 2027"], "category": category}

    def fetch(self, **simplify):
        data = [self.listing("1", "Google", "Software"), self.listing("2", "Rockwell", "Hardware"),
                self.listing("3", "Rockwell", "Software"), self.listing("4", "Jump", "Quant")]
        cfg = {"simplify": {"enabled": True, "company_keywords": ["google"], **simplify}}
        with patch.object(watcher, "source_items", return_value=data):
            return {j["id"]: j for j in watcher.fetch_simplify(cfg)}

    def test_categories_are_pulled_regardless_of_company(self):
        self.assertEqual(set(self.fetch()), {"simplify:1"})
        found = self.fetch(include_categories=["hardware", "Quant"])
        self.assertEqual(set(found), {"simplify:1", "simplify:2", "simplify:4"})
        self.assertNotIn("via_category", found["simplify:1"])
        self.assertTrue(found["simplify:2"]["via_category"])
        self.assertEqual(found["simplify:2"]["category"], "Hardware")

    def test_category_roles_filter_only_category_pulls(self):
        data = [self.listing("1", "Google", "Hardware"), self.listing("2", "Rockwell", "Hardware"),
                self.listing("3", "Rockwell", "Hardware"), self.listing("4", "Jump", "Quant")]
        data[0]["title"] = "Mechanical Test Intern"      # tracked company: category roles do not apply
        data[1]["title"] = "FPGA Design Intern"
        data[2]["title"] = "Optical Engineer Intern"
        cfg = {"simplify": {"enabled": True, "company_keywords": ["google"],
                            "include_categories": ["Hardware", "Quant"],
                            "category_roles": {"Hardware": ["fpga", "embedded", "firmware"]}}}
        with patch.object(watcher, "source_items", return_value=data):
            ids = {j["id"] for j in watcher.fetch_simplify(cfg)}
        self.assertEqual(ids, {"simplify:1", "simplify:2", "simplify:4"})

    def test_category_exclude_drops_unwanted_category_pulls_only(self):
        data = [self.listing("1", "Google", "Hardware"), self.listing("2", "Rockwell", "Hardware"),
                self.listing("3", "Rockwell", "Hardware"), self.listing("4", "Rockwell", "Quant")]
        data[0]["title"] = "Materials Intern"            # tracked company: not filtered
        data[1]["title"] = "Optical Engineer Intern"     # fits a computer engineer: kept
        data[2]["title"] = "Materials Process Engineer Intern"
        data[3]["title"] = "Materials Quant Intern"      # exclusion is per category
        cfg = {"simplify": {"enabled": True, "company_keywords": ["google"],
                            "include_categories": ["Hardware", "Quant"],
                            "category_exclude": {"Hardware": ["materials", "process engineer"]}}}
        with patch.object(watcher, "source_items", return_value=data):
            ids = {j["id"] for j in watcher.fetch_simplify(cfg)}
        self.assertEqual(ids, {"simplify:1", "simplify:2", "simplify:4"})

    def test_category_jobs_skip_top_channel_and_feed_category_channels(self):
        cfg = {"companies": [], "simplify": {"company_keywords": ["google"]},
               "alert_channels": [{"name": "hw", "webhook_env": "DISCORD_WEBHOOK_HW",
                                   "categories": ["hardware"]}]}
        env = {"DISCORD_WEBHOOK_URL": "d", "DISCORD_WEBHOOK_URL_TOP": "t", "DISCORD_WEBHOOK_HW": "h"}
        hardware = {"id": "simplify:2", "company": "Rockwell", "title": "x", "location": "", "url": "u",
                    "category": "Hardware", "via_category": True}
        software = {**hardware, "id": "simplify:3", "category": "Software"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(watcher.destinations(hardware, cfg),
                             ["discord:DISCORD_WEBHOOK_URL", "discord:DISCORD_WEBHOOK_HW"])
            self.assertEqual(watcher.destinations(software, cfg), ["discord:DISCORD_WEBHOOK_URL"])
            tracked = {**hardware, "company": "Google", "via_category": False}
            self.assertEqual(watcher.destinations(tracked, cfg)[0], "discord:DISCORD_WEBHOOK_URL_TOP")

    def test_category_lists_are_validated(self):
        from project_config import validate_config
        validate_config({"companies": [], "simplify": {"include_categories": ["Hardware"]}})
        with self.assertRaises(ValueError):
            validate_config({"companies": [], "simplify": {"include_categories": "Hardware"}})
        validate_config({"companies": [], "simplify": {"category_roles": {"Hardware": ["fpga"]}}})
        for option in ("category_roles", "category_exclude"):
            for bad in ({"Hardware": "fpga"}, ["fpga"], {"Hardware": [1]}):
                with self.assertRaises(ValueError):
                    validate_config({"companies": [], "simplify": {option: bad}})


class AlertChannelTests(unittest.TestCase):
    CFG = {"companies": [], "alert_channels": [
        {"name": "quant", "webhook_env": "DISCORD_WEBHOOK_QUANT", "companies": ["Jane Street", "Citadel"]},
        {"name": "ml-nyc", "webhook_env": "DISCORD_WEBHOOK_MLNYC", "roles": ["machine learning", "ml"],
         "locations": ["New York"], "terms": ["Summer 2027"]}]}

    def job(self, **kw):
        return {"id": "jobright:1", "company": "Acme", "title": "SWE Intern",
                "location": "Austin, TX", "url": "u", **kw}

    def route(self, job, env=None):
        env = {"DISCORD_WEBHOOK_URL": "d", "DISCORD_WEBHOOK_QUANT": "q", "DISCORD_WEBHOOK_MLNYC": "m",
               **(env or {})}
        with patch.dict(os.environ, env, clear=True):
            return watcher.destinations(job, self.CFG)

    def test_each_channel_gets_only_matching_jobs_in_addition_to_the_default(self):
        self.assertEqual(self.route(self.job()), ["discord:DISCORD_WEBHOOK_URL"])
        self.assertEqual(self.route(self.job(company="Jane Street")),
                         ["discord:DISCORD_WEBHOOK_URL", "discord:DISCORD_WEBHOOK_QUANT"])
        ml = self.job(title="Machine Learning Intern", location="New York, NY",
                      terms=["Summer 2027"])
        self.assertEqual(self.route(ml), ["discord:DISCORD_WEBHOOK_URL", "discord:DISCORD_WEBHOOK_MLNYC"])
        self.assertEqual(self.route({**ml, "location": "Austin, TX"}), ["discord:DISCORD_WEBHOOK_URL"])
        both = {**ml, "company": "Citadel"}
        self.assertEqual(len(self.route(both)), 3)

    def test_channel_without_a_configured_webhook_is_skipped(self):
        env = {"DISCORD_WEBHOOK_URL": "d"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(watcher.destinations(self.job(company="Citadel"), self.CFG),
                             ["discord:DISCORD_WEBHOOK_URL"])

    def test_config_validation_and_alert_channel_webhook_enables_notifications(self):
        from project_config import notifications_enabled, validate_config
        validate_config(self.CFG)
        for bad in ("quant", [{"webhook_env": "DISCORD_WEBHOOK_X"}],
                    [{"name": "x", "webhook_env": "SECRET"}],
                    [{"name": "x", "webhook_env": "DISCORD_WEBHOOK_X", "roles": "ml"}]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_config({"companies": [], "alert_channels": bad})
        self.assertFalse(notifications_enabled(self.CFG, {}))
        self.assertTrue(notifications_enabled(self.CFG, {"DISCORD_WEBHOOK_QUANT": "q"}))


class RoleChannelTests(unittest.TestCase):
    CFG = {"companies": [], "alert_channels": [
        {"name": "embedded", "webhook_env": "DISCORD_WEBHOOK_EMBEDDED", "roles": ["embedded", "firmware"]},
        {"name": "swe", "webhook_env": "DISCORD_WEBHOOK_SWE", "roles": ["software"],
         "exclude_roles": ["embedded", "firmware"]},
        {"name": "hw", "webhook_env": "DISCORD_WEBHOOK_HW", "categories": ["Hardware"],
         "exclude_roles": ["embedded", "firmware"]},
        {"name": "hw-title", "webhook_env": "DISCORD_WEBHOOK_HW", "roles": ["optical"],
         "exclude_roles": ["embedded", "firmware"]},
        {"name": "watchlist", "webhook_env": "DISCORD_WEBHOOK_WATCH", "companies": ["Nvidia", "Jane Street"]}]}
    ENV = {name: "x" for name in ("DISCORD_WEBHOOK_URL", "DISCORD_WEBHOOK_EMBEDDED", "DISCORD_WEBHOOK_SWE",
                                  "DISCORD_WEBHOOK_HW", "DISCORD_WEBHOOK_WATCH")}

    def route(self, title, **kw):
        job = {"id": "ashby:a:1", "company": "Acme", "title": title, "location": "", "url": "u", **kw}
        with patch.dict(os.environ, self.ENV, clear=True):
            return [d.split("_")[-1] for d in watcher.destinations(job, self.CFG)
                    if d != "discord:DISCORD_WEBHOOK_URL"]

    def test_embedded_and_other_hardware_and_software_are_split(self):
        self.assertEqual(self.route("Embedded Software Intern"), ["EMBEDDED"])
        self.assertEqual(self.route("Firmware Intern", category="Hardware"), ["EMBEDDED"])
        self.assertEqual(self.route("Analog Intern", category="Hardware"), ["HW"])
        self.assertEqual(self.route("Optical Engineer Intern"), ["HW"])
        self.assertEqual(self.route("Software Engineer Intern"), ["SWE"])

    def test_two_entries_for_one_webhook_post_once(self):
        self.assertEqual(self.route("Optical Intern", category="Hardware"), ["HW"])

    def test_watchlist_matches_companies_and_other_channels_still_apply(self):
        self.assertEqual(self.route("Marketing Intern", company="NVIDIA Corp"), ["WATCH"])  # whole word, any case
        self.assertEqual(self.route("Marketing Intern", company="Nvidiax Labs"), [])
        self.assertEqual(self.route("Sales Intern", company="Jane Street"), ["WATCH"])
        self.assertEqual(self.route("Software Intern", company="Nvidia"), ["SWE", "WATCH"])

    def test_a_channel_with_no_filter_is_rejected(self):
        from project_config import validate_config
        with self.assertRaises(ValueError):
            validate_config({"companies": [], "alert_channels": [
                {"name": "all", "webhook_env": "DISCORD_WEBHOOK_ALL", "companies": []}]})
        with self.assertRaises(ValueError):
            validate_config({"companies": [], "alert_channels": [
                {"name": "x", "webhook_env": "DISCORD_WEBHOOK_X", "roles": ["a"], "exclude_roles": "b"}]})


class SimplifyCacheTests(unittest.TestCase):
    URL = "https://feed.example/listings.json"
    CFG = {"simplify": {"enabled": True, "url": URL, "max_age_days": 7}, "terms": ["Summer 2027"]}
    LISTING = [{"id": "1", "active": True, "date_posted": time.time(), "company_name": "Acme",
                "title": "SWE Intern", "locations": ["Austin, TX"], "url": "https://x.example/1",
                "terms": ["Summer 2027"]}]

    def setUp(self):
        watcher.SOURCE_HEALTH.clear()
        patcher = patch.object(watcher, "CONDITIONAL_FETCH", True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(watcher.SOURCE_HEALTH.clear)

    def ok(self, etag="v1"):
        return Mock(status_code=200, headers={"ETag": etag}, json=lambda: self.LISTING)

    def fetch(self, *responses, cfg=None):
        with patch.object(watcher.requests, "get", side_effect=list(responses)) as get:
            jobs = watcher.fetch_simplify(cfg or self.CFG)
        sent = get.call_args.kwargs["headers"].get("If-None-Match") if get.call_args else None
        return jobs, sent

    def test_first_fetch_is_full_and_stores_the_etag(self):
        jobs, sent = self.fetch(self.ok())
        self.assertEqual([j["id"] for j in jobs], ["simplify:1"])
        self.assertIsNone(sent)
        record = watcher.SOURCE_HEALTH[self.URL]
        self.assertEqual(record["etag"], "v1")
        self.assertTrue(record["ok"] and record["filter_digest"] and record["full_fetch"])

    def test_unchanged_feed_returns_nothing_and_keeps_the_cache(self):
        self.fetch(self.ok())
        before = watcher.SOURCE_HEALTH[self.URL]
        jobs, sent = self.fetch(Mock(status_code=304, headers={}))
        self.assertEqual((jobs, sent), ([], "v1"))
        after = watcher.SOURCE_HEALTH[self.URL]
        self.assertIsNot(after, before)  # counts as polled this run
        self.assertTrue(after["ok"])
        self.assertEqual((after["etag"], after["full_fetch"]), (before["etag"], before["full_fetch"]))

    def test_changed_feed_replaces_the_etag(self):
        self.fetch(self.ok("v1"))
        jobs, sent = self.fetch(self.ok("v2"))
        self.assertEqual((len(jobs), sent), (1, "v1"))
        self.assertEqual(watcher.SOURCE_HEALTH[self.URL]["etag"], "v2")

    def test_filter_change_or_age_forces_a_full_fetch(self):
        self.fetch(self.ok())
        changed = {**self.CFG, "terms": ["Fall 2027"]}
        self.assertIsNone(self.fetch(self.ok(), cfg=changed)[1])
        watcher.SOURCE_HEALTH[self.URL]["full_fetch"] = time.time() - watcher.FULL_FETCH_INTERVAL - 1
        self.assertIsNone(self.fetch(self.ok(), cfg=changed)[1])

    def test_dry_run_and_failed_source_never_use_the_cache(self):
        self.fetch(self.ok())
        with patch.object(watcher, "CONDITIONAL_FETCH", False):
            self.assertIsNone(self.fetch(self.ok())[1])
        with patch.object(watcher.time, "sleep"):
            self.fetch(*[Mock(status_code=500, headers={})] * 3)
            self.assertFalse(watcher.SOURCE_HEALTH[self.URL]["ok"])
            self.assertIsNone(self.fetch(self.ok())[1])


if __name__ == "__main__":
    unittest.main()
