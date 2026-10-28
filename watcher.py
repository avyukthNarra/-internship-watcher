#!/usr/bin/env python3
"""
Internship Watcher
------------------
Polls company boards and the SimplifyJobs and Jobright feeds, filters matching
internships, deduplicates against durable history, and queues delivery to
Discord, email, and Notion.

Designed to run on a schedule (GitHub Actions cron, or local cron). Each run
checkpoints delivery, deduplication, and tracker state for safe retries.
"""

import argparse
import hashlib
import json
import os
import re
import smtplib
import ssl
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.mime.text import MIMEText
from functools import lru_cache
from pathlib import Path

import requests

from job_utils import (load_json, save_json, canonical_url, job_identity, clean_job,
                       fingerprint, term_matches, preference_matches)
from job_feeds import board_url, feed_items
from project_config import (DEFAULT_DEDUP_DAYS, DEFAULT_DISCORD_LIMIT, DEFAULT_MAX_DELIVERY_ATTEMPTS,
                            load_personal_webhooks, notifications_enabled, validate_config)
from source_health import SOURCE_ALERT_AFTER, build_health, health_summary, health_exit_code

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.json"
SEEN_PATH = ROOT / "seen.json"
MSG_MAP_PATH = ROOT / "message_map.json"  # discord message id -> job, for 📌 tracking

SIMPLIFY_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/"
    "Summer2027-Internships/dev/.github/scripts/listings.json"
)

HEADERS = {"User-Agent": "internship-watcher/1.0 (personal job alert script)"}
TIMEOUT = 20


# ---------------------------------------------------------------- utilities

@lru_cache(maxsize=None)
def _keyword_regex(keywords):
    """Whole-word match (optional plural s), so "intern" skips "International"
    and "sales" skips "Salesforce"."""
    parts = [re.escape(k.strip().lower()) for k in keywords if k.strip()]
    return re.compile(r"(?<!\w)(?:" + "|".join(parts) + r")s?(?!\w)") if parts else None


def matches(title: str, include_kw, exclude_kw) -> bool:
    t = (title or "").lower()
    include, exclude = _keyword_regex(tuple(include_kw)), _keyword_regex(tuple(exclude_kw))
    if include is None or not include.search(t):
        return False
    return exclude is None or not exclude.search(t)


SOURCE_HEALTH = {}
NOT_MODIFIED = object()  # a conditional fetch found the feed unchanged
CONDITIONAL_FETCH = True  # main() turns this off for dry runs so previews show the full feed
FULL_FETCH_INTERVAL = 3600  # always refetch in full at least hourly as a safety net


def fetch(url, as_text=False, etag=None, track_etag=False):
    """GET with retries. With `etag`, sends If-None-Match and returns
    NOT_MODIFIED on HTTP 304. With `track_etag`, the response ETag is kept
    in the source record for the next run."""
    previous = SOURCE_HEALTH.get(url, {})
    headers = {**HEADERS, **({"If-None-Match": etag} if etag else {})}
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers, timeout=TIMEOUT)
            if r.status_code == 304 and etag:
                SOURCE_HEALTH[url] = {**previous, "ok": True, "last_success": time.time()}
                return NOT_MODIFIED
            if r.status_code == 200:
                result = r.text if as_text else r.json()
                record = {"ok": True, "last_success": time.time()}
                new_etag = r.headers.get("ETag") if track_etag else None
                if isinstance(new_etag, str):
                    record["etag"] = new_etag
                SOURCE_HEALTH[url] = record
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


def get(url, etag=None, track_etag=False):
    if etag or track_etag:
        return fetch(url, etag=etag, track_etag=track_etag)
    return fetch(url)


def get_text(url):
    return fetch(url, as_text=True)


def norm_key(job) -> str:
    """Legacy fingerprint retained for compatibility; no longer used for matching."""
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

def source_items(url, key=None, etag=None, track_etag=False):
    previous = dict(SOURCE_HEALTH.get(url, {}))
    data = get(url, etag=etag, track_etag=track_etag) if (etag or track_etag) else get(url)
    if data is NOT_MODIFIED:
        return NOT_MODIFIED
    if data is None:
        return []
    items = feed_items(data, key)
    if items is None:
        SOURCE_HEALTH[url] = {**previous, "ok": False, "error": "Unexpected feed schema"}
        return []
    return items


def fetch_greenhouse(board: str):
    """Greenhouse public board API."""
    data = source_items(board_url("greenhouse", board), "jobs")
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
    data = source_items(board_url("lever", org))
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
    data = source_items(board_url("ashby", org), "jobs")
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


def _filter_digest(cfg):
    """Changes whenever a setting that affects which listings match changes,
    which invalidates the cached ETag."""
    keys = ("simplify", "include_keywords", "exclude_keywords", "exclude_locations",
            "terms", "keep_unknown_terms")
    blob = json.dumps({k: cfg.get(k) for k in keys}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def fetch_simplify(cfg):
    """SimplifyJobs aggregated internship list (covers Workday/etc. companies)."""
    sim = cfg.get("simplify", {})
    url = sim.get("url", SIMPLIFY_URL)
    record = SOURCE_HEALTH.get(url, {})
    digest = _filter_digest(cfg)
    cached = (CONDITIONAL_FETCH and record.get("ok") and record.get("etag")
              and record.get("filter_digest") == digest
              and time.time() - record.get("full_fetch", 0) < FULL_FETCH_INTERVAL)
    data = source_items(url, etag=record["etag"] if cached else None, track_etag=CONDITIONAL_FETCH)
    if data is NOT_MODIFIED:
        # Nothing changed since a run that already evaluated every listing.
        return []
    if SOURCE_HEALTH.get(url, {}).get("ok") and SOURCE_HEALTH[url].get("etag"):
        SOURCE_HEALTH[url] = {**SOURCE_HEALTH[url], "filter_digest": digest, "full_fetch": time.time()}
    company_filter = [c.lower() for c in sim.get("company_keywords", [])]
    categories = {c.lower() for c in sim.get("include_categories", [])}
    category_roles = {name.lower(): _keyword_regex(tuple(words))
                      for name, words in sim.get("category_roles", {}).items() if words}
    category_exclude = {name.lower(): _keyword_regex(tuple(words))
                        for name, words in sim.get("category_exclude", {}).items() if words}
    min_age_days = sim.get("max_age_days", 14)
    cutoff = time.time() - min_age_days * 86400

    out = []
    for j in data:
        if not j.get("active") or not j.get("is_visible", True):
            continue
        if j.get("date_posted", 0) < cutoff:
            continue
        company = j.get("company_name", "")
        category = j.get("category") or ""
        by_company = not company_filter or company_matches(company, company_filter)
        by_category = category.lower() in categories
        if not (by_company or by_category):
            continue
        roles = category_roles.get(category.lower())
        if not by_company and roles and not roles.search(j.get("title", "").lower()):
            continue  # pulled for its category, but the role is not one you want
        blocked = category_exclude.get(category.lower())
        if not by_company and blocked and blocked.search(j.get("title", "").lower()):
            continue
        job = {
            "id": f"simplify:{j.get('id')}",
            "terms": j.get("terms", []),
            "company": company,
            "title": j.get("title", ""),
            "location": ", ".join(j.get("locations", [])[:3]),
            "url": j.get("url", ""),
            "category": category,
        }
        if not by_company:
            job["via_category"] = True  # wanted for its category, not a company you track
        out.append(job)
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
        # Brackets/parens/spaces in untrusted text would break or rewrite the link.
        title = j["title"].replace("[", "(").replace("]", ")")
        link = j["url"].replace(")", "%29").replace("(", "%28").replace(" ", "%20")
        content = (f"**{j['company']}** — [{title}]({link})"
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
        s.starttls(context=ssl.create_default_context())
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
    jobs = [clean_job(j) for j in jobs]
    return [j for j in jobs if matches(j["title"], include, exclude)
            and not location_excluded(j.get("location", ""), cfg.get("exclude_locations", []))
            and term_matches(j, terms, cfg.get("keep_unknown_terms", True))]


def select_new(jobs, seen, ledger, now, ttl_days=DEFAULT_DEDUP_DAYS):
    """Exact identities persist; fuzzy cross-source fingerprints expire."""
    identities = ledger.setdefault("identities", {})
    recent_fingerprints = ledger.setdefault("fingerprints", {})
    cutoff = now - ttl_days * 86400
    recent_fingerprints = {key: timestamp for key, timestamp in recent_fingerprints.items()
                           if timestamp >= cutoff}
    ledger["fingerprints"] = recent_fingerprints
    new = []
    # Existing IDs seed current fingerprints without resurrecting old alerts.
    for j in jobs:
        if j["id"] in seen:
            identities[job_identity(j)] = j["id"]
            recent_fingerprints.setdefault(fingerprint(j), now)
    for j in jobs:
        identity, fp = job_identity(j), fingerprint(j)
        if j["id"] not in seen and identity not in identities:
            if not (j.get("agg") and fp in recent_fingerprints):
                new.append(j)
        seen.add(j["id"])
        identities[identity] = j["id"]
        recent_fingerprints.setdefault(fp, now)
    return new


def destinations(job, cfg):
    result = []
    top_names = {c["name"].lower() for c in cfg.get("companies", [])}
    top = ((job["id"].split(":", 1)[0] in ("greenhouse", "lever", "ashby", "simplify")
            and not job.get("via_category"))
           or job["company"].lower() in top_names
           or company_matches(job["company"], cfg.get("simplify", {}).get("company_keywords", [])))
    hook = "DISCORD_WEBHOOK_URL_TOP" if top and os.environ.get("DISCORD_WEBHOOK_URL_TOP") else "DISCORD_WEBHOOK_URL"
    if os.environ.get(hook):
        result.append("discord:" + hook)
    if os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS"):
        result.append("email")
    if os.environ.get("NOTION_TOKEN") and os.environ.get("NOTION_PARENT_PAGE_ID"):
        result.append("notion")
    # Personal profiles and shared alert channels route the same way.
    for preferences in [*cfg.get("profiles", {}).values(), *cfg.get("alert_channels", [])]:
        hook = preferences.get("webhook_env")
        if hook and os.environ.get(hook) and preference_matches(job, preferences):
            result.append("discord:" + hook)
    return list(dict.fromkeys(result))


def deliver(ledger, cfg, msg_map, checkpoint):
    # Bound work while retaining every undelivered job for the next run.
    budget = cfg.get("max_discord_per_run", DEFAULT_DISCORD_LIMIT)
    max_attempts = cfg.get("max_delivery_attempts", DEFAULT_MAX_DELIVERY_ATTEMPTS)
    dead = ledger.setdefault("dead", {})
    for entry in list(ledger.setdefault("pending", {}).values()):
        for destination in list(entry["destinations"]):
            job = entry["job"]
            success = False
            error = "DeliveryFailed"
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
            except Exception as exc:
                # One malformed posting must never stop the jobs queued behind it.
                error = type(exc).__name__
            if success:
                entry["destinations"].remove(destination)
                entry.pop("error", None)
                entry.get("tries", {}).pop(destination, None)
                continue
            tries = entry.setdefault("tries", {})
            tries[destination] = tries.get(destination, 0) + 1
            entry["attempts"] = entry.get("attempts", 0) + 1
            entry["error"] = error
            if max_attempts and tries[destination] >= max_attempts:
                # Park it: reported in health.json but no longer retried or failing runs.
                dead[f"{job['id']}|{destination}"] = {
                    "job": job, "destination": destination, "error": error,
                    "attempts": tries[destination], "dead_at": time.time()}
                entry["destinations"].remove(destination)
                tries.pop(destination, None)
            checkpoint()
    ledger["pending"] = {k: v for k, v in ledger["pending"].items() if v["destinations"]}
    checkpoint()


def queue_deliveries(ledger, jobs, seen, cfg, now):
    """Record delivery intent before sending anything or acknowledging seen IDs."""
    pending = ledger.setdefault("pending", {})
    for job in jobs:
        targets = destinations(job, cfg)
        if targets:
            pending.setdefault(job["id"], {
                "job": job, "destinations": targets, "created": now,
            })
    ledger["known_ids"] = sorted(seen)


def report_health(health):
    save_json(ROOT / "health.json", health)
    summary = health_summary(health)
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
            stream.write(summary + "\n")
    return health_exit_code(health)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Fetch and preview without writes or notifications")
    args = parser.parse_args(argv)
    cfg = load_json(CONFIG_PATH, {})
    validate_config(cfg)
    load_personal_webhooks()
    dry_run = args.dry_run or not notifications_enabled(cfg)
    global CONDITIONAL_FETCH
    CONDITIONAL_FETCH = not dry_run
    ledger_path = ROOT / "delivery_state.json"
    health_path = ROOT / "health.json"
    ledger = load_json(ledger_path, {})
    # Ledger IDs are authoritative after a crash between the two state writes.
    seen = set(load_json(SEEN_PATH, [])) | set(ledger.get("known_ids", []))
    previous_health = load_json(health_path, {})
    SOURCE_HEALTH.clear()
    SOURCE_HEALTH.update(previous_health.get("sources", {}))
    previous_sources = dict(SOURCE_HEALTH)
    all_jobs = discover(cfg)
    # Fetchers replace a source record on every attempt. An unchanged object
    # belongs to a source no longer polled and must not stay in current health.
    current_sources = {url: record for url, record in SOURCE_HEALTH.items()
                       if record is not previous_sources.get(url)}
    now = time.time()
    new_jobs = select_new(all_jobs, seen, ledger, now, cfg.get("dedup_days", DEFAULT_DEDUP_DAYS))
    print(f"Found {len(all_jobs)} matching postings, {len(new_jobs)} new.")
    for j in new_jobs:
        print(f"  NEW: {j['company']} — {j['title']} ({j['url']})")
    if dry_run:
        print("Dry run: no state changes, notifications, or Notion calls.")
        return 0

    queue_deliveries(ledger, new_jobs, seen, cfg, now)

    def checkpoint():
        save_json(ledger_path, ledger)

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
    health = build_health(
        current_sources, previous_sources, now=now,
        matching_jobs=len(all_jobs), new_jobs=len(new_jobs),
        pending_deliveries=sum(len(entry["destinations"]) for entry in ledger["pending"].values()),
        dead_deliveries=len(ledger.get("dead", {})),
        sync_error=sync_error,
    )
    return report_health(health)


if __name__ == "__main__":
    sys.exit(main())
