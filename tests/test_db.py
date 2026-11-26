import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import psycopg

import db
import state_db


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

    def test_returns_only_new_ids_and_keeps_first_seen_stable(self):
        first = datetime(2026, 11, 25, tzinfo=timezone.utc)
        job = self.job()
        self.assertEqual(db.upsert_jobs([job], first), {job["id"]})
        self.assertEqual(db.upsert_jobs([job], first + timedelta(minutes=10)), set())

        changed = self.job(title="Software Engineering Intern", location="Austin")
        self.assertEqual(db.upsert_jobs([changed], first + timedelta(minutes=20)), set())
        with psycopg.connect(TEST_URL) as conn:
            row = conn.execute(
                "select first_seen, last_seen, title, location from public.jobs where id = %s",
                (job["id"],),
            ).fetchone()
        self.assertEqual(row, (first, first + timedelta(minutes=20),
                               "Software Engineering Intern", "Austin"))

    def test_duplicate_ids_use_the_last_job_record(self):
        now = datetime(2026, 11, 25, tzinfo=timezone.utc)
        first = self.job(title="First copy")
        last = self.job(title="Last copy", location="New York")
        self.assertEqual(db.upsert_jobs([first, last], now), {first["id"]})
        with psycopg.connect(TEST_URL) as conn:
            row = conn.execute(
                "select title, location from public.jobs where id = %s", (first["id"],)
            ).fetchone()
        self.assertEqual(row, ("Last copy", "New York"))

    def test_jobs_are_written_in_batches_without_losing_inserted_ids(self):
        jobs = [
            self.job(id=f"greenhouse:acme:{index}",
                     url=f"https://boards.greenhouse.io/acme/jobs/{index}")
            for index in range(1001)
        ]
        ids = {job["id"] for job in jobs}
        self.assertEqual(db.upsert_jobs(jobs, datetime(2026, 11, 25, tzinfo=timezone.utc)), ids)
        with psycopg.connect(TEST_URL) as conn:
            count = conn.execute("select count(*) from public.jobs").fetchone()[0]
        self.assertEqual(count, 1001)

    def test_last_seen_only_advances_after_one_hour_when_fields_are_unchanged(self):
        first = datetime(2026, 11, 25, tzinfo=timezone.utc)
        job = self.job()
        db.upsert_jobs([job], first)
        db.upsert_jobs([job], first + timedelta(minutes=59))
        with psycopg.connect(TEST_URL) as conn:
            recent = conn.execute("select last_seen from public.jobs where id = %s",
                                  (job["id"],)).fetchone()[0]
        self.assertEqual(recent, first)

        db.upsert_jobs([job], first + timedelta(hours=1, seconds=1))
        with psycopg.connect(TEST_URL) as conn:
            last_seen = conn.execute(
                "select first_seen, last_seen from public.jobs where id = %s", (job["id"],)
            ).fetchone()
        self.assertEqual(last_seen, (first, first + timedelta(hours=1, seconds=1)))

    def test_close_missing_is_scoped_to_successful_boards(self):
        now = datetime(2026, 11, 25, tzinfo=timezone.utc)
        db.upsert_jobs([
            self.job(),
            self.job(id="greenhouse:other:2", company="Other"),
            self.job(id="simplify:3", source="simplify", company="FeedCo"),
            self.job(id="greenhouse:acme:4", title="Still open"),
        ], now)
        raw_conn = psycopg.connect(TEST_URL)

        class CountingConnection:
            calls = 0

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return raw_conn.__exit__(*exc_info)

            def execute(self, *args, **kwargs):
                self.calls += 1
                return raw_conn.execute(*args, **kwargs)

        counted = CountingConnection()
        with patch.object(db, "connect", return_value=counted):
            db.close_missing_jobs({"greenhouse:acme"}, {"greenhouse:acme:4"}, now)
        self.assertEqual(counted.calls, 1)
        with psycopg.connect(TEST_URL) as conn:
            rows = dict(conn.execute("select id, closed_at from public.jobs").fetchall())
        self.assertEqual(rows["greenhouse:acme:123"], now)
        self.assertIsNone(rows["greenhouse:other:2"])
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

    def test_health_value_round_trip(self):
        health = {
            "last_completed_scan": 1795564800.0,
            "matching_jobs": 18,
            "new_jobs": 2,
            "successful_sources": 1,
            "failed_sources": 1,
            "stale_failed_sources": 0,
            "sources": {"https://example.invalid": {"ok": False, "error": "Timeout"}},
        }
        self.assertEqual(state_db.load_health(), {})
        state_db.save_health(health)
        self.assertEqual(state_db.load_health(), health)
