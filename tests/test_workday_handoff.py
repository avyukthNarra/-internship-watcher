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


class LaptopPagingAndBackoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / 'backoff.json'
        watcher.SOURCE_HEALTH.clear()
        self.addCleanup(watcher.SOURCE_HEALTH.clear)

    @staticmethod
    def page(offset):
        return Mock(status_code=200, headers={}, json=lambda: {
            'total': 300,
            'jobPostings': [{'externalPath': f'/job/A/{i}', 'title': 'Intern',
                             'locationsText': 'USA'} for i in range(offset, offset + 20)]})

    def test_validate_max_pages(self):
        from project_config import validate_config
        for value in (1, 5, 10):
            validate_config({'companies': [{**COMPANY, 'max_pages': value}]})
        for value in (0, 11, -1, True, 2.5, '5', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_config({'companies': [{**COMPANY, 'max_pages': value}]})

    def test_laptop_defaults_override_and_early_stop(self):
        def response(*args, **kwargs):
            return self.page(kwargs['json']['offset'])
        for company, expected in ((COMPANY, 5), ({**COMPANY, 'max_pages': 10}, 10),
                                  ({**COMPANY, 'max_pages': 1}, 1)):
            with self.subTest(expected=expected), patch.object(watcher.requests, 'post', side_effect=response) as post, patch.object(watcher.time, 'sleep') as sleep:
                data = workday_fetch.collect({'companies': [company]}, backoff_path=self.state)
                self.assertEqual(post.call_count, expected)
                self.assertEqual(len(data['boards'][BOARD]['jobs']), expected * 20)
                self.assertEqual(sleep.call_count, expected - 1)
                self.assertTrue(all(call.args == (1,) for call in sleep.call_args_list))
        with patch.object(watcher.requests, 'post', return_value=Mock(status_code=200, headers={}, json=lambda: {'total': 0, 'jobPostings': []})) as post:
            workday_fetch.collect({'companies': [COMPANY]}, backoff_path=self.state)
            self.assertEqual(post.call_count, 1)

    def test_backoff_persistence_stops_requests_and_resets(self):
        other = {**COMPANY, 'tenant': 'other'}
        cfg = {'companies': [COMPANY, other]}
        block = Mock(status_code=429, headers={'Retry-After': '4000'})
        with patch('time.time', return_value=10000), patch.object(watcher.requests, 'post', return_value=block) as post, patch.object(watcher.time, 'sleep'):
            result = workday_fetch.collect(cfg, backoff_path=self.state)
            self.assertEqual(post.call_count, 1)
            self.assertFalse(result['boards']['other/NVIDIAExternalCareerSite/wd5']['ok'])
            self.assertEqual(json.loads(self.state.read_text()), {'blocks': 1, 'retry_at': 14000})
            self.assertIsNone(workday_fetch.collect(cfg, backoff_path=self.state))
            self.assertEqual(post.call_count, 1)
        block.headers = {'Retry-After': '0'}
        with patch('time.time', return_value=14000), patch.object(watcher.requests, 'post', return_value=block), patch.object(watcher.time, 'sleep'):
            workday_fetch.collect(cfg, backoff_path=self.state)
        self.assertEqual(json.loads(self.state.read_text()), {'blocks': 2, 'retry_at': 17600})
        good = Mock(status_code=200, headers={}, json=lambda: {'total': 0, 'jobPostings': []})
        with patch('time.time', return_value=17600), patch.object(watcher.requests, 'post', return_value=good), patch.object(watcher.time, 'sleep'):
            workday_fetch.collect(cfg, backoff_path=self.state)
        self.assertEqual(json.loads(self.state.read_text()), {'blocks': 0, 'retry_at': 0})

    def test_backoff_cap_and_dry_run(self):
        workday_fetch.atomic_write(self.state, {'blocks': 10, 'retry_at': 0})
        block = Mock(status_code=403, headers={'Server': 'cloudflare', 'Content-Type': 'text/html'})
        with patch('time.time', return_value=10000), patch.object(watcher.requests, 'post', return_value=block):
            workday_fetch.collect({'companies': [COMPANY]}, backoff_path=self.state, dry_run=True)
            self.assertEqual(json.loads(self.state.read_text())['blocks'], 10)
            workday_fetch.collect({'companies': [COMPANY]}, backoff_path=self.state)
        self.assertEqual(json.loads(self.state.read_text()), {'blocks': 11, 'retry_at': 31600})


if __name__ == '__main__':
    unittest.main()
