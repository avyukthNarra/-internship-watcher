import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import psycopg

import state_db


TEST_URL = os.environ.get("TEST_DATABASE_URL")


@unittest.skipUnless(TEST_URL, "set TEST_DATABASE_URL to run Postgres tests")
class StateDatabaseTests(unittest.TestCase):
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

    def test_dict_and_list_round_trip(self):
        expected_dict = {"pending": {"job": ["discord"]}, "known_ids": ["x"]}
        expected_list = ["job:1", "job:2"]
        state_db.save("delivery_state.json", expected_dict)
        state_db.save("seen.json", expected_list)
        self.assertEqual(state_db.load("delivery_state.json"), expected_dict)
        self.assertEqual(state_db.load("seen.json"), expected_list)

    def test_only_changed_parts_get_a_new_timestamp(self):
        state_db.save("delivery_state.json", {"pending": {"a": 1}, "known_ids": ["a"]})
        with psycopg.connect(TEST_URL) as conn:
            before = dict(conn.execute(
                "select key, updated_at from public.state_parts where name = 'delivery_state.json'"
            ).fetchall())
        time.sleep(0.03)
        state_db.save("delivery_state.json", {"pending": {"a": 2}, "known_ids": ["a"]})
        with psycopg.connect(TEST_URL) as conn:
            after = dict(conn.execute(
                "select key, updated_at from public.state_parts where name = 'delivery_state.json'"
            ).fetchall())
        self.assertGreater(after["pending"], before["pending"])
        self.assertEqual(after["known_ids"], before["known_ids"])

    def test_missing_required_history_trips_flood_guard(self):
        with self.assertRaisesRegex(RuntimeError, "missing"):
            state_db.load("seen.json", [])
        with self.assertRaisesRegex(RuntimeError, "missing"):
            state_db.load("delivery_state.json", {})

    def test_import_and_export_cli(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as target:
            source = Path(source)
            values = {
                "seen.json": ["a"],
                "delivery_state.json": {"known_ids": ["a"], "pending": {}},
                "health.json": {"sources": {}},
                "notion_state.json": {"pending_applied": []},
                "message_map.json": {"msg": {"ts": 1}},
            }
            for name, value in values.items():
                (source / name).write_text(json.dumps(value))
            env = {**os.environ, "DATABASE_URL": TEST_URL}
            subprocess.run([sys.executable, str(Path(state_db.__file__)), "import", "--from", str(source)],
                           check=True, env=env)
            subprocess.run([sys.executable, str(Path(state_db.__file__)), "export", "--to", target],
                           check=True, env=env)
            for name, expected in values.items():
                self.assertEqual(json.loads((Path(target) / name).read_text()), expected)
