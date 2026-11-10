#!/usr/bin/env python3
"""Restore health.json from git when a run changed nothing but timestamps and counts.

The workflow commits state after every run; a rewritten scan timestamp alone
used to produce a commit per run. Run this before `git add`. health.json is left
alone (and committed) when any other state file changed, or when a meaningful
field changed: failing sources and their failing_since, pending or parked
deliveries, or a sync error.
"""
import json
import subprocess
import sys
from pathlib import Path

STATE_FILES = ("seen.json", "message_map.json", "notion_state.json", "delivery_state.json")
VOLATILE_TOP = {"last_completed_scan", "matching_jobs", "new_jobs"}
# Per-source cache details; losing them only costs one full download.
VOLATILE_SOURCE = {"last_success", "etag", "full_fetch", "filter_digest"}


def material(health):
    """The parts of health.json worth a commit on their own."""
    result = {k: v for k, v in health.items() if k not in VOLATILE_TOP and k != "sources"}
    result["sources"] = {url: {k: v for k, v in record.items() if k not in VOLATILE_SOURCE}
                         for url, record in health.get("sources", {}).items()}
    return result


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True)


def main(root="."):
    root = Path(root)
    if git("-C", str(root), "status", "--porcelain", "--", *STATE_FILES).stdout.strip():
        return 0  # real state changed; health.json is committed with it
    committed = git("-C", str(root), "show", "HEAD:health.json")
    path = root / "health.json"
    if committed.returncode != 0 or not path.exists():
        return 0
    try:
        unchanged = material(json.loads(committed.stdout)) == material(json.loads(path.read_text()))
    except ValueError:
        return 0  # unreadable: leave it for the normal commit path
    if unchanged:
        git("-C", str(root), "checkout", "--", "health.json")
        print("health.json: only timestamps/counts changed; not committing it.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
