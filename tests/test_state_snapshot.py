import json
import tempfile
import unittest
from pathlib import Path

import state_snapshot


def fixture_state(root: Path, *, known=None):
    known = known if known is not None else ["job:1", "job:2"]
    values = {
        "seen.json": ["job:1", "job:2"],
        "delivery_state.json": {"known_ids": known, "pending": {}, "identities": {}, "fingerprints": {}},
        "message_map.json": {},
        "notion_state.json": {"pending_pins": {}, "pending_applied": {}, "users": {}},
        "health.json": {"last_completed_scan": 123, "sources": {}, "pending_deliveries": 0},
    }
    for name, value in values.items():
        (root / name).write_text(json.dumps(value), encoding="utf-8")
    return values


class StateSnapshotTests(unittest.TestCase):
    def test_round_trip_and_restore_twice_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, out, target = root / "source", root / "snapshots", root / "target"
            source.mkdir(); target.mkdir()
            fixture_state(source)
            original_cwd = Path.cwd()
            try:
                import os
                os.chdir(source)
                generation = state_snapshot.create(out)
            finally:
                os.chdir(original_cwd)
            state_snapshot.restore(generation, target)
            first = {name: (target / name).read_bytes() for name in state_snapshot.STATE_FILES}
            (target / "keep.txt").write_text("keep")
            mtimes = {name: (target / name).stat().st_mtime_ns for name in state_snapshot.STATE_FILES}
            state_snapshot.restore(generation, target)
            self.assertEqual(first, {name: (target / name).read_bytes() for name in state_snapshot.STATE_FILES})
            self.assertEqual(mtimes, {name: (target / name).stat().st_mtime_ns for name in state_snapshot.STATE_FILES})
            self.assertEqual("keep", (target / "keep.txt").read_text())

    def _make_generation(self, root):
        source, out = root / "source", root / "out"
        source.mkdir(parents=True); out.mkdir(parents=True)
        fixture_state(source)
        import os
        old = Path.cwd()
        try:
            os.chdir(source)
            return state_snapshot.create(out)
        finally:
            os.chdir(old)

    def test_corrupted_file_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            generation = self._make_generation(Path(temp))
            (generation / "seen.json").write_text("[]\n")
            with self.assertRaisesRegex(state_snapshot.SnapshotError, "hash or size mismatch"):
                state_snapshot.restore(generation, Path(temp) / "target")

    def test_missing_file_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            generation = self._make_generation(Path(temp))
            (generation / "health.json").unlink()
            with self.assertRaisesRegex(state_snapshot.SnapshotError, "missing generation file"):
                state_snapshot.restore(generation, Path(temp) / "target")

    def test_mixed_generation_membership_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            generation_a = self._make_generation(root / "a")
            generation_b = self._make_generation(root / "b")
            # A file entry stamped with a different producer generation is rejected.
            manifest_path = generation_b / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["files"]["seen.json"]["generation_id"] = json.loads((generation_a / "manifest.json").read_text())["generation_id"]
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(state_snapshot.SnapshotError, "not marked as part"):
                state_snapshot.restore(generation_b, root / "target")

    def test_schema_version_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            generation = self._make_generation(Path(temp))
            manifest_path = generation / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["schema_version"] = 99
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(state_snapshot.SnapshotError, "unsupported or missing"):
                state_snapshot.restore(generation, Path(temp) / "target")

    def test_inconsistent_ledger_rejected_at_create(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture_state(root, known=["job:1"])
            import os
            old = Path.cwd()
            try:
                os.chdir(root)
                with self.assertRaisesRegex(state_snapshot.SnapshotError, "omits IDs") as caught:
                    state_snapshot.create(root / "out")
            finally:
                os.chdir(old)
            self.assertEqual("INCONSISTENT_LEDGER", caught.exception.reason_code)
            self.assertFalse((root / "out").exists())

    def test_orphaned_receipt_rejected_at_create(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture_state(root)
            (root / "message_map.json").write_text(json.dumps({
                "message": {"job": {"id": "job:unknown"}, "cid": "channel", "ts": 123}
            }))
            import os
            old = Path.cwd()
            try:
                os.chdir(root)
                with self.assertRaisesRegex(state_snapshot.SnapshotError, "receipt job IDs") as caught:
                    state_snapshot.create(root / "out")
            finally:
                os.chdir(old)
            self.assertEqual("INCONSISTENT_RECEIPT", caught.exception.reason_code)
            self.assertFalse((root / "out").exists())


if __name__ == "__main__":
    unittest.main()
