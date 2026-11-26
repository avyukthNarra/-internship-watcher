"""Database writes for discovered jobs and the repository default company list."""
import os
from datetime import datetime, timezone

import psycopg
from psycopg import sql

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
    """Upsert jobs in bounded batches and return IDs inserted this run."""
    now = _timestamp(now)
    rows_by_id = {}
    for job in jobs:
        job_id = job["id"]
        # Configured boards and aggregate feeds can overlap; the last copy is authoritative.
        rows_by_id[job_id] = (
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
            now,
        )
    rows = list(rows_by_id.values())
    if not rows:
        return set()

    batch_size = 1000
    row_placeholders = sql.SQL("({})").format(
        sql.SQL(", ").join(sql.Placeholder() for _ in rows[0])
    )
    statement = sql.SQL("""insert into public.jobs
        (id, identity, company, title, location, url, terms, source, category, first_seen, last_seen)
        values {values}
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
          closed_at = null
        where public.jobs.identity is distinct from excluded.identity
           or public.jobs.company is distinct from excluded.company
           or public.jobs.title is distinct from excluded.title
           or public.jobs.location is distinct from excluded.location
           or public.jobs.url is distinct from excluded.url
           or public.jobs.terms is distinct from excluded.terms
           or public.jobs.source is distinct from excluded.source
           or public.jobs.category is distinct from excluded.category
           or public.jobs.closed_at is not null
           or public.jobs.last_seen <= excluded.last_seen - interval '1 hour'
        returning id, (xmax = 0) as inserted""")
    inserted_ids = set()
    with connect() as conn:
        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            values_sql = sql.SQL(", ").join(row_placeholders for _ in batch)
            query = statement.format(values=values_sql)
            params = [value for row in batch for value in row]
            returned = conn.execute(query, params).fetchall()
            inserted_ids.update(job_id for job_id, inserted in returned if inserted)
    return inserted_ids


def close_missing_jobs(board_sources_ok, seen_ids, now):
    """Close missing jobs for successful direct boards in one SQL statement."""
    sources = sorted(set(board_sources_ok))
    if not sources:
        return
    now = _timestamp(now)
    with connect() as conn:
        conn.execute(
            """with active_sources as (
                   select unnest(%s::text[]) as source
               ), present_jobs as (
                   select unnest(%s::text[]) as id
               )
               update public.jobs as job set closed_at = %s
               from active_sources as active
               where left(job.id, length(active.source) + 1) = active.source || ':'
                 and job.closed_at is null
                 and not exists (select 1 from present_jobs where present_jobs.id = job.id)""",
            (sources, list(seen_ids), now),
        )
