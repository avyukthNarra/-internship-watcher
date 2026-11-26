import os
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import psycopg

import db


TEST_URL = os.environ.get("TEST_DATABASE_URL")


@unittest.skipUnless(TEST_URL, "set TEST_DATABASE_URL to run Postgres tests")
class JobsDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"DATABASE_URL": TEST_URL})
        self.env.start()
        self.addCleanup(self.env.stop)
        root = Path(__file__).resolve().parents[1]
        with psycopg.connect(TEST_URL, autocommit=True) as conn:
            conn.execute("drop schema if exists public cascade")
            conn.execute("create schema public")
            conn.execute("drop schema if exists auth cascade")
            conn.execute("drop role if exists anon")
            conn.execute("drop role if exists authenticated")
            conn.execute("drop role if exists service_role")
            conn.execute((root / "supabase/tests/local_auth_stub.sql").read_text())
            conn.execute((root / "supabase/migrations/20261126000000_init.sql").read_text())

    @staticmethod
    def job(**changes):
        return {
            "id": "greenhouse:acme:123", "company": "Acme", "title": "SWE Intern",
            "location": "Remote", "url": "https://boards.greenhouse.io/acme/jobs/123",
            "terms": ["Summer 2027"], "category": "Software", **changes,
        }

    def test_first_seen_is_stable_across_upserts(self):
        now = datetime(2026, 11, 25, tzinfo=timezone.utc)
        job = self.job()
        db.upsert_jobs([job], now)
        changed = self.job(title="Software Engineering Intern", location="Austin")
        db.upsert_jobs([changed], datetime(2026, 11, 26, tzinfo=timezone.utc))
        with psycopg.connect(TEST_URL) as conn:
            row = conn.execute(
                "select first_seen, last_seen, title, location, closed_at from public.jobs where id = %s",
                (job["id"],),
            ).fetchone()
        self.assertEqual(row[0], now)
        self.assertEqual(row[1], datetime(2026, 11, 26, tzinfo=timezone.utc))
        self.assertEqual(row[2:4], ("Software Engineering Intern", "Austin"))
        self.assertIsNone(row[4])

    def test_only_successful_direct_board_sources_are_closed(self):
        now = datetime(2026, 11, 25, tzinfo=timezone.utc)
        db.upsert_jobs([
            self.job(),
            self.job(id="lever:broken:2", company="Broken"),
            self.job(id="simplify:3", source="simplify", company="FeedCo"),
            self.job(id="greenhouse:acme:4", title="Still open"),
        ], now)
        db.close_missing_jobs({"greenhouse:acme"}, {"greenhouse:acme:4"}, now)
        with psycopg.connect(TEST_URL) as conn:
            rows = dict(conn.execute("select id, closed_at from public.jobs").fetchall())
        self.assertEqual(rows["greenhouse:acme:123"], now)
        self.assertIsNone(rows["lever:broken:2"])
        self.assertIsNone(rows["simplify:3"])
        self.assertIsNone(rows["greenhouse:acme:4"])

    def test_default_top_company_sync_replaces_table(self):
        db.sync_default_top_companies({
            "companies": [{"name": "Acme"}, {"name": "Beta"}],
            "simplify": {"company_keywords": ["Gamma", "Acme"]},
        })
        db.sync_default_top_companies({
            "companies": [{"name": "NewCo"}], "simplify": {"company_keywords": ["FeedCo"]},
        })
        with psycopg.connect(TEST_URL) as conn:
            names = {row[0] for row in conn.execute(
                "select name from public.default_top_companies"
            ).fetchall()}
        self.assertEqual(names, {"NewCo", "FeedCo"})
