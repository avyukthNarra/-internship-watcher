#!/usr/bin/env python3
"""
Internship Watcher
------------------
Polls public job-board APIs (Greenhouse, Lever, Ashby) for the companies in
config.json, plus the SimplifyJobs aggregated internship feed, filters for
internship roles matching your keywords, dedupes against seen.json, and sends
notifications via Discord webhook and/or email.

Designed to run on a schedule (GitHub Actions cron, or local cron). Each run
checkpoints delivery, deduplication, and tracker state for safe retries.
"""

import argparse
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

from job_utils import (load_json, save_json, canonical_url, job_identity,
                       fingerprint, term_matches, preference_matches)

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

def matches(title: str, include_kw, exclude_kw) -> bool:
    t = title.lower()
    if not any(k.lower() in t for k in include_kw):
        return False
    if any(k.lower() in t for k in exclude_kw):
        return False
    return True


SOURCE_HEALTH = {}


def fetch(url, as_text=False):
    previous = SOURCE_HEALTH.get(url, {})
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 200:
                result = r.text if as_text else r.json()
                SOURCE_HEALTH[url] = {"ok": True, "last_success": time.time()}
                return result
            error = f"HTTP {r.status_code}"
            if r.status_code != 429 and r.status_code < 500:
                break
        except (requests.RequestException, ValueError) as exc:
            error = type(exc).__name__
        if attempt < 2:
            time.sleep(2 ** attempt)
    SOURCE_HEALTH[url] = {**previous, "ok": False, "error": error}
    print(f"  [warn] {url} -> {error}")
    return None


def get(url):
    return fetch(url)


def get_text(url):
    return fetch(url, as_text=True)


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

def source_items(url, key=None):
    previous_success = SOURCE_HEALTH.get(url, {}).get("last_success")
    data = get(url)
    if data is None:
        return []
    items = data.get(key) if key and isinstance(data, dict) else data if not key else None
    if not isinstance(items, list) or not all(isinstance(j, dict) and j.get("id") is not None for j in items):
        SOURCE_HEALTH[url] = {"ok": False, "error": "Unexpected feed schema"}
        if previous_success is not None:
            SOURCE_HEALTH[url]["last_success"] = previous_success
        return []
    return items


def fetch_greenhouse(board: str):
    """Greenhouse public board API."""
    data = source_items(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", "jobs")
    return [
        {
            "id": f"greenhouse:{board}:{j['id']}",
            "title": j.get("title", ""),
            "location": (j.get("location") or {}).get("name", ""),
            "url": j.get("absolute_url", ""),
        }
        for j in data
    ]


def fetch_lever(org: str):
    """Lever public postings API."""
    data = source_items(f"https://api.lever.co/v0/postings/{org}?mode=json")
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
    data = source_items(f"https://api.ashbyhq.com/posting-api/job-board/{org}", "jobs")
    return [
        {
            "id": f"ashby:{org}:{j.get('id')}",
            "title": j.get("title", ""),
            "location": j.get("location", ""),
            "url": j.get("jobUrl") or j.get("applyUrl", ""),
        }
        for j in data
    ]


ATS_FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
}


def fetch_simplify(cfg):
    """SimplifyJobs aggregated internship list (covers Workday/etc. companies)."""
    data = source_items(cfg.get("simplify", {}).get("url", SIMPLIFY_URL))
    sim = cfg.get("simplify", {})
    company_filter = [c.lower() for c in sim.get("company_keywords", [])]
    min_age_days = sim.get("max_age_days", 14)
    cutoff = time.time() - min_age_days * 86400

    out = []
    for j in data:
        if not j.get("active") or not j.get("is_visible", True):
            continue
        if j.get("date_posted", 0) < cutoff:
            continue
        company = j.get("company_name", "")
        if company_filter and not company_matches(company, company_filter):
            continue
        out.append(
            {
                "id": f"simplify:{j.get('id')}",
                "terms": j.get("terms", []),
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
        url = f"https://raw.githubusercontent.com/jobright-ai/{repo}/master/README.md"
        text = get_text(url)
        if not text:
            continue
        company = None
        parsed_rows = 0
        for line in text.splitlines():
            m = JOBRIGHT_ROW.match(line)
            if not m:
                continue
            parsed_rows += 1
            company = m["company"] or company  # ↳ rows inherit the company
            if not company:
                continue
            # "Jun 09" has no year: assume the most recent past occurrence
            try:
                posted = datetime.strptime(m["date"] + f" {now.year}", "%b %d %Y").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
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
                    "url": canonical_url(m["url"]),
                }
            )
        if not parsed_rows:
            SOURCE_HEALTH[url] = {**SOURCE_HEALTH.get(url, {}), "ok": False,
                                  "error": "No parseable Jobright rows"}
    return out


# ------------------------------------------------------------ notifications

def notify_discord(webhook_url, jobs):
    """Individual messages in every batch; caller checkpoints each success."""
    posted, failed = [], set()
    for j in jobs:
        content = (f"**{j['company']}** — [{j['title']}]({j['url']})"
                   + (f" · {j['location']}" if j.get("location") else "")
                   + "\n-# 📌 react to add this to your Notion tracker")
        # Avoid invalid payloads from unusually long feed fields.
        if len(content) > 2000:
            content = f"**{j['company'][:100]}** — {j['title'][:200]}\n{j['url']}"
        separator = "&" if "?" in webhook_url else "?"
        for attempt in range(3):
            try:
                r = requests.post(webhook_url + separator + "wait=true",
                                  json={"content": content, "allowed_mentions": {"parse": []}},
                                  timeout=TIMEOUT)
                if r.status_code == 200:
                    d = r.json()
                    posted.append({"mid": d["id"], "cid": d["channel_id"],
                                   "ts": time.time(), "job": j})
                    break
                if r.status_code != 429 and r.status_code < 500:
                    break
                if attempt < 2:
                    time.sleep(min(float(r.headers.get("Retry-After", 2 ** attempt)), 30))
            except (requests.RequestException, ValueError, KeyError):
                # Timeout can mean accepted-but-response-lost; keep pending.
                break
        if not posted or posted[-1]["job"]["id"] != j["id"]:
            failed.add(j["id"])
        time.sleep(0.4)
    return posted, failed


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

    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        s.login(user, password)
        s.sendmail(user, [to_addr], msg.as_string())


# -------------------------------------------------------------------- main

def discover(cfg):
    jobs = []
    include = cfg.get("include_keywords", ["intern"])
    exclude = cfg.get("exclude_keywords", [])

    def company_jobs(c):
        try:
            fetcher = ATS_FETCHERS[c["ats"]]
            return c, fetcher(c["board"])
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            SOURCE_HEALTH["board:" + c.get("board", "unknown")] = {
                "ok": False, "error": type(exc).__name__}
            return c, []

    print(f"Checking {len(cfg.get('companies', []))} company boards...")
    with ThreadPoolExecutor(max_workers=16) as executor:
        for company, found in executor.map(company_jobs, cfg.get("companies", [])):
            jobs.extend({**j, "company": company["name"]} for j in found)
    for name, fetcher in (("simplify", fetch_simplify), ("jobright", fetch_jobright)):
        if cfg.get(name, {}).get("enabled", name == "simplify"):
            try:
                jobs.extend({**j, "agg": True} for j in fetcher(cfg))
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                SOURCE_HEALTH[name] = {"ok": False, "error": type(exc).__name__}
    terms = cfg.get("terms", cfg.get("simplify", {}).get("terms", []))
    return [j for j in jobs if matches(j["title"], include, exclude)
            and not location_excluded(j.get("location", ""), cfg.get("exclude_locations", []))
            and term_matches(j, terms, cfg.get("keep_unknown_terms", True))]


def select_new(jobs, seen, ledger, now, ttl_days=30):
    """Exact identities persist; fuzzy cross-source fingerprints expire."""
    identities = ledger.setdefault("identities", {})
    prints = ledger.setdefault("fingerprints", {})
    cutoff = now - ttl_days * 86400
    prints = ledger["fingerprints"] = {k: v for k, v in prints.items() if v >= cutoff}
    new = []
    # Existing IDs seed current fingerprints without resurrecting old alerts.
    for j in jobs:
        if j["id"] in seen:
            identities[job_identity(j)] = j["id"]
            prints.setdefault(fingerprint(j), now)
    for j in jobs:
        identity, fp = job_identity(j), fingerprint(j)
        if j["id"] not in seen and identity not in identities:
            if not (j.get("agg") and fp in prints):
                new.append(j)
        seen.add(j["id"])
        identities[identity] = j["id"]
        prints.setdefault(fp, now)
    return new


def destinations(job, cfg):
    result = []
    top_names = {c["name"].lower() for c in cfg.get("companies", [])}
    top = (job["id"].split(":", 1)[0] in ("greenhouse", "lever", "ashby", "simplify")
           or job["company"].lower() in top_names
           or company_matches(job["company"], cfg.get("simplify", {}).get("company_keywords", [])))
    hook = "DISCORD_WEBHOOK_URL_TOP" if top and os.environ.get("DISCORD_WEBHOOK_URL_TOP") else "DISCORD_WEBHOOK_URL"
    if os.environ.get(hook):
        result.append("discord:" + hook)
    if os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS"):
        result.append("email")
    if os.environ.get("NOTION_TOKEN") and os.environ.get("NOTION_PARENT_PAGE_ID"):
        result.append("notion")
    for uid, preferences in cfg.get("profiles", {}).items():
        hook = preferences.get("webhook_env")
        if hook and os.environ.get(hook) and preference_matches(job, preferences):
            result.append("discord:" + hook)
    return list(dict.fromkeys(result))


def deliver(ledger, cfg, msg_map, checkpoint):
    # Bound work while retaining every undelivered job for the next run.
    budget = cfg.get("max_discord_per_run", 50)
    for entry in list(ledger.setdefault("pending", {}).values()):
        for destination in list(entry["destinations"]):
            job = entry["job"]
            success = False
            try:
                if destination.startswith("discord:"):
                    hook = os.environ.get(destination.split(":", 1)[1])
                    if not hook or budget <= 0:
                        continue
                    budget -= 1
                    records, failures = notify_discord(hook, [job])
                    success = not failures
                    for rec in records:
                        msg_map[rec["mid"]] = {k: rec[k] for k in ("cid", "ts", "job")}
                        save_json(MSG_MAP_PATH, msg_map)
                elif destination == "email":
                    notify_email(cfg, [job])
                    success = True
                elif destination == "notion":
                    import notion_sync
                    success = notion_sync.log_master(job)
            except (requests.RequestException, smtplib.SMTPException, OSError, ValueError, KeyError) as exc:
                entry["error"] = type(exc).__name__
            if success:
                entry["destinations"].remove(destination)
                entry.pop("error", None)
            else:
                entry["attempts"] = entry.get("attempts", 0) + 1
            checkpoint()
    ledger["pending"] = {k: v for k, v in ledger["pending"].items() if v["destinations"]}
    checkpoint()


def validate_config(cfg):
    if not isinstance(cfg, dict) or not isinstance(cfg.get("companies"), list):
        raise ValueError("config.json must contain a companies list")
    for company in cfg["companies"]:
        if not isinstance(company, dict) or not all(isinstance(company.get(k), str) and company[k]
                                                   for k in ("name", "ats", "board")):
            raise ValueError("Every company needs name, ats, and board strings")
        if company["ats"] not in ATS_FETCHERS:
            raise ValueError("Unsupported ATS: " + company["ats"])
    for key in ("max_discord_per_run", "dedup_days", "follow_up_days"):
        if key in cfg and (type(cfg[key]) is not int or cfg[key] < 0):
            raise ValueError(key + " must be a non-negative integer")
    for key in ("terms", "include_keywords", "exclude_keywords", "exclude_locations"):
        if key in cfg and (not isinstance(cfg[key], list) or not all(isinstance(v, str) for v in cfg[key])):
            raise ValueError(key + " must be a list of strings")
    if not isinstance(cfg.get("profiles", {}), dict):
        raise ValueError("profiles must map Discord user IDs to preferences")
    for profile in cfg.get("profiles", {}).values():
        if not isinstance(profile, dict):
            raise ValueError("Each profile must be an object")
        for key in ("roles", "companies", "locations", "terms"):
            if key in profile and (not isinstance(profile[key], list)
                                   or not all(isinstance(v, str) for v in profile[key])):
                raise ValueError("Profile " + key + " must be a list of strings")
        if "follow_up_days" in profile and (type(profile["follow_up_days"]) is not int or profile["follow_up_days"] < 0):
            raise ValueError("Profile follow_up_days must be a non-negative integer")
        if "webhook_env" in profile and (not isinstance(profile["webhook_env"], str)
                                         or not profile["webhook_env"].startswith("DISCORD_WEBHOOK_")):
            raise ValueError("Profile webhook_env must begin DISCORD_WEBHOOK_")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Fetch and preview without writes or notifications")
    args = parser.parse_args(argv)
    cfg = load_json(CONFIG_PATH, {})
    validate_config(cfg)
    # Actions supplies optional personal channels in one JSON secret; only
    # explicitly named Discord webhook variables may be injected.
    personal_hooks = json.loads(os.environ.get("PERSONAL_WEBHOOKS_JSON") or "{}")
    if not isinstance(personal_hooks, dict):
        raise ValueError("PERSONAL_WEBHOOKS_JSON must be an object")
    for name, value in personal_hooks.items():
        if not name.startswith("DISCORD_WEBHOOK_") or not isinstance(value, str):
            raise ValueError("Personal webhook keys must begin DISCORD_WEBHOOK_")
        os.environ.setdefault(name, value)
    enabled = any(os.environ.get(k) for k in ("DISCORD_WEBHOOK_URL", "DISCORD_WEBHOOK_URL_TOP"))
    enabled |= bool(os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS"))
    enabled |= bool(os.environ.get("NOTION_TOKEN") and os.environ.get("NOTION_PARENT_PAGE_ID"))
    enabled |= any(os.environ.get(p.get("webhook_env", "")) for p in cfg.get("profiles", {}).values())
    dry_run = args.dry_run or not enabled
    ledger_path = ROOT / "delivery_state.json"
    health_path = ROOT / "health.json"
    ledger = load_json(ledger_path, {})
    # Ledger IDs are authoritative after a crash between the two state writes.
    seen = set(load_json(SEEN_PATH, [])) | set(ledger.get("known_ids", []))
    previous_health = load_json(health_path, {})
    SOURCE_HEALTH.clear()
    SOURCE_HEALTH.update(previous_health.get("sources", {}))
    old_sources = dict(SOURCE_HEALTH)
    all_jobs = discover(cfg)
    # Retain only sources actually fetched this run.
    current_sources = {k: v for k, v in SOURCE_HEALTH.items() if v is not old_sources.get(k)}
    now = time.time()
    new_jobs = select_new(all_jobs, seen, ledger, now, cfg.get("dedup_days", 30))
    print(f"Found {len(all_jobs)} matching postings, {len(new_jobs)} new.")
    for j in new_jobs:
        print(f"  NEW: {j['company']} — {j['title']} ({j['url']})")
    if dry_run:
        print("Dry run: no state changes, notifications, or Notion calls.")
        return 0

    pending = ledger.setdefault("pending", {})
    for j in new_jobs:
        targets = destinations(j, cfg)
        if targets:
            pending.setdefault(j["id"], {"job": j, "destinations": targets, "created": now})
    ledger["known_ids"] = sorted(seen)
    checkpoint = lambda: save_json(ledger_path, ledger)
    checkpoint()  # persist intent before any external side effect
    save_json(SEEN_PATH, sorted(seen))
    msg_map = load_json(MSG_MAP_PATH, {})
    msg_map = {k: v for k, v in msg_map.items() if v["ts"] >= now - 3 * 86400}
    save_json(MSG_MAP_PATH, msg_map)
    sync_error = None
    try:
        deliver(ledger, cfg, msg_map, checkpoint)
        if os.environ.get("NOTION_TOKEN") and os.environ.get("NOTION_PARENT_PAGE_ID"):
            import notion_sync
            notion_sync.run([], cfg=cfg)
    except Exception as exc:
        sync_error = type(exc).__name__
        print(f"[error] Sync failed: {sync_error}; checkpointed work will retry.")
    failures = sum(not v.get("ok") for v in current_sources.values())
    health = {"last_completed_scan": now, "sources": current_sources,
              "successful_sources": len(current_sources) - failures, "failed_sources": failures,
              "matching_jobs": len(all_jobs), "new_jobs": len(new_jobs),
              "pending_deliveries": sum(len(v["destinations"]) for v in ledger["pending"].values()),
              "sync_error": sync_error}
    save_json(health_path, health)
    summary = (f"Sources: {health['successful_sources']} OK, {failures} failed; "
               f"pending deliveries: {health['pending_deliveries']}; sync: {sync_error or 'OK'}")
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
            stream.write(summary + "\n")
    return int(bool(failures or sync_error or health["pending_deliveries"]))


if __name__ == "__main__":
    sys.exit(main())
