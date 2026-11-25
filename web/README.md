# Internship browser

Static, read-only page for browsing current internships. It is plain HTML, CSS, and JavaScript, with no build step and no npm packages. Open it from a static file server.

## Run locally

From the repository root:

```bash
python3 -m http.server -d web
```

Then open `http://127.0.0.1:8000/`.

Unit tests for filtering, sorting, and URL checks:

```bash
node --test web/app.test.js
```

## Data

The page fetches one URL, `DATA_URL` in `web/jobs.js`. It defaults to `./sample-jobs.json`. Change that constant when a published `jobs.json` is available. The file must be served from the same origin: the page sends `Content-Security-Policy: default-src 'self'`.

`web/sample-jobs.json` is fictional sample data (fake companies, `https://example.com/...` links). The response must be a JSON array. Each object uses:

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

The page searches company, title, and location, and can filter by company, term, location text, first seen in the last 24 hours, and `top`. Results sort newest first.

Text from the file is inserted with DOM APIs (`textContent`), not `innerHTML`. Apply links open in a new tab with `rel="noopener noreferrer"`.

## Deployment

Do not deploy this folder yet. Hosting (Netlify or Vercel) and publishing the live jobs file wait on the repository owner. This folder has no hosting config and no secrets.
