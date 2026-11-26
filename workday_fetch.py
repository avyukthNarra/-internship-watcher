#!/usr/bin/env python3
"""Fetch Workday at home and optionally publish to a private git clone."""
import argparse
import json
import os
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
import time
from datetime import datetime, timezone
from pathlib import Path

import watcher
from job_feeds import board_url, company_board
from project_config import validate_config
from workday_results import MAX_RESULTS_BYTES, validate_results

HEARTBEAT_SECONDS = 2 * 3600
LAPTOP_MAX_PAGES = 5
DEFAULT_WORKERS = 3
MAX_WORKERS = 4
BACKOFF_INITIAL = 30 * 60
BACKOFF_MAX = 6 * 3600
BACKOFF_PATH = watcher.ROOT / "laptop" / ".workday_backoff.json"


def load_backoff(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {'blocks': 0, 'retry_at': 0}
    if (not isinstance(data, dict) or type(data.get('blocks')) is not int
            or data['blocks'] < 0 or type(data.get('retry_at')) not in (int, float)
            or not 0 <= data['retry_at'] < 1e12):
        raise ValueError('Invalid laptop backoff state; inspect the state file')
    return data


def _fetch_board(company, blocked):
    """Fetch one board unless another worker already hit a Workday block."""
    board = company_board(company)
    if blocked.is_set():
        return board, {'ok': False, 'error': 'Skipped after Workday block', 'jobs': []}, {}
    url = board_url('workday', board)
    watcher.SOURCE_HEALTH.pop(url, None)
    try:
        jobs = watcher.fetch_workday(board, max_pages=company.get('max_pages', LAPTOP_MAX_PAGES), page_delay=1)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return board, {'ok': False, 'error': type(exc).__name__, 'jobs': []}, {}
    record = dict(watcher.SOURCE_HEALTH.get(url, {}))
    ok = bool(record.get('ok'))
    if record.get('skipped'):
        blocked.set()
    return board, {'ok': ok, 'error': None if ok else str(record.get('error', 'Request failed')), 'jobs': jobs if ok else []}, record


def collect(config, *, backoff_path=BACKOFF_PATH, dry_run=False, workers=DEFAULT_WORKERS):
    """Fetch every Workday board. Different companies run on up to `workers`
    threads (each board still pages sequentially with a 1s gap); use 1 to keep
    the laptop quiet, for example while gaming."""
    companies = [c for c in config['companies'] if c['ats'] == 'workday']
    state = load_backoff(backoff_path)
    if time.time() < state['retry_at']:
        print(f"Workday backoff active until {datetime.fromtimestamp(state['retry_at'], timezone.utc).isoformat()}")
        return None
    blocked = threading.Event()
    results = {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, MAX_WORKERS))) as pool:
        futures = []
        for index, company in enumerate(companies):
            futures.append(pool.submit(_fetch_board, company, blocked))
            if index < len(companies) - 1:
                time.sleep(1)  # stagger starts so requests never burst
        for future in futures:
            board, result, record = future.result()
            results[board] = (result, record)
    boards = {company_board(c): results[company_board(c)][0] for c in companies}
    if blocked.is_set():
        retry_after = max((record.get('retry_at', 0) for _, record in results.values()), default=0)
        blocks = state['blocks'] + 1
        cooldown = min(BACKOFF_MAX, BACKOFF_INITIAL * 2 ** min(blocks - 1, 4))
        retry_at = max(time.time() + cooldown, retry_after)
        if not dry_run:
            atomic_write(backoff_path, {'blocks': blocks, 'retry_at': retry_at})
        print(f"Workday block: cooling down until {datetime.fromtimestamp(retry_at, timezone.utc).isoformat()}")
    elif all(result['ok'] for result in boards.values()) and state['blocks'] and not dry_run:
        atomic_write(backoff_path, {'blocks': 0, 'retry_at': 0})
    data = {'schema': 1, 'fetched_at': datetime.now(timezone.utc).isoformat(), 'boards': boards}
    validate_results(data, [company_board(c) for c in companies])
    return data


def should_publish(data, previous):
    try:
        old_time = datetime.fromisoformat(previous['fetched_at'].replace('Z', '+00:00'))
        new_time = datetime.fromisoformat(data['fetched_at'].replace('Z', '+00:00'))
        return data['boards'] != previous['boards'] or (new_time - old_time).total_seconds() >= HEARTBEAT_SECONDS
    except (KeyError, TypeError, ValueError, AttributeError):
        return True


def atomic_write(path, data):
    raw = (json.dumps(data, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    if len(raw) > MAX_RESULTS_BYTES:
        raise ValueError('Results too large')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            name = stream.name
            stream.write(raw)
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def git(repo, *args, check=True):
    return subprocess.run(['git', '-C', str(repo), *args], check=check, text=True, capture_output=True)


def publish(repo, data):
    repo = Path(repo).resolve()
    path = repo / 'workday_jobs.json'
    try:
        previous = json.loads(git(repo, 'show', 'HEAD:workday_jobs.json').stdout)
    except (subprocess.CalledProcessError, ValueError):
        previous = None
    if not should_publish(data, previous):
        print('No changes or heartbeat due; checking for unpushed commits')
    else:
        atomic_write(path, data)
        git(repo, 'add', '--', 'workday_jobs.json')
        git(repo, '-c', 'user.name=Workday Laptop', '-c', 'user.email=workday-laptop@users.noreply.github.com', 'commit', '-m', 'Update Workday results')
    for attempt in range(3):
        if git(repo, 'push', check=False).returncode == 0:
            return
        if attempt < 2:
            git(repo, 'pull', '--rebase')
            time.sleep(2 ** attempt)
    raise RuntimeError('Git push failed after three attempts')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, help='write a local results file')
    parser.add_argument('--push', type=Path, metavar='REPO_DIR', help='publish to a private results clone')
    parser.add_argument('--dry-run', action='store_true', help='fetch and print without writing or pushing')
    parser.add_argument('--workers', type=int, default=DEFAULT_WORKERS, choices=range(1, MAX_WORKERS + 1),
                        help='companies fetched in parallel (1 = quiet mode)')
    args = parser.parse_args(argv)
    if not args.out and not args.push and not args.dry_run:
        parser.error('specify --out, --push, or --dry-run')
    config = json.loads(watcher.CONFIG_PATH.read_text(encoding='utf-8'))
    validate_config(config)
    data = collect(config, dry_run=args.dry_run, workers=args.workers)
    if data is None:
        return 0
    if args.dry_run:
        print(json.dumps(data, indent=2))
    else:
        if args.out:
            atomic_write(args.out, data)
        if args.push:
            publish(args.push, data)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
