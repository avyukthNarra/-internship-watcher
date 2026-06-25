#!/usr/bin/env python3
"""
Notion sync for the internship watcher.

Two jobs:
1. Master log — every new posting the watcher finds is appended to one
   shared Notion database ("All Internship Postings").
2. Personal trackers — members of the Discord server 📌-react to a job
   message; this module polls those reactions (Discord bot token, REST
   only) and files the job into that member's own Notion database,
   created automatically under the same parent page on first reaction.
   Members then manage Status (Saved/Applied/OA/Interview/Offer/Rejected)
   themselves in Notion.

Env: NOTION_TOKEN, NOTION_PARENT_PAGE_ID, DISCORD_BOT_TOKEN (optional —
without it only the master log is synced).

State: notion_state.json (database ids, which jobs are already filed
per user), message_map.json (written by watcher.py: message id -> job).
"""

import json
import os
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
    """Users who 📌-reacted to a message (REST only, no gateway needed)."""
    try:
        r = requests.get(
            f"{DISCORD_API}/channels/{channel_id}/messages/{message_id}"
            f"/reactions/{PIN_EMOJI}?limit=100",
            headers={"Authorization": f"Bot {bot_token}"}, timeout=30)
    except requests.exceptions.RequestException as e:
        # A Discord hiccup on one message shouldn't abort the whole sync.
        print(f"  [warn] discord reactions -> {type(e).__name__}; skipping")
        return []
    if r.status_code != 200:
        if r.status_code != 404:  # 404 = message deleted, not noteworthy
            print(f"  [warn] discord reactions -> HTTP {r.status_code}")
        return []
    return [u for u in r.json() if not u.get("bot")]


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

    if dirty:
        STATE_PATH.write_text(json.dumps(state, indent=1))
