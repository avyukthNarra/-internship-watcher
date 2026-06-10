# CLAUDE.md — project context for future sessions

## What this is
A deployed internship-alert system for the owner (CS student, junior year fall 2026, hunting Summer 2027 AI/SWE internships). It runs on GitHub Actions every 10 minutes — there is no server. The README has full architecture and setup docs; read it first.

## Deployment facts (not in the README)
- Live repo: `github.com/avyTamuGit/internship-watcher` (public — keeps Actions minutes unlimited). This directory is the checkout.
- `gh` CLI is NOT installed on this machine. GitHub API calls (secrets, workflow dispatch, repo admin) use the token stored in the macOS keychain: extract with `git credential fill` (protocol=https, host=github.com). Pushing uses SSH (account `avyTamuGit`).
- All five secrets are configured and verified working end-to-end (June 2026): `DISCORD_WEBHOOK_URL` (general channel), `DISCORD_WEBHOOK_URL_TOP` (top-companies channel), `DISCORD_BOT_TOKEN` (bot "IntershipTracker", reads 📌 reactions via REST only), `NOTION_TOKEN`, `NOTION_PARENT_PAGE_ID` (page "Internship Hub").
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
