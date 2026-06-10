# Internship Watcher

Monitors 100+ top tech companies, AI startups, and quant firms for new AI/SWE internship postings every 10 minutes, pings a Discord server the moment something drops, and files jobs into per-member Notion trackers via 📌 reactions.

```
                       ┌──────────────────────────────────────────┐
                       │   GitHub Actions (every 10 min, free)    │
                       └──────────────────────────────────────────┘
                                          │
        ┌───────────────────┬─────────────┴──────────────┬────────────────────┐
        ▼                   ▼                            ▼                    ▼
  107 company boards   SimplifyJobs feed         Jobright/InternList    (your additions)
  Greenhouse / Lever   (Google, NVIDIA, Meta,    GitHub repos (SWE +
  / Ashby JSON APIs    other Workday-only cos)   Data-Analysis lists)
        │                   │                            │
        └───────────┬───────┴──────────┬─────────────────┘
                    ▼                  ▼
          keyword filter      cross-source dedup (seen.json
          (intern, co-op…)    + company+title fingerprints)
                    │
       ┌────────────┴───────────────┐
       ▼                            ▼
  ⭐ top-companies channel     # general channel            ┌─► Notion master log
  (curated boards +           (everything else        ─────┤   (all postings)
  big-tech feed)              from the firehose)           └─► 📌 react → your own
                                                               Notion tracker
```

## How it works

Each run, `watcher.py`:

1. Fetches all job boards in `config.json` in parallel (~10s for 107 boards) plus two aggregated feeds: **SimplifyJobs** (covers Workday-only companies like Google, NVIDIA, Tesla, Microsoft) and **Jobright** (which also runs intern-list.com; their GitHub repos republish listings from LinkedIn, Indeed, Handshake, and 200K+ career sites).
2. Filters titles against `include_keywords` / `exclude_keywords` and the configured terms (currently Fall 2026 – Summer 2027).
3. Dedupes against `seen.json` — by posting id, and for aggregator entries also by a company+title fingerprint, so a job appearing on a company board *and* Simplify *and* Jobright notifies exactly once.
4. Posts each genuinely new job as its own Discord message. Jobs from the curated boards or the big-tech feed go to the **top-companies** webhook; the rest go to the **general** webhook. Batches over 25 (e.g. first seeding) are posted as a digest instead.
5. Logs every new posting to the shared **"All Internship Postings"** Notion database, then polls 📌 reactions on recent job messages and files those jobs into the reacting member's personal Notion tracker (auto-created on first reaction).

No HTML scraping anywhere — every source is a stable JSON API or a markdown file in a public repo, which is why it doesn't break weekly.

## Full setup from scratch

### 1. Fork/push the repo and enable Actions

Push these files to a GitHub repo. `.github/workflows/watch.yml` runs every 10 minutes (GitHub treats schedules as best-effort; expect 10–15 min in practice). Trigger it once manually from the **Actions** tab to seed `seen.json` — the first run digests everything currently open.

### 2. Discord webhooks (notifications)

For each channel you want (top-companies and/or general):

1. Server Settings → **Integrations** → **Webhooks** → **New Webhook**
2. Name it, point it at the right channel, **Copy Webhook URL**
3. Repo → Settings → Secrets and variables → Actions → **New repository secret**:
   - `DISCORD_WEBHOOK_URL` — the general/firehose channel
   - `DISCORD_WEBHOOK_URL_TOP` — the top-companies channel (optional; falls back to the general one)

### 3. Notion (shared log + personal trackers, optional)

1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations) → **New integration** (type: Internal). Copy the secret → repo secret `NOTION_TOKEN`.
2. Create a Notion page to hold everything (e.g. "Internship Hub"). On that page: **•••** → **Connections** → add your integration.
3. The page id is the 32-hex-char string at the end of the page URL (dashes optional) → repo secret `NOTION_PARENT_PAGE_ID`.
4. Share that page with your server members (Share → invite, or publish to web) so they can see their trackers.

### 4. Discord bot (📌 reaction tracking, optional)

Needed only so the watcher can *read* reactions; it never posts.

1. [discord.com/developers/applications](https://discord.com/developers/applications) → **New Application** → **Bot** → **Reset Token** → copy → repo secret `DISCORD_BOT_TOKEN`. No privileged intents needed.
2. OAuth2 → URL Generator: scope `bot`, permissions **View Channels** + **Read Message History**. Open the generated URL and invite the bot to your server.
3. Make sure the bot's role can see the channels the webhooks post into.

### Secrets summary

| Secret | Required for | 
| ------ | ------------ |
| `DISCORD_WEBHOOK_URL` | all Discord notifications |
| `DISCORD_WEBHOOK_URL_TOP` | separate top-companies channel |
| `NOTION_TOKEN` + `NOTION_PARENT_PAGE_ID` | Notion master log + trackers |
| `DISCORD_BOT_TOKEN` | 📌 per-member tracking |
| `SMTP_USER`, `SMTP_PASS`, `ALERT_EMAIL` | optional email alerts (Gmail app password) |

## Using it (for server members)

- Watch the channels; every message is one internship.
- React **📌** to any job within 3 days of posting → within ~10 minutes it appears in "📌 *your name*'s Internship Tracker" in Notion with Status **Saved**.
- Update Status in Notion as you go: Saved → Applied → OA → Interview → Offer / Rejected.

## Customizing

- **Add a company**: find its careers page. `boards.greenhouse.io/<slug>` → `"ats": "greenhouse"`; `jobs.lever.co/<slug>` → `"ats": "lever"`; `jobs.ashbyhq.com/<slug>` → `"ats": "ashby"`. Add to `companies` in `config.json`. Verify slugs first with `python3 verify_boards.py` (add candidates to its list) — wrong slugs 404 silently.
- **Adding a company also promotes it**: channel routing treats any company in `companies` or `simplify.company_keywords` as "top".
- **Tune the Simplify feed**: `simplify.terms` filters by season; `company_keywords` controls which companies from the giant feed you hear about; `max_age_days` ignores stale postings.
- **Tune Jobright volume**: `jobright.repos` — drop `2026-Data-Analysis-Internship` to halve the firehose, or disable with `"enabled": false`. Repo names track Jobright's categories at [github.com/jobright-ai](https://github.com/jobright-ai); bump the year as they roll over.
- **Narrow to ML/research only**: set `include_keywords` to e.g. `["machine learning intern", "research intern", "ml intern", "ai intern"]`.

## State files (committed back by the workflow)

| File | Contents |
| ---- | -------- |
| `seen.json` | every posting id + company+title fingerprint ever notified. Delete to re-alert on everything. |
| `message_map.json` | Discord message id → job, for reaction tracking (3-day rolling window) |
| `notion_state.json` | Notion database ids + which jobs are filed per member |

## Troubleshooting

- **`[warn] ... -> HTTP 404` in logs**: a company changed its board slug — re-verify with `verify_boards.py` and update `config.json`.
- **No notifications but runs are green**: check the run logs — "0 new" is normal most runs; postings cluster in bursts (especially Aug–Oct).
- **Duplicate pings**: dedup fingerprints are exact company+title; minor title variants across sources can slip through occasionally.
- **Schedule stops after ~60 days of repo inactivity**: GitHub disables idle workflows; the bot's `seen.json` commits normally prevent this, but if it pauses, re-enable from the Actions tab.
- **Workflow push conflicts**: the persist step rebases before pushing; if you push config changes mid-run it may retry next cycle. Run `git pull --rebase` locally before editing.

## Local run (testing / alternative to Actions)

```bash
pip install -r requirements.txt
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."   # optional
python3 watcher.py
```

Everything is env-var driven; with nothing set it prints findings to the console.
