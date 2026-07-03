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

STATUS_OPTIONS = [
    {"name": "Saved", "color": "gray"},
    {"name": "Applied", "color": "blue"},
    {"name": "OA", "color": "yellow"},
    {"name": "Interview", "color": "orange"},
    {"name": "Offer", "color": "green"},
    {"name": "Rejected", "color": "red"},
    {"name": "Closed", "color": "brown"},  # posting vanished before applying
]

DEAD_SWEEP_INTERVAL = 24 * 3600  # re-check Saved rows once a day


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

    Only called for messages the bulk channel scan already showed to have a
    📌, so it fires a handful of times per run at most. A 429 is NOT "no
    reactions" — honor Retry-After and retry, otherwise reactions are
    silently dropped.
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


def _pinned_message_ids(bot_token, msg_map):
    """Which tracked messages currently carry a 📌 — found by paging each
    channel's recent messages in bulk (reaction summaries ride along free),
    instead of one reactions request per tracked message. Cuts ~150 Discord
    calls per run down to ~4."""
    by_channel = {}
    for mid, rec in msg_map.items():
        by_channel.setdefault(rec["cid"], []).append(int(mid))

    pinned = set()
    for cid, mids in by_channel.items():
        cursor = str(min(mids) - 1)
        while True:
            batch = _channel_messages(bot_token, cid, cursor)
            if not batch:
                break  # done, or fetch failed — reactions retry next run
            for m in batch:
                if m["id"] in msg_map and any(
                        r.get("emoji", {}).get("name") == "📌"
                        for r in m.get("reactions", [])):
                    pinned.add(m["id"])
            if len(batch) < 100:
                break
            cursor = str(max(int(m["id"]) for m in batch))
    return pinned


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


# Site/aggregator names that may trail a title or fill og:site_name — never
# the actual employer.
_SITE_SUFFIXES = {
    "simplify", "simplify jobs", "linkedin", "indeed", "greenhouse", "lever",
    "ashby", "workday", "smartrecruiters", "glassdoor", "ziprecruiter",
    "wellfound", "builtin", "jobs", "careers",
}

# Second-level domains owned by an ATS/aggregator: the bare domain label is the
# vendor, not the employer, so don't fall back to it as a company name.
_BRAND_DOMAINS = {
    "greenhouse", "lever", "ashbyhq", "myworkdayjobs", "oraclecloud", "icims",
    "smartrecruiters", "workable", "simplify", "linkedin", "indeed",
    "glassdoor", "ziprecruiter", "wellfound", "jobvite", "bamboohr",
    "successfactors", "dayforcehcm", "paylocity",
}

# Hosts whose first path segment is the employer slug.
_PATH_SLUG_HOSTS = ("greenhouse.io", "lever.co", "ashbyhq.com",
                    "smartrecruiters.com", "workable.com")
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _humanize(slug):
    """creditkarma -> Creditkarma, ExpediaGroup -> Expedia Group,
    al-warren-oil -> Al Warren Oil."""
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", slug)        # split camelCase
    s = s.replace("-", " ").replace("_", " ").strip()
    return s.title() if (s.islower() or s.isupper()) else s


def _strip_site_suffix(title):
    for sep in (" | ", " — ", " – ", " - "):
        if sep in title:
            head, tail = title.rsplit(sep, 1)
            if tail.strip().lower() in _SITE_SUFFIXES:
                return head.strip()
    return title


def _strip_trailing_company(role, company):
    for sep in (" @ ", " at ", " - ", " — ", " – ", " | "):
        tail = (sep + company).lower()
        if role.lower().endswith(tail):
            return role[: -len(tail)].strip()
    return role


def _company_from_title(title):
    """Employer out of "Role @ Company", "Role at Company", or
    "Company hiring Role ..." (LinkedIn) patterns."""
    t = _strip_site_suffix(title)
    for pat in (r"\s+@\s+(?P<c>.+)$", r"\s+at\s+(?P<c>.+)$"):
        m = re.search(pat, t)
        if m:
            return m.group("c").strip()
    m = re.match(r"(?P<c>.+?)\s+hiring\s+", t)
    return m.group("c").strip() if m else None


def _company_from_url(url):
    """Employer from the URL: Workday tenant, ATS path slug, else domain label
    (skipping ATS/aggregator domains). May return None."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    parts = [p for p in parsed.path.split("/") if p]
    if host.endswith("myworkdayjobs.com"):
        return _humanize(host.split(".")[0])             # tenant subdomain
    for dom in _PATH_SLUG_HOSTS:
        if host.endswith(dom) and parts:
            return _humanize(parts[0])
    labels = host.split(".")
    if len(labels) >= 2 and labels[-2] not in _BRAND_DOMAINS:
        return labels[-2].title()
    return None


def _json(url):
    r = requests.get(url, headers={"User-Agent": "internship-watcher/1.0"},
                     timeout=15)
    return r.json() if r.status_code == 200 else None


def _ats_api(url):
    """Exact job data from an ATS public API as {company, role, location}, or
    None. `company` is None when the API doesn't carry it (Greenhouse/Lever/
    Ashby) and the caller resolves it from the page/slug instead."""
    p = urllib.parse.urlparse(url)
    host = p.hostname or ""
    parts = [s for s in p.path.split("/") if s]
    uuid = next((s for s in parts if _UUID_RE.fullmatch(s)), None)
    q = urllib.parse.parse_qs(p.query)
    try:
        if host.endswith("greenhouse.io") and parts:
            board, jid = parts[0], None
            if "jobs" in parts:
                i = parts.index("jobs")
                jid = parts[i + 1] if i + 1 < len(parts) else None
            jid = jid or q.get("gh_jid", [None])[0]
            # The board endpoint carries the clean company name (og:title on the
            # page is the company on some boards but the role on others, so it
            # can't be trusted); the job endpoint carries role + location.
            bn = _json(f"https://boards-api.greenhouse.io/v1/boards/{board}")
            company = bn.get("name") if bn else None
            role = location = None
            if jid:
                d = _json(f"https://boards-api.greenhouse.io/v1/boards/{board}"
                          f"/jobs/{jid}")
                if d:
                    role = d.get("title")
                    location = (d.get("location") or {}).get("name", "")
            if company or role:
                return {"company": company, "role": role,
                        "location": location or ""}
        elif host.endswith("lever.co") and parts and uuid:
            d = _json(f"https://api.lever.co/v0/postings/{parts[0]}/{uuid}")
            if d:
                return {"company": None, "role": d.get("text"),
                        "location": (d.get("categories") or {}).get("location", "")}
        elif host.endswith("ashbyhq.com") and parts and uuid:
            d = _json(f"https://api.ashbyhq.com/posting-api/job-board/{parts[0]}")
            for j in (d or {}).get("jobs", []):
                if j.get("id") == uuid:
                    return {"company": None, "role": j.get("title"),
                            "location": j.get("location", "")}
        elif host.endswith("smartrecruiters.com") and parts:
            cid = None
            if "company" in parts:
                i = parts.index("company")
                cid = parts[i + 1] if i + 1 < len(parts) else None
            cid = cid or q.get("dcr_ci", [None])[0] or parts[0]
            pid = uuid or next((s for s in reversed(parts) if s.isdigit()), None)
            if cid and pid:
                d = _json(f"https://api.smartrecruiters.com/v1/companies/{cid}"
                          f"/postings/{pid}")
                if d:
                    loc = d.get("location") or {}
                    loc_s = ", ".join(x for x in (loc.get("city"),
                                                  loc.get("region")) if x)
                    return {"company": (d.get("company") or {}).get("name"),
                            "role": d.get("name"), "location": loc_s}
    except requests.exceptions.RequestException:
        pass
    return None


def _clean_company(c):
    """Trim careers-site decorations: "BHE Career Site" -> "BHE"."""
    c = (c or "").strip()
    for suf in (" Career Site", " Careers Site", " Careers", " Career",
                " Jobs", " Talent Network", " Talent"):
        if c.endswith(suf):
            c = c[: -len(suf)].strip()
    return c or "Unknown"


def _parse_job_from_url(url):
    """Best-effort (company, role, location) from a job posting URL.

    Role/location come from the ATS API when the link is Greenhouse/Lever/Ashby;
    otherwise from og:title. Company is resolved from the cleanest signal in
    turn: a Greenhouse board's og:title, og:site_name, the employer named in the
    title, the URL slug, then the domain. Always returns something so an applied
    link is never dropped, even if the page can't be fetched.
    """
    host = urllib.parse.urlparse(url).hostname or ""
    og_title = og_site = title_tag = None
    try:
        r = requests.get(
            url, headers={"User-Agent":
                          "internship-watcher/1.0 (+notion applied sync)"},
            timeout=20)
        if r.status_code == 200:
            og_title = _meta(r.text, "og:title")
            og_site = _meta(r.text, "og:site_name")
            m = re.search(r"<title[^>]*>(.*?)</title>", r.text,
                          re.IGNORECASE | re.DOTALL)
            title_tag = html.unescape(m.group(1)).strip() if m else None
    except requests.exceptions.RequestException:
        pass

    api = _ats_api(url)

    # company: most reliable signal first
    company = api.get("company") if api else None
    if not company and og_site and len(og_site) <= 60 \
            and og_site.lower() not in _SITE_SUFFIXES:
        company = og_site
    company = _clean_company(
        company or _company_from_title(og_title or title_tag or "")
        or _company_from_url(url) or "Unknown")

    # role + location: exact via ATS API, else the page title
    role = location = None
    if api:
        role, location = api["role"], api["location"]
    if not role:
        cand = _strip_site_suffix(og_title or title_tag or "")
        cand = _strip_trailing_company(cand, company).strip(" |-—–·")
        low = cand.lower()
        junk = {"", "careers", "jobs", company.lower(),
                f"{company.lower()} careers", f"{company.lower()} jobs"}
        if low.rstrip(".") not in {j.rstrip(".") for j in junk}:
            role = cand
    role = role or "Applied position"
    location = (location or "").strip().strip(",").strip()
    return company.strip()[:200], role.strip()[:200], location[:200]


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


# ---------------------------------------------------- dead-posting sweep

def _config_boards():
    """company name (lowercased) -> (ats, board slug) from config.json, so
    custom-domain Greenhouse links ("careers.datadoghq.com/...?gh_jid=N")
    can still be liveness-checked via the board API."""
    try:
        cfg = json.loads((ROOT / "config.json").read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return {c["name"].lower(): (c["ats"], c["board"])
            for c in cfg.get("companies", [])}


def _posting_open(url, company=None, boards=None):
    """True if the ATS still lists the posting, False if it's gone, None
    when the host can't be checked reliably (aggregator links, custom
    career sites). Network errors are None — never mark a row Closed on
    a hiccup."""
    p = urllib.parse.urlparse(url)
    host = p.hostname or ""
    parts = [s for s in p.path.split("/") if s]
    uuid = next((s for s in parts if _UUID_RE.fullmatch(s)), None)
    q = urllib.parse.parse_qs(p.query)
    try:
        jid = q.get("gh_jid", [None])[0]
        board = None
        if host.endswith("greenhouse.io") and parts:
            board = parts[0]
            if not jid and "jobs" in parts:
                i = parts.index("jobs")
                jid = parts[i + 1] if i + 1 < len(parts) else None
        elif jid and company:  # greenhouse job on a custom career domain
            ats, slug = (boards or {}).get(company.lower(), (None, None))
            if ats == "greenhouse":
                board = slug
        if board and jid:
            r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/"
                             f"{board}/jobs/{jid}", timeout=15)
            return {200: True, 404: False}.get(r.status_code)
        if host.endswith("lever.co") and parts and uuid:
            r = requests.get(f"https://api.lever.co/v0/postings/{parts[0]}"
                             f"/{uuid}", timeout=15)
            return {200: True, 404: False}.get(r.status_code)
        if host.endswith("ashbyhq.com") and parts and uuid:
            d = _json(f"https://api.ashbyhq.com/posting-api/job-board/{parts[0]}")
            if d is None:
                return None
            return any(j.get("id") == uuid for j in d.get("jobs", []))
    except requests.exceptions.RequestException:
        pass
    return None


def _sweep_dead_postings(state):
    """Once a day, flip tracker rows still at Saved whose posting has
    disappeared from its ATS to Closed — so nobody drafts an application
    for a dead link. Applied+ rows are left alone (postings closing after
    you applied is normal). Returns True if state changed."""
    now = time.time()
    if now - state.get("dead_sweep_ts", 0) < DEAD_SWEEP_INTERVAL:
        return False
    state["dead_sweep_ts"] = now

    boards = _config_boards()
    closed = 0
    for u in state.get("users", {}).values():
        db = u.get("db")
        if not db:
            continue
        cursor = None
        while True:
            payload = {"filter": {"property": "Status",
                                  "select": {"equals": "Saved"}}}
            if cursor:
                payload["start_cursor"] = cursor
            res = _notion("POST", f"/databases/{db}/query", payload)
            if not res:
                break
            for page in res.get("results", []):
                props = page.get("properties", {})
                link = (props.get("Link") or {}).get("url")
                comp = "".join(t.get("plain_text", "") for t in
                               (props.get("Company") or {}).get("rich_text", []))
                if link and _posting_open(link, comp, boards) is False:
                    if _notion("PATCH", f"/pages/{page['id']}",
                               {"properties": {"Status":
                                               {"select": {"name": "Closed"}}}}):
                        closed += 1
            cursor = res.get("next_cursor")
            if not res.get("has_more"):
                break
    if closed:
        print(f"Notion: marked {closed} vanished posting(s) Closed.")
    return True  # dead_sweep_ts advanced


# ----------------------------------------------------------- stats callout

# Statuses that mean an application was actually sent (the "applied" total).
APPLIED_STATUSES = ("Applied", "OA", "Interview", "Offer", "Rejected")


def _status_counts(db_id):
    """Tally of Status values across a tracker DB, or None if the query
    failed (never zero the stats over a network blip)."""
    counts = {}
    cursor = None
    while True:
        payload = {"start_cursor": cursor} if cursor else {}
        res = _notion("POST", f"/databases/{db_id}/query", payload)
        if not res:
            return None
        for page in res.get("results", []):
            sel = (page.get("properties", {}).get("Status") or {}).get("select")
            if sel:
                counts[sel["name"]] = counts.get(sel["name"], 0) + 1
        cursor = res.get("next_cursor")
        if not res.get("has_more"):
            return counts


def _stats_text(state):
    lines = []
    for u in state.get("users", {}).values():
        if not u.get("db"):
            continue
        counts = _status_counts(u["db"])
        if counts is None:
            continue
        total = sum(counts.get(s, 0) for s in APPLIED_STATUSES)
        pipeline = " · ".join(f"{s} {counts.get(s, 0)}"
                              for s in APPLIED_STATUSES)
        lines.append(f"{u['name']}: {total} applied — {pipeline}"
                     f" — Saved {counts.get('Saved', 0)}")
    return "\n".join(lines)


def _update_stats(state):
    """Keep a 📊 callout on the parent page counting how many places each
    member has applied to. Members flip Status by hand in Notion between
    runs, so this re-queries the tracker DBs instead of trusting local
    state. Returns True if state changed."""
    text = _stats_text(state)
    if not text:
        return False
    stamp = datetime.now(timezone.utc).strftime("%b %d, %H:%M UTC")
    rich = [{"type": "text",
             "text": {"content": f"{text}\nupdated {stamp}"}}]
    block_id = state.get("stats_block")
    if block_id:
        if _notion("PATCH", f"/blocks/{block_id}",
                   {"callout": {"rich_text": rich}}):
            return False
        b = _notion("GET", f"/blocks/{block_id}")
        if b and not b.get("archived"):
            return False  # update hiccuped but the block exists; retry next run
    # First run, or the callout was deleted in Notion — (re)create it. The
    # API can only append to the bottom of the page; drag it to the top
    # once and every later run edits it in place.
    res = _notion("PATCH",
                  f"/blocks/{os.environ['NOTION_PARENT_PAGE_ID']}/children",
                  {"children": [{"object": "block", "type": "callout",
                                 "callout": {"rich_text": rich,
                                             "icon": {"type": "emoji",
                                                      "emoji": "📊"}}}]})
    if res and res.get("results"):
        state["stats_block"] = res["results"][0]["id"]
        print("Notion: created 📊 stats callout on the hub page.")
        return True
    return False


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
        for mid in _pinned_message_ids(bot_token, msg_map):
            rec = msg_map[mid]
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

    # 4) daily: mark Saved rows whose posting vanished as Closed
    if _sweep_dead_postings(state):
        dirty = True

    # 5) refresh the 📊 applied-count callout on the hub page
    if _update_stats(state):
        dirty = True

    if dirty:
        STATE_PATH.write_text(json.dumps(state, indent=1))
