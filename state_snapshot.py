"""Create and restore validated, immutable watcher state generations."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 1
STATE_FILES = (
    "seen.json",
    "delivery_state.json",
    "message_map.json",
    "notion_state.json",
    "health.json",
)
MANIFEST = "manifest.json"


class SnapshotError(Exception):
    """A state snapshot cannot safely be created or restored."""

    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SnapshotError("MISSING_FILE", f"missing state file: {path.name}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotError("INVALID_JSON", f"invalid JSON in {path.name}") from exc


def _validate_state(data: dict[str, object]) -> None:
    expected_types = {
        "seen.json": list,
        "delivery_state.json": dict,
        "message_map.json": dict,
        "notion_state.json": dict,
        "health.json": dict,
    }
    for name, expected in expected_types.items():
        if not isinstance(data[name], expected):
            raise SnapshotError("INVALID_STATE", f"{name} must contain a JSON {expected.__name__}")

    seen = data["seen.json"]
    ledger = data["delivery_state.json"]
    if any(not isinstance(item, str) for item in seen) or len(set(seen)) != len(seen):
        raise SnapshotError("INVALID_STATE", "seen.json must contain unique string IDs")
    known = ledger.get("known_ids")
    if not isinstance(known, list) or any(not isinstance(item, str) for item in known):
        raise SnapshotError("INVALID_STATE", "delivery_state.json known_ids must be a list of strings")
    if not set(seen).issubset(known):
        raise SnapshotError("INCONSISTENT_LEDGER", "delivery_state.json known_ids omits IDs from seen.json")
    pending = ledger.get("pending", {})
    if not isinstance(pending, dict):
        raise SnapshotError("INVALID_STATE", "delivery_state.json pending must be an object")
    if not set(pending).issubset(known):
        raise SnapshotError("INCONSISTENT_LEDGER", "pending delivery IDs must be present in known_ids")
    for job_id, entry in pending.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("destinations"), list):
            raise SnapshotError("INVALID_STATE", f"pending entry {job_id!r} must have destinations")
    message_map = data["message_map.json"]
    for receipt in message_map.values():
        if (not isinstance(receipt, dict) or not isinstance(receipt.get("job"), dict)
                or not isinstance(receipt["job"].get("id"), str)):
            raise SnapshotError("INVALID_STATE", "message_map.json receipts must contain a job ID")
        if receipt["job"]["id"] not in known:
            raise SnapshotError("INCONSISTENT_RECEIPT", "message_map receipt job IDs must be present in known_ids")


def _record_count(data) -> int:
    return len(data) if isinstance(data, (list, dict)) else 0


def _generation_name(run_id: str, attempt: str, generation_id: str) -> str:
    def safe(value: str) -> str:
        return "".join(c if c.isalnum() or c in "-_." else "_" for c in value)
    return f"{safe(run_id)}-{safe(attempt)}-{generation_id}"


def create(out_dir: str | Path) -> Path:
    """Capture state from the current directory into a new generation folder."""
    source = Path.cwd()
    destination_root = Path(out_dir).resolve()
    states: dict[str, object] = {}
    payloads: dict[str, bytes] = {}
    for name in STATE_FILES:
        path = source / name
        try:
            raw = path.read_bytes()
        except FileNotFoundError as exc:
            raise SnapshotError("MISSING_FILE", f"missing state file: {name}") from exc
        try:
            states[name] = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SnapshotError("INVALID_JSON", f"invalid JSON in {name}") from exc
        payloads[name] = raw
    _validate_state(states)

    # Confirm no file changed while the five inputs were being captured.
    for name in STATE_FILES:
        try:
            current = (source / name).read_bytes()
        except FileNotFoundError as exc:
            raise SnapshotError("CHANGED_DURING_CAPTURE", f"{name} disappeared during capture") from exc
        if current != payloads[name]:
            raise SnapshotError("CHANGED_DURING_CAPTURE", f"{name} changed during capture")

    run_id = os.environ.get("GITHUB_RUN_ID") or "local"
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT") or "local"
    generation_id = hashlib.sha256(os.urandom(32)).hexdigest()[:20]
    generation_name = _generation_name(run_id, attempt, generation_id)
    files = {
        name: {
            "sha256": hashlib.sha256(payloads[name]).hexdigest(),
            "size_bytes": len(payloads[name]),
            "record_count": _record_count(states[name]),
            "generation_id": generation_id,
        }
        for name in STATE_FILES
    }
    manifest = {
        "run_id": run_id,
        "run_attempt": attempt,
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "generation_id": generation_id,
        "files": files,
    }

    destination_root.mkdir(parents=True, exist_ok=True)
    destination_root.chmod(0o700)
    final_dir = destination_root / generation_name
    if final_dir.exists():
        raise SnapshotError("GENERATION_EXISTS", "refusing to overwrite an existing generation")
    temp_dir = Path(tempfile.mkdtemp(prefix=".snapshot-", dir=destination_root))
    try:
        for name in STATE_FILES:
            path = temp_dir / name
            path.write_bytes(payloads[name])
            path.chmod(0o600)
        manifest_path = temp_dir / MANIFEST
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest_path.chmod(0o600)
        os.replace(temp_dir, final_dir)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    return final_dir


def _verified_generation(generation_dir: str | Path) -> tuple[dict, dict[str, bytes]]:
    root = Path(generation_dir)
    manifest = _load_json(root / MANIFEST)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise SnapshotError("SCHEMA_VERSION_MISMATCH", "unsupported or missing snapshot schema version")
    generation_id = manifest.get("generation_id")
    entries = manifest.get("files")
    if not isinstance(generation_id, str) or not isinstance(entries, dict) or set(entries) != set(STATE_FILES):
        raise SnapshotError("INVALID_MANIFEST", "manifest must list exactly the required state files")
    payloads = {}
    parsed = {}
    for name in STATE_FILES:
        entry = entries.get(name)
        if not isinstance(entry, dict) or entry.get("generation_id") != generation_id:
            raise SnapshotError("MIXED_GENERATION", f"{name} is not marked as part of this generation")
        try:
            payload = (root / name).read_bytes()
        except FileNotFoundError as exc:
            raise SnapshotError("MISSING_FILE", f"missing generation file: {name}") from exc
        if hashlib.sha256(payload).hexdigest() != entry.get("sha256") or len(payload) != entry.get("size_bytes"):
            raise SnapshotError("HASH_MISMATCH", f"hash or size mismatch for {name}")
        try:
            parsed[name] = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SnapshotError("INVALID_JSON", f"invalid JSON in generation file {name}") from exc
        if _record_count(parsed[name]) != entry.get("record_count"):
            raise SnapshotError("INVALID_MANIFEST", f"record count mismatch for {name}")
        payloads[name] = payload
    _validate_state(parsed)
    return manifest, payloads


def restore(generation_dir: str | Path, target_dir: str | Path) -> None:
    """Verify a generation and atomically replace its state files in target_dir."""
    _, payloads = _verified_generation(generation_dir)
    target = Path(target_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)
    staged: dict[str, Path] = {}
    backups: dict[str, bytes | None] = {}
    try:
        for name, payload in payloads.items():
            path = target / name
            current = path.read_bytes() if path.exists() else None
            backups[name] = current
            if current == payload:
                continue
            fd, temp_name = tempfile.mkstemp(prefix=f".{name}.", dir=target)
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            staged[name] = Path(temp_name)
        replaced = []
        try:
            for name, temp_path in staged.items():
                os.replace(temp_path, target / name)
                replaced.append(name)
        except Exception:
            for name in reversed(replaced):
                original = backups[name]
                if original is None:
                    (target / name).unlink(missing_ok=True)
                else:
                    fd, rollback_name = tempfile.mkstemp(prefix=f".{name}.rollback.", dir=target)
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(original)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(rollback_name, target / name)
            raise
    finally:
        for path in staged.values():
            path.unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create_parser = commands.add_parser("create")
    create_parser.add_argument("--out", required=True)
    restore_parser = commands.add_parser("restore")
    restore_parser.add_argument("--from", dest="source", required=True)
    restore_parser.add_argument("--to", dest="target", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            print(create(args.out))
        else:
            restore(args.source, args.target)
            print("restored")
        return 0
    except SnapshotError as exc:
        print(f"{exc.reason_code}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
