# Internship Watcher

This repository monitors internship postings and routes matching jobs to Discord, email, and Notion. It is designed to run from GitHub Actions or locally. GitHub's schedule is best effort, so the `*/10` cron is a request to GitHub rather than a delivery guarantee; runs can be delayed for hours.

## Architecture

Each watcher run:

1. Fetches the 173 company boards listed in `config.json` using the Greenhouse, Lever, and Ashby public APIs. It also reads the enabled SimplifyJobs and Jobright feeds.
2. Applies the title, location, and season filters to every source. The top-level `terms` list applies to all sources; `simplify.terms` remains a backward-compatible fallback only when top-level `terms` is absent. `keep_unknown_terms` controls whether a posting with no recognizable season term is retained and defaults to keeping unknown terms.
3. Identifies postings by ATS identity or canonical URL. Known campaign parameters are removed, while other URL query parameters are preserved because they may identify the job. Exact identities remain known indefinitely. Cross-source fuzzy fingerprints are retained for `dedup_days` (30 days by default). Legacy `norm:` entries in state are ignored for matching and are not removed.
4. Places each new job into `delivery_state.json` with its individual destinations. Discord notifications are individual posts and retain the 📌 instruction. There are no digest messages. `max_discord_per_run` defaults to 50; undelivered destinations remain queued for a later run.
5. Delivers to the configured Discord webhooks, email, and Notion master log. Notion reaction and applied-link processing then update personal trackers.

The watcher checkpoints intent before external delivery and uses atomic JSON writes. A request timeout can still mean that Discord accepted a message before the response was lost, so a retry can duplicate a Discord post. Querying existing Notion rows by job identity reduces duplicate tracker rows, but delivery is not exactly once.

The repository also contains the `internship-pinger` Cloudflare Worker. It triggers the `watch.yml` workflow and monitors completed main-branch runs, sending hourly stale or failure warnings. See [`internship-pinger/README.md`](internship-pinger/README.md) for its setup.

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

`config.json` contains the 173 `companies` entries plus explicit defaults for `terms`, `keep_unknown_terms`, `dedup_days` (30), `max_discord_per_run` (50), `follow_up_days` (14), and `profiles` (an empty object unless configured). It also contains the SimplifyJobs and Jobright feed settings. Add a board only after verifying its slug with `verify_boards.py`; unsupported or stale slugs can return 404. The configured `exclude_locations` list uses word-boundary matching and keeps locations that clearly contain a US state or USA. Empty or unknown locations are retained.

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
| `seen.json` | Previously observed source posting IDs |
| `delivery_state.json` | Known identities, 30-day fingerprints, legacy `norm:` entries ignored but retained, and pending per-destination queues |
| `message_map.json` | Recent Discord message IDs and jobs used for 📌 scans |
| `notion_state.json` | Notion database IDs, users, applied cursor, `pending_applied`, and `pending_pins` |
| `health.json` | Last completed scan, source successes/failures, matching and new counts, pending deliveries, and sync errors |

`health.json` is also the run's operational summary: a source failure, pending delivery, or Notion sync error is reported explicitly and retried through durable state.

## Local run

```bash
python watcher.py --dry-run
python watcher.py
```

Run the tests with `python3 -m unittest discover -s tests -v` and `node --test internship-pinger/worker.test.js`. The workflow always uploads the five state files as a recovery artifact with seven-day retention. Its persistence step always runs, makes up to three rebase/push attempts, and preserves the artifact if a rebase conflict prevents pushing. Do not assume the scheduled workflow runs exactly every ten minutes.

## Troubleshooting

- A 404 for a board usually means its ATS slug changed. Verify it before editing `config.json`.
- A nonzero pending count in `health.json` means a destination will be retried on a later run.
- A duplicate Discord post can result from an accepted webhook request whose response timed out. The queue preserves work for retry; it does not claim exactly-once delivery.
- Deleting state files causes history to be reconsidered. Preserve `seen.json`, `delivery_state.json`, `message_map.json`, and `notion_state.json` unless you intentionally want to reprocess work.
- Old Notion rows and saved history remain valid. Rows whose URL was previously damaged by an older version are not automatically reconstructed.
