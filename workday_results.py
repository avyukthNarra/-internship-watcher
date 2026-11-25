"""Validation for the untrusted laptop results interchange."""
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

MAX_RESULTS_BYTES = 5 * 1024 * 1024
RESULTS_MAX_AGE = 3 * 3600


def validate_results(data, boards):
    if not isinstance(data, dict) or set(data) != {'schema', 'fetched_at', 'boards'} or type(data['schema']) is not int or data['schema'] != 1:
        raise ValueError('Invalid results envelope')
    if not isinstance(data['fetched_at'], str):
        raise ValueError('Invalid timestamp')
    try:
        timestamp = datetime.fromisoformat(data['fetched_at'].replace('Z', '+00:00'))
        if timestamp.utcoffset() is None or timestamp.utcoffset().total_seconds() != 0:
            raise ValueError('Timestamp must be UTC')
    except (ValueError, OverflowError):
        raise ValueError('Invalid timestamp') from None
    if not isinstance(data['boards'], dict) or set(data['boards']) - set(boards):
        raise ValueError('Invalid boards')
    for board, result in data['boards'].items():
        if not isinstance(result, dict) or set(result) != {'ok', 'error', 'jobs'} or type(result['ok']) is not bool or not (result['error'] is None or isinstance(result['error'], str)) or not isinstance(result['jobs'], list):
            raise ValueError('Invalid board result')
        if (result['ok'] and result['error'] is not None) or (not result['ok'] and (not result['error'] or result['jobs'])):
            raise ValueError('Invalid board status')
        tenant, site, host = board.split('/')
        for job in result['jobs']:
            if not isinstance(job, dict) or set(job) != {'id', 'title', 'location', 'url', 'posted_date'} or any(not isinstance(job[k], str) for k in ('id', 'title', 'location', 'url')) or not (job['posted_date'] is None or isinstance(job['posted_date'], str)):
                raise ValueError('Invalid job')
            url = urlsplit(job['url'])
            if (url.scheme != 'https' or url.netloc != f'{tenant}.{host}.myworkdayjobs.com' or not url.path.startswith(f'/{site}/job/') or url.fragment or url.query or job['id'] != f'workday:{board}:{url.path[len(site) + 1:]}'):
                raise ValueError('Invalid job URL or ID')
    return timestamp


def read_results(path, boards, now=None):
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_RESULTS_BYTES + 1)
    if len(raw) > MAX_RESULTS_BYTES:
        raise ValueError('Results too large')
    data = json.loads(raw)
    timestamp = validate_results(data, boards)
    age = ((now or datetime.now(timezone.utc)) - timestamp).total_seconds()
    if age < 0 or age >= RESULTS_MAX_AGE:
        raise ValueError('Stale results')
    return data
