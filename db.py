"""Database writes for jobs and the repository's default company list."""
import os
from datetime import datetime, timezone

import psycopg

from job_utils import job_identity


def connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(url, prepare_threshold=None, connect_timeout=20)


def _timestamp(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return value


def sync_default_top_companies(cfg):
    names = [company["name"] for company in cfg.get("companies", [])]
    names.extend(cfg.get("simplify", {}).get("company_keywords", []))
    names = list(dict.fromkeys(name for name in names if isinstance(name, str) and name))
    with connect() as conn:
        conn.execute("delete from public.default_top_companies")
        if names:
            conn.cursor().executemany(
                "insert into public.default_top_companies (name) values (%s)",
                [(name,) for name in names],
            )


def upsert_jobs(jobs, now):
    now = _timestamp(now)
    rows = []
    for job in jobs:
        job_id = job["id"]
        rows.append((
            job_id,
            job_identity(job),
            job.get("company") or "",
            job.get("title") or "",
            job.get("location") or "",
            job.get("url") or "",
            list(job.get("terms") or []),
            job.get("source") or job_id.split(":", 1)[0],
            job.get("category"),
            now,
        ))
    if not rows:
        return
    with connect() as conn:
        conn.cursor().executemany(
            """insert into public.jobs
               (id, identity, company, title, location, url, terms, source, category,
                first_seen, last_seen)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               on conflict (id) do update set
                 identity = excluded.identity,
                 company = excluded.company,
                 title = excluded.title,
                 location = excluded.location,
                 url = excluded.url,
                 terms = excluded.terms,
                 source = excluded.source,
                 category = excluded.category,
                 last_seen = excluded.last_seen,
                 closed_at = null""",
            [(*row[:9], row[9], row[9]) for row in rows],
        )


def close_missing_jobs(board_sources_ok, seen_ids, now):
    """Close jobs missing from successful direct ATS board snapshots only.

    `board_sources_ok` contains `ats:board` keys, matching the prefix of watcher
    job IDs. Aggregate feeds are never passed here.
    """
    now = _timestamp(now)
    seen_ids = list(seen_ids)
    with connect() as conn:
        for source in sorted(set(board_sources_ok)):
            prefix = f"{source}:"
            conn.execute(
                """update public.jobs set closed_at = %s
                   where left(id, %s) = %s and closed_at is null
                     and not (id = any(%s))""",
                (now, len(prefix), prefix, seen_ids),
            )
