# CLAUDE.md — project context for future sessions

## What this is

An internship alert and application-tracking system. The main watcher reads 173 configured company boards plus SimplifyJobs and Jobright feeds, filters every source, and routes individual postings to Discord, email, and Notion. It can run from GitHub Actions or locally. The GitHub `*/10` schedule is best effort and must not be documented as a ten-minute guarantee.

The `internship-pinger` Cloudflare Worker is now in this repository. It triggers `watch.yml`, monitors completed main-branch runs, and sends hourly stale/failure warnings. Keep worker changes and watcher changes conceptually separate; its README and Node test are part of the repository.

## Architecture facts

- `watcher.py` fetches the configured Greenhouse, Lever, and Ashby boards and the enabled aggregate feeds.
- Filtering applies to all sources. Top-level `terms` is the season filter for every source; `simplify.terms` is only a backward-compatible fallback when top-level `terms` is absent. Unknown season terms are retained by default and can be controlled with `keep_unknown_terms`; profile terms can be configured independently.
- `job_utils.py` canonicalizes URLs while preserving meaningful query parameters. Exact job identities persist. Cross-source fuzzy fingerprints expire after `dedup_days` (default 30). Legacy `norm:` entries in state are ignored for matching, not removed.
- `delivery_state.json` is the durable per-destination queue for Discord, email, and Notion. `max_discord_per_run` defaults to 50. Discord uses individual posts and keeps 📌 pins; there are no digest messages.
- `health.json` records the last completed scan, source health, pending deliveries, and sync errors. A failed run leaves checkpointed work for retry.
- `notion_state.json` durably tracks `pending_pins` and `pending_applied`. Applied rows set `Applied On` and a follow-up date; `follow_up_days` defaults to 14, supports per-profile overrides, and `0` disables the date. Stats report status counts and due follow-ups.
- Notion upserts query existing rows by canonical job identity, including legacy rows, so existing history does not need a reseed migration. Previously stripped URLs are not automatically repairable.
- Applied-link parsing may fetch HTML metadata after trying ATS APIs. Do not claim that the project never fetches HTML.
- Config defaults include explicit `terms`, `keep_unknown_terms`, `dedup_days` 30, `max_discord_per_run` 50, `follow_up_days` 14, and an empty `profiles` object. Personal `profiles` are keyed by Discord user ID and may specify roles, companies, locations, terms, unknown-term handling, webhook environment variable, and follow-up interval. Profiles affect optional notification routing and follow-up settings; they do not gate explicit saved/applied actions.
- `PERSONAL_WEBHOOKS_JSON` is a GitHub secret containing a JSON mapping from `DISCORD_WEBHOOK_*` variable names to URLs. The workflow imports it into the environment before running the watcher; `profile.webhook_env` must use that prefix. Keep examples redacted and do not add workflow changes for ordinary profile configuration.
- A webhook timeout can represent an accepted Discord request, so duplicate Discord posts remain possible. Do not claim exactly-once delivery. Existing Notion-row scans reduce duplicates.

## Deployment facts

- Live repo: `github.com/avyukthNarra/-internship-watcher` (public, including the leading `-`; account `avyukthNarra`). Check `git remote -v` before assuming. This checkout may contain work in progress; do not imply a live rollout unless it has been verified.
- The original `github.com/avyTamuGit/internship-watcher` deployment was disabled during the account migration. Do not re-enable it while the new deployment is the active path.
- `gh` CLI is not installed on this machine. The old macOS keychain credential belongs to `avyTamuGit`; pushing to the new repo uses SSH.
- Existing Notion history and state were carried across during migration. Do not reseed or delete state casually.
- Secrets normally include Discord webhooks, `DISCORD_BOT_TOKEN`, `APPLIED_CHANNEL_ID`, `NOTION_TOKEN`, and `NOTION_PARENT_PAGE_ID`; SMTP secrets are optional.

## Working rules

- Verify every new ATS board slug with `verify_boards.py` before adding it. Wrong slugs can 404 silently.
- Preserve `seen.json`, `delivery_state.json`, `message_map.json`, and `notion_state.json`. Deleting them can requeue or re-alert historical jobs.
- The workflow always uploads state artifacts with seven-day retention. Persistence runs even after watcher failures and retries rebase/push up to three times; a rebase conflict leaves the artifact available for recovery.
- Keep retries and state checkpoints durable. A run can fail after an external service accepted a request.
- Do not add a new feed merely because it sounds useful; inspect whether it duplicates SimplifyJobs or Jobright.
- Run `python3 -m unittest discover -s tests -v` and `node --test internship-pinger/worker.test.js`. Keep setup and secret documentation useful for both GitHub Actions and local dry runs.
