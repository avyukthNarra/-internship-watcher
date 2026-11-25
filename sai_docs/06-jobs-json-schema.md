# Public jobs export schema

The watcher writes a public snapshot to the ignored, generated `jobs.json` file
after a successful non-dry scan. It contains only postings that passed the
global filters. Personal profiles and delivery or application state do not
affect its contents.

The root value is an array, newest `first_seen` first. Each entry has exactly
these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | SHA-256 hash of the canonical job identity. |
| `company` | string | Public company name from the posting. |
| `title` | string | Public job title. |
| `location` | string | Public location text. |
| `url` | string | Canonical HTTP or HTTPS posting URL. Known tracking tags and likely personal or referral query keys are removed; job identity query keys and SPA fragments are preserved. Invalid URLs are empty strings. |
| `terms` | array of strings | Season or recruiting terms, such as `Summer 2027`. |
| `source` | string | Source name: `greenhouse`, `lever`, `ashby`, `simplify`, `vanshb03`, `jobright`, or `unknown`. |
| `first_seen` | string | First observation in UTC ISO 8601 format, such as `2026-11-24T12:00:00Z`. |
| `top` | boolean | The watcher's existing top-company or top-source classification. |
| `roles` | array of strings | Role labels, in this order when present: `SWE`, `Data`, `ML/AI`, `Research`, `Embedded`, `Hardware`, `Quant`. Empty when none match. |

`roles` comes from `config.json` `alert_channels`, using the same whole-word
`preference_matches` rule that routes Discord channel alerts. Only a channel's
`roles`, `exclude_roles`, and `categories` count; its term, company, location,
and webhook settings are ignored and never exported. Channel names map to
labels as follows: `swe` → `SWE`, `data` → `Data`, `ml` → `ML/AI`, `research`
→ `Research`, `embedded` → `Embedded`, `hardware` and `hardware-by-title` →
`Hardware`, `quant` and `quant-by-title` → `Quant`. Channels with other names
add no label, so a new channel stays private until it is added to
`CHANNEL_ROLE_LABELS` in `site_export.py`. A posting can have several labels
(for example `ML/AI` and `Research`). With no `alert_channels`, every list is
empty.

Consumers should tolerate a missing `roles` key (exports written before the
field existed). The `web/` page then infers roles from the title.

The export contains only postings present in the current scan. Previously
exported entries are used only to preserve `first_seen`, so a posting that
leaves its feed's current window disappears from the site. `site_export_days`
(default 45) caps the age of currently listed postings; it does not extend
retention beyond the feed window. The export is capped at 5,000 entries to
keep the generated artifact bounded if a feed grows sharply.

The source value can also be `workday` for listings from the Workday adapter.

`web/sample-jobs.json` contains fictional examples for local front-end work;
it follows the same exact key set and uses only `example.com` links.
