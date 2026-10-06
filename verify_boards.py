#!/usr/bin/env python3
"""Check configured company boards, or verify a candidate before adding it."""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from job_feeds import BOARD_APIS, board_url, feed_items
from job_utils import load_json
from project_config import validate_config

CONFIG_PATH = Path(__file__).parent / "config.json"
HEADERS = {"User-Agent": "internship-watcher/1.0 (board verification)"}


def check(company):
    """Return (name, ats, board, job count, error); -1 means verification failed."""
    name, ats, board = company
    try:
        response = requests.get(board_url(ats, board), headers=HEADERS, timeout=15)
        if response.status_code != 200:
            return name, ats, board, -1, f"HTTP {response.status_code}"
        jobs = feed_items(response.json(), BOARD_APIS[ats]["key"])
        if jobs is None:
            return name, ats, board, -1, "Unexpected feed schema"
        return name, ats, board, len(jobs), None
    except (requests.RequestException, ValueError) as exc:
        return name, ats, board, -1, type(exc).__name__


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH,
                        help="Configuration to check (defaults to this repository's config.json)")
    parser.add_argument("--company", action="append", default=[],
                        help="Check this configured company only; repeat for multiple companies")
    parser.add_argument("--candidate", nargs=2, action="append", metavar=("ATS", "BOARD"),
                        help="Verify a new ATS/board pair without editing config.json")
    args = parser.parse_args(argv)

    if args.candidate:
        if args.company:
            parser.error("Use --company or --candidate, not both")
        for ats, board in args.candidate:
            if ats not in BOARD_APIS:
                parser.error("Unsupported ATS: " + ats)
        companies = [(board, ats, board) for ats, board in args.candidate]
    else:
        cfg = load_json(args.config, {})
        validate_config(cfg)
        requested = {name.casefold() for name in args.company}
        available = {company["name"].casefold() for company in cfg["companies"]}
        if requested - available:
            parser.error("Unknown configured companies: " + ", ".join(sorted(requested - available)))
        companies = [(company["name"], company["ats"], company["board"])
                     for company in cfg["companies"]
                     if not requested or company["name"].casefold() in requested]

    with ThreadPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(check, companies))
    failed = 0
    for name, ats, board, count, error in results:
        if error:
            failed += 1
            print(f"FAIL {name}: {ats}:{board} — {error}")
        else:
            print(f"OK   {name}: {ats}:{board} — {count} jobs")
    print(f"Verified {len(results) - failed}/{len(results)} boards; {failed} failed.")
    return int(failed > 0)


if __name__ == "__main__":
    sys.exit(main())
