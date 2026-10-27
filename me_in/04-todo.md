# To-do list (in order)

Nothing here has been done yet. These docs are the only change on your branch. Each item points at the finding that explains it. Tick them off as you go.

Ground rules for every change: keep the tests green (`python3 -m unittest discover -s tests -v`, `node --test internship-pinger/worker.test.js`), never delete or reseed the state files, and verify any new board with `verify_boards.py`.

## Phase 0 — Today, no code

- [ ] Commit `me_in/` on your branch and push, then open a PR into `main`.
- [ ] **S1:** create a GitHub Environment limited to `main`, move the secrets into it, add `environment:` to `watch.yml`. (This needs the repo owner, `avyukthNarra`.)
- [ ] **S9:** confirm the pinger's `GH_PAT` is a fine-grained, single-repo, Actions-only token with an expiry.
- [ ] Run `gitleaks detect` on the full history to back up the pattern scan in the audit.

## Phase 1 — Stop the bleeding (small, safe changes)

- [x] **R1 (board):** `oldmissioncapital` moved to Ashby (`old-mission-capital`). Done 2026-10-27.
- [x] **S4:** `starttls()` now verifies the certificate. Done.
- [x] **J1 + J2:** whole-word keyword matching with tests. Done. ("Marketing Technology Engineer Intern" is still excluded; see `02-optimizations.md` J2.)
- [x] **R3 + R4 + S6:** `clean_job()` plus Discord link escaping, with tests. Done.
- [x] **R2:** per-destination catch-all, 20-attempt cap, `dead` list, not counted as pending. Done (committed locally).
- [x] **J4 (URL):** `SIMPLIFY_URL` points at `Summer2027-Internships`. Done.
- [x] **S9 (mentions):** pinger sets `allowed_mentions`. Done. Token scope still to confirm.

## Phase 2 — Make the pipeline cheaper and cleaner

- [ ] **R5:** stop committing `health.json` every run (or only commit when state changed).
- [ ] **R6:** one authority for seen IDs; split the pending queue from history; prune IDs not seen for about 180 days (behind a test).
- [ ] **P1:** ETag/conditional GET for the 13 MB SimplifyJobs feed.
- [ ] **P2:** per-thread `requests.Session`. Measure `--dry-run` time before and after.
- [ ] **R7 + R8:** throttle the Notion stats refresh; look up master-log rows by `Link` filter instead of scanning the whole table.
- [ ] **R1 (real fix):** exit non-zero only for stuck deliveries, sync errors, or a broad outage; report single stale sources as warnings.
- [ ] **S8:** pin `requests`, pin actions to SHAs, add `.github/dependabot.yml`.

## Phase 3 — Input hardening

- [ ] **S3:** `net_safety.safe_get()` (scheme allowlist, private-IP block, redirect re-check, 1 MB cap). Use it in `_parse_job_from_url` and `_posting_open`.
- [ ] **S5:** `allowed_user_ids` in config, per-message and per-run URL caps, and a cap on tracker creations per run.
- [ ] **S7:** shared `host_is()` helper and `quote()` on path segments in API URLs.

## Phase 4 — Privacy and state (do this before the website)

- [ ] **S2:** move `notion_state.json` and `message_map.json` out of the public repo (private repo first; a real database if the website goes multi-user). Remove them from the artifact upload.
- [ ] Protect `main` (PR required, `CODEOWNERS` on `.github/workflows/`), now that the bot no longer needs to push state there.
- [ ] Decide whether the already-committed personal data needs a history rewrite. That affects everyone with a clone, so get agreement first.

## Phase 5 — More coverage (only as needed)

- [ ] **J5:** list tracked companies that have no direct board and decide which are worth an adapter.
- [ ] Workday adapter (pagination, stable IDs, source-failure handling), then SmartRecruiters/Workable as needed. Follow `03-scraper-guide.md`.
- [ ] **J3:** optional global `role_keywords` filter for the shared channels.
- [ ] Re-check for a Jobright 2027 repo; drop `Fall 2026` from `terms` in December.

## Phase 6 — FINAL TASK: the website (Netlify or Vercel)

Do this last. A site that other people use brings back everything in Phase 4, because it handles other people's data.

**Recommended path: two stages.**

**Stage A — public, read-only job board (no accounts, no personal data).**
- Have the watcher also write a `jobs.json` (company, title, location, URL, season, source, first-seen time, "top" flag) containing only data that is already public. Publish it with the site, not in `main`'s state files.
- Static front end on Netlify or Vercel (either is fine; both deploy from GitHub on push and give preview URLs for branches). Search, filters for company/role/season/location, newest first, "new in the last 24h", and an Apply link.
- Rebuild or refresh: the Actions run can trigger a deploy hook after each scan, or the site fetches `jobs.json` at runtime from a stable URL. A runtime fetch avoids redeploying every 10 minutes.
- Your branch (`sai-contributions-setting_up_website`) is the right place for this. Keep the site in its own folder (for example `web/`) so the watcher is untouched.

**Stage B — accounts, saved jobs and applied tracking (only if people need it).**
- Needs sign-in (Discord OAuth fits, since users are already on Discord), a database for per-user data (Supabase, Neon, or Cloudflare D1), and per-user preferences replacing `profiles` in `config.json`.
- This replaces the Notion-per-user design for website users, so decide whether Notion stays as an optional export.
- Prerequisites: S2 done, S5 limits in place, and any user-supplied webhook URL validated to be `https://discord.com/api/webhooks/…` or `discordapp.com`. Never fetch arbitrary user URLs without S3's `safe_get()`.
- Netlify and Vercel functions have execution time limits and no persistent disk. Keep the scraper on GitHub Actions or a scheduled worker, and let the site only read from the database.

**Decisions I need from you before building:**
1. Netlify or Vercel? (No strong technical difference here. Pick the one you already have an account on.)
2. Stage A only, or Stage B as well?
3. Who is the audience: friends in your Discord, or anyone on the internet? This decides how much of Phase 4 is mandatory first.
4. Site name or domain, if you have one.
