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
| `url` | string | HTTP or HTTPS posting URL with query and fragment removed; invalid URLs are empty strings. |
| `terms` | array of strings | Season or recruiting terms, such as `Summer 2027`. |
| `source` | string | Source name: `greenhouse`, `lever`, `ashby`, `simplify`, `vanshb03`, `jobright`, or `unknown`. |
| `first_seen` | string | First observation in UTC ISO 8601 format, such as `2026-11-24T12:00:00Z`. |
| `top` | boolean | The watcher's existing top-company or top-source classification. |

The configured retention defaults to `site_export_days: 45`. Entries older
than the window are removed, and the export is capped at 5,000 entries. The
cap keeps the generated artifact bounded if a feed grows sharply.

`web/sample-jobs.json` contains fictional examples for local front-end work;
it follows the same exact key set and uses only `example.com` links.
