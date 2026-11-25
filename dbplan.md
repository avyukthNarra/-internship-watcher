# Plan: Supabase database, user accounts and website

Status: **plan, not built.** Updated 2026-11-25 on branch `avy-dev`.

## Goal

Turn the watcher from a Discord bot with JSON files into a pipeline plus a website:

- **The pipeline** (GitHub Actions, every 10 minutes) scrapes boards, as it does today, and writes jobs into Supabase.
- **Users sign in** on the website and get:
  - a job feed;
  - their own tracker: which jobs they saved or applied to, and **when they applied**;
  - their own **top-company list**, which defaults to the list in this repo;
  - alert preferences, by Discord DM or email.
- The **Discord bot keeps working**. Its 📌 pins and applied-channel links write into the same per-user tracker.

## Accounts: what to use for login

**Recommendation: Supabase Auth with "Sign in with Discord" as the main button and "Sign in with Google" as the second one.** No passwords.

- **Discord login gives us the user's Discord ID.** That's what DMs, 📌 pin tracking and the applied channel all key on. Today `config.json` `profiles` and `notion_state.json` `users` are already keyed by Discord user ID.
- **Google login** covers people who don't use Discord. They get email alerts and can link Discord later.
- **Supabase identity linking** joins both logins into one account, so the same email or a manual "Connect Discord" button doesn't create duplicates.
- **Built into Supabase:** auth is part of the database, so row-level security can say "a user can only see their own rows" with `auth.uid()`, with no separate auth service to keep in sync. The free plan includes 50k monthly active users.

Is Google auth alone a good idea? It's fine for logging in, but it doesn't tell us who someone is on Discord. Discord-first fits this product better.

| Alternative | Verdict |
|---|---|
| Clerk | Polished prebuilt UI, but a second vendor, and RLS needs extra JWT wiring |
| Auth.js (NextAuth) | Free and flexible, but we run sessions ourselves and wire RLS by hand |
| Firebase Auth | Good, but it's a different ecosystem from our Postgres |
| Email and password | More support burden (resets, leaks) and no benefit here |
| Magic link email | Fine as an optional third option later |

## Architecture

```
GitHub Actions watcher (Python, every 10 min)
   ├─ upserts jobs ─────────────────────┐
   ├─ reads users' prefs + top lists    │
   ├─ sends channel posts / DMs / email ▼
   │                               Supabase (Postgres + Auth + REST)
   │                                    ▲            ▲
Discord bot (📌 pins, #applied)  ───────┘            │
                                                     │
Website: Next.js on Vercel  ──── supabase-js ────────┘
   (jobs feed, login, my tracker, settings)
```

- **The pipeline** connects with a server-only key (the database URL or service role), stored in the GitHub `production` environment. That key bypasses row-level security.
- **The website** uses the public anon key plus the signed-in user's session. Row-level security decides what each user can read or write.
- **Hosting: Vercel**, the natural home for Next.js. This settles the open question from Sai's step 5.

## Schema

All of this lives in `supabase/migrations/*.sql`, managed with the Supabase CLI.

### Jobs (written by the pipeline, readable by everyone)

```sql
create table jobs (
  id          text primary key,            -- existing watcher id, e.g. 'greenhouse:anthropic:123'
  identity    text not null,               -- job_utils.job_identity, for cross-source dedupe
  company     text not null,
  title       text not null,
  location    text,
  url         text not null,
  terms       text[] not null default '{}',
  source      text not null,               -- greenhouse | lever | ashby | workday | simplify | vanshb03 | jobright
  category    text,
  first_seen  timestamptz not null default now(),
  last_seen   timestamptz not null default now(),
  closed_at   timestamptz                  -- set when the posting disappears
);
create index on jobs (first_seen desc);
create index on jobs (identity);
create index on jobs (lower(company));
```

### Default top companies (from the repo)

```sql
create table default_top_companies (
  name text primary key                    -- synced from config.json "companies" + simplify.company_keywords
);
```

The pipeline syncs this table from `config.json` on every run, so editing the repo still sets the default for everyone.

### Users

```sql
create table profiles (
  user_id          uuid primary key references auth.users on delete cascade,
  display_name     text,
  discord_user_id  text unique,             -- filled from the Discord identity
  email            text,
  notify_dm        boolean not null default false,
  notify_email     boolean not null default false,
  created_at       timestamptz not null default now()
);

create table user_preferences (            -- same fields job_utils.preference_matches already understands
  user_id            uuid primary key references profiles on delete cascade,
  roles              text[] not null default '{}',
  locations          text[] not null default '{}',
  terms              text[] not null default '{}',
  exclude_roles      text[] not null default '{}',
  categories         text[] not null default '{}',
  keep_unknown_terms boolean not null default true,
  only_top_companies boolean not null default true,   -- alert only on the user's top list
  follow_up_days     int not null default 14
);
```

### Each user's top-company list (defaults to the repo's)

Store each user's **changes to the default** rather than a full copy, so new companies added to the repo reach everyone who hasn't removed them:

```sql
create table user_top_company_overrides (
  user_id  uuid references profiles on delete cascade,
  company  text not null,
  action   text not null check (action in ('add', 'remove')),
  primary key (user_id, company)
);

create view user_top_companies as          -- effective list = default + adds - removes
  select p.user_id, d.name as company
    from profiles p cross join default_top_companies d
   where not exists (select 1 from user_top_company_overrides o
                      where o.user_id = p.user_id and o.company = d.name and o.action = 'remove')
  union
  select user_id, company from user_top_company_overrides where action = 'add';
```

"Reset to default" just deletes that user's override rows.

### Each user's job tracker (saved, applied, and when)

One table holds everyone's rows. Row-level security makes each user see only their own, which behaves like a private table per user without creating thousands of tables.

```sql
create type application_status as enum
  ('saved', 'applied', 'interviewing', 'offer', 'rejected', 'withdrawn');

create table user_jobs (
  user_id       uuid references profiles on delete cascade,
  job_id        text references jobs on delete restrict,
  status        application_status not null default 'saved',
  saved_at      timestamptz not null default now(),
  applied_at    timestamptz,                 -- the time they applied
  follow_up_on  date,                        -- applied_at + follow_up_days, editable
  notes         text,
  source        text not null default 'web', -- web | discord_pin | discord_applied | import
  updated_at    timestamptz not null default now(),
  primary key (user_id, job_id)
);

create table user_job_events (             -- full history: every status change with its time
  id         bigint generated always as identity primary key,
  user_id    uuid not null,
  job_id     text not null,
  status     application_status not null,
  at         timestamptz not null default now()
);
-- trigger on user_jobs insert/update: append an event; set applied_at = now() the first time status becomes 'applied'.
```

### Alerts and bot state

```sql
create table notifications (               -- per-user alert ledger (dedupe + retries)
  user_id   uuid references profiles on delete cascade,
  job_id    text references jobs,
  channel   text check (channel in ('dm', 'email')),
  status    text not null default 'pending' check (status in ('pending', 'sent', 'dead')),
  attempts  int not null default 0,
  error     text,
  sent_at   timestamptz,
  primary key (user_id, job_id, channel)
);
```

The watcher's internal state also moves into Supabase as JSON documents: the delivery ledger, health, the Discord message map and the Notion state. They go into `state_docs` / `state_parts`, exactly as in the earlier quick-move design.
- `job_utils.load_json` / `save_json` route the five state files there when `STATE_DATABASE_URL` is set.
- Only the changed top-level keys are written.
- A flood guard refuses to run if the history is missing.

This lets the bot move with no logic changes, and those documents can become real tables later.

### Row-level security

| Table | Anonymous visitors | Signed-in user | Pipeline (service key) |
|---|---|---|---|
| `jobs`, `default_top_companies` | read | read | write |
| `profiles`, `user_preferences`, `user_top_company_overrides`, `user_jobs`, `user_job_events` | none | own rows: read and write | read and write |
| `notifications`, `state_docs`, `state_parts` | none | none | read and write |

A trigger on `auth.users` insert creates the `profiles` and `user_preferences` rows and copies the Discord ID from the identity data.

## Pipeline changes (watcher)

Each run:
1. **Sync** `default_top_companies` from `config.json`.
2. **Fetch boards** (unchanged) and **upsert `jobs`**: set `last_seen`, never overwrite `first_seen`, and set `closed_at` on postings that are gone.
3. **Post to the global channels** exactly as today (`watcher.deliver`, via the state documents).
4. **Per-user alerts.** Load every user's preferences and effective top list in one query, run `job_utils.preference_matches(job, prefs)` (reused unchanged) on each new job plus an optional top-list check, then insert `notifications` rows.
5. **Send** with a per-run budget and a per-user cap. DMs use the bot token: `POST /users/@me/channels`, then `POST /channels/{id}/messages`. Error 50007 means DMs are closed, so the alert is marked dead with no retry. Email uses the existing SMTP code.
6. **Bridge Discord into the tracker.** For 📌 reactions and `#applied` links, look up `profiles.discord_user_id` and upsert `user_jobs` (`saved`, or `applied` with `applied_at`). This replaces the per-user part of Notion sync, and Notion becomes optional and legacy.

**New code**
- `state_db.py`: bot state documents.
- `db.py`: connection and upsert helpers using `psycopg` 3 and the Supabase pooler URL.
- `user_alerts.py`: preference matching and the notifications queue.

**Edited**
- `watcher.py`: jobs upsert, alerts and the bridge.
- `notion_sync.py`: write to `user_jobs`.
- `job_utils.py`: state routing.
- `watch.yml`: secrets; drop the private-repo state steps.

## Website (Next.js on Vercel)

| Page | What it does |
|---|---|
| `/` | Job feed: search, filters (term, location, source), "Top companies only" toggle using the user's list (or the default when logged out), new-today badge, plus **Save** and **Mark applied** buttons |
| `/login` | Discord (main) and Google buttons |
| `/tracker` | The user's table of saved and applied jobs, sortable, with inline status edits, applied time, follow-up date, notes and CSV export |
| `/settings` | Alert preferences, the top-company editor (search to add, remove, "reset to default", default entries marked), notification toggles, connect Discord or Google |

- **Stack:** Next.js App Router, `@supabase/ssr`, Tailwind.
- **Reuse:** the current `web/` (`app.js` filters and the `site_export` field set) as the starting point.

## Build order

1. **Supabase setup:** create the project, enable the Discord and Google providers, write the migrations and RLS, and add the secrets (pooler `DATABASE_URL`, service key) to the `production` environment.
2. **Bot state to the database:** add `state_db.py`, import from the private state repo, and cut over. Watch a few runs for green and `0 new`.
3. **Jobs table:** the pipeline upserts jobs. Backfill from the current `known_ids` and pending entries where the details exist; the feed fills naturally within about 45 days.
4. **Website MVP:** feed, login, tracker and settings, deployed to Vercel.
5. **Per-user alerts:** DMs and email from preferences and the top list.
6. **Discord bridge and import:** 📌 pins and `#applied` write to `user_jobs`. Import existing Notion history (`notion_state.json` users, plus "Applied On" dates from Notion pages) as `source = 'import'`.
7. **Hardening:**
   - a nightly `pg_dump` to the private state repo (the free plan has no point-in-time restore);
   - retention (close and archive old jobs; prune `notifications`);
   - rate limits on alerts;
   - a privacy page and account deletion (the cascade deletes are already in the schema).

**Rough effort:** steps 1–3 take 2–3 days, step 4 about a week, and steps 5–6 2–3 days.

## Costs and limits

- **Supabase free:** 500 MB database, 50k monthly active users, pauses after 7 idle days (the pipeline keeps it active), and no point-in-time restore. Pro is $25/month when needed.
- **Vercel Hobby:** free for personal and non-commercial use. A commercial launch needs Pro.
- **Discord DMs:** only reach users who share a server with the bot and allow DMs. Mass unsolicited DMs get flagged. The bot needs verification at 75+ servers.

## Verification

- **Migrations:** apply cleanly to a local Supabase (`supabase start`).
- **RLS:** tests with two users confirm that A can't read or write B's `user_jobs`.
- **Pipeline:** a run against a staging project upserts jobs, keeps `first_seen` stable across runs, and a test user with a narrow filter gets exactly the matching DM.
- **Top list:** a new user sees the default list. Adding a company to `config.json` shows it for them on the next run, but not for a user who removed it.
- **Tracker:** "Mark applied" sets `applied_at` once and logs an event. A 📌 in Discord creates a `saved` row for the linked account.
- **Production cutover:** three green runs, no flood, and the state repo stops receiving watcher commits.

## Decisions needed

- Discord-first login (recommended), or equal Discord and Google buttons?
- Should alerts default to top companies only (recommended), or to everything matching the user's filters?
- Will the site be public, or limited to an allowlist or Discord server members at first?
