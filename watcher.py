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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

import requests

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.json"
SEEN_PATH = ROOT / "seen.json"
MSG_MAP_PATH = ROOT / "message_map.json"  # discord message id -> job, for 📌 tracking

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


def get_text(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.text
        print(f"  [warn] {url} -> HTTP {r.status_code}")
    except requests.RequestException as e:
        print(f"  [warn] {url} -> {e}")
    return None


def norm_key(job) -> str:
    """Company+title fingerprint for deduping the same job across sources."""
    return "norm:" + re.sub(r"[^a-z0-9]+", "", (job["company"] + job["title"]).lower())


def company_matches(company: str, keywords) -> bool:
    """Word-boundary keyword match, so "unity" hits "Unity" but not
    "Ivy Tech Community College", and "arm" not "Farmers"."""
    c = company.lower()
    return any(re.search(rf"\b{re.escape(k)}\b", c) for k in keywords)


# "City, ST" with a US state code (no overlap with Canadian provinces), or an
# explicit USA mention. The (?=\W|$) stops ", IN" from matching ", India".
_US_HINT = re.compile(
    r"\b(?:usa|u\.s\.|united states)\b|,\s*(?:"
    r"AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|"
    r"MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|"
    r"WA|WV|WI|WY|DC)(?=\W|$)", re.IGNORECASE)


def location_excluded(location: str, patterns) -> bool:
    """True if the location names an excluded country/city. Word-boundary
    match so "india" doesn't hit "Indianapolis, IN", and anything carrying
    a US state code or USA survives ("Dublin, OH" vs "Dublin"). Unknown/
    empty locations are kept — better a stray ping than a missed posting."""
    loc = (location or "").lower()
    if not any(re.search(rf"\b{re.escape(p)}\b", loc) for p in patterns):
        return False
    return not _US_HINT.search(location or "")


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
        if company_filter and not company_matches(company, company_filter):
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


JOBRIGHT_ROW = re.compile(
    r"^\|\s*(?:\*\*\[(?P<company>.+?)\]\(.*?\)\*\*|↳)\s*"
    r"\|\s*\*\*\[(?P<title>.+?)\]\((?P<url>https://jobright\.ai/jobs/info/(?P<jid>[0-9a-f]+)\S*?)\)\*\*\s*"
    r"\|\s*(?P<location>.*?)\s*\|.*?\|\s*(?P<date>\w{3} \d{2})\s*\|"
)


def fetch_jobright(cfg):
    """Jobright/intern-list.com listings, published to their GitHub repos as
    markdown tables (one repo per category, rolling window of recent posts)."""
    jr = cfg.get("jobright", {})
    max_age_days = jr.get("max_age_days", 7)
    now = datetime.now(timezone.utc)

    out = []
    for repo in jr.get("repos", []):
        text = get_text(
            f"https://raw.githubusercontent.com/jobright-ai/{repo}/master/README.md")
        if not text:
            continue
        company = None
        for line in text.splitlines():
            m = JOBRIGHT_ROW.match(line)
            if not m:
                continue
            company = m["company"] or company  # ↳ rows inherit the company
            if not company:
                continue
            # "Jun 09" has no year: assume the most recent past occurrence
            posted = datetime.strptime(m["date"], "%b %d").replace(
                year=now.year, tzinfo=timezone.utc)
            if posted > now:
                posted = posted.replace(year=now.year - 1)
            if (now - posted).days > max_age_days:
                continue
            out.append(
                {
                    "id": f"jobright:{m['jid']}",
                    "company": company,
                    "title": m["title"],
                    "location": m["location"],
                    "url": m["url"].split("?")[0],
                }
            )
    return out


# ------------------------------------------------------------ notifications

def notify_discord(webhook_url: str, jobs):
    """Post one message per job so members can 📌-react to file it into
    their personal Notion tracker. Big batches (re-seeds) fall back to a
    digest. Returns records mapping message ids to jobs."""
    if len(jobs) > 25:
        _notify_discord_digest(webhook_url, jobs)
        return []

    posted = []
    for j in jobs:
        content = (
            f"**{j['company']}** — [{j['title']}]({j['url']})"
            + (f" · {j['location']}" if j["location"] else "")
            + "\n-# 📌 react to add this to your Notion tracker"
        )
        r = requests.post(f"{webhook_url}?wait=true",
                          json={"content": content}, timeout=TIMEOUT)
        if r.status_code == 429:
            time.sleep(float(r.json().get("retry_after", 2)) + 0.5)
            r = requests.post(f"{webhook_url}?wait=true",
                              json={"content": content}, timeout=TIMEOUT)
        if r.status_code == 200:
            d = r.json()
            posted.append(
                {
                    "mid": d["id"],
                    "cid": d["channel_id"],
                    "ts": time.time(),
                    "job": {k: j.get(k, "") for k in
                            ("id", "company", "title", "url", "location")},
                }
            )
        else:
            print(f"  [warn] discord post -> HTTP {r.status_code}")
        time.sleep(0.4)  # stay under the webhook rate limit
    return posted


def _notify_discord_digest(webhook_url: str, jobs):
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
    seen_before = set(seen)
    include_kw = cfg.get("include_keywords", ["intern"])
    exclude_kw = cfg.get("exclude_keywords", [])

    all_jobs = []

    # 1) Direct ATS boards for companies you care most about (parallel)
    def fetch_company(c):
        fetcher = ATS_FETCHERS.get(c["ats"])
        if not fetcher:
            print(f"  [warn] unknown ATS '{c['ats']}' for {c['name']}")
            return c, []
        return c, fetcher(c["board"])

    companies = cfg.get("companies", [])
    print(f"Checking {len(companies)} company boards...")
    with ThreadPoolExecutor(max_workers=16) as ex:
        for c, jobs in ex.map(fetch_company, companies):
            for j in jobs:
                if matches(j["title"], include_kw, exclude_kw):
                    j["company"] = c["name"]
                    all_jobs.append(j)

    # 2) Aggregated feeds (catch Workday-only companies, new startups, etc.)
    if cfg.get("simplify", {}).get("enabled", True):
        print("Checking SimplifyJobs aggregated feed...")
        for j in fetch_simplify(cfg):
            if matches(j["title"], include_kw, exclude_kw):
                j["agg"] = True
                all_jobs.append(j)

    if cfg.get("jobright", {}).get("enabled", False):
        print("Checking Jobright/InternList feeds...")
        for j in fetch_jobright(cfg):
            if matches(j["title"], include_kw, exclude_kw):
                j["agg"] = True
                all_jobs.append(j)

    # Drop postings in excluded locations (e.g. non-US) across all sources.
    excl_loc = [p.lower() for p in cfg.get("exclude_locations", [])]
    if excl_loc:
        before = len(all_jobs)
        all_jobs = [j for j in all_jobs
                    if not location_excluded(j.get("location", ""), excl_loc)]
        if before != len(all_jobs):
            print(f"Location filter dropped {before - len(all_jobs)} posting(s).")

    # Dedupe against history. Direct-board postings dedupe by id only (two
    # real openings can share a title); aggregator entries are also dropped
    # when any source already surfaced the same company+title.
    new_jobs = []
    for j in all_jobs:
        if j["id"] in seen:
            continue
        if j.get("agg") and norm_key(j) in seen:
            seen.add(j["id"])  # remember the alias id, stop re-checking it
            continue
        new_jobs.append(j)
        seen.add(j["id"])
        seen.add(norm_key(j))
    for j in all_jobs:
        seen.add(norm_key(j))
    print(f"\nFound {len(all_jobs)} matching postings, {len(new_jobs)} new.")

    if new_jobs:
        for j in new_jobs:
            print(f"  NEW: {j['company']} — {j['title']} ({j['url']})")

        # Route: curated boards + Simplify (already keyword-filtered to big
        # names) -> the "top companies" channel; the Jobright firehose -> the
        # main channel, unless its company matches a curated name/keyword.
        webhook = os.environ.get("DISCORD_WEBHOOK_URL")
        webhook_top = os.environ.get("DISCORD_WEBHOOK_URL_TOP")
        top_names = {c["name"].lower() for c in cfg.get("companies", [])}
        top_kw = [k.lower() for k in
                  cfg.get("simplify", {}).get("company_keywords", [])]

        top, rest = [], []
        for j in new_jobs:
            src = j["id"].split(":", 1)[0]
            company = j["company"].lower()
            is_top = (src in ("greenhouse", "lever", "ashby", "simplify")
                      or company in top_names
                      or company_matches(company, top_kw))
            (top if is_top else rest).append(j)

        msg_records = []
        if top and (webhook_top or webhook):
            msg_records += notify_discord(webhook_top or webhook, top)
            print(f"Discord notification sent ({len(top)} top-company).")
        if rest and webhook:
            msg_records += notify_discord(webhook, rest)
            print(f"Discord notification sent ({len(rest)} other).")

        if msg_records:
            msg_map = load_json(MSG_MAP_PATH, {})
            for rec in msg_records:
                msg_map[rec["mid"]] = {
                    "cid": rec["cid"], "ts": rec["ts"], "job": rec["job"]}
            cutoff = time.time() - 3 * 86400  # reactions tracked for 3 days
            msg_map = {k: v for k, v in msg_map.items() if v["ts"] >= cutoff}
            MSG_MAP_PATH.write_text(json.dumps(msg_map, indent=0))
        if os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS"):
            notify_email(cfg, new_jobs)
            print("Email notification sent.")
        if not webhook and not os.environ.get("SMTP_USER"):
            print("[note] No DISCORD_WEBHOOK_URL or SMTP_USER/SMTP_PASS set; "
                  "printed to console only.")

    if seen != seen_before:
        SEEN_PATH.write_text(json.dumps(sorted(seen), indent=0))

    # 3) Notion: master log of every new posting + per-member trackers
    #    built from 📌 reactions (see notion_sync.py).
    if os.environ.get("NOTION_TOKEN") and os.environ.get("NOTION_PARENT_PAGE_ID"):
        import notion_sync
        notion_sync.run(new_jobs)

    return 0


if __name__ == "__main__":
    sys.exit(main())
