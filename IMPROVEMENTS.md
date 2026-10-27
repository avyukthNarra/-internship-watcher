# Maintenance priorities

These are follow-up suggestions, not migrations performed by this refactor.

## 1. Separate source coverage warnings from delivery failures

The current policy marks a run failed whenever one source stays down for five hours, even if every notification and tracker update succeeds. The Postman and Wayve migrations showed how this can produce a long streak of failed runs that hides an otherwise healthy pipeline. Report stale sources separately from pending delivery/sync errors, with per-company warnings and a clear threshold for a broad source outage.

There is an existing local Source Doctor commit that could help track dead boards, but it is not deployed and its required Claude credentials are absent. Review its permissions, cost limits, and behavior on missing credentials before enabling it. Keep manual board verification available independently of that automation.

## 2. Move runtime state out of the main code branch

The workflow currently commits five state files to `main` after scans. This mixes operational updates with code changes and creates a rebase/push race with development. A dedicated state branch would separate the histories while keeping the current recovery artifacts. A durable database/object store is a larger alternative if concurrent workers become necessary.

Either migration needs a tested restore procedure that preserves exact identities, pending deliveries, Discord message mappings, and Notion cursors. Do not delete or reseed the existing history to make the migration easier.

## 3. Make installs reproducible

`requirements.txt` currently allows any `requests` version above its minimum. Record a tested dependency set and update it deliberately, with automated dependency-update PRs. Consider pinning workflow actions to reviewed commit SHAs as well. This makes a failed deployment easier to reproduce without freezing updates indefinitely.

## 4. Measure feed freshness and coverage

HTTP success and valid JSON do not prove that a source is publishing current internships. Record fetched counts, newest posting timestamps when available, and matching counts per source. Alert on sustained, unusual drops rather than treating every empty board as broken. Include the configured season and aggregate feed URLs in the health summary so seasonal feed changes are easier to audit.

## 5. Restore direct Postman coverage if it matters

Postman now relies on the existing aggregate feeds because its new Workday board is unsupported. A small, tested Workday adapter could restore direct coverage, but it must handle pagination, stable posting identities, and source failures. Prioritize it based on actual gaps in the aggregate feeds rather than adding another feed by default.
