# Internship Job Pipeline

This repository runs `pipeline.py` from GitHub Actions every 10 minutes on a best-effort schedule; GitHub may delay scheduled runs. The pipeline discovers matching jobs and writes them to Supabase project `mkphndqkihjanumsyrli`. Its `DATABASE_URL` is stored as a secret in the GitHub `production` environment.

The Discord bot lives in the separate legacy repository, [`avyukthNarra/internship-watcher-discord`](https://github.com/avyukthNarra/internship-watcher-discord). This repository's pipeline does not send Discord, email, or Notion notifications.

## Pipeline architecture

Each run:

1. Loads `config.json` and calls `watcher.discover()` to fetch and filter configured ATS boards and aggregate feeds.
2. Synchronizes `companies[].name` and `simplify.company_keywords` to `default_top_companies`.
3. Upserts discovered postings into Supabase `jobs`, preserving `first_seen` and identifying newly inserted IDs.
4. Closes jobs missing from direct boards that were fetched successfully and saves a compact source-health summary.

The Python modules have separate responsibilities:

| Module | Responsibility |
| --- | --- |
| `pipeline.py` | Run discovery, database synchronization, and health reporting |
| `db.py` | Upsert jobs, close missing jobs, and sync default top companies |
| `state_db.py` | Store the compact pipeline health summary |
| `watcher.py` | Reusable board/feed discovery and filters; legacy notification code remains for compatibility |
| `job_feeds.py` | Shared board endpoints and feed validation |
| `project_config.py` | Validate configuration and resolve defaults |
| `source_health.py` | Calculate scan health and choose the run's exit status |
| `job_utils.py` | Job identities, preferences, and atomic JSON storage |

The workflow is `.github/workflows/pipeline.yml`. To run it manually, use the Actions tab's workflow dispatch button. For a local run, install dependencies and set `DATABASE_URL` to a development database before running `python pipeline.py`.

The sections below about Discord, Notion, delivery queues, and private JSON state describe the legacy bot's behavior. The active bot and its state live in the legacy repository.

## Notion and Discord workflow

The shared Notion database is **All Internship Postings**. A member reacts 📌 to an individual Discord job post; the bot reads reactions through the Discord REST API and creates or updates that member's tracker. Pin work is durable in `pending_pins`.

To record an application, paste a job URL in the configured applied channel. The parser uses ATS APIs where possible and fetches HTML metadata when it needs to identify the company, role, or location. The URL is preserved. Applied work is durable in `pending_applied`, and the channel cursor is checkpointed before processing advances.

Applied tracker rows have `Status`, `Applied On`, and `Follow-up` properties. The default follow-up interval is 14 days (`follow_up_days`); a profile can override it, and `0` disables the due date. The Notion stats callout includes applied status counts and due follow-ups. Existing tracker rows are scanned by canonical job identity before an upsert, including rows created by the legacy schema. Existing history is retained; no reseed or migration is required. URLs that were already stripped by an older version cannot be repaired automatically.

Personal routing preferences are optional entries in `config.json` under `profiles`, keyed by Discord user ID. A profile may define `roles`, `companies`, `locations`, `terms`, `keep_unknown_terms`, `webhook_env`, and `follow_up_days`. These preferences control that profile's optional notifications and follow-up behavior; they do not gate explicit saved or applied actions.

## Setup

Install dependencies with:

```bash
pip install -r requirements.txt
```

### Discord webhooks

Create one or two Discord webhooks and provide their URLs as repository secrets or local environment variables:

| Variable | Use |
| --- | --- |
| `DISCORD_WEBHOOK_URL` | General notifications |
| `DISCORD_WEBHOOK_URL_TOP` | Optional top-company notifications |

For personal profile webhooks, set the `PERSONAL_WEBHOOKS_JSON` GitHub secret to a JSON object mapping `DISCORD_WEBHOOK_*` environment-variable names to webhook URLs. For example, use a placeholder value such as `{"DISCORD_WEBHOOK_URL_EXAMPLE":"https://discord.com/api/webhooks/REDACTED"}`; never commit a real token. The workflow imports these mappings before running the watcher. A profile's `webhook_env` must start with `DISCORD_WEBHOOK_`. This secret is already exposed by the workflow; adding or changing profiles only requires configuration and the matching secret mapping.

The watcher posts individual messages. `DISCORD_BOT_TOKEN` is separate: it is needed to read 📌 reactions and the applied channel, and the bot uses REST only. Give it View Channels, Read Message History, and Add Reactions. Enable Message Content Intent if using the applied channel. Set `APPLIED_CHANNEL_ID` to that channel's ID.

### Notion

Create an internal integration at [notion.so/my-integrations](https://www.notion.so/my-integrations), share the parent page with it, and set:

| Variable | Use |
| --- | --- |
| `NOTION_TOKEN` | Notion API access |
| `NOTION_PARENT_PAGE_ID` | Parent page for the master log and trackers |

### Email

Email is optional. Set `SMTP_USER`, `SMTP_PASS`, and optionally `ALERT_EMAIL`; `SMTP_HOST` and `SMTP_PORT` can be configured in `config.json` or the environment.

### Dry runs and credentials

With no delivery credentials, or with `python watcher.py --dry-run`, the watcher fetches and previews matching boards and feeds but does not write state or call Discord, email, or Notion. Fetching public boards is the only external activity in this mode. A normal run requires at least one configured delivery destination.

## Configuration

`config.json` contains the `companies` entries plus explicit defaults for `terms`, `keep_unknown_terms`, `dedup_days` (30), `max_discord_per_run` (50), `follow_up_days` (14), and `profiles` (an empty object unless configured). It also contains the SimplifyJobs and Jobright feed settings. Add a board only after verifying its slug with `verify_boards.py`; unsupported or stale slugs can return 404. The configured `exclude_locations` list uses word-boundary matching and keeps locations that clearly contain a US state or USA. Empty or unknown locations are retained.

New or changed company boards are seeded silently on their first successful fetch: their current postings are recorded without Discord, email, or Notion delivery, and later postings can alert normally. A failed fetch is retried; dry runs do not save the seed. Existing boards retain their alert behavior, and aggregate feeds are unchanged.

To find boards you don't track yet, `discover_boards.py` tries likely Greenhouse, Lever, and Ashby slugs for a list of company names (`--names file.txt`) or for the open Y Combinator list of companies that are hiring (`--yc --min-team 10`). It prints boards with matching internship postings for you to review and never edits `config.json`; verify each pick with `verify_boards.py --candidate ATS BOARD` before adding it. A board listed under `[NAME DIFFERS - check]` may belong to a different company with a similar name.

Wayve is fetched directly from its Ashby board. Postman is not configured as a direct board; it is included in the SimplifyJobs company filter and remains eligible for Jobright routing. Postman alerts depend on those feeds publishing matching jobs within the configured age window.

### Alert channels

The shipped config has role channels (`swe`, `data`, `research`, `ml`, `embedded`, `hardware`, `quant`). Embedded and firmware titles go to `embedded` only; other hardware goes to `hardware`; `swe` skips embedded titles. A title that fits two roles (for example "Machine Learning Software Intern") posts in both. They stay inactive until `DISCORD_WEBHOOK_SWE`, `_DATA`, `_RESEARCH`, `_ML`, `_EMBEDDED`, `_HARDWARE`, and `_QUANT` are added to `PERSONAL_WEBHOOKS_JSON`.

To get pings for specific companies, add a shared watchlist entry and have people follow that Discord channel:

```json
{"name": "watchlist", "webhook_env": "DISCORD_WEBHOOK_WATCHLIST", "companies": ["Nvidia", "Jane Street"]}
```

Company names match as whole words in any case, so `Nvidia` also matches "NVIDIA Corp". Add or remove names in `config.json`; matching jobs post as they drop.

`alert_channels` (optional list) posts matching jobs into extra Discord channels, in addition to the normal channel. Each entry has a `name`, a `webhook_env`, and any of `roles`, `exclude_roles`, `companies`, `locations`, `terms`, `categories`, `keep_unknown_terms`; empty or missing lists impose no restriction, but an entry must set at least one of `roles`, `companies`, `locations`, `terms`, `categories` (otherwise it would repeat every job). `exclude_roles` rejects titles containing any listed word. Several entries may share one `webhook_env`; a job that matches more than one still posts there once. People opt in by turning on notifications for the channels they care about, so no per-person setup is needed.

```json
{
  "alert_channels": [
    {"name": "quant", "webhook_env": "DISCORD_WEBHOOK_QUANT",
     "companies": ["Jane Street", "Citadel", "Two Sigma"]},
    {"name": "ml-nyc", "webhook_env": "DISCORD_WEBHOOK_MLNYC",
     "roles": ["machine learning", "ml"], "locations": ["New York"], "terms": ["Summer 2027"]}
  ]
}
```

`simplify.category_exclude` (a map of category to keywords) drops category-only pulls whose title contains an unwanted word, for example `"Hardware": ["materials", "technician"]`, and `simplify.category_roles` does the reverse, keeping only titles that contain one of the listed words. Both apply only to postings pulled because of their category, never to companies you track, and are matched as whole words.

A SimplifyJobs term of `N/A` (and `TBD`, `unknown`, `none`) is treated as an unknown season, so `keep_unknown_terms` decides whether those postings are kept. Previously `N/A` was mistaken for a season that never matched, which silently hid those postings.

Channels (and profiles) can also match on `categories`, the SimplifyJobs category of a posting (for example `Hardware`, `Quant`, `Software`, `AI/ML/Data`, `Product`). Only SimplifyJobs postings carry a category.

`simplify.include_categories` pulls every SimplifyJobs posting in those categories regardless of company, still subject to the title, location, and season filters. Such postings go to the general channel and any matching alert channel, but not the TOP channel unless the company is one you track. The shipped config pulls `Hardware` and `Quant` and defines `hardware` and `quant` alert channels; those channels stay inactive until you add `DISCORD_WEBHOOK_HARDWARE` and `DISCORD_WEBHOOK_QUANT` to `PERSONAL_WEBHOOKS_JSON`.

Add each channel's webhook URL to the `PERSONAL_WEBHOOKS_JSON` secret under the same name (for example `{"DISCORD_WEBHOOK_QUANT": "https://discord.com/api/webhooks/REDACTED"}`); no workflow change is needed. A channel whose webhook is not set is skipped.

`allowed_user_ids` (optional list of Discord user IDs) restricts who the bot serves. When it is set, 📌 reactions and applied-channel links from anyone else are ignored; when it is absent or empty, everyone is served. Applied-channel intake is also bounded: at most 5 links per message (extras get a ⚠️ reaction) and 20 links read per run, with the rest picked up on later runs.

For profiles, use Discord user IDs as keys, for example:

```json
{
  "profiles": {
    "123456789012345678": {
      "roles": ["machine learning", "software"],
      "companies": ["Example"],
      "locations": ["New York"],
      "terms": ["Summer 2027"],
      "keep_unknown_terms": true,
      "webhook_env": "DISCORD_WEBHOOK_URL_EXAMPLE",
      "follow_up_days": 14
    }
  },
  "max_discord_per_run": 50,
  "dedup_days": 30,
  "follow_up_days": 14,
  "keep_unknown_terms": true
}
```

## Durable state

These files are runtime state. GitHub Actions persists them after each run; local runs write them beside the scripts.

| File | Contents |
| --- | --- |
| `seen.json` | Previously observed source posting IDs (private: kept in the `internship-watcher-state` repo) |
| `delivery_state.json` | Known identities, 30-day fingerprints, legacy `norm:` entries ignored but retained, and pending per-destination queues (private: kept in the `internship-watcher-state` repo) |
| `message_map.json` | Recent Discord message IDs and jobs used for 📌 scans (private: kept in the `internship-watcher-state` repo) |
| `notion_state.json` | Notion database IDs, users, applied cursor, `pending_applied`, and `pending_pins` (private: kept in the `internship-watcher-state` repo) |
| `health.json` | Last completed scan, source successes/failures, matching and new counts, pending deliveries, parked (given-up) deliveries, sync errors, and the SimplifyJobs ETag cache (an unchanged feed is skipped via HTTP 304, refetched in full at least hourly and whenever filter settings change) (private: kept in the `internship-watcher-state` repo) |

`health.json` is also the run's operational summary: a source failure, pending delivery, or Notion sync error is reported explicitly and retried through durable state. A failing source records `failing_since`. Once it has been down for 5 hours the watcher opens a `source-down` GitHub issue (closed automatically on recovery) and dispatches the `source-doctor.yml` workflow, where Claude investigates and opens a PR updating `config.json`; the run itself still succeeds. A broad outage (more than 5 stale sources, or 10% of sources), pending deliveries, and sync errors fail the run. The source doctor is off unless the repository variable `SOURCE_DOCTOR_ENABLED` is `true`, and it also needs a `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) or `ANTHROPIC_API_KEY` repository secret.

## Local run

```bash
python watcher.py --dry-run
python watcher.py
```

### Database tests

Run `scripts/db_test.sh` to start a temporary local PostgreSQL instance, apply the schema and RLS checks, and run the database tests. Install PostgreSQL 18 and the project dependencies first.

Check the boards in the actual configuration, a selected company, or a new candidate:

```bash
python verify_boards.py
python verify_boards.py --company Wayve
python verify_boards.py --candidate ashby wayve
python verify_boards.py --candidate workday nvidia/NVIDIAExternalCareerSite/wd5
```

The verifier uses the same endpoints and feed-shape checks as the watcher, reports HTTP/schema errors, and exits nonzero if any board fails. It does not change runtime state or send notifications. Feed options and personal preferences are validated before a watcher scan begins.

Run the tests with `python3 -m unittest discover -s tests -v` and `node --test internship-pinger/worker.test.js`. The pipeline workflow does not upload private state artifacts; jobs and the compact health summary are stored in Supabase. Do not assume the scheduled workflow runs exactly every ten minutes.

See [IMPROVEMENTS.md](IMPROVEMENTS.md) for prioritized maintenance suggestions and their tradeoffs.

## Troubleshooting

- A 404 for a board usually means its ATS slug changed. Verify it before editing `config.json`.
- A nonzero pending count in `health.json` means a destination will be retried on a later run.
- A duplicate Discord post can result from an accepted webhook request whose response timed out. The queue preserves work for retry; it does not claim exactly-once delivery.
- Deleting state files causes history to be reconsidered. Preserve `seen.json`, `delivery_state.json`, `message_map.json`, and `notion_state.json` unless you intentionally want to reprocess work.
- Old Notion rows and saved history remain valid. Rows whose URL was previously damaged by an older version are not automatically reconstructed.

Workday company entries use `ats: "workday"` with `tenant`, `site`, and `host` (for example `wd5`). The verifier accepts `--candidate workday TENANT/SITE/HOST` and `--company NAME`. Workday searches for `intern` and is relevance-capped at the first 100 search results per tenant; enabled aggregate feeds provide backup coverage. Relative posting dates are approximate and may be unavailable.
