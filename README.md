# Internship Watcher

Continuously monitors top tech companies and AI startups for new internship postings and pings you on Discord and/or email. Instead of fragile HTML scraping, it polls the stable public JSON APIs behind most career pages (Greenhouse, Lever, Ashby) plus two aggregated feeds: SimplifyJobs (covers Workday-based companies like Google, NVIDIA, Tesla, Microsoft) and Jobright/intern-list.com (their GitHub repos republish listings sourced from LinkedIn, Indeed, Handshake, and 200K+ career sites). Jobs appearing in multiple sources are deduped by a company+title fingerprint, so each role notifies once.

## How it works

Every run, `watcher.py` fetches all job boards listed in `config.json`, filters titles against your `include_keywords` / `exclude_keywords`, drops anything already recorded in `seen.json`, sends a notification for genuinely new postings, and updates `seen.json`. Run it on a schedule and it becomes a continuous monitor.

## Setup (GitHub Actions — recommended, free, runs 24/7)

1. Create a new GitHub repo and push these files.
2. In a Discord server you control: Server Settings → Integrations → Webhooks → New Webhook → copy the URL.
3. In the repo: Settings → Secrets and variables → Actions → add secret `DISCORD_WEBHOOK_URL` with that URL.
4. (Optional email) Add secrets `SMTP_USER`, `SMTP_PASS` (for Gmail, use an App Password from myaccount.google.com/apppasswords), and `ALERT_EMAIL`.
5. Done — `.github/workflows/watch.yml` runs every 30 minutes and commits `seen.json` back so you're never re-notified. Trigger it manually once from the Actions tab to seed the history (the first run will alert on everything currently open).

## Setup (local cron alternative)

```bash
pip install requests
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
python watcher.py
```

Then `crontab -e` and add: `*/30 * * * * cd /path/to/internship-watcher && DISCORD_WEBHOOK_URL="..." python3 watcher.py >> watcher.log 2>&1`

## Customizing

- **Add a company**: find its careers page URL. `boards.greenhouse.io/<slug>` → `"ats": "greenhouse"`; `jobs.lever.co/<slug>` → `"ats": "lever"`; `jobs.ashbyhq.com/<slug>` → `"ats": "ashby"`. Add the slug as `board` in `config.json`. If a board returns 404 warnings in the logs, the slug changed — check the careers URL.
- **Tune the aggregated feed**: `simplify.company_keywords` filters which companies from the big feed you hear about (empty list = all of them, which is noisy), `terms` filters by season, `max_age_days` ignores stale postings.
- **Narrow to ML/research roles**: change `include_keywords` to e.g. `["machine learning intern", "research intern", "ml intern", "ai intern"]`.

## Notes

- Postings on Workday-only career sites (Google, Apple, NVIDIA, etc.) come in through the Simplify feed rather than direct polling, since Workday has no friendly public API.
- `seen.json` is the only state. Delete it to re-alert on everything.
