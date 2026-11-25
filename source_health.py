"""Build and format scan health without performing network or state writes."""

SOURCE_ALERT_AFTER = 5 * 3600
# One dead board gets a GitHub issue, not a failed run. Either limit counts as a broad outage.
MAX_STALE_SOURCES = 5
BROAD_OUTAGE_FRACTION = 0.10  # stale share of sources that counts as an outage


def build_health(sources, previous_sources, *, now, matching_jobs, new_jobs,
                 pending_deliveries, sync_error, dead_deliveries=0):
    sources = {url: dict(record) for url, record in sources.items()}
    for url, source in sources.items():
        if source.get("ok"):
            # Fetchers copy the previous record, so drop outage fields on recovery.
            source.pop("failing_since", None)
            source.pop("issue", None)
        else:
            previous = previous_sources.get(url, {})
            source["failing_since"] = source.get("failing_since") or previous.get("failing_since") or now
            if previous.get("issue"):
                source["issue"] = previous["issue"]
    failures = sum(not source.get("ok") for source in sources.values())
    stale = sum(not source.get("ok") and now - source["failing_since"] >= SOURCE_ALERT_AFTER
                for source in sources.values())
    return {
        "last_completed_scan": now,
        "sources": sources,
        "successful_sources": len(sources) - failures,
        "failed_sources": failures,
        "stale_failed_sources": stale,
        "matching_jobs": matching_jobs,
        "new_jobs": new_jobs,
        "pending_deliveries": pending_deliveries,
        "dead_deliveries": dead_deliveries,
        "sync_error": sync_error,
    }


def health_summary(health):
    lines = [
        f"Sources: {health['successful_sources']} OK, {health['failed_sources']} failed "
        f"({health['stale_failed_sources']} down {SOURCE_ALERT_AFTER // 3600}h+); "
        f"pending deliveries: {health['pending_deliveries']}"
        f"{', parked: ' + str(health['dead_deliveries']) if health.get('dead_deliveries') else ''}; sync: {health['sync_error'] or 'OK'}"
    ]
    for url, source in sorted(health["sources"].items()):
        if not source.get("ok"):
            hours = (health["last_completed_scan"] - source["failing_since"]) / 3600
            lines.append(f"- {url}: {source.get('error')} for {hours:.1f}h")
    return "\n".join(lines)


def health_exit_code(health):
    """Stale sources are tracked as issues and shown in the summary; a broad outage
    (more than MAX_STALE_SOURCES, or BROAD_OUTAGE_FRACTION of sources), stuck
    deliveries, or a sync error fail the run."""
    stale, total = health["stale_failed_sources"], health["successful_sources"] + health["failed_sources"]
    broad_outage = stale > MAX_STALE_SOURCES or (bool(total) and stale / total >= BROAD_OUTAGE_FRACTION)
    return int(broad_outage or bool(health["sync_error"] or health["pending_deliveries"]))
