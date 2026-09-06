"""Shared job identity, preferences, and crash-safe JSON storage."""
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def load_json(path, default):
    path = Path(path)
    if not path.exists():
        return default
    # Corrupt state must stop the run, never masquerade as an empty history.
    return json.loads(path.read_text())


def save_json(path, data):
    path = Path(path)
    fd, temp = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, indent=1, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def canonical_url(url):
    """Remove known campaign tags, preserving job IDs and SPA fragments."""
    p = urlsplit(url or '')
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith('utm_')
             and k.lower() not in {'gh_src', 'lever-source', 'lever-origin',
                                   'fbclid', 'gclid', 'mc_cid', 'mc_eid'}]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path,
                       urlencode(sorted(query)), p.fragment))


def job_identity(job):
    url = canonical_url(job.get('url', ''))
    p = urlsplit(url)
    host = p.hostname or ''
    parts = [s for s in p.path.split('/') if s]
    query = dict(parse_qsl(p.query))
    if query.get('gh_jid'):
        return 'greenhouse:' + query['gh_jid']
    if host == 'greenhouse.io' or host.endswith('.greenhouse.io'):
        if 'jobs' in parts and parts.index('jobs') + 1 < len(parts):
            return 'greenhouse:' + parts[parts.index('jobs') + 1]
    for domain, ats in (('lever.co', 'lever'), ('ashbyhq.com', 'ashby')):
        if host == domain or host.endswith('.' + domain):
            if len(parts) >= 2:
                return ats + ':' + parts[0].lower() + ':' + parts[1]
    return 'url:' + url if url else 'id:' + job['id']


def job_terms(job):
    explicit = job.get('terms') or []
    inferred = re.findall(r'\b(Fall|Winter|Spring|Summer|Autumn)\s*[-/]?\s*(20\d{2})\b',
                          job.get('title', ''), re.I)
    return sorted({s.lower().replace('autumn', 'fall') for s in explicit}
                  | {f'{s.lower().replace("autumn", "fall")} {y}' for s, y in inferred})


def term_matches(job, terms, keep_unknown=True):
    actual = job_terms(job)
    if not terms:
        return True
    if actual:
        return bool(set(actual) & {t.lower() for t in terms})
    years = set(re.findall(r"\b20\d{2}\b", job.get("title", "")))
    wanted_years = {year for term in terms for year in re.findall(r"\b20\d{2}\b", term)}
    if years and wanted_years and not years & wanted_years:
        return False
    return keep_unknown


def fingerprint(job):
    fields = [job.get('company', ''), job.get('title', ''),
              job.get('location', ''), '|'.join(job_terms(job))]
    normalized = [re.sub(r'[^a-z0-9]+', '', field.lower()) for field in fields]
    return hashlib.sha256(json.dumps(normalized).encode()).hexdigest()


def preference_matches(job, preferences):
    """All configured dimensions must match; empty lists impose no restriction."""
    for key, field in (('roles', 'title'), ('companies', 'company'),
                       ('locations', 'location')):
        wanted = preferences.get(key, [])
        if wanted and not any(re.search(r'\b' + re.escape(s.lower()) + r'\b',
                                         job.get(field, '').lower()) for s in wanted):
            return False
    return term_matches(job, preferences.get('terms', []),
                        preferences.get('keep_unknown_terms', True))
