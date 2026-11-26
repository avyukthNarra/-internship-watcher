"""Store the watcher's JSON state documents in Supabase Postgres."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb


STATE_FILES = (
    "seen.json",
    "delivery_state.json",
    "health.json",
    "notion_state.json",
    "message_map.json",
)
FLOOD_GUARD_FILES = {"seen.json", "delivery_state.json"}


def connect():
    """Open a database connection using the pipeline's pooler URL."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(url, prepare_threshold=None, connect_timeout=20)


def handles(path):
    """Whether this path is one of the state files routed to Postgres."""
    return bool(os.environ.get("DATABASE_URL")) and Path(path).name in STATE_FILES


def _hash(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load(name, default=None):
    """Load one document. Required history cannot silently start empty."""
    name = Path(name).name
    if name not in STATE_FILES:
        raise ValueError(f"Unsupported state document: {name}")
    with connect() as conn:
        if name in FLOOD_GUARD_FILES:
            doc = conn.execute(
                "select kind, value from public.state_docs where name = %s", (name,)
            ).fetchone()
            if doc is None:
                raise RuntimeError(f"Required state document {name} is missing from the database")
        else:
            doc = conn.execute(
                "select kind, value from public.state_docs where name = %s", (name,)
            ).fetchone()
        if doc is None:
            return default
        kind, value = doc
        if kind == "value":
            return value
        rows = conn.execute(
            "select key, value from public.state_parts where name = %s", (name,)
        ).fetchall()
    result = {key: part for key, part in rows}
    return result


def save(name, value):
    """Save a whole document atomically, updating only changed object keys."""
    name = Path(name).name
    if name not in STATE_FILES:
        raise ValueError(f"Unsupported state document: {name}")
    if isinstance(value, dict):
        kind = "dict"
        parts = value
        stored_value = None
    else:
        kind = "value"
        parts = None
        stored_value = value

    with connect() as conn:
        conn.execute(
            """insert into public.state_docs (name, kind, value) values (%s, %s, %s)
               on conflict (name) do update set kind = excluded.kind, value = excluded.value,
                   updated_at = now()""",
            (name, kind, Jsonb(stored_value) if kind == "value" else None),
        )
        if kind == "value":
            conn.execute("delete from public.state_parts where name = %s", (name,))
        else:
            current = dict(conn.execute(
                "select key, value from public.state_parts where name = %s", (name,)
            ).fetchall())
            for key, part in parts.items():
                if key not in current or _hash(current[key]) != _hash(part):
                    conn.execute(
                        """insert into public.state_parts (name, key, value) values (%s, %s, %s)
                           on conflict (name, key) do update set value = excluded.value,
                               updated_at = now()""",
                        (name, str(key), Jsonb(part)),
                    )
            removed = set(current) - {str(key) for key in parts}
            if removed:
                conn.execute(
                    "delete from public.state_parts where name = %s and key = any(%s)",
                    (name, list(removed)),
                )


def import_dir(directory):
    """Import the five JSON files from a state export directory."""
    directory = Path(directory)
    values = {}
    for name in STATE_FILES:
        path = directory / name
        if not path.is_file():
            raise FileNotFoundError(path)
        values[name] = json.loads(path.read_text())
    for name, value in values.items():
        save(name, value)


def export_dir(directory):
    """Export all five documents to a JSON directory."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name in STATE_FILES:
        value = load(name, default={})
        (directory / name).write_text(json.dumps(value, indent=1, sort_keys=True) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    imp = commands.add_parser("import", help="import state JSON files")
    imp.add_argument("--from", dest="directory", required=True)
    exp = commands.add_parser("export", help="export state JSON files")
    exp.add_argument("--to", dest="directory", required=True)
    args = parser.parse_args(argv)
    if args.command == "import":
        import_dir(args.directory)
    else:
        export_dir(args.directory)


if __name__ == "__main__":
    main()
