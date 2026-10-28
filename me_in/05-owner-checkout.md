# Owner checkout: review this branch before merging

Written for the repository owner (`avyukthNarra`) and any Claude session asked to review the branch `sai-contributions-setting_up_website`. It states what changed, why, what to verify, what only an admin can do, and where the project is going. Read `CLAUDE.md` first; this file adds to it and does not replace it.

Status on 2026-10-27: 17 commits ahead of `main`, 27 files changed, 117 Python tests and 5 Node tests passing, `verify_boards.py` reports 200/200 boards. **Nothing here is live until it is merged to `main`.** Do not assume a rollout has happened.

## How a reviewing Claude should use this

1. Run the checks in "Verify it yourself" below. Do not trust this document over the tests.
2. Read the diff by area (`git diff main --stat`, then the files in each section).
3. Check each claim marked **Behavior change**; those are the ones that alter what users receive.
4. Treat the "Owner-only actions" section as a task list for a human with admin rights. A Claude without admin cannot do them.
5. Report anything that contradicts this file instead of silently correcting it.

## What the branch changes, by area

### Security and input hardening
- **SMTP** now verifies certificates (`starttls` with `ssl.create_default_context()`).
- **`net_safety.py` (new):** `host_is` does dot-boundary host checks (so `evilgreenhouse.io` no longer matches `greenhouse.io`); `safe_get_text` fetches only http/https, only public IPs, checks every redirect hop, and caps responses at 1 MB. `notion_sync.py` uses it for applied-link HTML fetching and quotes ATS URL parts.
- **Untrusted feed fields:** `job_utils.clean_job` blanks control characters and non-http(s) URLs. Discord message text escapes `[ ] ( )` and spaces so a posting cannot rewrite the link.
- **Applied-link intake:** optional `allowed_user_ids` allowlist; at most 5 links per message and 20 per run. Extra links are deferred (cursor left in place), not dropped.
- **Pinger:** `internship-pinger/worker.js` alert bodies send `allowed_mentions: { parse: [] }`.
- **Supply chain:** `requests` pinned to `2.32.5`; `.github/dependabot.yml` (pip and github-actions, weekly).
- **Not fixed (needs the owner):** S1, S2, branch protection, S9. See below.

### Reliability and cost
- **Dead-letter parking:** a delivery that fails `max_delivery_attempts` times (default 20, about 3 hours) is parked in `delivery_state.json["dead"]` instead of retrying forever. The health summary shows `parked: N`.
- **Exit policy:** `source_health.health_exit_code` now fails a run only for a broad outage (10% or more of sources down), stuck deliveries, or a sync error. One stale board warns and no longer fails every run or triggers pinger alerts. This came from `oldmissioncapital`, which returned 404 for about 150 hours and failed every run.
- **ETag cache for the SimplifyJobs feed** (13 MB, previously downloaded every run). Off in dry runs; a full fetch is forced every hour and whenever filter settings change. The cache is in `health.json` source records.
- **`trim_health_noise.py` (new):** the workflow runs it before committing state. If no state file changed and only volatile `health.json` fields changed (timestamps, counts, ETag bookkeeping), it restores `health.json` from git. In the last 300 bot commits it would have skipped 152. This line in `watch.yml` takes effect only after merge.
- **Skipped on purpose, with measurements** (see `me_in/02-optimizations.md`): state pruning (`seen.json` grows about 100 IDs a day, and pruning risks re-alerts), fewer Notion calls (cannot be verified without a token), connection reuse (timings were noise).

### Filtering correctness
- **Whole-word keyword matching** (optional plural `s`): "intern" no longer matches "International" or "Internet". This dropped 83 non-internships from the matching set. Note "Marketing Technology Engineer Intern" is still excluded by "marketing".
- **`N/A`, `TBD`, `unknown`, `none` seasons count as unknown**, so `keep_unknown_terms` decides. Before, `N/A` looked like a season that never matched, which hid 97 of 214 recent Hardware listings.
- **New excludes:** `civil engineering`, `chemical`, `chemistry`, `structural`, `geotechnical`, `hvac`, `welding`.

### Coverage
- **Boards:** 28 added (25 hardware, quant and startup boards, plus Spaceium, Brumby and One Robot from the YC hardware search), and Old Mission moved to Ashby. Every slug was checked with `verify_boards.py`.
- **SimplifyJobs path** now `Summer2027-Internships`. **Whole categories** can be pulled: `simplify.include_categories` is `["Hardware", "Quant"]`, with `category_exclude` and `category_roles` filters. Category-only pulls go to the general channel, never TOP.
- **New aggregate feed `vanshb03`:** separate postings from SimplifyJobs (most recent entries were not in it). Config block `vanshb03` (`enabled`, `max_age_days` 3, `year` 2027). Its links are `go.vansh.nyc` shortlinks, so URL identity cannot dedupe it; the company, title, location and season fingerprint does, because seasons are labelled like Simplify's. Against the SimplifyJobs set we pull, 17 of 367 recent entries overlapped.
- **`discover_boards.py` (new, read-only):** guesses Greenhouse, Lever and Ashby slugs from names or the YC list (`--yc`, `--industry WORD`), probes them, and prints candidates. It never edits `config.json`.

### Routing: who gets pinged
- TOP webhook: the 200 configured boards and the `simplify.company_keywords` companies. Everything else goes to the general webhook.
- **`alert_channels` (new):** shared Discord channels matched on `roles`, `exclude_roles`, `companies`, `locations`, `terms`, `categories`. An entry must set at least one include filter (validation rejects an entry that would repeat every job). Several entries may share one webhook, and a job posts there once.
- **Shipped channels (silent until a webhook exists):** `swe`, `data`, `research`, `ml`, `embedded`, `hardware` (category entry plus a title entry), `quant` (category entry plus a title entry). Embedded and firmware titles go to `embedded` only; `swe` and `hardware` exclude them. Env names: `DISCORD_WEBHOOK_SWE`, `_DATA`, `_RESEARCH`, `_ML`, `_EMBEDDED`, `_HARDWARE`, `_QUANT`.
- **Watchlist:** a shared channel listing specific companies, documented in the README. It is not in `config.json` yet because it needs a company list.
- **No digests.** `CLAUDE.md` still says there are no digest messages, and the owner asked for per-job pings only.

## Behavior changes the owner should expect after merge

| Change | Effect |
| --- | --- |
| New boards, categories, N/A fix, vanshb03 | One-time burst of about 350 alerts (about 228 from boards and categories plus about 125 from vanshb03). At 50 Discord posts per run it drains over about 7 runs. |
| Whole-word matching | Fewer false positives; no alerts for "International"/"Internet" titles. |
| Exit policy | A single stale source no longer turns the run red. A broad outage still does. |
| `trim_health_noise.py` | Fewer bot commits to `main`. |
| New channel routing | No effect until webhooks are added to `PERSONAL_WEBHOOKS_JSON`. |

To soften the burst, lower `vanshb03.max_age_days` or `simplify.max_age_days` before merging.

## Verify it yourself

```bash
python3 -m unittest discover -s tests -v     # expect 117 passing
node --test internship-pinger/worker.test.js # expect 5 passing
python3 verify_boards.py                     # expect 200/200
python3 watcher.py --dry-run                 # fetch and print, writes nothing
git diff main --stat
```

Spot checks worth doing: `watcher.destinations` for a sample job with webhook env vars set; `source_health.health_exit_code` with one stale source; the `deliver` dead-letter path in `tests/test_watcher.py`.

## Do not break

- Keep `seen.json`, `delivery_state.json`, `message_map.json`, `notion_state.json`. Deleting them re-alerts history.
- Keep queue and cursor checkpoints durable in `deliver` and the Notion helpers. A run can fail after an external service accepted a request.
- Do not claim direct Workday coverage: Postman is covered through the aggregate feeds only, and its dead Greenhouse entry stays removed.
- Do not claim exactly-once delivery. A webhook timeout can mean Discord accepted the post.
- Verify every new board slug with `verify_boards.py` first.

## Owner-only actions (need admin on `avyukthNarra/-internship-watcher`)

Being listed in `CODEOWNERS` does not grant any of these. Settings changes need the Admin role.

1. **S1: stop collaborators reading secrets.** Settings → Environments → New environment (for example `production`); restrict deployment branches to `main`; move the repository secrets into the environment; add `environment: production` to the watcher job in `.github/workflows/watch.yml`. Confirm the pinger still dispatches on `main` afterwards.
2. **S2: personal data in a public repo.** Only `notion_state.json` is sensitive: its `users` entry holds a real Discord user ID, a name, and `applied` and `jobs` records with application URLs. `message_map.json` holds public job data for 3 days and is not personal. Options: (a) move `notion_state.json` to a private repo and change the workflow's persist step, or (b) retire Notion once Sheets tracking exists, then delete both files. Scrubbing already-published history needs a force push to `main` and affects every clone, so agree on it first.
3. **Protect `main`:** require pull requests, require code owner review, add a `CODEOWNERS` entry for `.github/workflows/`.
4. **S9:** confirm the pinger's `GH_PAT` is fine-grained, single-repo, Actions-only, and has an expiry.
5. **Secret scan:** run `gitleaks detect` on the full history; it was not run (not installed on the contributor machine).
6. **Discord:** create the role channels, make a webhook for each, and add them to the `PERSONAL_WEBHOOKS_JSON` secret as one JSON object. Editing the secret replaces the whole value, so keep existing entries. Do not touch the disabled `avyTamuGit/internship-watcher` deployment.

## Where it is going

1. **Now:** merge after review, create webhooks, add the watchlist companies.
2. **Website, Stage A (`web/`, Netlify or Vercel, not started):** a read-only job board with filters over a published `jobs.json`. Per-user data stays local in the browser with export and import. Gate: items 1 to 3 above, plus the merge.
3. **Application tracking:** a per-user Google Sheet through browser sign-in, with the full job description text fetched on demand. This would replace Notion pins and applied-link intake; once it works, `notion_state.json`, `message_map.json`, and Notion sync can be retired.
4. **Alerts without Discord:** a notification opt-in on the site. Real web push needs a small settings store and a VAPID key; an open-tab notification needs neither. iOS needs the site added to the home screen.
5. **Coverage as needed:** a Workday adapter (Postman and others have no direct board), a monthly `discover_boards.py --yc` run, and the Hardware Club lists as discovery input. Skipped on purpose: LinkedIn, Handshake, Wellfound (login or terms), Hacker News (low yield), Built In, Startup.jobs, Levels.fyi, EE Times and Embedded.com (no public feed; unverified).

## Open questions for the owner

- Is a one-time burst of about 350 alerts acceptable, or should the age windows shrink first?
- Which of S2 options (a) or (b)?
- Who should get admin, and who stays at write access?
- Do you want the shipped channel names and role keywords, or a smaller set?

## Where the detail lives

`me_in/00-CONTEXT.md` (system overview), `01-security-audit.md` (all S findings), `02-optimizations.md` (measurements), `03-scraper-guide.md` (how to extend), `04-todo.md` (checklist).
