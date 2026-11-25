# Security and privacy audit

Scope: every tracked file in the repo, plus the git history for secret patterns. Findings marked **verified** were reproduced against the code or live data. Findings marked **by inspection** come from reading the code only.

Limits of this audit: the secret scan was pattern-based (webhook URLs, Notion/GitHub/Slack/AWS token shapes, Discord bot token shape) over tracked files and a history search for `api/webhooks`. It found nothing. It isn't exhaustive. Run a dedicated tool (`gitleaks detect`) before you rely on "no secrets in history". I did not test anything against live Discord, Notion or GitHub.

## Summary

| ID | Severity | Finding | Status |
| --- | --- | --- | --- |
| S1 | High | Anyone with write access can exfiltrate every secret via a branch workflow | by inspection |
| S2 | High | Public repo publishes a member's Discord ID, name, and saved/applied job list | verified |
| S3 | Medium | SSRF in applied-link parsing (no URL/IP checks, unbounded download) | verified |
| S4 | Medium | SMTP STARTTLS does not verify the server certificate | verified |
| S5 | Medium | No limits on what Discord members can make the bot do | by inspection |
| S6 | Medium | Untrusted feed text and URLs go into Discord markdown unescaped | by inspection |
| S7 | Low | Host checks use `endswith("domain")` without a dot boundary; path parts unquoted | verified |
| S8 | Low | Unpinned dependencies and actions, no Dependabot | verified |
| S9 | Low | Pinger token scope and alert hygiene | by inspection |
| S10 | Low | Public Actions logs and artifacts | by inspection |

## S1 — Secrets are reachable from any branch (High)

`watch.yml` can be started with `workflow_dispatch`, and a dispatch on a branch runs **that branch's copy** of the workflow file. Every secret (`DISCORD_WEBHOOK_URL`, `DISCORD_BOT_TOKEN`, `NOTION_TOKEN`, `SMTP_PASS`, `PERSONAL_WEBHOOKS_JSON`, …) is a repository-level secret. So anyone with write access can push a branch whose workflow prints or POSTs those secrets, then dispatch it.

This was a theoretical risk while one person owned the repo. It's real now that a second account (`Saibot913`) has push access, and it gets worse with every collaborator you add. This is about blast radius, not about trusting anyone. A leaked laptop token is enough.

**Fix:**
1. Create a GitHub Environment (Settings → Environments → `production`). Restrict deployment branches to `main`. Move the secrets there as *environment* secrets.
2. Add `environment: production` to the `watch` job in `watch.yml`.
3. Once state no longer lives on `main` (see S2), protect `main`: require a PR, require review, and add a `CODEOWNERS` entry for `.github/workflows/`.

Until step 1 is done, treat every collaborator as having full access to your Discord webhooks, Notion workspace, and email password.

## S2 — State files publish personal data (High)

The workflow commits `notion_state.json` and `message_map.json` to a **public** repo. I confirmed they contain:

- A Discord user ID (`552591070773641227`) and display name (`Floof`).
- The Notion tracker database ID and page IDs for that user.
- 80 saved-job IDs and **34 application URLs**, including ones like `…/bankofamerica.com/…/job-detail/14418/…` and `jobs.ashbyhq.com/notion/…/application`. That is a public list of where this person applied.
- Discord channel IDs and message IDs.

It's also permanent: there are 9,221 commits, and deleting the files from `main` doesn't remove them from history. Notion DB IDs alone can't be used without your token, but the Discord ID, name, and application history are personal data.

This matters a lot for the website. Other people's application history must never be in a public repo.

**Fix (pick one):**
- **Smallest change:** move the five state files to a *private* repo (or a private branch in a private mirror) and have the workflow check it out with a fine-grained token.
- **Better for the website:** keep state in a real store (Cloudflare KV/D1/R2 or Supabase). See `04-todo.md`.
- Separate the data: `seen.json`, `delivery_state.json` and `health.json` are public-safe. `notion_state.json` (users, applied URLs) and `message_map.json` are not. Moving just those two is a quick first step.
- If the personal data has to be purged from history, that's a history rewrite on a shared repo. Get everyone's agreement first. Rotating Notion DB IDs doesn't help.

## S3 — SSRF in the applied-link parser (Medium)

`notion_sync._parse_job_from_url` (lines ~455–464) does `requests.get(url)` on a URL pasted into the applied channel. The only guard is a timeout. Any member of that channel controls the URL. Gaps:

- No scheme check, no host/IP check. `http://127.0.0.1:…`, `http://192.168.x.x/…` and cloud metadata addresses are all fetchable. Redirects are followed, so a public URL can bounce to a private one.
- The response is read fully into memory (`r.text`). A multi-GB response stalls or crashes the run.
- Parsed `og:title`/`og:site_name` get written into Notion as company/role, so a hostile page controls those fields.
- On GitHub-hosted runners the blast radius is small. If you ever run the watcher locally (the README encourages it), this can reach services on your own machine and LAN.

**Fix:** allow only `http`/`https`; resolve the hostname and reject loopback, private, link-local and CGNAT ranges (also re-check after each redirect, or disable redirects and follow them manually); stream the body and stop at about 1 MB; cap the number of URLs processed per message and per run. Put the check in one `safe_get()` helper in a new `net_safety.py` and use it from both `_parse_job_from_url` and `_posting_open`.

## S4 — SMTP certificate is not verified (Medium)

`watcher.notify_email` calls `s.starttls()` with no context. I checked the stdlib source: with no context, `smtplib` uses `ssl._create_stdlib_context()`, which does **not** verify the certificate or hostname. A network attacker can intercept the connection and read `SMTP_PASS`. Only matters if email is enabled (it is optional).

**Fix (one line):** `s.starttls(context=ssl.create_default_context())` (add `import ssl`).

## S5 — No limits on what Discord members can trigger (Medium)

- Any non-bot user who reacts 📌 to a job message gets a **new Notion database created** under your parent page (`_ensure_tracker`). There is no allowlist. Someone who joins the server can create unlimited databases.
- The applied channel has no per-message or per-run URL cap. Each URL costs up to 20 s of fetching plus ATS calls. A pasted wall of links can consume the 30-minute job budget and starve the main scan.
- `_pin_reactors` reads only the first 100 reactors of a message.

**Fix:** add `allowed_user_ids` (or "must have a `profiles` entry") to `config.json` and ignore everyone else; cap URLs per message (say 5) and tracker creations per run; log and skip the rest.

## S6 — Feed text goes into Discord markdown unescaped (Medium)

`notify_discord` builds `**{company}** — [{title}]({url})`. SimplifyJobs and Jobright are community-maintained, and ATS boards are company-controlled, so these strings are untrusted. A title containing `](https://evil.example)` or a URL containing `)` or spaces breaks or rewrites the link. Non-HTTP schemes aren't validated either. The good news: `allowed_mentions: {"parse": []}` is set, so `@everyone` spam is blocked.

A related reliability effect: an invalid `url` sent to Notion's `Link` property returns HTTP 400 forever. See R2.

**Fix:** a `clean_job()` step at the fetch boundary that coerces fields to strings, strips control characters and newlines, escapes `[]()` in titles, requires `http(s)://` URLs, and percent-encodes `(`, `)` and spaces. Drop jobs that fail validation and count them in `health.json`.

## S7 — Loose host matching (Low)

`notion_sync.py` uses `host.endswith("greenhouse.io")` (also `lever.co`, `ashbyhq.com`, `smartrecruiters.com`, `myworkdayjobs.com`) at lines ~354–357, 381, 402, 407, 413, 714, 727, 731. That also matches `evilgreenhouse.io`. `job_utils.job_identity` already does it correctly (`host == d or host.endswith("." + d)`). Impact is low (it just calls the real ATS API with an attacker-chosen slug), but it's an easy hardening: one shared `host_is(host, domain)` helper. Also wrap path segments inserted into API URLs with `urllib.parse.quote(part, safe="")`.

## S8 — Supply chain hygiene (Low)

`requirements.txt` is `requests>=2.31` (any newer version, no lockfile). All workflow actions are pinned to tags (`checkout@v5`, `setup-python@v6`, `setup-node@v4`, `upload-artifact@v7`), not commit SHAs. They're all first-party GitHub actions, which lowers the risk. There's no `.github/dependabot.yml`.

**Fix:** pin to `requests==<tested version>` (2.32.5 is installed locally), pin actions to SHAs, add Dependabot for `pip`, `github-actions` and `npm`. This is already item 3 in `IMPROVEMENTS.md`.

## S9 — Pinger token and alerts (Low)

- The Worker has no inbound routes (only a cron trigger) and `workers_dev = false`, so it has no public attack surface. Good.
- `GH_PAT` should be a **fine-grained** token limited to this one repository with only Actions read/write. Give it an expiry and rotate it. Never use a classic `repo` token.
- `deliverAlert` doesn't set `allowed_mentions`. Add `allowed_mentions: { parse: [] }` so GitHub-supplied text can never ping anyone.
- The Worker dispatches the workflow every 10 minutes *and* the workflow has its own `*/10` cron. Both fire. The concurrency group stops overlap, so it's harmless, but it's redundant.

## S10 — Public logs and artifacts (Low)

Actions logs on a public repo are public. The code is careful: it prints exception *type names*, not messages, so no webhook URLs leak. The exceptions are `print(... r.text[:200])` for Notion and Discord error bodies (`notion_sync.py` ~111 and ~224), which can echo IDs. Artifacts on a public repo can be downloaded by any signed-in GitHub user, so the `watcher-state-*` upload contains the same data as S2. Drop `notion_state.json` and `message_map.json` from the upload once S2 is fixed.

## What is done well

- No secrets in tracked files or in the history patterns searched. `.env*` is git-ignored.
- Secrets are read only from the environment. Webhook URLs are never logged.
- `allowed_mentions` blocks mass pings. `PERSONAL_WEBHOOKS_JSON` is fully validated before use. `webhook_env` names must start with `DISCORD_WEBHOOK_`.
- Config is validated strictly before a run starts. Atomic state writes (`mkstemp` + `fsync` + `os.replace`).
- `test.yml` runs with `contents: read` and no secrets, so fork PRs can't reach secrets.
- Bot permissions are minimal (view, read history, add reactions). The Notion integration is scoped to one parent page.

## Fix order

1. S1 environment gate (10 minutes, no code).
2. S2 move `notion_state.json` + `message_map.json` out of the public repo.
3. S4 one-line SMTP fix; S9 `allowed_mentions` and token scope.
4. S3 + S5 + S6 + S7 as a single "input hardening" change with tests.
5. S8 pinning and Dependabot.
