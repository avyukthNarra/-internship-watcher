# Plan: move the watcher's state into a database

Status: **plan only, nothing built yet.** Written 2026-11-25 on branch `avy-dev`.

## Why

The watcher runs every 10 minutes from GitHub Actions. Each run does three things:

1. checks out the private repo `avyukthNarra/internship-watcher-state`;
2. loads five JSON files from it;
3. commits the files back, together with a full `snapshot/` copy.

| File | Size | What it holds |
|---|---|---|
| `delivery_state.json` | 2.5 MB | the delivery ledger (see below) |
| `seen.json` | 1.0 MB | sorted list of every job ID ever seen |
| `message_map.json` | 121 KB | `{discord_message_id: {cid, ts, job}}`, pruned to 3 days |
| `health.json` | 27 KB | per-source health, rebuilt every run |
| `notion_state.json` | 10 KB | Notion database and page IDs per Discord user, retry queues, cursors |

The ledger (`delivery_state.json`) holds:
- `known_ids`, a copy of seen;
- `seeded_sources`;
- `identities`;
- `fingerprints`, which expire after `dedup_days`;
- `pending`, `{job_id: {job, destinations[], tries, attempts, error}}`;
- `dead`.

### Problems with this

- **Churn.** The private repo got 105 commits on its first day. At that rate it gets about 50k commits a year, each rewriting roughly 7 MB of JSON.
- **Push races.** Persisting means `pull --rebase` and push, with 3 retries. A real conflict fails the run.
- **Unbounded growth.** These are never pruned:
  - `seen.json`
  - `known_ids`, `identities` and `dead` in the ledger
  - Notion `users.jobs`
- **`jobs.json` is never kept.** It is gitignored and not persisted, so `first_seen` resets every run, and the website still reads `web/sample-jobs.json`.
- **The website needs a backend.** `sai_docs/04-todo.md` plans Discord login and per-user saved/applied jobs, and a static Vercel or Netlify site can't store that.

## How state is accessed today (what we'd change)

There is no storage layer. Everything goes through two helpers in `job_utils.py`:
- `load_json(path, default)` returns `default` if the file is missing and raises on corrupt JSON;
- `save_json(path, data)` does an atomic temp-file write and rename.

Call sites on `main`:
- **save:** `watcher.py:635, 746, 797, 800, 803, 828`, `notion_sync.py:517`
- **load:** `watcher.py:767, 769, 770, 801`, `notion_sync.py:511, 686`
- **Not state:** `config.json`, `legacy_board_sources.json`, and `jobs.json` also go through these helpers, but they aren't state files.

`watcher.main` calls `checkpoint()` after every delivery attempt, which re-saves the ledger. `notion_sync._save` runs many times per run.

Tests point the path constants at temp directories:
- `test_watcher.py:149` patches `ROOT`, `SEEN_PATH` and `MSG_MAP_PATH`;
- `test_notion_sync.py:20` patches `STATE_PATH`;
- `test_pipeline.py:14` patches `ROOT`.

## Chosen approach: Supabase Postgres, quick cutover

Keep the bot logic unchanged and swap only where the five files live.

### Why Supabase
- **Free tier:** 500 MB database, 2 projects, no compute-hour cap. Our state is about 4 MB.
- **Pausing isn't a risk:** free projects pause after about 1 week of inactivity, and a watcher running every 10 minutes never gets close.
- **Later, for the website:**
  - a REST API (PostgREST) with row-level security, so a static site can read a public jobs view;
  - Discord OAuth in Supabase Auth, which covers Sai's per-user features.

### Design

**New module `state_db.py`, about 150 lines.**
- It is used only when the `STATE_DATABASE_URL` environment variable is set.
- `job_utils.load_json` and `save_json` check `state_db.handles(path)`. If the file name is one of the five state files and the URL is set, the call goes to Postgres; otherwise it uses the file as today.
- So tests, laptop dry runs and `config.json` are unaffected, and `watcher.py` and `notion_sync.py` don't change.

**Schema** (created automatically on first connect):
```sql
CREATE TABLE state_docs (
    name       text PRIMARY KEY,          -- e.g. 'delivery_state.json'
    kind       text NOT NULL CHECK (kind IN ('dict', 'value')),
    value      jsonb,                      -- whole value when kind = 'value' (seen.json is a list)
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE state_parts (
    name       text NOT NULL REFERENCES state_docs (name) ON DELETE CASCADE,
    key        text NOT NULL,              -- top-level key, e.g. 'pending', 'known_ids'
    value      jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (name, key)
);
```

**Writes only touch what changed.**
- A dict document is stored one row per top-level key.
- The module remembers a sha256 of each key's value from the last load or save, and a save upserts only the keys whose hash changed. A delivery checkpoint rewrites `pending` (small), not the 1 MB `known_ids`.
- Each save runs in one transaction.

**Flood guard.**
- If `seen.json` or `delivery_state.json` is missing from the database, `load` raises and the run stops. Otherwise an empty history would make every live posting look new.
- A connection error also stops the run, and the next cron retries. It never falls back to empty state.

**Connection.**
- `psycopg` 3 (`psycopg[binary]==3.3.9`), with `prepare_threshold=None` and `connect_timeout=20`.
- Use the Supabase **pooler** connection string. The direct connection is IPv6-only, and GitHub runners can't reach it.

**CLI.**
- `python3 state_db.py import --from DIR` loads the five JSON files into the database.
- `python3 state_db.py export --to DIR` writes them back out, for backups and restores.

### Steps

1. **Avy:** create a free Supabase project and copy the Session or Transaction pooler connection string. Claude asks for it on a masked Pane secret card, so it never appears in chat.
2. **Code (on `avy-dev`):**
   - Add `state_db.py`.
   - Add the hook in `job_utils.load_json` / `save_json`.
   - Add `psycopg[binary]` to `requirements.txt`.
   - Add `tests/test_state_db.py`, which runs against Postgres when `STATE_DB_TEST_URL` is set: round trip, changed-keys-only writes, the flood guard, and import/export.
   - Add a `postgres` service container to `test.yml` so CI runs those tests.
   - Test locally against Homebrew Postgres, which is already installed.
3. **Workflow:**
   - In `watch.yml`, add `STATE_DATABASE_URL: ${{ secrets.STATE_DATABASE_URL }}` to the run env.
   - Remove the "Load private state", "Copy private state", "Capture recovery snapshot" and "Persist private state" steps.
   - `permissions` stays `contents: read`.
   - Keep `concurrency: watcher` so there is only ever one writer.
4. **Backups:**
   - Add a new `state-backup.yml` that runs daily and on demand.
   - It runs `state_db.py export`, then `state_snapshot.py create`, then commits to the private state repo using the existing `STATE_DEPLOY_KEY`.
   - This keeps the restore steps in `sai_docs/07-recovery-snapshot.md` working. It's needed because the free plan has no point-in-time restore.
5. **Cutover:**
   1. Disable `watch.yml`.
   2. Clone the private state repo at its latest commit and run `state_db.py import --from <clone>`.
   3. Add `STATE_DATABASE_URL` as a secret in the `production` environment.
   4. Merge the PR (CODEOWNERS review applies, since `.github/` changes).
   5. Re-enable the watcher and trigger a run.
6. **Verify over a few runs (about 30 minutes):**
   - Runs are green and report `0 new` (no flood).
   - `state_docs` / `state_parts` show fresh `updated_at` values.
   - The private state repo stops getting commits from `watch.yml`.
   - The next real posting reaches Discord, and Notion sync reports OK.
   - The backup workflow runs once and commits an export.

**Rollback:**
- Remove the secret and revert the `watch.yml` change.
- To carry state back, run `state_db.py export --to <state clone>` and commit before switching back.

**Effort:** about 1 hour of code once the connection string exists, plus about 30 minutes of watching runs.

### Pros
- No more push races or commit churn.
- Saves are transactional: a crash can't half-write state.
- A small change: one new module and a two-line hook, and bot logic is untouched.
- Tests keep using files.
- Sets up the website (live data, auth) on the same database later.

### Cons and risks
- **New external dependency:** if Supabase is down, that run fails and the next cron retries.
- **Free-plan limits:** no point-in-time restore (covered by the daily export), and Pro costs $25/month if the website grows.
- **Not truly relational yet:** the data is stored as JSON documents. Per-user website features will want real tables (see Later).
- **Import risk:** a bad import could flood Discord. This is mitigated by the flood guard, disabling the watcher during import, and checking that the first run reports `0 new`.

## Later (not in this change)

- **Real tables:** `jobs`, `deliveries`, `discord_messages`, `source_health`, `runs`, plus Notion tables. These replace the JSON documents, with retention rules for old jobs and dead deliveries.
- **Persist `jobs.json`:** route it through `state_db` too (one more name in `STATE_FILES`) so `first_seen` survives, or expose it as a `public_jobs` view for the site.
- **Website reads:** point `web/jobs.js` `DATA_URL` at the Supabase REST endpoint, with a read-only RLS policy.
- **Per-user features:** Supabase Auth with Discord as the provider, for saved and applied jobs.

## Alternatives considered

| Option | Pros | Cons | Pick it when |
|---|---|---|---|
| **Stay on JSON in git, add pruning and persist `jobs.json`** | No new service, free, small change | Push races and churn stay; no backend for the site | The website stays a static list |
| **SQLite file** in the private repo or R2 | SQL and transactions, no vendor | A binary file in git bloats worse than JSON; R2 needs locking; the site can't query it | You want SQL but no vendor |
| **Turso** (hosted SQLite): about 5 GB, 500M reads and 10M writes a month free | SQLite semantics, generous free tier | Turso is joining Supabase, so its roadmap is unclear; no built-in auth or REST | You prefer SQLite and will build an API |
| **Cloudflare D1:** 5 GB, 5M reads and 100k writes a day free, 500 MB per database | The pinger is already a Worker; pairs with Cloudflare Pages | Python on Actions must use D1's REST API; 100k writes a day is tight (about 700 rows per run) | Everything moves to Cloudflare |
| **Neon** (serverless Postgres): 1 GB and 100 compute-hours a month free | Postgres, branching | A run every 10 minutes keeps compute awake about 60% of the time, roughly 110 compute-hours a month, over the free 100 | Cron goes hourly, or on a paid plan |
| **Firebase / MongoDB Atlas** | JSON-shaped | Poor fit for relational data (jobs ↔ deliveries ↔ users) | Not recommended |

Free-tier numbers change often; check them before committing. Sources:
- [Supabase pricing](https://supabase.com/pricing)
- [Supabase pausing FAQ](https://supabase.com/kb/faqs/platform/free-project-pausing)
- [Neon free plan](https://neon.com/faqs/free-plan-limits-and-quotas)
- [Turso pricing](https://turso.tech/pricing)
- [Cloudflare D1 pricing](https://developers.cloudflare.com/d1/platform/pricing/)

## Open questions for Avy and Sai

- Will the website have per-user features soon? If yes, do the real-tables step right after this change.
- Who owns the Supabase project? Avy's account is assumed. Add Sai as a member if he needs to read data.
- Where will the website be hosted (Vercel, Netlify or Cloudflare Pages)? This decides how the site reads jobs.
