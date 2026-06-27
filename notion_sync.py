#!/usr/bin/env python3
"""
Notion sync for the internship watcher.

Three jobs:
1. Master log — every new posting the watcher finds is appended to one
   shared Notion database ("All Internship Postings").
2. Personal trackers — members of the Discord server 📌-react to a job
   message; this module polls those reactions (Discord bot token, REST
   only) and files the job into that member's own Notion database,
   created automatically under the same parent page on first reaction.
   Members then manage Status (Saved/Applied/OA/Interview/Offer/Rejected)
   themselves in Notion.
3. Applied channel — members paste a job link into a dedicated channel;
   this module reads new messages (REST only), scrapes company/role from
   the link, and files it into the poster's own tracker with Status
   "Applied", confirming with a ✅ reaction.

Env: NOTION_TOKEN, NOTION_PARENT_PAGE_ID, DISCORD_BOT_TOKEN (optional —
without it only the master log is synced), APPLIED_CHANNEL_ID (optional —
enables job 3).

State: notion_state.json (database ids, which jobs are already filed
per user), message_map.json (written by watcher.py: message id -> job).
"""

import html
import json
import os
import re
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent
STATE_PATH = ROOT / "notion_state.json"
MSG_MAP_PATH = ROOT / "message_map.json"

NOTION_API = "https://api.notion.com/v1"
DISCORD_API = "https://discord.com/api/v10"
PIN_EMOJI = urllib.parse.quote("📌")
CHECK_EMOJI = urllib.parse.quote("✅")
WARN_EMOJI = urllib.parse.quote("⚠️")

DISCORD_EPOCH = 1420070400000  # ms; Discord snowflakes count from here
URL_RE = re.compile(r"https?://[^\s<>|]+")
ATS_HOSTS = ("greenhouse.io", "lever.co", "ashbyhq.com")

STATUS_OPTIONS = [
    {"name": "Saved", "color": "gray"},
    {"name": "Applied", "color": "blue"},
    {"name": "OA", "color": "yellow"},
    {"name": "Interview", "color": "orange"},
    {"name": "Offer", "color": "green"},
    {"name": "Rejected", "color": "red"},
]


def _notion_headers():
    return {
        "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def _notion(method, path, payload=None):
    for attempt in range(3):
        try:
            r = requests.request(method, f"{NOTION_API}{path}",
                                 headers=_notion_headers(), json=payload,
                                 timeout=30)
        except requests.exceptions.RequestException as e:
            # Transient network blip (read timeout, connection reset). A single
            # slow Notion response must not crash the whole watcher run — back
            # off and retry, then give up like any other failed call.
            print(f"  [warn] notion {path} -> {type(e).__name__}; "
                  f"retry {attempt + 1}/3")
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After", 2)))
            continue
        if r.status_code >= 400:
            print(f"  [warn] notion {path} -> HTTP {r.status_code}: "
                  f"{r.text[:200]}")
            return None
        return r.json()
    return None


def _create_db(parent_page_id, title, with_status):
    props = {
        "Role": {"title": {}},
        "Company": {"rich_text": {}},
        "Location": {"rich_text": {}},
        "Link": {"url": {}},
        "Source": {"select": {}},
        "Added": {"date": {}},
    }
    if with_status:
        props["Status"] = {"select": {"options": STATUS_OPTIONS}}
    d = _notion("POST", "/databases", {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": title}}],
        "properties": props,
    })
    return d["id"] if d else None


def _add_row(db_id, job, status=None):
    source = job["id"].split(":", 1)[0]
    props = {
        "Role": {"title": [{"text": {"content": job["title"][:200]}}]},
        "Company": {"rich_text": [{"text": {"content": job["company"][:200]}}]},
        "Location": {"rich_text": [{"text": {"content": (job.get("location") or "")[:200]}}]},
        "Link": {"url": job["url"] or None},
        "Source": {"select": {"name": source}},
        "Added": {"date": {"start": datetime.now(timezone.utc).strftime("%Y-%m-%d")}},
    }
    if status:
        props["Status"] = {"select": {"name": status}}
    return _notion("POST", "/pages",
                   {"parent": {"database_id": db_id}, "properties": props})


# ------------------------------------------------------- discord reactions

def _pin_reactors(bot_token, channel_id, message_id):
    """Users who 📌-reacted to a message (REST only, no gateway needed).

    The sync polls every tracked message individually, so this route gets
    hammered and Discord returns 429 constantly. A 429 is NOT "no reactions"
    — honor Retry-After and retry, otherwise reactions are silently dropped.
    """
    url = (f"{DISCORD_API}/channels/{channel_id}/messages/{message_id}"
           f"/reactions/{PIN_EMOJI}?limit=100")
    for attempt in range(5):
        try:
            r = requests.get(url, headers={"Authorization": f"Bot {bot_token}"},
                             timeout=30)
        except requests.exceptions.RequestException as e:
            # A Discord hiccup on one message shouldn't abort the whole sync.
            print(f"  [warn] discord reactions -> {type(e).__name__}; skipping")
            return []
        if r.status_code == 429:
            time.sleep(min(float(r.headers.get("Retry-After", 1)), 5))
            continue
        if r.status_code != 200:
            if r.status_code != 404:  # 404 = message deleted, not noteworthy
                print(f"  [warn] discord reactions -> HTTP {r.status_code}")
            return []
        return [u for u in r.json() if not u.get("bot")]
    print("  [warn] discord reactions -> still rate-limited after retries")
    return []


# --------------------------------------------------- applied-channel links

def _react(bot_token, channel_id, message_id, emoji):
    """Add a bot reaction to confirm a message was handled (best-effort)."""
    url = (f"{DISCORD_API}/channels/{channel_id}/messages/{message_id}"
           f"/reactions/{emoji}/@me")
    try:
        requests.put(url, headers={"Authorization": f"Bot {bot_token}"},
                     timeout=30)
    except requests.exceptions.RequestException:
        pass  # a missing ✅ is cosmetic; never let it abort the sync


def _channel_messages(bot_token, channel_id, after):
    """Messages newer than the `after` snowflake (Discord returns newest-first).

    Reads message content over REST — the bot's Message Content intent must be
    enabled in the Discord developer portal or `content` comes back empty.
    """
    url = f"{DISCORD_API}/channels/{channel_id}/messages?limit=100&after={after}"
    for attempt in range(5):
        try:
            r = requests.get(url, headers={"Authorization": f"Bot {bot_token}"},
                             timeout=30)
        except requests.exceptions.RequestException as e:
            print(f"  [warn] discord messages -> {type(e).__name__}; skipping")
            return []
        if r.status_code == 429:
            time.sleep(min(float(r.headers.get("Retry-After", 1)), 5))
            continue
        if r.status_code != 200:
            print(f"  [warn] discord messages -> HTTP {r.status_code}: "
                  f"{r.text[:200]}")
            return []
        return r.json()
    print("  [warn] discord messages -> still rate-limited after retries")
    return []


def _snowflake_now():
    """A Discord snowflake for the current instant (used to baseline)."""
    return str((int(time.time() * 1000) - DISCORD_EPOCH) << 22)


def _extract_url(text):
    m = URL_RE.search(text or "")
    return m.group(0).rstrip(").,]") if m else None


_META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)


def _attr(tag, name):
    m = (re.search(rf'{name}\s*=\s*"([^"]*)"', tag, re.IGNORECASE)
         or re.search(rf"{name}\s*=\s*'([^']*)'", tag, re.IGNORECASE))
    return html.unescape(m.group(1)).strip() if m else None


def _meta(page, prop):
    """Value of <meta property|name="prop" content="...">, attr-order agnostic.

    Scans tag-by-tag (each `<meta ...>` is matched on its own) so a lazy regex
    can't run across minified markup and swallow other tags' attributes.
    """
    for tag in _META_TAG_RE.findall(page):
        if (_attr(tag, "property") or _attr(tag, "name")) == prop:
            content = _attr(tag, "content")
            if content:
                return content
    return None


# Trailing segments that are the aggregator/site, not the employer.
_SITE_SUFFIXES = {
    "simplify", "simplify jobs", "linkedin", "indeed", "greenhouse", "lever",
    "ashby", "workday", "glassdoor", "ziprecruiter", "wellfound", "builtin",
    "jobs", "careers",
}


def _split_role_company(title):
    """From a page title, return (role, company-or-None).

    Handles "Role @ Company", "Role at Company", "Role - Company" after first
    stripping a trailing site name like "... | Simplify Jobs".
    """
    for sep in (" | ", " — ", " – ", " - "):
        if sep in title:
            head, tail = title.rsplit(sep, 1)
            if tail.strip().lower() in _SITE_SUFFIXES:
                title = head.strip()
                break
    for sep_re in (r"\s+@\s+", r"\s+at\s+", r"\s+[-|–—]\s+"):
        parts = re.split(sep_re, title, maxsplit=1)
        if len(parts) == 2 and parts[1].strip():
            return parts[0].strip(), parts[1].strip()
    return title.strip(), None


def _company_from_url(url):
    """Derive a company name from the URL: ATS board slug, else domain label."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    parts = [p for p in parsed.path.split("/") if p]
    if any(host.endswith(d) for d in ATS_HOSTS) and parts:
        return parts[0].replace("-", " ").replace("_", " ").title()
    labels = host.split(".")
    return labels[-2].title() if len(labels) >= 2 else (host or "Unknown")


def _parse_job_from_url(url):
    """Best-effort (company, role, location) from a job posting URL.

    og:title gives the role; the company comes from the ATS slug, or the page's
    og:site_name on non-ATS hosts (a Greenhouse/Lever/Ashby site_name is the ATS
    brand, not the employer), or the domain. Always returns something so an
    applied link is never dropped, even if the page can't be fetched.
    """
    host = urllib.parse.urlparse(url).hostname or ""
    is_ats = any(host.endswith(d) for d in ATS_HOSTS)
    company = _company_from_url(url)
    role = "Applied position"
    try:
        r = requests.get(
            url, headers={"User-Agent":
                          "internship-watcher/1.0 (+notion applied sync)"},
            timeout=20)
        if r.status_code == 200:
            page = r.text
            title = _meta(page, "og:title")
            if not title:
                m = re.search(r"<title[^>]*>(.*?)</title>", page,
                              re.IGNORECASE | re.DOTALL)
                title = html.unescape(m.group(1)).strip() if m else ""
            if title:
                role_part, company_part = _split_role_company(title)
                role = role_part or role
                # On ATS hosts the slug is the reliable employer; only trust a
                # company parsed from the title (or og:site_name) elsewhere,
                # since e.g. Simplify carries the real employer in its title.
                if not is_ats:
                    if company_part:
                        company = company_part
                    else:
                        site = _meta(page, "og:site_name")
                        if site and len(site) <= 60 \
                                and site.lower() not in _SITE_SUFFIXES:
                            company = site
    except requests.exceptions.RequestException:
        pass  # keep the URL-derived company + generic role
    return company[:200], role[:200], ""


def _sync_applied(state, bot_token, parent):
    """Read new links in the applied channel and file them as Status=Applied
    into the poster's own tracker. Returns True if state changed."""
    channel_id = os.environ.get("APPLIED_CHANNEL_ID")
    if not (bot_token and channel_id):
        return False

    after = state.get("applied_after")
    if not after:
        # First run: baseline to now so we don't backfill old channel chatter
        # as applications. Only links posted from here on are processed.
        state["applied_after"] = _snowflake_now()
        print("Applied sync: baselined channel; tracking new posts from now.")
        return True

    msgs = _channel_messages(bot_token, channel_id, after)
    if not msgs:
        return False
    msgs.sort(key=lambda m: int(m["id"]))  # process oldest -> newest

    dirty = False
    filed = 0
    max_id = int(after)
    for m in msgs:
        mid = m["id"]
        max_id = max(max_id, int(mid))
        author = m.get("author", {})
        if author.get("bot"):
            continue
        url = _extract_url(m.get("content", ""))
        if not url:
            _react(bot_token, channel_id, mid, WARN_EMOJI)  # no link found
            continue

        uid = author["id"]
        name = author.get("global_name") or author.get("username") or uid
        u = state["users"].setdefault(uid, {"name": name, "jobs": []})
        applied = u.setdefault("applied", [])
        norm = url.split("?")[0]
        if norm in applied:
            _react(bot_token, channel_id, mid, CHECK_EMOJI)
            continue
        if not u.get("db"):
            u["db"] = _create_db(
                parent, f"📌 {name}'s Internship Tracker", with_status=True)
            dirty = True
            print(f"Notion: created tracker for {name}.")

        company, role, location = _parse_job_from_url(url)
        job = {"id": f"applied:{mid}", "company": company, "title": role,
               "url": norm, "location": location}
        if u.get("db") and _add_row(u["db"], job, status="Applied"):
            applied.append(norm)
            _react(bot_token, channel_id, mid, CHECK_EMOJI)
            filed += 1
            dirty = True

    if str(max_id) != after:
        state["applied_after"] = str(max_id)
        dirty = True
    if filed:
        print(f"Notion: filed {filed} applied link(s).")
    return dirty


# ------------------------------------------------------------------- main

def run(new_jobs):
    state = {}
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text())
    state.setdefault("users", {})
    parent = os.environ["NOTION_PARENT_PAGE_ID"]
    dirty = False

    # 1) master log
    if not state.get("master_db"):
        state["master_db"] = _create_db(
            parent, "All Internship Postings", with_status=False)
        dirty = True
    if state.get("master_db"):
        for j in new_jobs:
            _add_row(state["master_db"], j)
        if new_jobs:
            print(f"Notion: logged {len(new_jobs)} posting(s) to master db.")

    # 2) personal trackers from 📌 reactions
    bot_token = os.environ.get("DISCORD_BOT_TOKEN")
    msg_map = {}
    if MSG_MAP_PATH.exists():
        msg_map = json.loads(MSG_MAP_PATH.read_text())
    if bot_token and msg_map:
        filed = 0
        for mid, rec in msg_map.items():
            # Pace the per-message reaction polls so we don't blow Discord's
            # rate limit on the very first calls (the map holds ~100+ msgs).
            time.sleep(0.25)
            for user in _pin_reactors(bot_token, rec["cid"], mid):
                uid = user["id"]
                name = user.get("global_name") or user.get("username") or uid
                u = state["users"].setdefault(uid, {"name": name, "jobs": []})
                if not u.get("db"):
                    u["db"] = _create_db(
                        parent, f"📌 {name}'s Internship Tracker",
                        with_status=True)
                    dirty = True
                    print(f"Notion: created tracker for {name}.")
                job = rec["job"]
                if u.get("db") and job["id"] not in u["jobs"]:
                    if _add_row(u["db"], job, status="Saved"):
                        u["jobs"].append(job["id"])
                        dirty = True
                        filed += 1
        if filed:
            print(f"Notion: filed {filed} 📌-tracked job(s).")

    # 3) applied-channel links -> poster's tracker, Status=Applied
    if _sync_applied(state, bot_token, parent):
        dirty = True

    if dirty:
        STATE_PATH.write_text(json.dumps(state, indent=1))
