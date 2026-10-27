#!/usr/bin/env python3
"""Find Greenhouse, Lever, and Ashby boards for companies you don't track yet.

Feed it company names (one per line) or the open Y Combinator list. For each
company it tries likely board slugs, keeps boards that respond, and counts the
postings that pass the watcher's internship filters. Output is a report for you
to review; this never edits config.json. Verify a pick with
`python3 verify_boards.py --candidate ATS BOARD` before adding it.
"""

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

import requests

from job_feeds import BOARD_APIS, board_url, feed_items
from job_utils import load_json
from project_config import validate_config

CONFIG_PATH = Path(__file__).parent / "config.json"
YC_URL = "https://yc-oss.github.io/api/companies/all.json"
HEADERS = {"User-Agent": "internship-watcher/1.0 (board discovery)"}
TITLE_FIELDS = {"greenhouse": "title", "lever": "text", "ashby": "title"}


def slug_variants(name, website=""):
    """Likely board slugs, most specific first: the website's domain label,
    then the name squashed ("Scale AI" -> scaleai) and hyphenated (scale-ai)."""
    slugs = []
    host = (urlsplit(website or "").hostname or "").lower()
    labels = [label for label in host.split(".") if label and label != "www"]
    if len(labels) >= 2:
        slugs.append(labels[-2])
    words = re.findall(r"[a-z0-9]+", (name or "").lower())
    if words:
        slugs.extend(["".join(words), "-".join(words)])
    return list(dict.fromkeys(s for s in slugs if len(s) >= 2))


def same_company(name, board_name):
    """Loose check that a Greenhouse board name belongs to this company."""
    squash = lambda text: re.sub(r"[^a-z0-9]+", "", (text or "").lower())
    a, b = squash(name), squash(board_name)
    return bool(a and b and (a in b or b in a))


def probe(ats, slug, matcher):
    """(job count, internship count, sample title) for a live board, else None."""
    try:
        response = requests.get(board_url(ats, slug), headers=HEADERS, timeout=15)
        if response.status_code != 200:
            return None
        jobs = feed_items(response.json(), BOARD_APIS[ats]["key"])
    except (requests.RequestException, ValueError):
        return None
    if jobs is None:
        return None
    titles = [str(j.get(TITLE_FIELDS[ats]) or "") for j in jobs]
    interns = [t for t in titles if matcher(t)]
    return len(jobs), len(interns), (interns[0] if interns else "")


def board_name(slug):
    """Greenhouse's board endpoint names the company, which Lever/Ashby lack."""
    try:
        response = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}",
                                headers=HEADERS, timeout=15)
        return response.json().get("name") if response.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return None


def discover(company, matcher):
    """All boards found for one {name, website} record."""
    found = []
    for slug in slug_variants(company["name"], company.get("website", "")):
        for ats in BOARD_APIS:
            result = probe(ats, slug, matcher)
            if result:
                entry = {"company": company["name"], "ats": ats, "board": slug,
                         "jobs": result[0], "internships": result[1], "sample": result[2]}
                if ats == "greenhouse":
                    entry["confirmed"] = same_company(company["name"], board_name(slug))
                found.append(entry)
    return found


def load_yc(min_team):
    companies = requests.get(YC_URL, headers=HEADERS, timeout=60).json()
    return [{"name": c["name"], "website": c.get("website", "")} for c in companies
            if c.get("isHiring") and c.get("status") == "Active"
            and (c.get("team_size") or 0) >= min_team]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--names", type=Path, help="Text file with one company name per line")
    source.add_argument("--yc", action="store_true", help="Y Combinator companies marked as hiring")
    parser.add_argument("--min-team", type=int, default=10, help="With --yc: minimum team size")
    parser.add_argument("--limit", type=int, default=0, help="Only check the first N companies")
    parser.add_argument("--min-interns", type=int, default=1,
                        help="Only report boards with at least this many matching postings")
    parser.add_argument("--json", type=Path, help="Also write the report to this file")
    args = parser.parse_args(argv)

    cfg = load_json(CONFIG_PATH, {})
    validate_config(cfg)
    import watcher  # reuse the exact title filter
    include, exclude = cfg.get("include_keywords", ["intern"]), cfg.get("exclude_keywords", [])
    matcher = lambda title: watcher.matches(title, include, exclude)
    tracked = {(c["ats"], c["board"].lower()) for c in cfg["companies"]}
    tracked_names = {c["name"].lower() for c in cfg["companies"]}

    if args.yc:
        companies = load_yc(args.min_team)
    else:
        companies = [{"name": line.strip()} for line in args.names.read_text().splitlines()
                     if line.strip() and not line.startswith("#")]
    companies = [c for c in companies if c["name"].lower() not in tracked_names]
    if args.limit:
        companies = companies[:args.limit]
    print(f"Checking {len(companies)} companies (boards already in config are skipped)...",
          file=sys.stderr)

    with ThreadPoolExecutor(max_workers=16) as executor:
        results = [entry for found in executor.map(lambda c: discover(c, matcher), companies)
                   for entry in found]
    results = list({(e["ats"], e["board"]): e for e in results}.values())  # same board via two companies
    report = sorted((e for e in results
                     if e["internships"] >= args.min_interns and (e["ats"], e["board"].lower()) not in tracked),
                    key=lambda e: (-e["internships"], e["company"]))
    for e in report:
        note = {True: " [name confirmed]", False: " [NAME DIFFERS - check]"}.get(e.get("confirmed"), "")
        print(f"{e['company']}: {e['ats']}:{e['board']} - {e['internships']} intern / {e['jobs']} jobs"
              f" - {e['sample']}{note}")
    print(f"\n{len(report)} candidate boards from {len(companies)} companies. "
          "Review each, then verify with verify_boards.py --candidate ATS BOARD.")
    if args.json:
        args.json.write_text(json.dumps(report, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
