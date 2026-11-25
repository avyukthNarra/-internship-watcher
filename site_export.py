"""Build a bounded, public-safe snapshot of globally matching internships."""

import hashlib
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from job_utils import canonical_url, clean_job, job_identity
from project_config import DEFAULT_SITE_EXPORT_DAYS

MAX_SITE_EXPORT_JOBS = 5000
EXPORT_FIELDS = frozenset({
    "id", "company", "title", "location", "url", "terms", "source",
    "first_seen", "top",
})
_SOURCES = frozenset({"greenhouse", "lever", "ashby", "workday", "simplify", "vanshb03", "jobright"})
_PRIVATE_QUERY_KEYS = frozenset({
    "ref", "referrer", "referral", "source", "src", "token", "email", "e",
    "uid", "user", "userid", "trk", "trackingid", "mkt_tok",
})


def _utc_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(value, timezone.utc)
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_utc(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _public_url(value):
    """Use the canonical public URL, dropping likely personal/referral query keys."""
    url = clean_job({"url": value}).get("url", "")
    try:
        parts = urlsplit(canonical_url(url))
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            return ""
        # Canonicalize scheme and host while preserving path casing and port.
        host = parts.hostname.lower()
        if ":" in host:
            host = f"[{host}]"
        if parts.port:
            host += f":{parts.port}"
        if parts.username or parts.password:
            return ""
        query = urlencode(sorted((key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
                                 if key.lower() not in _PRIVATE_QUERY_KEYS))
        return urlunsplit((parts.scheme.lower(), host, parts.path or "/", query, parts.fragment))
    except ValueError:
        return ""


def _top_job(job, cfg):
    job_id = str(job.get("id", ""))
    source = job_id.split(":", 1)[0].lower()
    if source in {"greenhouse", "lever", "ashby", "simplify"} and not job.get("via_category"):
        return True
    company = str(job.get("company", "")).lower()
    if company in {str(c.get("name", "")).lower() for c in cfg.get("companies", [])}:
        return True
    return any(str(keyword).lower() in company
               for keyword in cfg.get("simplify", {}).get("company_keywords", []))


def _export_id(job, public_url):
    identity_job = dict(job)
    identity_job["url"] = public_url
    identity = job_identity(identity_job)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def build_jobs_export(postings, previous_jobs=(), cfg=None, *, now=None, retention_days=None):
    """Return a deterministic public export from globally-filtered postings.

    Only explicitly selected fields leave this function. ``previous_jobs`` is
    used solely to preserve ``first_seen``; unknown fields are discarded.
    The function performs no file or network I/O.
    """
    cfg = cfg or {}
    current_time = _utc_datetime(now) if now is not None else datetime.now(timezone.utc)
    if current_time is None:
        raise ValueError("now must be an ISO timestamp, datetime, or Unix timestamp")
    days = (cfg.get("site_export_days", DEFAULT_SITE_EXPORT_DAYS)
            if retention_days is None else retention_days)
    if type(days) is not int or days < 0:
        raise ValueError("retention_days must be a non-negative integer")
    cutoff = current_time - timedelta(days=days)

    first_seen_by_id = {}
    for prior in previous_jobs if isinstance(previous_jobs, (list, tuple)) else ():
        if not isinstance(prior, dict):
            continue
        seen = _utc_datetime(prior.get("first_seen"))
        if isinstance(prior.get("id"), str) and seen:
            first_seen_by_id[prior["id"]] = seen

    by_id = {}
    for raw in postings:
        if not isinstance(raw, dict):
            continue
        job = clean_job(raw)
        public_url = _public_url(job.get("url", ""))
        safe_identity_job = {**job, "url": public_url}
        safe_identity_job["id"] = str(job.get("id") or "")
        export_id = _export_id(safe_identity_job, public_url)
        seen = first_seen_by_id.get(export_id, current_time)
        if seen < cutoff or seen > current_time:
            continue
        terms = job.get("terms") or []
        if isinstance(terms, str):
            terms = [terms]
        elif not isinstance(terms, (list, tuple, set)):
            terms = []
        safe_terms = sorted({re.sub(r"[\x00-\x1f\x7f]", " ", str(term)).strip()
                             for term in terms if str(term).strip()})
        job_source = str(job.get("id", "")).split(":", 1)[0].lower()
        source = job_source if job_source in _SOURCES else "unknown"
        item = {
            "id": export_id,
            "company": job.get("company", ""),
            "title": job.get("title", "Untitled"),
            "location": job.get("location", ""),
            "url": public_url,
            "terms": safe_terms,
            "source": source,
            "first_seen": _iso_utc(seen),
            "top": _top_job(job, cfg),
        }
        # Explicit reconstruction is the privacy boundary: no feed metadata,
        # delivery state, configuration, or prior unknown fields are copied.
        by_id[export_id] = item

    ordered = sorted(by_id.values(), key=lambda item: (item["first_seen"], item["id"]), reverse=True)
    return ordered[:MAX_SITE_EXPORT_JOBS]
