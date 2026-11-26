"""Read and write the pipeline's compact health summary."""
import os

import psycopg
from psycopg.types.json import Jsonb


def _connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(url, prepare_threshold=None, connect_timeout=20)


def load_health():
    """Fetch the single health value document, or an empty initial state."""
    with _connect() as conn:
        row = conn.execute(
            "select value from public.state_docs where name = 'health.json' and kind = 'value'"
        ).fetchone()
    return row[0] if row else {}


def save_health(value):
    """Replace the single health value document in one transaction."""
    with _connect() as conn:
        conn.execute(
            """insert into public.state_docs (name, kind, value)
               values ('health.json', 'value', %s)
               on conflict (name) do update set kind = 'value', value = excluded.value,
                   updated_at = now()""",
            (Jsonb(value),),
        )
