import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import watcher
import workday_fetch
from job_feeds import board_url
from source_health import build_health, health_exit_code, health_summary
from workday_results import read_results, validate_results

BOARD = 'nvidia/NVIDIAExternalCareerSite/wd5'
COMPANY = {'name': 'NVIDIA', 'ats': 'workday', 'tenant': 'nvidia', 'site': 'NVIDIAExternalCareerSite', 'host': 'wd5'}
CFG = {'companies': [COMPANY], 'simplify': {'enabled': False}, 'jobright': {'enabled': False}, 'vanshb03': {'enabled': False}}


def sample(now=None):
    return {'schema': 1, 'fetched_at': (now or datetime.now(timezone.utc)).isoformat(), 'boards': {
        BOARD: {'ok': True, 'error': None, 'jobs': [{'id': f'workday:{BOARD}:/job/A/B', 'title': 'Intern', 'location': '',
          'url': 'https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/A/B', 'posted_date': None}]}}}


class HandoffTests(unittest.TestCase):
    def setUp(self):
        watcher.SOURCE_HEALTH.clear()
        self.addCleanup(watcher.SOURCE_HEALTH.clear)

    def test_block_skips_remaining_and_not_down(self):
        other = {**COMPANY, 'name': 'Other', 'tenant': 'other'}
        response = Mock(status_code=429, headers={'Retry-After': '7200'})
        with patch.dict('os.environ', {}, clear=True), patch.object(watcher.requests, 'post', return_value=response) as post:
            watcher.discover({**CFG, 'companies': [COMPANY, other]})
        self.assertEqual(post.call_count, 1)
        self.assertGreater(watcher.SOURCE_HEALTH[board_url('workday', BOARD)]['retry_at'], watcher.time.time() + 7000)
        health = build_health(watcher.SOURCE_HEALTH, {}, now=watcher.time.time()+20000, matching_jobs=0, new_jobs=0, pending_deliveries=0, sync_error=None)
        self.assertEqual(health['stale_failed_sources'], 0)
        self.assertEqual(health['skipped_sources'], 2)
        self.assertEqual(health_exit_code(health), 0)
        self.assertIn('skipped', health_summary(health))

    def test_throttle(self):
        response = Mock(status_code=200, headers={}, json=lambda: {'total': 0, 'jobPostings': []})
        with patch.dict('os.environ', {}, clear=True), patch.object(watcher.requests, 'post', return_value=response) as post:
            watcher.discover(CFG)
            watcher.discover(CFG)
        self.assertEqual(post.call_count, 1)
        self.assertTrue(watcher.SOURCE_HEALTH[board_url('workday', BOARD)]['skipped'])

    def test_file_fresh_stale_malformed_and_hostile(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'jobs.json'
            with patch.dict('os.environ', {'WORKDAY_RESULTS': str(path)}), patch.object(watcher.requests, 'post') as post:
                path.write_text(json.dumps(sample()))
                self.assertEqual(len(watcher.discover(CFG)), 1)
                for data in (sample(datetime.now(timezone.utc)-timedelta(hours=3)), {'schema': 1}, sample()):
                    if 'boards' in data and data['fetched_at'] > (datetime.now(timezone.utc)-timedelta(hours=1)).isoformat():
                        data['boards'][BOARD]['jobs'][0]['url'] = 'https://nvidia.wd5.myworkdayjobs.com.evil.test/job/A'
                    path.write_text(json.dumps(data))
                    self.assertEqual(watcher.discover(CFG), [])
                    self.assertTrue(watcher.SOURCE_HEALTH[board_url('workday', BOARD)]['skipped'])
                path.unlink()
                self.assertEqual(watcher.discover(CFG), [])
                post.assert_not_called()

    def test_cloudflare_html(self):
        response = Mock(status_code=403, headers={'Server': 'cloudflare', 'Content-Type': 'text/html'})
        with patch.dict('os.environ', {}, clear=True), patch.object(watcher.requests, 'post', return_value=response):
            watcher.discover(CFG)
        self.assertTrue(watcher.SOURCE_HEALTH[board_url('workday', BOARD)]['skipped'])

    def test_collect_schema_and_heartbeat(self):
        response = Mock(status_code=200, headers={}, json=lambda: {'total': 0, 'jobPostings': []})
        with patch.object(watcher.requests, 'post', return_value=response):
            data = workday_fetch.collect(CFG)
        validate_results(data, [BOARD])
        old = copy.deepcopy(data)
        self.assertFalse(workday_fetch.should_publish(data, old))
        old['fetched_at'] = (datetime.now(timezone.utc)-timedelta(hours=6)).isoformat()
        self.assertTrue(workday_fetch.should_publish(data, old))
        old = copy.deepcopy(data); old['boards'][BOARD]['ok'] = False
        self.assertTrue(workday_fetch.should_publish(data, old))
        with tempfile.TemporaryDirectory() as tmp, patch.object(workday_fetch, 'git') as git:
            git.return_value = Mock(stdout=json.dumps(data), returncode=0)
            workday_fetch.publish(tmp, data)
            self.assertFalse(any('commit' in call.args for call in git.call_args_list))
            self.assertTrue(any('push' in call.args for call in git.call_args_list))
            git.reset_mock(); git.return_value = Mock(stdout=json.dumps(old), returncode=0)
            workday_fetch.publish(tmp, data)
            self.assertTrue(any('commit' in call.args for call in git.call_args_list))
            self.assertEqual(json.loads((Path(tmp)/'workday_jobs.json').read_text()), data)


if __name__ == '__main__':
    unittest.main()
