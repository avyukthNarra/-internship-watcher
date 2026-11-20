# Internship Watcher implementation backlog

**Audit base** `53c995b2c232c1f6cf6a962209858331e411e2b3`\
**Evidence** [findings.md](findings.md)

Use the stable `Txx` IDs in commits or issues. Each task links to the evidence that motivated it. **P0** contains production or privacy risk. **P1** prevents lost work or misleading health. **P2** improves correctness, throughput, or maintainability. **P3** covers measured or optional improvements. Dependency IDs are hard sequencing constraints. Interleaving unrelated tasks is fine.

## Production safety, state and recovery

- [ ] **T01 · P0 · Fence the production workflow and manual ping.**\
  **Evidence** [OPS-01](findings.md#ops-01), [SAFE-04](findings.md#safe-04) · **Depends on** none.\
  **Done when** a protected environment and write-permission boundary enforce which ref can load production credentials, notify, or publish state. Feature-branch previews use read-only permissions and isolated or absent sinks. State publication reads a manifest and cannot publish checked-out application code. Verify this in offline workflow checks and an isolated test repository.

- [ ] **T02 · P0 · Make a validated private recovery snapshot before Git operations.**\
  **Evidence** [OPS-02](findings.md#ops-02), [SAFE-01](findings.md#safe-01) · **Depends on** none.\
  **Done when** recovery captures one immutable state generation before rebase with run ID, run attempt, schema version, hashes, record counts and producer-level generation membership. Verify that acknowledged receipts, cursors and queue state agree across files. A forced synthetic conflict leaves the newest complete private generation available. Restore rejects corrupt or mixed generations and succeeds twice without changing acknowledged state.

- [ ] **T03 · P0 · Stop publishing user-linked operational data.**\
  **Evidence** [SAFE-01](findings.md#safe-01), [SAFE-02](findings.md#safe-02), [TRK-06](findings.md#trk-06) · **Depends on** T02.\
  **Done when** state, production profiles if populated, and full recovery artifacts use access controls in a private interim snapshot store or the final durable store. Public outputs are checked for synthetic markers representing identities, applied URLs, query values and provider object IDs. The owner records decisions on historical exposure, cleanup and Notion sharing. Use a single authorized writer through cutover and retain an approved private backup.

- [ ] **T04 · P1 · Read current state before every writer sends.**\
  **Evidence** [OPS-01](findings.md#ops-01), [OPS-02](findings.md#ops-02), [OPS-03](findings.md#ops-03) · **Depends on** T01.\
  **Done when** a queued job or rerun from an older code revision reads the latest compatible state after acquiring the writer lock. A second local process cannot write the same state concurrently. Synthetic stale-rerun and concurrent-writer tests preserve prior delivery acknowledgments.

- [ ] **T05 · P1 · Move runtime writes to a private durable store.**\
  **Evidence** [OPS-02](findings.md#ops-02), [OPS-03](findings.md#ops-03), [SAFE-01](findings.md#safe-01), [DEL-01](findings.md#del-01) · **Depends on** T02, T03, T04, T09.\
  **Done when** a versioned importer matches canonical counts and per-record identities, queues, receipts, cursor values and authorization scope. A write fence prevents conflicting writers, checkpoints survive runner loss and a clean run no longer creates a code-history commit. Test crash after intent, after acceptance, and after partial progress. Rehearse latest-generation rollback before enabling production writes.

- [ ] **T06 · P0 · Bound Applied enrichment and sanitize integration diagnostics.**\
  **Evidence** [SAFE-02](findings.md#safe-02), [TRK-01](findings.md#trk-01) · **Depends on** none.\
  **Done when** supported ATS enrichment uses an explicit outbound policy. Generic enrichment, if kept, validates public destinations and every redirect and limits bytes and elapsed time. Unsupported links can still be filed without a fetch. Offline boundary tests cover rejection and fallback with synthetic URLs. Logs contain endpoint classes and reason codes instead of response bodies or full user links.

- [ ] **T07 · P0 if SMTP is enabled · Authenticate the SMTP peer before login.**\
  **Evidence** [SAFE-03](findings.md#safe-03) · **Depends on** none.\
  **Done when** SMTP passes a certificate- and hostname-verifying TLS context, and a mocked provider records that login follows completed verified negotiation. The configured provider works in an authorized isolated setup.

- [ ] **T08 · P1 · Make production readiness explicit.**\
  **Evidence** [SAFE-04](findings.md#safe-04), [OPS-06](findings.md#ops-06) · **Depends on** T01.\
  **Done when** scheduled runs validate expected routes, credential pairs and reserved webhook keys. Missing required credentials produce a redacted preflight report and an unhealthy run. Tests cover all-absent, partly configured, profile-only and explicitly blank settings. Explicit local preview still exits successfully without writes.

## Delivery and notification reliability

- [ ] **T09 · P1 · Make a returned Discord receipt recoverable.**\
  **Evidence** [DEL-01](findings.md#del-01), [OPS-02](findings.md#ops-02) · **Depends on** none.\
  **Done when** a successful response's message receipt is retained independently of the pin-map write. An injected failure while saving the map is recoverable from the receipt without posting again. Document the remaining case where the provider accepts but no receipt reaches the application. Carry this contract to the durable store in T05.

- [ ] **T10 · P1 · Give each destination a retry lifecycle and fair scheduling.**\
  **Evidence** [DEL-02](findings.md#del-02), [DEL-03](findings.md#del-03), [SAFE-04](findings.md#safe-04) · **Depends on** T09.\
  **Done when** each destination records attempt count, reason, eligibility timestamp and accepted/deferred/ambiguous/permanent outcomes. A healthy later route progresses even with 50 older failing destinations. Missing credentials and quarantined work are visible privately, and safe requeue is explicit. Successful routes retain acknowledgment and never erase errors for other routes.

- [ ] **T11 · P1 · Reserve run time for checkpoints and provider recovery.**\
  **Evidence** [DEL-03](findings.md#del-03), [ING-07](findings.md#ing-07), [OPS-02](findings.md#ops-02) · **Depends on** T10.\
  **Done when** sends and tracker maintenance stop at a soft deadline, queued work remains resumable and persistence has a reserved window. Rate-limited work is deferred until the provider's permitted time. Fake-clock tests cover repeated 429/5xx, a long queue, and a slow stage without long real sleeps.

- [ ] **T12 · P2 · Give new or previously disabled routes an explicit replay policy.**\
  **Evidence** [DEL-04](findings.md#del-04), [ING-05](findings.md#ing-05) · **Depends on** T10, T22.\
  **Done when** dry-run replay previews time-bounded eligible jobs per selected route from postings still fetchable or payloads and receipts recorded prospectively. Report when earlier routing history cannot be reconstructed from the old ID set. A replay fixture proves that jobs with no earlier eligible route can be considered without resending acknowledged routes or changing historical discovery IDs.

- [ ] **T13 · P2 · Harden Discord rendering and routing expectations.**\
  **Evidence** [DEL-05](findings.md#del-05), [TRK-02](findings.md#trk-02) · **Depends on** none.\
  **Done when** final messages respect Discord's payload limits, preserve the required pin instruction and disable unintended mentions. Tests cover punctuation, Unicode, Markdown, long fields and a long URL. Define when pin tracking is unavailable and communicate its window.

- [ ] **T14 · P2 · Separate SMTP acceptance from connection teardown.**\
  **Evidence** [DEL-06](findings.md#del-06), [SAFE-03](findings.md#safe-03) · **Depends on** T07, T10.\
  **Done when** acknowledged SMTP DATA stays acknowledged after a failed QUIT. Timeout before acknowledgment remains explicitly ambiguous. Where measured useful, reuse a bounded session without collapsing per-job outcomes. Tests prove restart behavior and preserve one alert per queued job.

## Source coverage, filtering and identity

- [ ] **T15 · P1 · Validate provider rows and preserve useful partial results.**\
  **Evidence** [ING-01](findings.md#ing-01), [ING-06](findings.md#ing-06), [QA-01](findings.md#qa-01) · **Depends on** none.\
  **Done when** discovery and verifier share typed source results and stable source IDs. Valid siblings survive a bad row, JSON null and malformed bodies differ from an empty valid board, and transport success is tracked separately from a valid parse. Verify missing identifiers and links, invalid nested fields, and unexpected title or term types.

- [ ] **T16 · P1 · Recheck stale boards and document fallbacks.**\
  **Evidence** [ING-02](findings.md#ing-02) · **Depends on** none.\
  **Done when** Browserbase, Mistral and Old Mission Capital each have a verified employer-backed board slug, documented aggregate coverage, or a recorded reason to pause direct polling. Capture verifier result, date and impact for each. Evaluate Postman coverage separately.

- [ ] **T17 · P1 · Measure feed freshness and make season switching auditable.**\
  **Evidence** [ING-02](findings.md#ing-02), [OPS-06](findings.md#ops-06) · **Depends on** T15.\
  **Done when** each source shows fetched, rejected and matching counts plus newest usable timestamp where available. Effective feed URL and configured seasons are visible in a redacted summary. Compare current and proposed Simplify URLs on dates, counts and overlap before changing them. Record when upstream timestamps are unavailable.

- [ ] **T18 · P2 · Make Jobright parsing resilient to table drift.**\
  **Evidence** [ING-01](findings.md#ing-01), [ING-03](findings.md#ing-03) · **Depends on** T15.\
  **Done when** fixtures cover blank bodies, unsupported table layouts, orphan continuation rows, escaped Markdown, invalid dates, year rollover and February 29. Report structural and row failures separately. Preserve valid rows and company provenance in mixed responses.

- [ ] **T19 · P2 · Improve location, role and season matching with labeled examples.**\
  **Evidence** [ING-04](findings.md#ing-04), [ING-08](findings.md#ing-08) · **Depends on** T15.\
  **Done when** adapters retain structured and secondary locations and respect documented listing visibility. A fixed labeled sample covers multi-city roles, ambiguous place names, country and remote variants, co-ops and season formats. The preview explains match reasons, and a shadow comparison quantifies expected gains and regressions before changing defaults.

- [ ] **T20 · P2 · Validate checked-in configuration in CI.**\
  **Evidence** [ING-08](findings.md#ing-08), [SAFE-04](findings.md#safe-04), [QA-01](findings.md#qa-01) · **Depends on** none.\
  **Done when** offline validation uses the tracked configuration and reports usable field paths for duplicate boards, invalid slugs/repos/URLs, blank keywords, key casing, invalid budgets and SMTP settings. Current fallback for legacy `simplify.terms` and zero follow-up days has coverage. Explicitly document any accepted zero-value limits.

- [ ] **T21 · P2 · Separate actionable URLs from canonical provider identity.**\
  **Evidence** [ING-06](findings.md#ing-06), [ING-05](findings.md#ing-05) · **Depends on** T15.\
  **Done when** a job carries its original click URL, native source identity and canonical alias independently. Fixtures verify useful query semantics, repeated parameters, fragments, native and custom-domain aliases and non-actionable missing links. A shadow migration retains compatibility with historical IDs before cutover.

- [ ] **T22 · P2 · Make fuzzy dedup decisions explainable and reversible.**\
  **Evidence** [ING-05](findings.md#ing-05), [DEL-04](findings.md#del-04) · **Depends on** T21.\
  **Done when** source observations, exact matches, heuristic suppression and actual per-route deliveries are distinct. Replay same-source distinct requisitions, both aggregate and native arrival orders, expiration and legacy IDs. Record retention and the expected duplicate-versus-missed-alert tradeoff before enabling new rules.

- [ ] **T23 · P3 · Measure and reduce source polling overhead.**\
  **Evidence** [ING-07](findings.md#ing-07), [OPS-04](findings.md#ops-04) · **Depends on** T17.\
  **Done when** timing, payload, retry counts and rate-limit impact are measured by provider. Changes to pooling, caching, concurrency or retry jitter show value under controlled replay, preserve partial coverage and deterministic outcomes, and keep low-traffic providers within documented limits.

- [ ] **T24 · P3 · Decide whether direct Workday coverage is worth maintaining.**\
  **Evidence** [ING-02](findings.md#ing-02), [ING-06](findings.md#ing-06) · **Depends on** T16, T17.\
  **Done when** a representative approved sample compares aggregate coverage for Postman and other relevant employers. If recurring misses justify an adapter, include pagination, stable IDs, failure classification and a verifier fixture. Record a measured decision either way.

## Discord interactions and Notion

- [ ] **T25 · P1 · Keep Applied intake progressing after bad input and channel changes.**\
  **Evidence** [TRK-01](findings.md#trk-01), [SAFE-02](findings.md#safe-02) · **Depends on** none.\
  **Done when** malformed records are isolated and valid subsequent messages reach a durable queue. Each cursor and queued item includes origin channel. Initial baseline and authorized backfill are explicit. A permission or intent gap is distinguishable from empty input through readiness checks or a documented diagnostic. Pending Notion writes drain independently of optional intake and acknowledgment settings.

- [ ] **T26 · P1 · Reconcile creation of master, tracker and stats resources.**\
  **Evidence** [TRK-03](findings.md#trk-03), [QA-03](findings.md#qa-03) · **Depends on** none.\
  **Done when** stable IDs or resource keys survive ambiguous creates and appends. A subsequent run reconciles existing resources before creating new ones, preserves page IDs and distinguishes deleted/archived resources from missing permission. Fixtures cover accepted response loss, missing schema and transient rate limits.

- [ ] **T27 · P1 · Close postings only on verified provider evidence.**\
  **Evidence** [TRK-04](findings.md#trk-04), [ING-06](findings.md#ing-06) · **Depends on** none.\
  **Done when** transient, malformed and unsupported lookups stay unknown, stale board slugs cannot trigger bulk closure, regional routing is validated, and repeated checks of the same posting reuse a result within the scan. A concurrent manual pipeline edit survives the sweep. Agree whether closure is a separate liveness field before changing existing records.

- [ ] **T28 · P2 · Make message and pin pagination loss-aware.**\
  **Evidence** [TRK-02](findings.md#trk-02), [TRK-01](findings.md#trk-01) · **Depends on** T25.\
  **Done when** fixtures cover at least 250 backlog messages, arrivals during pagination, a restart mid-scan, more than one reactor page and missing permissions. Persist a bounded continuation until all eligible items are queued. Define pin retention, handling of reaction types and catch-up after a multi-day outage.

- [ ] **T29 · P2 · Define and test acknowledgment behavior.**\
  **Evidence** [TRK-02](findings.md#trk-02), [TRK-01](findings.md#trk-01) · **Depends on** T25.\
  **Done when** one failed link prevents a multi-link success acknowledgment, accepted Notion writes survive reaction failure, and acknowledgments target the origin channel. Decide whether user confirmation warrants a durable retry; if it does, use a separate idempotent operation and exercise crash after filing.

- [ ] **T30 · P2 · Define application-date and follow-up rules.**\
  **Evidence** [TRK-05](findings.md#trk-05), [TRK-06](findings.md#trk-06) · **Depends on** none.\
  **Done when** a delayed link gets the agreed event date/timezone, new rows receive dates on initialization, and a verified backfill handles missing dates without overriding manual changes. Tests cover zero follow-up days, per-user overrides, advanced statuses and due eligibility. Agree whether any separate reminders are desired before adding them.

- [ ] **T31 · P2 · Measure and narrow Notion reads and stats writes.**\
  **Evidence** [TRK-06](findings.md#trk-06), [TRK-03](findings.md#trk-03), [OPS-06](findings.md#ops-06) · **Depends on** T26.\
  **Done when** normal upserts use a measured indexed or filtered lookup with a legacy path. Status edits show up within an agreed refresh interval. A partial tracker read keeps last-good counts or indicates partial coverage, and a large roster remains complete with consented visibility. Benchmark reads and writes against small and production-shaped fixtures.

- [ ] **T32 · P2 · Stage the Notion API data-source migration.**\
  **Evidence** [TRK-07](findings.md#trk-07), [TRK-03](findings.md#trk-03) · **Depends on** T26.\
  **Done when** existing resource IDs are inventoried and mapped before version change, with fixtures for single-source and multi-source databases. Existing pages, statuses and trackers remain consistent, unauthorized access is surfaced, and rollback has a known version and newest compatible state.

## Scheduling, observability and release

- [ ] **T33 · P1 · Separate operational health dimensions.**\
  **Evidence** [OPS-06](findings.md#ops-06), [OPS-05](findings.md#ops-05), [ING-02](findings.md#ing-02) · **Depends on** T08, T10, T15.\
  **Done when** health records attempt/start, scan completion, delivery and tracker sync progress, last durable write, and pending age. Report normal cap deferral, stale single source, broad outage, permanent route failure and sync failure distinctly. Verify outcomes when there are no jobs, no configured sinks, and no working sources.

- [ ] **T34 · P2 · Make the Worker monitor workflow and alert outcomes independently.**\
  **Evidence** [OPS-05](findings.md#ops-05), [OPS-06](findings.md#ops-06) · **Depends on** T33.\
  **Done when** the scheduled handler validates GitHub payload and timestamps, reports latest usable success during failure streaks, distinguishes cancellations and bounds alert retry and duplicate reminders. Deterministic tests cover API errors, null/empty responses, missing timestamps or webhook, alert 503 and repeated scheduled time. Document token scope and API version.

- [ ] **T35 · P2 · Choose one normal scheduler and prove fallback behavior.**\
  **Evidence** [OPS-04](findings.md#ops-04), [OPS-05](findings.md#ops-05), [OPS-01](findings.md#ops-01) · **Depends on** T34, T04.\
  **Done when** the approved primary scheduler drives normal scans and a backup, if retained, only dispatches after checking staleness and queued or running work. Compare dispatch counts, freshness and end-to-end detection latency before and after a canary. Record the scheduler owner and pause procedure.

- [ ] **T36 · P2 · Add a hermetic regression and recovery gate.**\
  **Evidence** [QA-01](findings.md#qa-01), [OPS-02](findings.md#ops-02), [DEL-01](findings.md#del-01), [TRK-03](findings.md#trk-03) · **Depends on** none.\
  **Done when** CI validates workflow syntax and tracked configuration, then exercises isolated checkpoint failures, accepted-response loss, restart and restore, permission/secret preflight, and production-shaped sanitized state. Use provider fakes and prohibit live destinations in checks. Keep targeted acceptance tests with each implementation task.

- [ ] **T37 · P2 · Pin release tools and publish an operator runbook.**\
  **Evidence** [QA-02](findings.md#qa-02), [QA-03](findings.md#qa-03), [OPS-04](findings.md#ops-04) · **Depends on** none.\
  **Done when** tested Python dependencies, reviewed action references, supported Node and Wrangler versions, and a repeatable deploy and rollback procedure are recorded. The docs distinguish HTTP Test Ping from phone delivery and include credential readiness, pin expiry, source triage and recovery guarantees that the tests actually support.

- [ ] **T38 · P3 · Introduce run-scoped status and profile checkpoint costs.**\
  **Evidence** [QA-04](findings.md#qa-04), [OPS-03](findings.md#ops-03), [TRK-06](findings.md#trk-06) · **Depends on** T05, T15.\
  **Done when** callers can explicitly own per-run results, timers and caches without changing CLI or verifier usage. Measure 0, 50 and 500 delivery outcomes on sanitized snapshots and compare checkpoint bytes and latency with the JSON baseline. Keep the smallest abstraction that improves isolation or measured cost.

## Migration and release gates

1. **Contain and rehearse.** Implement T01–T04, T06–T09 and synthetic recovery checks before broadening routing or running experiments with real integrations. Validate an immutable private recovery snapshot and the existing state schema.
2. **Shadow compare.** Import a sanitized, production-shaped snapshot. Compare known IDs including legacy entries, canonical aliases, fingerprint timestamps, pending recipient states, Discord receipts, Notion resource IDs, cursors and pending actions. Compare outputs against an identical recorded feed input and use isolated sinks for writes.
3. **Cut over one writer.** Pause scheduled and local writers, import the latest validated generation, and acquire the new writer fence. Canary one authorized end-to-end path and check durability after restart before resuming normal cadence. Record the deployed revision and generation.
4. **Roll back from current state.** Pause the new writer and restore or translate its latest committed generation, including any progress made since cutover. Verify counts, consistency and delivery acknowledgments before re-enabling the prior writer. Older state is for comparison and disaster recovery, since sending against it risks repeating acknowledged work.
5. **Review rollout evidence.** Compare real delivery lag, oldest backlog, error reasons, source completeness, restore success and tracker freshness to the agreed target. Record remaining open risks and any operational decisions from [findings.md](findings.md#10-open-operational-questions).

## Applying this backlog to the teammate branch

Use the [branch comparison](findings.md#11-teammate-branch-comparison) before implementing overlapping tasks. T07 has a concrete TLS implementation to verify. T06, T10, T13, T16, T17, T19, T20, T23, T25, T33 and T37 have partial work to evaluate against their acceptance criteria. Use the audited `main` findings as the baseline and use code diffs to decide what to reuse. Retain current state from the authorized writer when comparing or integrating changes.
