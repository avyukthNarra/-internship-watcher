"""Build and format scan health without performing network or state writes."""

SOURCE_ALERT_AFTER = 5 * 3600


def build_health(sources, previous_sources, *, now, matching_jobs, new_jobs,
                 pending_deliveries, sync_error):
    sources = {url: dict(record) for url, record in sources.items()}
    for url, source in sources.items():
        if source.get("ok"):
            source.pop("failing_since", None)
        else:
            source["failing_since"] = (source.get("failing_since")
                                       or previous_sources.get(url, {}).get("failing_since") or now)
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
        "sync_error": sync_error,
    }


def health_summary(health):
    lines = [
        f"Sources: {health['successful_sources']} OK, {health['failed_sources']} failed "
        f"({health['stale_failed_sources']} down {SOURCE_ALERT_AFTER // 3600}h+); "
        f"pending deliveries: {health['pending_deliveries']}; sync: {health['sync_error'] or 'OK'}"
    ]
    for url, source in sorted(health["sources"].items()):
        if not source.get("ok"):
            hours = (health["last_completed_scan"] - source["failing_since"]) / 3600
            lines.append(f"- {url}: {source.get('error')} for {hours:.1f}h")
    return "\n".join(lines)


def health_exit_code(health):
    """Short source outages are tolerated; stale sources and delivery failures are not."""
    return int(bool(health["stale_failed_sources"]
                    or health["sync_error"] or health["pending_deliveries"]))
