# Project context (read this first)

Written 2026-10-27 from a full read of the repo. Everything here was checked against the code or the live data files, not guessed.

## What this project is

A bot that watches job boards for internships and routes each new posting to Discord, email and a Notion tracker. It runs on GitHub Actions. A small Cloudflare Worker (`internship-pinger/`) wakes it up and alerts if it stalls.

- **Live repo:** `github.com/avyukthNarra/-internship-watcher` (public, leading `-` in the name). You (`Saibot913`) now have push access.
- **Your branch:** `sai-contributions-setting_up_website` (tracking `origin`). It has no commits of its own yet.
- **Scale today:** 172 company boards (95 Greenhouse, 71 Ashby, 6 Lever) plus SimplifyJobs and Jobright feeds. About 704 postings currently match the filters. About 18k job IDs are remembered.
- **Users today:** one tracked Notion user. The state files are shared with the whole server.

## File map

| File | Role |
| --- | --- |
| `watcher.py` | Main program: fetch → filter → dedupe → queue → deliver |
| `job_feeds.py` | Board API URL templates + feed shape check (`BOARD_APIS`, `board_url`, `feed_items`) |
| `job_utils.py` | `canonical_url`, `job_identity`, `fingerprint`, season matching, atomic JSON load/save |
| `project_config.py` | Validates `config.json`, loads `PERSONAL_WEBHOOKS_JSON`, defaults |
| `source_health.py` | Builds `health.json` + decides the run's exit code (pure, no I/O) |
| `notion_sync.py` | Master log, 📌 reactions → personal trackers, applied-channel links, dead-link sweep, stats callout |
| `verify_boards.py` | Checks board slugs before you add them |
| `config.json` | All the knobs: companies, keywords, locations, seasons, feed settings, profiles |
| `seen.json` | Every job ID ever matched (about 800 KB) |
| `delivery_state.json` | Pending deliveries + exact identities + 30-day fuzzy fingerprints (about 1.9 MB) |
| `message_map.json` | Discord message ID → job, 3-day window, used to find 📌 reactions |
| `notion_state.json` | Notion DB IDs, per-user tracker data, pending queues, Discord cursors |
| `health.json` | Last scan time, per-source status, pending count |
| `.github/workflows/watch.yml` | The scheduled run + commits state back to `main` |
| `.github/workflows/test.yml` | Runs unit tests on PRs and on pushes that touch code |
| `.github/workflows/test-ping.yml` | Manual "did my phone buzz" test message |
| `internship-pinger/` | Cloudflare Worker: triggers `watch.yml` every 10 min, alerts hourly if stale or failing |
| `tests/` | 64 Python tests (all pass) + 5 Node tests (all pass) |
| `CLAUDE.md`, `README.md`, `IMPROVEMENTS.md` | Existing docs. `CLAUDE.md` holds the working rules. |

## Hard rules inherited from `CLAUDE.md` (do not break these)

1. Never delete or reseed `seen.json`, `delivery_state.json`, `message_map.json` or `notion_state.json`. That re-alerts every historical job.
2. Verify every new board slug with `verify_boards.py` before adding it.
3. Don't claim exactly-once delivery. A webhook timeout can still produce a duplicate Discord post.
4. Don't re-enable the old `avyTamuGit` deployment.
5. Run `python3 -m unittest discover -s tests -v` and `node --test internship-pinger/worker.test.js` before pushing.

## Baseline checked today

- Python tests: 64 pass. Node tests: 5 pass.
- `verify_boards.py`: 171 of 172 boards OK. Failing: `oldmissioncapital` (Greenhouse, HTTP 404).
- That one dead board has been down about 150 hours. So every scheduled run currently exits non-zero, and the pinger sends failure alerts. See finding R1 in `02-optimizations.md`.

## The other docs in this folder

| File | What's in it |
| --- | --- |
| `01-security-audit.md` | Security and privacy findings, ranked, with fixes |
| `02-optimizations.md` | Reliability bugs, performance, and job-quality improvements |
| `03-scraper-guide.md` | How the scraper works and how to add boards, feeds and filters |
| `04-todo.md` | Ordered checklist, ending with the website task |
