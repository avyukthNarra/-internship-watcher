# Internship browser

A static, read-only job board for current internships. Plain HTML, CSS, and JavaScript: no build step, no npm packages, no external fonts or CDNs. Any static file server can host it.

## Run locally

From the repository root:

```bash
python3 -m http.server -d web
```

Then open `http://127.0.0.1:8000/`.

Unit tests (filtering, roles, URL state, relative times, monograms, sample data, and deploy header parity):

```bash
node --test web/app.test.js
```

## Files

| File | Purpose |
| --- | --- |
| `index.html` | Page markup. Sets a `default-src 'self'` CSP meta tag as a fallback for hosts without header config. |
| `styles.css` | Light and dark themes (`prefers-color-scheme`), system font stack, layout down to 360px. |
| `jobs.js` | Pure logic shared by the browser and Node tests: filtering, role inference, URL query state, formatting. |
| `app.js` | DOM layer: rendering, events, incremental "show more", loading/empty/error states. |
| `sample-jobs.json` | Fictional sample data (invented companies, `https://example.com/...` links). |
| `_headers` | Netlify response headers. |
| `vercel.json` | Vercel response headers (same values; a test checks they match). |

## Features

- Search company, title, and location. Press `/` anywhere to focus search; `Esc` clears it.
- Role chips: SWE, Data, ML/AI, Research, Embedded, Hardware, Quant. Selecting several shows jobs in any of them. Each chip shows how many results it would match under the other filters.
- Term select (chronological), location text, Remote, New (24h), and Top companies toggles, and newest/oldest sort.
- Click a company name to show only that company; remove it from the pill in the results bar.
- Every filter is mirrored in the URL query string, so a view can be shared or bookmarked, and the back button steps through company drill-downs:

  `?q=robot&role=SWE,ML/AI&term=Summer+2027&loc=austin&remote=1&new=1&top=1&company=Brightloom&sort=oldest`

- Rows show a monogram avatar (initials, color picked deterministically from the company name), title, NEW badge for jobs first seen in the last 24 hours, TOP marker, company, location, role tags, term chips, relative first-seen time ("2h ago", full text on hover), and an Apply button.
- Rows render 50 at a time. More load automatically as you scroll near the end, or with the "Show more" button, so 3,000+ jobs stay responsive.
- Skeleton rows while loading, an empty state with "Clear all filters", and an error state with "Try again".

## Data

The page fetches one URL, `DATA_URL` in `web/jobs.js`. It defaults to `./sample-jobs.json`. The response must be a JSON array of objects following [`sai_docs/06-jobs-json-schema.md`](../sai_docs/06-jobs-json-schema.md):

| Field | Type |
| --- | --- |
| `id` | string |
| `company` | string |
| `title` | string |
| `location` | string |
| `url` | string (`http` or `https` only; other schemes are not linked) |
| `terms` | array of strings |
| `source` | string |
| `first_seen` | ISO UTC timestamp |
| `top` | boolean |
| `roles` | array of role labels (optional for the page) |

If `roles` is missing (an export from before the field existed), the page infers roles from the title with the same whole-word keywords as `config.json` `alert_channels`. The export is more accurate because it also sees SimplifyJobs categories (for example Hardware and Quant).

Text from the file is inserted with DOM APIs (`textContent`), never `innerHTML`. Apply links open in a new tab with `rel="noopener noreferrer"`. Monogram colors come from fixed CSS classes, not inline styles.

### Pointing `DATA_URL` at the published `jobs.json`

The watcher writes `jobs.json` after each successful scan. Publishing it is not set up yet; there are two options:

1. **Same origin (recommended).** Copy the generated `jobs.json` into `web/` at deploy time (for example a deploy step that runs after a scan), and set `DATA_URL = "./jobs.json"`. No CSP change is needed, and the `jobs.json` cache headers below apply.
2. **Another origin** (for example a raw file URL or object storage). Set `DATA_URL` to the full `https://` URL and add that origin to `connect-src` in all three CSP copies: `web/_headers`, `web/vercel.json`, and the meta tag in `web/index.html`. For example: `default-src 'self'; connect-src 'self' https://data.example.com; ...`. The data host must also send `Access-Control-Allow-Origin` for the site's origin.

Update the `DATA_URL` test in `web/app.test.js` when you change it.

## Deploy

Nothing is deployed, and this folder holds no secrets. The owner picks the host. Both work without a build, serving the `web/` folder as is.

### Netlify

1. Add a new site from the GitHub repository.
2. Set **Base directory** to `web`, leave **Build command** empty, and set **Publish directory** to `web` (Netlify shows it relative to the repository root).
3. Deploy. Netlify reads `web/_headers` for the security and cache headers.

Setting the base directory keeps Netlify from installing the watcher's Python requirements.

### Vercel

1. Import the GitHub repository as a new project.
2. Set **Root Directory** to `web`, **Framework Preset** to "Other", and leave the build and output settings empty.
3. Deploy. Vercel reads `web/vercel.json` for the same headers.

### Headers sent by both

| Header | Value |
| --- | --- |
| `Content-Security-Policy` | `default-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `X-Frame-Options` | `DENY` (older browsers; `frame-ancestors` covers current ones) |
| `Permissions-Policy` | camera, microphone, geolocation off |
| `Cross-Origin-Opener-Policy` | `same-origin` |
| `Cache-Control` on `/jobs.json` and `/sample-jobs.json` | `public, max-age=60, stale-while-revalidate=300` |

Other files use each host's default (revalidate on every request), which is right because file names are not hashed. `frame-ancestors` only works as a header, which is why the page needs the host config and not just the meta tag. If you change a header, change both files; `node --test web/app.test.js` fails when they drift.

Both hosts also serve `README.md` and `app.test.js` from this folder as plain files. They contain nothing private.
