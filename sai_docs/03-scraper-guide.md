# How the scraper works, and how to extend it

## One run, start to finish

`python watcher.py` (`watcher.main`) does this, in order:

1. **Load and validate.** Read `config.json`, check it with `validate_config`, import `PERSONAL_WEBHOOKS_JSON`. If no delivery credentials exist (or you pass `--dry-run`) it fetches and prints, and writes nothing.
2. **Load state.** `seen.json` plus `delivery_state.json` (`known_ids` and the pending queue). The previous `health.json` seeds source health.
3. **Discover** (`discover`):
   - Run one fetcher per company in `config.json["companies"]` (16 threads). Each fetcher turns a board's JSON into a list of `{id, title, location, url}` dicts.
   - Fetch SimplifyJobs, vanshb03 and Jobright if enabled. These add `company` and `agg: True`.
   - **Filter every posting:** title must match an include keyword and no exclude keyword (`matches`), location must not be excluded (`location_excluded`), and the season must match (`term_matches`).
4. **Find the new ones** (`select_new`). A job is new if its ID isn't in `seen`, its cross-source identity isn't known, and (for aggregator jobs) its fuzzy fingerprint hasn't been seen in the last `dedup_days`.
5. **Queue before sending** (`queue_deliveries`). Each new job gets a list of destinations (`discord:<ENV_NAME>`, `email`, `notion`) in `delivery_state.json["pending"]`. State is saved to disk before anything is sent.
6. **Deliver** (`deliver`). Walk the queue, send each destination, remove it from the queue on success, and checkpoint after every attempt. At most `max_discord_per_run` (50) Discord posts per run.
7. **Notion sync** (`notion_sync.run`): log to the master database, turn 📌 reactions into personal tracker rows, read the applied channel, close dead links once a day, update the stats callout.
8. **Write `health.json`** and exit non-zero if a source has been down 5 hours or more, a delivery is stuck, or sync failed.

GitHub Actions (`watch.yml`) then commits the state files back to `main` and uploads them as an artifact.

## The key data shape

Every fetcher must return dicts shaped like this:

```python
{
  "id": "greenhouse:anthropic:12345",   # unique and stable, "<source>:<board>:<native id>"
  "title": "Software Engineer Intern",
  "location": "San Francisco, CA",      # "" if unknown (never None; see R3)
  "url": "https://boards.greenhouse.io/...",
}
```

`discover` adds `company` for board sources. Aggregator fetchers set `company` and `agg: True` themselves. The `id` prefix (`greenhouse`, `lever`, `ashby`, `simplify`, `vanshb03`, `jobright`) is used for routing and for the Notion `Source` column, so a new source needs its own prefix.

## Adding a company that uses Greenhouse, Lever or Ashby

This is the 90% case and needs no code.

1. Find the board slug. It's in the careers URL: `boards.greenhouse.io/<slug>`, `jobs.lever.co/<slug>`, `jobs.ashbyhq.com/<slug>`.
2. Verify it **before** editing anything:
   ```bash
   python3 verify_boards.py --candidate greenhouse <slug>
   ```
   You want `OK … N jobs`. A 404 means wrong slug or wrong ATS.
3. Add an entry to `companies` in `config.json`:
   ```json
   { "name": "Example Co", "ats": "greenhouse", "board": "exampleco" }
   ```
4. Check it again from the config, and run the tests:
   ```bash
   python3 verify_boards.py --company "Example Co"
   python3 watcher.py --dry-run
   python3 -m unittest discover -s tests -v
   ```
5. Commit. The first live run may queue every matching posting at that company, delivered 50 Discord posts per run.

`name` is what shows up in Discord and decides whether a job goes to the "top" webhook (`DISCORD_WEBHOOK_URL_TOP`). Any job from a configured board counts as top.

## Finding boards you don't track yet

`python3 discover_boards.py --names companies.txt` (one name per line) or `--yc --min-team 10` (add `--industry robotics --industry hardware`, repeatable, to match YC industries and tags) guesses slugs from each company's name and website, probes Greenhouse, Lever and Ashby, and lists boards with internship postings. It never edits `config.json`. On 2026-10-27 it checked 780 YC companies in about 3 minutes and found 34 boards with internship postings. Read the list, drop non-fits, run `verify_boards.py --candidate ATS BOARD` on the rest, then add them. Expect a one-time burst of alerts for a new board's current postings.

## Adding a company on a different ATS (new adapter)

Example: SmartRecruiters. Four small edits.

The endpoint, the `content` key and the job URL below are illustrative. I did not call the SmartRecruiters list API. Confirm the real response shape with `curl` before copying them.

1. **`job_feeds.py`**: add the endpoint to `BOARD_APIS` so the watcher and the verifier share it:
   ```python
   "smartrecruiters": {
       "url": "https://api.smartrecruiters.com/v1/companies/{board}/postings",
       "key": "content",
   },
   ```
   `feed_items` requires every record to be a dict with a non-null `id`. Check that the API's list really uses `id`.
2. **`watcher.py`**: write a fetcher next to `fetch_greenhouse` and register it:
   ```python
   def fetch_smartrecruiters(board):
       data = source_items(board_url("smartrecruiters", board), "content")
       return [{
           "id": f"smartrecruiters:{board}:{j['id']}",
           "title": j.get("name") or "",
           "location": ((j.get("location") or {}).get("city") or ""),
           "url": f"https://jobs.smartrecruiters.com/{board}/{j['id']}",
       } for j in data]

   ATS_FETCHERS["smartrecruiters"] = fetch_smartrecruiters
   ```
   Use `or ""` on every field (R3 in `02-optimizations.md`).
3. **`job_utils.job_identity`**: if the ATS has a recognizable URL form, add a branch so the same job seen via an aggregator isn't alerted twice. Optional but recommended.
4. **Tests**: copy a case from `tests/test_feeds.py` and `tests/test_board_verifier.py`. `project_config.validate_config` already accepts any ATS present in `BOARD_APIS`.

Pagination: `source_items` makes one request. If the ATS pages its results (Workday and SmartRecruiters do), loop in your fetcher and collect all pages before returning.

## Adding a new aggregate feed

Read `fetch_simplify` (JSON feed) and `fetch_jobright` (markdown table) as templates. Rules from `CLAUDE.md`: check first that it doesn't duplicate SimplifyJobs or Jobright. Then:

1. Write `fetch_<name>(cfg)` returning the same dict shape plus `company`.
2. Register it in the tuple in `discover` (`for name, fetcher in (("simplify", …), ("vanshb03", …), ("jobright", …))`) and give it a config block with `enabled`.
3. Validate its config keys in `project_config.validate_config`.
4. Use a unique `id` prefix. Treat any fetch/parse failure as a source failure (set `SOURCE_HEALTH`) rather than returning an empty list silently. `fetch_jobright` shows the pattern.

## Tuning what you receive (all in `config.json`)

| Setting | Effect |
| --- | --- |
| `include_keywords` / `exclude_keywords` | Title filters (substring today; see J1/J2 for the bugs) |
| `exclude_locations` | Skips non-US places, but keeps anything with a US state code or "USA" |
| `terms`, `keep_unknown_terms` | Season filter for all sources. Unknown seasons are kept by default |
| `simplify.company_keywords` | Which companies to pull from the SimplifyJobs feed (word-boundary match) |
| `simplify.max_age_days` / `jobright.max_age_days` / `vanshb03.max_age_days` | Ignore older aggregator posts (defaults 14, 7 and 7; the config sets vanshb03 to 3 to keep the first-run burst small) |
| `dedup_days` | How long fuzzy cross-source duplicates are suppressed (default 30) |
| `max_discord_per_run` | Discord posts per run (default 50); the rest wait in the queue |
| `profiles` | Per-person routing to a personal webhook, keyed by Discord user ID |

A personal profile needs a webhook secret too. Add the mapping to the `PERSONAL_WEBHOOKS_JSON` GitHub secret and set `webhook_env` to the same name (it must start with `DISCORD_WEBHOOK_`).

## Running and testing locally

```bash
pip install -r requirements.txt
python3 watcher.py --dry-run               # fetch + print, nothing written or sent
python3 verify_boards.py                   # check every configured board
python3 -m unittest discover -s tests -v   # 112 tests
node --test internship-pinger/worker.test.js
```

A non-dry local run writes the state files in the repo folder. Don't commit a local run's state over the live state (it can re-alert or lose pending work).

## Gotchas

- **Never delete the state files.** Deleting `seen.json`, `delivery_state.json`, `message_map.json` or `notion_state.json` makes the bot re-alert history.
- **IDs must be stable.** If a fetcher builds `id` from something that changes (a title, a timestamp), every run looks new.
- A board returning an empty list is valid and not an error. A 404 or schema mismatch is a failed source.
- `verify_boards.py` is the only place wrong slugs show up clearly. Wrong slugs "404 silently" in the sense that the run only fails after 5 hours of it (see R1).
- Postman has no direct board (Workday). It relies on the SimplifyJobs keyword list. Don't re-add its dead Greenhouse entry.
