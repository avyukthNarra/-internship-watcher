# CLAUDE.md — project context for future sessions

## What this is

This repository runs a website data pipeline. `pipeline.py` uses `watcher.discover()` to read configured company boards and feeds, then syncs jobs and source health to Supabase. The GitHub `*/10` schedule is best effort and must not be documented as a ten-minute guarantee. The Discord bot lives in the separate legacy repository `avyukthNarra/internship-watcher-discord`.

The `internship-pinger` Cloudflare Worker code remains in this repository for the legacy Discord bot. It is separate from the Supabase pipeline; do not assume its current `watch.yml` target is part of this repo's deployment.

## Architecture facts

- `pipeline.py` is the scheduled entrypoint. `watcher.discover()` fetches configured Greenhouse, Lever, Ashby, and Workday boards and the enabled aggregate feeds; `db.py` syncs jobs and defaults to Supabase.
- `job_feeds.py` defines shared board endpoints and feed validation used by discovery and the verifier. `project_config.py` owns configuration validation and shared defaults. `source_health.py` builds health reports without I/O; `pipeline.py` stores a compact summary in Supabase.
- Wayve uses Ashby (`wayve`). Postman moved to Workday and is covered through the aggregate feeds, including an explicit SimplifyJobs company keyword; do not restore its dead Greenhouse entry or claim direct Workday coverage.
- Filtering applies to all sources. Top-level `terms` is the season filter for every source; `simplify.terms` is only a backward-compatible fallback when top-level `terms` is absent. Unknown season terms are retained by default and can be controlled with `keep_unknown_terms`; profile terms can be configured independently.
- `job_utils.py` canonicalizes URLs while preserving meaningful query parameters. Exact job identities persist. Cross-source fuzzy fingerprints expire after `dedup_days` (default 30). Legacy `norm:` entries in state are ignored for matching, not removed.
- `health.json` in `state_docs` records the last completed scan, source counts, and per-source ok/error status. The pipeline exits nonzero for a broad source outage or database error.
- The legacy Discord bot retains its own delivery, message, and Notion state in its separate repository. Those files are not part of this pipeline.
- Notion upserts query existing rows by canonical job identity, including legacy rows, so existing history does not need a reseed migration. Previously stripped URLs are not automatically repairable.
- Applied-link parsing may fetch HTML metadata after trying ATS APIs. Do not claim that the project never fetches HTML.
- Notion pin and applied-link collection is separate from delivery; preserve the queue/cursor checkpoints when changing these helpers. Notion retry errors are recorded only when a request finally fails; ambiguous creates are not blindly retried.
- Config defaults include explicit `terms`, `keep_unknown_terms`, `dedup_days` 30, `max_discord_per_run` 50, `follow_up_days` 14, and an empty `profiles` object. Personal `profiles` are keyed by Discord user ID and may specify roles, companies, locations, terms, unknown-term handling, webhook environment variable, and follow-up interval. Profiles affect optional notification routing and follow-up settings; they do not gate explicit saved/applied actions.
- `PERSONAL_WEBHOOKS_JSON` is a GitHub secret containing a JSON mapping from `DISCORD_WEBHOOK_*` variable names to URLs. The workflow imports it into the environment before running the watcher; `profile.webhook_env` must use that prefix. Keep examples redacted and do not add workflow changes for ordinary profile configuration.
- A webhook timeout can represent an accepted Discord request, so duplicate Discord posts remain possible. Do not claim exactly-once delivery. Existing Notion-row scans reduce duplicates.

## Deployment facts

- This repository is `github.com/avyukthNarra/-internship-watcher` (public, including the leading `-`). Its `.github/workflows/pipeline.yml` runs `pipeline.py` every 10 minutes on a best-effort schedule and writes to Supabase project `mkphndqkihjanumsyrli`.
- The Discord bot runs from `github.com/avyukthNarra/internship-watcher-discord`, the legacy bot repository.
- `DATABASE_URL` is a secret in this repository's GitHub `production` environment. Do not print or commit its value.

## Working rules

- Verify every new ATS board slug with `verify_boards.py` before adding it. Wrong slugs can 404 silently.
- The verifier checks `config.json` by default; `--company NAME` selects an existing company and `--candidate ATS BOARD` checks a new slug without editing configuration. It exits nonzero on an HTTP or schema failure.
- The legacy Discord bot's state files belong to its separate repository. This pipeline does not load or write those files; never commit runtime state files here.
- Pipeline job data and its compact health summary live in Supabase. Do not add private state files or artifacts to the pipeline workflow.
- Do not add a new feed merely because it sounds useful; inspect whether it duplicates SimplifyJobs, vanshb03, or Jobright. vanshb03 was added after measuring that most of its recent postings were not in SimplifyJobs; its links are `go.vansh.nyc` shortlinks, so URL identity cannot dedupe it.
- Record user-visible changes (new sources, config keys, behavior changes, fixes) in `CHANGELOG.md` under Unreleased; follow semver as described there. Do not tag or bump a version without the owner.
- Run `python3 -m unittest discover -s tests -v` and `node --test internship-pinger/worker.test.js`. Keep setup and secret documentation useful for both GitHub Actions and local dry runs.
