# Fixes and optimizations

Three groups: **R** (reliability bugs and operational problems), **P** (performance and cost), **J** (job quality: finding more of the right postings and fewer wrong ones). Items marked **verified** were reproduced; the rest come from reading the code.

## Do these first

| Order | ID | Why |
| --- | --- | --- |
| 1 | R1 | Every run is failing right now because of one dead board |
| 2 | J1 + J2 | Two keyword bugs: wrong jobs get through and right jobs get dropped |
| 3 | R2 + R3 | One bad posting can wedge or crash the whole pipeline |
| 4 | R5 + R6 | State churn is growing the repo (9,221 commits, 39 MB pack) |
| 5 | P1 | A 13 MB download every 10 minutes |

---

## R — Reliability

### R1. One dead board makes every run fail (verified)
**Board fixed (2026-10-27):** Old Mission moved to Ashby (`old-mission-capital`, verified, 39 jobs). The exit-code policy below is still open.


`oldmissioncapital` (Greenhouse) returns HTTP 404 and has been down about **150 hours**. `health_exit_code` returns 1 when any source has been down 5 hours or more, so each scheduled run exits non-zero. The pinger then reports "N consecutive runs not successful". Meanwhile everything else is healthy (174 sources OK, 0 pending deliveries). This is exactly the problem described in `IMPROVEMENTS.md` item 1.

- **Immediate fix:** find the company's new slug and check it with `python3 verify_boards.py --candidate greenhouse <slug>`. If the company is gone or moved ATS, delete its entry from `config.json`. Run the tests.
- **Real fix:** stop treating one stale source as a failed run. Only exit non-zero for stuck deliveries or sync errors, or when a large share of sources is down (say 10% or more). Report stale sources as a warning in the step summary and a separate pinger line.

### R2. A bad delivery is retried forever and can block the queue (by inspection)
In `watcher.deliver`:
- A destination that fails permanently (for example Notion rejects the job with HTTP 400) just increments `attempts`. There is no cap and no dead-letter list. `pending_deliveries` stays above 0, so `health_exit_code` fails **every** future run.
- The `except` there catches only `requests`/`smtplib`/`OSError`/`ValueError`/`KeyError`. Anything else (`TypeError` from a `None` title, for example) escapes `deliver`, is caught in `main`, and aborts the rest of the loop. The same poison job is first in the queue next run, so it blocks every job behind it.

**Fix:** catch `Exception` per destination, record `error` and `attempts`. After N attempts (say 20, about 3 hours) move the entry to `ledger["dead"]` with its reason, and don't count dead entries toward the failure exit code. Show them in `health.json` instead.

### R3. `None` fields crash the whole run (verified)
`j.get("title", "")` returns `None`, not `""`, when the API sends an explicit `null`. I reproduced:
- `matches(None, …)` → `AttributeError`
- `fingerprint({... "location": None})` → `AttributeError`

`discover()` does its title/location filtering outside any `try`, and `select_new` is unguarded, so one null field in one posting out of 18,000 ends the run with a traceback. Lever's `categories.location` is the likeliest source (`fetch_lever` line ~157).

**Fix:** coerce every field at the fetch boundary: `str(x or "")`. A single `clean_job()` function (shared with S6 in the security audit) does both jobs. Add a test that feeds `null` fields through `discover`.

### R4. Empty or invalid titles/URLs are rejected by Notion (by inspection)
`_add_row` sends `Role` (title) and `Link` (url) exactly as received. An empty title or malformed URL gives HTTP 400, which feeds R2. `clean_job()` should default the title to `"Untitled"` and drop postings whose URL isn't `http(s)://`.

### R5. A commit every ten minutes (verified)
`health.json` stores `last_completed_scan`, so it changes on every run, so the "Persist state" step commits every run. That is the cause of **9,194 bot commits** (148 in the last 24 hours). The pack is 39 MB and grows forever, and each `git pull --rebase` fetches more history.

**Fix, in increasing effort:**
1. Stop committing `health.json`. Keep it in the artifact only, and read the last scan time from the Actions API (the pinger already does this).
2. Commit state only when job state changed (`seen`, `delivery_state`, `message_map`, `notion_state`).
3. Move state off `main` entirely (see S2 in the security audit). Then history size no longer affects your code repo, and `main` can be protected.

### R6. Duplicated and over-written state (verified) — measured 2026-10-27, **not worth changing now**
Growth is about 100 IDs a day (17,230 IDs on 10-17, 18,253 on 10-27), roughly 1.6 MB a year per file. That's too slow to justify pruning, and the duplicate `known_ids` is deliberate crash protection that `tests/test_pipeline.py` asserts. A bug in pruning would re-alert old jobs. Revisit only if the files pass about 10 MB. The original analysis follows.

- `seen.json` and `delivery_state.json["known_ids"]` are the **same 18,253 IDs** (I compared them). That's about 800 KB stored twice and written twice per run. Choose one as the authority.
- `checkpoint()` rewrites the whole 1.9 MB ledger (`indent=1`, `fsync`) after every single destination. A 50-message Discord batch writes roughly 100 MB. The identity and fingerprint history rarely changes during delivery.
- Nothing is ever pruned. `identities` has 7,652 entries and `seen` has 18,253, growing forever.

**Fix:** split the pending queue (small, changes constantly) into its own file from the history (large, changes at the end of the scan). Store a `last_seen` timestamp per ID and drop IDs not seen for about 180 days. Never prune an ID that is still live in a source, or you'd re-alert it. Keep this behind a test before turning it on.

### R7. Notion work happens on every run even when nothing changed (by inspection) — **skipped**
Throttling needs a persisted timestamp, which would add about 24 `notion_state.json` commits a day and undo the commit savings from R5. It saves about 2 calls per run per user. Revisit when there are many users, and then store the timestamp somewhere that isn't committed.

`notion_sync.run()` runs every 10 minutes. `_update_stats` re-queries every user's whole tracker database and PATCHes the stats callout each time. With one user that's a few calls. With a website and many users it becomes `users × pages-of-100` calls every 10 minutes. **Fix:** refresh stats at most hourly, or only when a status changed (or a pin/applied item was processed).

### R8. The master log scans the whole table (by inspection) — **not done: cannot verify without a Notion token**
Replacing the scan with a `Link` filter changes how the live master log finds existing rows. A mistake could create duplicate rows or fail writes, and I had no token to test against. To size the problem first, count the master database's rows from a machine that has `NOTION_TOKEN`. If it's in the thousands, build the filtered lookup with a test against a scratch Notion page.

`log_master` → `_upsert_row` → `_pages(master_db)` pages the **entire** master database (100 rows per call) the first time any job is logged in a run, then does a linear `job_identity()` scan per job. Notion allows about 3 requests/second, so a database with thousands of rows takes tens of seconds per run that has any new job. I did not measure the master DB's size.

**Fix:** since the watcher already dedupes with `seen`, look up a row by the `Link` property with a filtered query (one call per new job), or keep an identity → page ID map in state.

---

## P — Performance and cost

### P1. The SimplifyJobs feed is 13 MB, fetched every 10 minutes (verified)
`listings.json` is **13,074,080 bytes**. At 144 runs a day that's about 1.9 GB per day of download for a file that changes a few times an hour. GitHub's raw host returns an `ETag` (I confirmed one). **Fix:** conditional GET. Send `If-None-Match`; on HTTP 304 skip the feed for this run (nothing new can appear). Store the ETag next to the source health record. Include a hash of the relevant config (terms, keywords, `max_age_days`) in the cache key so a config change forces a refetch.

### P2. No connection reuse (by inspection) — **measured, dropped**
Timing all 172 boards with 16 threads gave plain `requests.get`: 14.4 s and 14.2 s; thread-local `Session`: 4.8 s and 16.7 s. The variance swamps any gain, and the change would require rewriting many test mocks. Not worth it.

Every call is a bare `requests.get`, so each of the 166 Greenhouse/Ashby requests opens a new TLS connection to the same two hosts. A `requests.Session` per worker thread (Sessions aren't fully thread-safe, so use `threading.local`) reuses connections. I haven't measured the gain. Time a full `python watcher.py --dry-run` before and after.

### P3. Poll cold boards less often (optional)
Many of the 172 boards rarely change. Poll the top companies every run and the rest every 30–60 minutes. Saves requests at the cost of slower alerts for those companies. Only worth it if run time or rate limits become a problem; they aren't today.

### P4. Things I checked that are NOT worth optimizing
- Keyword and company matching: 5,000 `company_matches` calls against 66 keywords take about 0.2 s. Leave it.
- `select_new` and fingerprinting: linear, fast.
- Discord's `time.sleep(0.4)` between posts: it's a sensible rate-limit guard.

---

## J — Job quality

### J1. `intern` also matches other words (verified)
`include_keywords` uses substring matching. Results with the current config:

| Title | Passes? |
| --- | --- |
| International Payments Engineer | **yes (wrong)** |
| Internet Infrastructure Engineer | **yes (wrong)** |
| Software Engineer Intern | yes |

`"internal"` is in the exclude list, which hides one symptom, but "international" and "internet" slip through. **Fix:** match with word boundaries: `\bintern(s|ship|ships)?\b|\bco-?op\b`.

### J2. Exclude words drop real engineering internships (verified)
`exclude_keywords` was also substring matching, so `"sales"` killed "Salesforce Developer Intern".

**Done (2026-10-27):** both lists now use whole-word matching. "Salesforce Developer Intern" passes. "Marketing Technology Engineer Intern" is still excluded, because "marketing" is a whole word there. That was my mistake in the first version of this doc. If you want those roles, apply the exclude only when no tech keyword (`software`, `engineer`, `developer`, `ml`, `data`) is present. Not done.

Result on live data (27,795 postings scanned): **83 postings stop matching** (all non-internships like "Director, US International Tax" that matched only through "International"), and **0 new postings** start matching after adding `"civil engineering"` to the exclude list (whole-word matching would otherwise have let SpaceX civil-engineering internships through).

### J3. No positive role filter (by inspection)
Today any title with "intern" passes unless excluded, so non-engineering roles (facilities, operations, design…) reach Discord. Add an optional global `role_keywords` list (for example `software`, `engineer`, `machine learning`, `data`, `research`). Keep it off by default so nothing changes until you choose. `profiles[*].roles` already does this per person, but only for routing to a personal webhook. A global list would cut noise in the shared channels.

### J4. Feed URLs and seasons need a look (verified)
- `simplify.url` points at `…/Summer2026-Internships/…`. Today it returns byte-for-byte the same file as `…/Summer2027-Internships/…` (same size and ETag), so it works, but only because of an alias. Point to the 2027 name explicitly so a removed alias can't silently break the source.
- Jobright: the config uses `2026-Software-Engineer-Internship` and `2026-Data-Analysis-Internship`. The `2027-Software-Engineer-Internship` repo returns 404 right now. Re-check every few weeks. The "No parseable Jobright rows" health check will tell you if the 2026 repos go quiet.
- `terms` currently lists Fall 2026, Winter 2027, Spring 2027, Summer 2027. Drop Fall 2026 around December, and add Fall 2027 when it starts appearing.

### J5. Coverage: sources worth adding (by inspection)
Do this *after* checking the feed overlap, as `CLAUDE.md` says. Don't add a feed just because it sounds useful.
- **Workday** (Postman, and many large companies). Currently covered only through the aggregators. The public job-search endpoint is `POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs`, paged with `limit`/`offset`. It's undocumented, so verify each tenant by hand first. See `IMPROVEMENTS.md` item 5.
- **SmartRecruiters**: `https://api.smartrecruiters.com/v1/companies/{id}/postings`. The repo already calls the single-posting version in `notion_sync._ats_api`.
- **Workable, Recruitee, Teamtailor**: all have public JSON job lists. Add one only if a company you care about uses it.
- **Lever EU**: some Lever customers are on `api.eu.lever.co`. A 404 on the normal host for a company that clearly uses Lever is the symptom.
- A "which of my target companies have **no** direct board" report (companies in `simplify.company_keywords` but not in `companies`) would tell you where the real gaps are.

### J6. Housekeeping
- `watcher.norm_key` and `SOURCE_ALERT_AFTER` look unused in `watcher.py`, but tests reference both (`tests/test_watcher.py:66`, `tests/test_pipeline.py:130`). Don't remove them without updating the tests.
- In `fetch_simplify`, the variable `min_age_days` holds a *maximum* age. Rename to `max_age_days`.
- `simplify.terms` duplicates the top-level `terms`. The README documents it as a fallback, so leave it unless you decide to simplify.
