# Internship pinger

This Cloudflare Worker dispatches the repository's `watch.yml` workflow every
10 minutes and checks the completed runs for failures and stale successes. It
uses the workflow-specific GitHub endpoint:

`/actions/workflows/watch.yml/runs?status=completed&per_page=10`

Alerts are stateless and use `event.scheduledTime`: only the first normal
scheduled tick in each UTC hour (minutes 00–09) sends a reminder. A continuing
failure therefore gets one reminder per hour under normal cron delivery; a
platform redelivery of the same event can duplicate a reminder because the
worker stores no state. The worker does not claim to remember whether it
already alerted for a particular failure streak.

## Deploy

Install and authenticate Wrangler, then run these commands from this directory:

```sh
wrangler login
wrangler secret put GH_PAT
wrangler secret put DISCORD_WEBHOOK_URL
wrangler deploy
```

`GH_PAT` needs permission to dispatch workflows and read Actions runs.
`DISCORD_WEBHOOK_URL` is optional; without it, monitoring still runs and logs
that alert delivery was skipped. The repository defaults to
`avyukthNarra/-internship-watcher`. To point the worker at another repository,
set the optional `REPO` environment value (for example with
`wrangler secret put REPO`). No HTTP route is required; the cron trigger in
`wrangler.toml` runs it every ten minutes.

Run the local tests with:

```sh
npm test
```
