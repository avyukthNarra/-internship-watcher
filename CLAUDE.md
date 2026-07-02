# CLAUDE.md — project context for future sessions

## What this is
A deployed internship-alert system for the owner (CS student, junior year fall 2026, hunting Summer 2027 AI/SWE internships). It runs on GitHub Actions every 10 minutes — there is no server. The README has full architecture and setup docs; read it first.

## Deployment facts (not in the README)
- Live repo: `github.com/avyukthNarra/-internship-watcher` (public, note the leading `-` in the name; account `avyukthNarra`). This directory is the checkout (check `git remote -v` before assuming).
- The ORIGINAL deployment `github.com/avyTamuGit/internship-watcher` still exists but its watch.yml was disabled 2026-07-02 (its `DISCORD_BOT_TOKEN` went 401 on 2026-06-27 when the bot token was reset during the account migration, and it was double-posting every job to Discord and the Notion master DB). Don't re-enable it while the new repo runs.
- `gh` CLI is NOT installed on this machine. The macOS keychain token (extract with `git credential fill`, protocol=https, host=github.com) belongs to the OLD account `avyTamuGit` — it can read the new public repo/Actions logs but NOT its secrets or admin. Pushing to the new repo uses SSH.
- Secrets on the LIVE repo (verified working via Actions logs, July 2026): `DISCORD_WEBHOOK_URL`, `DISCORD_WEBHOOK_URL_TOP`, `DISCORD_BOT_TOKEN` (bot "IntershipTracker", REST only), `NOTION_TOKEN`, `NOTION_PARENT_PAGE_ID` (page "Internship Hub"), `APPLIED_CHANNEL_ID` (#applied channel). Both repos pointed at the SAME Notion databases (`notion_state.json` was copied at migration).
- GitHub schedules are heavily throttled in practice: cron says `*/10` but runs fire every ~1–4.5 h (median ~2 h, measured over 200+ runs). This—not code—is why 📌 reactions take hours to reach Notion.
- GitHub secrets are written via the API with libsodium sealed-box encryption (PyNaCl is installed for this).
- Owner's Discord display name is Floof; their personal Notion tracker already exists.

## Working rules learned in this project
- **Never add a company board slug without verifying it live** — wrong slugs 404 silently forever. Add candidates to `verify_boards.py` and run it; only keep slugs that return jobs.
- **Always `git pull --rebase` before committing** — the Actions bot commits `seen.json`/`message_map.json`/`notion_state.json` back every run, so the remote moves constantly.
- Deleting `seen.json` re-alerts on every open posting (~450+ messages). Don't do it casually; >25 new jobs in a run falls back to a digest message (no 📌 tracking on digests).
- The SimplifyJobs feed URL still points at the `Summer2026-Internships` repo, which carries Summer/Fall 2027 terms via its `terms` field. When SimplifyJobs eventually starts a `Summer2027-Internships` repo, update `SIMPLIFY_URL` in `watcher.py`. Same for the Jobright repo years in `config.json` (`jobright.repos`).
- Jobright runs intern-list.com — they are the same source; don't add intern-list separately.
- Instagram story scraping (zero2sudo) was evaluated and deliberately skipped: login-walled, datacenter IPs get blocked (won't work from Actions), ban risk, and his links duplicate sources already covered. Don't re-propose it unless the user asks.
- Tokens were pasted into chat at setup time. If the user reports webhook spam or anything odd: rotate the Discord webhooks/bot token and Notion secret, then update the repo secrets via the API.
