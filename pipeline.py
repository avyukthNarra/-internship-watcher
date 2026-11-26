#!/usr/bin/env python3
"""Fetch matching internships and synchronize them to Supabase."""
import json
import sys
import time
from pathlib import Path

import db
import state_db
import watcher
from source_health import build_health, health_exit_code


CONFIG_PATH = Path(__file__).with_name("config.json")


def main():
    cfg = json.loads(CONFIG_PATH.read_text())
    watcher.validate_config(cfg)

    previous_health = state_db.load_health()
    previous_sources = previous_health.get("sources", {})
    watcher.SOURCE_HEALTH.clear()
    watcher.SOURCE_HEALTH.update(previous_sources)

    all_jobs = watcher.discover(cfg)
    current_sources = {
        url: record for url, record in watcher.SOURCE_HEALTH.items()
        if record is not previous_sources.get(url)
    }
    now = time.time()

    try:
        db.sync_default_top_companies(cfg)
        new_ids = db.upsert_jobs(all_jobs, now)
        boards = getattr(all_jobs, "boards", {})
        board_sources_ok = {
            source for source in boards
            if any(
                company["ats"] + ":" + watcher.company_board(company) == source
                and watcher.SOURCE_HEALTH.get(
                    watcher.board_url(company["ats"], watcher.company_board(company)), {}
                ).get("ok")
                for company in cfg.get("companies", [])
            )
        }
        board_seen_ids = {job["id"] for board in boards.values() for job in board}
        db.close_missing_jobs(board_sources_ok, board_seen_ids, now)
    except Exception as exc:
        print(f"Database pipeline failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    health = build_health(
        current_sources,
        previous_sources,
        now=now,
        matching_jobs=len(all_jobs),
        new_jobs=len(new_ids),
        pending_deliveries=0,
        sync_error=None,
    )
    source_records = {
        url: {key: record[key] for key in ("ok", "error", "failing_since") if key in record}
        for url, record in health["sources"].items()
    }
    health_doc = {
        "last_completed_scan": health["last_completed_scan"],
        "matching_jobs": health["matching_jobs"],
        "new_jobs": health["new_jobs"],
        "successful_sources": health["successful_sources"],
        "failed_sources": health["failed_sources"],
        "stale_failed_sources": health["stale_failed_sources"],
        "sources": source_records,
    }
    try:
        state_db.save_health(health_doc)
    except Exception as exc:
        print(f"Database pipeline failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"Found {len(all_jobs)} matching postings, {len(new_ids)} new.")
    print(
        f"Sources: {health['successful_sources']} OK, {health['failed_sources']} failed "
        f"({health['stale_failed_sources']} stale); database sync OK."
    )
    for url, record in sorted(source_records.items()):
        if not record.get("ok"):
            print(f"  FAILED: {url} — {record.get('error', 'unknown error')}")
    return health_exit_code(health)


if __name__ == "__main__":
    sys.exit(main())
