#!/usr/bin/env python3
"""
Internship Watcher
------------------
Polls public job-board APIs (Greenhouse, Lever, Ashby) for the companies in
config.json, plus the SimplifyJobs aggregated internship feed, filters for
internship roles matching your keywords, dedupes against seen.json, and sends
notifications via Discord webhook and/or email.

Designed to run on a schedule (GitHub Actions cron, or local cron). Each run
is stateless except for seen.json, which is committed back / persisted.
"""

import json
import os
import re
import smtplib
import sys
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

import requests

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.json"
SEEN_PATH = ROOT / "seen.json"

SIMPLIFY_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/"
    "Summer2026-Internships/dev/.github/scripts/listings.json"
)

HEADERS = {"User-Agent": "internship-watcher/1.0 (personal job alert script)"}
TIMEOUT = 20


# ---------------------------------------------------------------- utilities

def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    return default


def matches(title: str, include_kw, exclude_kw) -> bool:
    t = title.lower()
    if not any(k.lower() in t for k in include_kw):
        return False
    if any(k.lower() in t for k in exclude_kw):
        return False
    return True


def get(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
        print(f"  [warn] {url} -> HTTP {r.status_code}")
    except requests.RequestException as e:
        print(f"  [warn] {url} -> {e}")
    return None


# ------------------------------------------------------------- ATS fetchers

def fetch_greenhouse(board: str):
    """Greenhouse public board API."""
    data = get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs")
    if not data:
        return []
    return [
        {
            "id": f"greenhouse:{board}:{j['id']}",
            "title": j.get("title", ""),
            "location": (j.get("location") or {}).get("name", ""),
            "url": j.get("absolute_url", ""),
        }
        for j in data.get("jobs", [])
    ]


def fetch_lever(org: str):
    """Lever public postings API."""
    data = get(f"https://api.lever.co/v0/postings/{org}?mode=json")
    if not isinstance(data, list):
        return []
    return [
        {
            "id": f"lever:{org}:{j.get('id')}",
            "title": j.get("text", ""),
            "location": (j.get("categories") or {}).get("location", ""),
            "url": j.get("hostedUrl", ""),
        }
        for j in data
    ]


def fetch_ashby(org: str):
    """Ashby public job-board API."""
    data = get(f"https://api.ashbyhq.com/posting-api/job-board/{org}")
    if not data:
        return []
    return [
        {
            "id": f"ashby:{org}:{j.get('id')}",
            "title": j.get("title", ""),
            "location": j.get("location", ""),
            "url": j.get("jobUrl") or j.get("applyUrl", ""),
        }
        for j in data.get("jobs", [])
    ]


ATS_FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
}


def fetch_simplify(cfg):
    """SimplifyJobs aggregated internship list (covers Workday/etc. companies)."""
    data = get(SIMPLIFY_URL)
    if not isinstance(data, list):
        return []
    sim = cfg.get("simplify", {})
    wanted_terms = set(sim.get("terms", []))
    company_filter = [c.lower() for c in sim.get("company_keywords", [])]
    min_age_days = sim.get("max_age_days", 14)
    cutoff = time.time() - min_age_days * 86400

    out = []
    for j in data:
        if not j.get("active") or not j.get("is_visible", True):
            continue
        if j.get("date_posted", 0) < cutoff:
            continue
        if wanted_terms and not (wanted_terms & set(j.get("terms", []))):
            continue
        company = j.get("company_name", "")
        if company_filter and not any(k in company.lower() for k in company_filter):
            continue
        out.append(
            {
                "id": f"simplify:{j.get('id')}",
                "company": company,
                "title": j.get("title", ""),
                "location": ", ".join(j.get("locations", [])[:3]),
                "url": j.get("url", ""),
            }
        )
    return out


# ------------------------------------------------------------ notifications

def notify_discord(webhook_url: str, jobs):
    # Discord caps messages at 2000 chars; chunk the list.
    lines = [
        f"**{j['company']}** — [{j['title']}]({j['url']})"
        + (f" · {j['location']}" if j["location"] else "")
        for j in jobs
    ]
    header = f"🔔 **{len(jobs)} new internship posting(s)** — {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}\n"
    chunk = header
    for line in lines:
        if len(chunk) + len(line) + 1 > 1900:
            requests.post(webhook_url, json={"content": chunk}, timeout=TIMEOUT)
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        requests.post(webhook_url, json={"content": chunk}, timeout=TIMEOUT)


def notify_email(cfg, jobs):
    host = os.environ.get("SMTP_HOST", cfg.get("smtp_host", "smtp.gmail.com"))
    port = int(os.environ.get("SMTP_PORT", cfg.get("smtp_port", 587)))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]
    to_addr = os.environ.get("ALERT_EMAIL", user)

    body_lines = []
    for j in jobs:
        body_lines.append(f"{j['company']} — {j['title']}")
        if j["location"]:
            body_lines.append(f"  {j['location']}")
        body_lines.append(f"  {j['url']}\n")
    msg = MIMEText("\n".join(body_lines))
    msg["Subject"] = f"[Internship Watcher] {len(jobs)} new posting(s)"
    msg["From"] = user
    msg["To"] = to_addr

    with smtplib.SMTP(host, port) as s:
        s.starttls()
        s.login(user, password)
        s.sendmail(user, [to_addr], msg.as_string())


# -------------------------------------------------------------------- main

def main():
    cfg = load_json(CONFIG_PATH, {})
    seen = set(load_json(SEEN_PATH, []))
    include_kw = cfg.get("include_keywords", ["intern"])
    exclude_kw = cfg.get("exclude_keywords", [])

    all_jobs = []

    # 1) Direct ATS boards for companies you care most about
    for c in cfg.get("companies", []):
        fetcher = ATS_FETCHERS.get(c["ats"])
        if not fetcher:
            print(f"  [warn] unknown ATS '{c['ats']}' for {c['name']}")
            continue
        print(f"Checking {c['name']} ({c['ats']})...")
        for j in fetcher(c["board"]):
            if matches(j["title"], include_kw, exclude_kw):
                j["company"] = c["name"]
                all_jobs.append(j)

    # 2) Aggregated feed (catches Workday-only companies, new startups, etc.)
    if cfg.get("simplify", {}).get("enabled", True):
        print("Checking SimplifyJobs aggregated feed...")
        for j in fetch_simplify(cfg):
            if matches(j["title"], include_kw, exclude_kw):
                all_jobs.append(j)

    # Dedupe against history
    new_jobs = [j for j in all_jobs if j["id"] not in seen]
    print(f"\nFound {len(all_jobs)} matching postings, {len(new_jobs)} new.")

    if new_jobs:
        for j in new_jobs:
            print(f"  NEW: {j['company']} — {j['title']} ({j['url']})")

        webhook = os.environ.get("DISCORD_WEBHOOK_URL")
        if webhook:
            notify_discord(webhook, new_jobs)
            print("Discord notification sent.")
        if os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS"):
            notify_email(cfg, new_jobs)
            print("Email notification sent.")
        if not webhook and not os.environ.get("SMTP_USER"):
            print("[note] No DISCORD_WEBHOOK_URL or SMTP_USER/SMTP_PASS set; "
                  "printed to console only.")

        seen.update(j["id"] for j in new_jobs)
        SEEN_PATH.write_text(json.dumps(sorted(seen), indent=0))

    return 0


if __name__ == "__main__":
    sys.exit(main())
