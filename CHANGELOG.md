# Changelog

All notable changes are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The repository has never been tagged. The owner picks the version when merging: treat current `main` as `1.0.0`, and this branch as `1.1.0` (new features, existing `config.json` keys unchanged). Entries stay under Unreleased until then.

For semver here, a major bump means a breaking change to `config.json`, the state file formats, or the workflow's required secrets. A minor bump adds a feature or source. A patch is a fix with no new config.

## [Unreleased]

### Added
- `alert_channels`: shared Discord channels matched on `roles`, `exclude_roles`, `companies`, `locations`, `terms`, `categories`. Shipped role channels: `swe`, `data`, `research`, `ml`, `embedded`, `hardware`, `quant` (silent until their webhooks exist). Channels must set at least one include filter.
- `vanshb03` aggregate feed (`vanshb03` config block; 3-day window).
- `simplify.include_categories`, `category_exclude`, `category_roles`: pull whole SimplifyJobs categories (Hardware, Quant).
- 28 company boards (hardware, quant, startups) and the `Summer2027-Internships` Simplify path.
- `discover_boards.py`: read-only board finder (`--names`, `--yc`, `--industry`).
- `net_safety.py`: public-IP, redirect-checked, size-capped fetching for applied links.
- `trim_health_noise.py`: skips `health.json`-only state commits.
- `allowed_user_ids` allowlist and per-message and per-run caps for applied-link intake.
- `max_delivery_attempts` (default 20) and a `dead` ledger for parked deliveries.
- ETag conditional requests for the SimplifyJobs feed.
- Dependabot for pip and GitHub Actions; `requests` pinned.
- `sai_docs/`: context, security audit, optimizations, scraper guide, todo, owner checkout.

### Changed
- Keyword matching is whole-word, so "intern" no longer matches "International".
- `N/A`, `TBD`, `unknown`, and `none` seasons are treated as unknown (`keep_unknown_terms` decides).
- A single stale source no longer fails the run; only broad outages, stuck deliveries, or sync errors do.
- Old Mission Capital moved to its Ashby board.
- New `exclude_keywords`: civil engineering, chemical, chemistry, structural, geotechnical, hvac, welding.
- Expect a one-time burst of about 350 alerts on the first run after merge.

### Fixed
- SMTP now verifies certificates.
- Untrusted feed fields are cleaned; Discord link text is escaped.
- Host checks use dot boundaries, and ATS URL parts are quoted.
- Pinger alerts send `allowed_mentions: { parse: [] }`.

### Security
- Open until the owner acts: S1 (secrets reachable from branch workflows), S2 (`notion_state.json` publishes a user's Discord ID, name, and application URLs), branch protection. See `sai_docs/05-owner-checkout.md`.
