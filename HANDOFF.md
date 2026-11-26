# Handoff: Supabase pipeline and website

Last updated 2026-11-25. The design is in `dbplan.md`; this file is the to-do list.

## Where things stand

- **Branch `avy-dev`:** has everything merged (PRs #14, #15, #16, #17). CI is green, including the `db` job.
- **PR #18 (`avy-dev` → `main`) is open:** https://github.com/avyukthNarra/-internship-watcher/pull/18. Nothing is live from GitHub Actions until it merges.
- **Supabase project `internship-watcher`:** ref `mkphndqkihjanumsyrli`, URL https://mkphndqkihjanumsyrli.supabase.co, free plan, us-east-1.
  - All migrations in `supabase/migrations/` are applied, and the security advisor is clean (only the three pipeline-only tables are flagged, intentionally locked).
  - It holds 923 jobs from a manual run on 2026-11-25. All have `first_seen` on that date, so the site shows them all as "New today" for the first day.
- **GitHub `production` environment secret:** `DATABASE_URL` (session pooler, host `aws-1-us-east-1.pooler.supabase.com`). The password is also saved in Pane as `internship-watcher/DB_PASSWORD`.
- **The Discord bot** now runs from the public legacy repo `avyukthNarra/internship-watcher-discord`, using state from the private `internship-watcher-state` repo. `watch.yml` is disabled in this repo.

## Next steps (in order)

1. **Merge PR #18.** It needs owner approval because it touches `.github/`.
   - After merging, `pipeline.yml` runs every 10 minutes (best effort).
   - Check the first scheduled run: it should report `Found N matching postings, K new` and `database sync OK`.
2. **Turn on sign-in in Supabase** (Authentication → Sign In / Providers):
   - **Discord:** discord.com/developers → app → OAuth2. Add the redirect `https://mkphndqkihjanumsyrli.supabase.co/auth/v1/callback`, then paste the client ID and secret into Supabase.
   - **Google:** Google Cloud Console → APIs & Services → Credentials → OAuth client (Web), with the same redirect URL. Paste the ID and secret into Supabase.
   - Turn on **Allow manual linking**, which the "Connect Discord" button in Settings needs.
   - Under URL Configuration, set the Site URL and add the redirect URLs `http://localhost:3000/**` and `https://<vercel-domain>/**`.
3. **Deploy the website on Vercel.** Import the repo with Root Directory `site`, Framework Next.js and Node 22.
   - Env vars: `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`. Both are public values, listed in `site/.env.example`.
   - Then add the Vercel domain to the Supabase redirect URLs.
4. **Smoke-test signed in:**
   - sign in with Discord, which should fill `profiles.discord_user_id`;
   - Save a job, then Mark applied, and check that `applied_at` and the follow-up date fill in;
   - edit the top-company list, then reset it to default;
   - export the tracker as CSV.
5. **Per-user alerts** (plan, "Pipeline changes", step 4): match new jobs to each user's preferences and top list with `job_utils.preference_matches`, add rows to `notifications`, and send Discord DMs (bot token) or email.
   - DMs only reach users who share a server with the bot.
   - The bot token is currently only in the legacy repo.
6. **Discord 📌 pins and `#applied` links → `user_jobs`:** match on `profiles.discord_user_id`. Notion sync is dropped here.

## Housekeeping

- **Pinger (Cloudflare Worker `internship-pinger`).** It still triggers the disabled `watch.yml` here, which causes hourly ⚠️ alerts.
  - In the Cloudflare dashboard → Worker → Settings → Variables, set `REPO` = `avyukthNarra/internship-watcher-discord`.
  - Add that repo to the pinger's fine-grained `GH_PAT`.
  - Check that `GH_PAT` is single-repo, Actions-only, and has an expiry.
- **Rotate the database password.** It appeared in a Claude session's output on 2026-11-25. Reset it in Supabase → Database settings, then update GitHub `production` → `DATABASE_URL` and the Pane secret.
- **Rotate the Notion token.** It was stored in plain text in an old local `.claude/settings.local.json` entry, since removed. The legacy bot has no `NOTION_TOKEN` yet, so Notion, pins and applied tracking are off there until one is added.
- **Remove the old deploy key** "internship-watcher bot (watch.yml)" from `internship-watcher-state`, and remove this repo's now-unused Discord and Notion secrets from `production`.
- **Delete stale remote branches:** `sai` and `dependabot/pip/requests-2.34.2`.
- **Workday 429s:** Sai owns this. The directions were emailed on 2026-11-25.

## Useful commands

```sh
scripts/db_test.sh                       # local Postgres: schema + RLS tests + DB tests
python -m unittest discover -s tests -v  # full suite (DB tests need TEST_DATABASE_URL)
DATABASE_URL=... python pipeline.py      # one pipeline run against Supabase
```
