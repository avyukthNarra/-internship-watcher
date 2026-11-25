# Workday laptop handoff

The Windows laptop fetches configured Workday boards on the home network every 30 minutes by default, searches five pages per board (ten for NVIDIA), and pushes a validated `workday_jobs.json` to a separate private repository. A changed result is committed immediately; unchanged results get a heartbeat every two hours. The watcher accepts results less than three hours old. All other sources still run. The laptop holds only a results-repository write deploy key, never Discord or Notion credentials. No self-hosted runner is used.

The owner must create a private `internship-watcher-workday` repository (or choose another name), initialize its default branch, add the laptop's public deploy key with write access, create a separate read-only deploy key for Actions, and add that private key as the `WORKDAY_DEPLOY_KEY` secret in the watcher repository’s `production` GitHub environment. Follow `laptop/README.md`, then approve the workflow PR. Deploy keys cannot be shared between GitHub repositories; use separate key pairs.

Proposed `watch.yml` change (replace `OWNER` and the repo name; insert after the existing watcher checkout, before the watcher runs):

```yaml
      - name: Checkout private Workday results
        uses: actions/checkout@v7
        continue-on-error: true
        with:
          repository: OWNER/internship-watcher-workday
          ssh-key: ${{ secrets.WORKDAY_DEPLOY_KEY }}
          path: workday-results
          persist-credentials: false
```

Add this environment variable to the existing watcher execution step's `env` mapping:

```yaml
          WORKDAY_RESULTS: ${{ github.workspace }}/workday-results/workday_jobs.json
```

After a block, the laptop stops requesting Workday and backs off for at least 30 minutes, doubling consecutive cooldowns up to six hours and honoring longer Retry-After values. If checkout fails, the file is missing, malformed, or stale, Workday is skipped with informational health status and no source-down alert. If the laptop is off or a board fetch fails, those boards are skipped; aggregate feeds still cover most postings. Check the laptop log, scheduled task, network, deploy keys, and private repo commit time. Git push failures retry with rebase; a conflict needs manual resolution.
