#!/usr/bin/env python3
"""Fetch Workday at home and optionally publish to a private git clone."""
import argparse
import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import watcher
from job_feeds import board_url, company_board
from project_config import validate_config
from workday_results import MAX_RESULTS_BYTES, validate_results

HEARTBEAT_SECONDS = 2 * 3600


def collect(config):
    companies = [c for c in config['companies'] if c['ats'] == 'workday']
    boards = {}
    for index, company in enumerate(companies):
        board = company_board(company)
        if index:
            time.sleep(1)
        watcher.SOURCE_HEALTH.clear()
        try:
            jobs = watcher.fetch_workday(board)
            record = watcher.SOURCE_HEALTH.get(board_url('workday', board), {})
            ok = bool(record.get('ok'))
            boards[board] = {'ok': ok, 'error': None if ok else str(record.get('error', 'Request failed')), 'jobs': jobs if ok else []}
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            boards[board] = {'ok': False, 'error': type(exc).__name__, 'jobs': []}
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
    args = parser.parse_args(argv)
    if not args.out and not args.push and not args.dry_run:
        parser.error('specify --out, --push, or --dry-run')
    config = json.loads(watcher.CONFIG_PATH.read_text(encoding='utf-8'))
    validate_config(config)
    data = collect(config)
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
