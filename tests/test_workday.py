import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import watcher
import verify_boards
import notion_sync
from job_feeds import board_url
from project_config import validate_config

BOARD = 'nvidia/NVIDIAExternalCareerSite/wd5'
FIXTURES = Path(__file__).parent / 'fixtures'


def fixture(name='nvidia'):
    return json.loads((FIXTURES / f'workday_{name}.json').read_text())


class WorkdayTests(unittest.TestCase):
    def setUp(self):
        watcher.SOURCE_HEALTH.clear()
        self.addCleanup(watcher.SOURCE_HEALTH.clear)

    def response(self, data):
        return Mock(status_code=200, json=lambda: data)

    def test_fixtures_and_pagination_identity(self):
        for name in ('nvidia', 'salesforce', 'adobe', 'blueorigin', 'bostondynamics'):
            data = fixture(name)
            data['total'] = len(data['jobPostings'])
            with self.subTest(tenant=name), patch.object(watcher.requests, 'post', return_value=self.response(data)):
                self.assertEqual(len(watcher.fetch_workday(BOARD)), data['total'])
        data = fixture()
        a, b = data['jobPostings']
        with patch.object(watcher.requests, 'post', return_value=self.response({'total': 2, 'jobPostings': [a, b]})):
            jobs = watcher.fetch_workday(BOARD)
        with patch.object(watcher.requests, 'post', return_value=self.response({'total': 2, 'jobPostings': [b, a]})):
            reverse = watcher.fetch_workday(BOARD)
        self.assertEqual({j['id'] for j in jobs}, {j['id'] for j in reverse})
        self.assertTrue(jobs[0]['url'].startswith('https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/'))

    def postings(self, start, count):
        base = fixture()['jobPostings'][0]
        return [{**base, 'externalPath': f'/job/Austin/Intern_{i}'} for i in range(start, start + count)]

    def test_cap_returns_results_and_marks_truncated(self):
        pages = [{'total': 200 if n == 0 else 0, 'jobPostings': self.postings(n * 20, 20)} for n in range(2)]
        with patch.object(watcher.requests, 'post', side_effect=[self.response(p) for p in pages]) as post, patch.object(watcher.time, 'sleep') as sleep:
            jobs = watcher.fetch_workday(BOARD)
        self.assertEqual(len(jobs), 40)
        self.assertEqual([c.kwargs['json']['offset'] for c in post.call_args_list], [0, 20])
        self.assertEqual(sleep.call_count, 1)
        self.assertTrue(watcher.SOURCE_HEALTH[board_url('workday', BOARD)]['truncated'])
        with patch.object(watcher.requests, 'post', return_value=self.response({'total': 0, 'jobPostings': []})):
            self.assertEqual(watcher.fetch_workday(BOARD), [])
        self.assertNotIn('truncated', watcher.SOURCE_HEALTH[board_url('workday', BOARD)])

    def test_overlap_skipped_and_later_total_ignored(self):
        pages = [{'total': 21, 'jobPostings': self.postings(0, 20)},
                 {'total': 0, 'jobPostings': self.postings(19, 2)}]
        with patch.object(watcher.requests, 'post', side_effect=[self.response(p) for p in pages]), patch.object(watcher.time, 'sleep'):
            jobs = watcher.fetch_workday(BOARD)
        self.assertEqual(len(jobs), 21)
        self.assertTrue(watcher.SOURCE_HEALTH[board_url('workday', BOARD)]['ok'])

    def test_duplicate_page_fails(self):
        items = self.postings(0, 20)
        pages = [{'total': 40, 'jobPostings': items}, {'total': 0, 'jobPostings': items}]
        with patch.object(watcher.requests, 'post', side_effect=[self.response(p) for p in pages]), patch.object(watcher.time, 'sleep'):
            self.assertEqual(watcher.fetch_workday(BOARD), [])
        self.assertEqual(watcher.SOURCE_HEALTH[board_url('workday', BOARD)]['error'], 'Repeated pagination page')

    def test_http_error_not_retried(self):
        for status in (429, 503):
            with self.subTest(status=status), patch.object(watcher.requests, 'post', return_value=Mock(status_code=status)) as post, patch.object(watcher.time, 'sleep') as sleep:
                self.assertEqual(watcher.fetch_workday(BOARD), [])
                self.assertEqual(post.call_count, 1)
                sleep.assert_not_called()
                self.assertEqual(watcher.SOURCE_HEALTH[board_url('workday', BOARD)]['error'], f'HTTP {status}')

    def test_dates(self):
        now = datetime(2026, 11, 24, tzinfo=timezone.utc)
        for text, expected in [('Posted Today', '2026-11-24'), ('Posted Yesterday', '2026-11-23'),
                               ('Posted 3 Days Ago', '2026-11-21'), ('Posted 30+ Days Ago', '2026-10-25'),
                               ('unknown', None), (None, None)]:
            self.assertEqual(watcher.workday_posted_date(text, now), expected)

    def test_malformed_envelope_fails_but_bad_postings_are_skipped(self):
        good = fixture()['jobPostings'][0]
        bad = copy.deepcopy(good)
        del bad['externalPath']
        for data in ({}, {'total': 1, 'jobPostings': None}, {'jobPostings': []}):
            with self.subTest(data=data), patch.object(watcher.requests, 'post', return_value=self.response(data)):
                self.assertEqual(watcher.fetch_workday(BOARD), [])
                self.assertFalse(watcher.SOURCE_HEALTH[board_url('workday', BOARD)]['ok'])
        with patch.object(watcher.requests, 'post', return_value=self.response({'total': 3, 'jobPostings': [bad, None, good]})):
            self.assertEqual(len(watcher.fetch_workday(BOARD)), 1)
            self.assertTrue(watcher.SOURCE_HEALTH[board_url('workday', BOARD)]['ok'])
        with patch.object(watcher.requests, 'post', return_value=self.response({'total': 50, 'jobPostings': []})):
            self.assertEqual(watcher.fetch_workday(BOARD), [])
            self.assertTrue(watcher.SOURCE_HEALTH[board_url('workday', BOARD)]['ok'])

    def test_discover_records_exception_at_board_url(self):
        company = {'name': 'NVIDIA', 'ats': 'workday', 'tenant': 'nvidia',
                   'site': 'NVIDIAExternalCareerSite', 'host': 'wd5'}
        cfg = {'companies': [company], 'simplify': {'enabled': False}, 'jobright': {'enabled': False}}
        with patch.dict(watcher.ATS_FETCHERS, {'workday': Mock(side_effect=ValueError('bad data'))}):
            self.assertEqual(watcher.discover(cfg), [])
        self.assertFalse(watcher.SOURCE_HEALTH[board_url('workday', BOARD)]['ok'])
        self.assertNotIn('workday:' + BOARD, watcher.seeded_boards({}, set(), {}, [company]))
        self.assertIn('workday:' + BOARD, watcher.seeded_boards({}, set(), {board_url('workday', BOARD): {}}, [company]))

    def test_notion_board_mapping_accepts_workday(self):
        companies = [{'name': 'NVIDIA', 'ats': 'workday', 'tenant': 'nvidia',
                      'site': 'NVIDIAExternalCareerSite', 'host': 'wd5'},
                     {'name': 'Acme', 'ats': 'greenhouse', 'board': 'acme'}]
        with patch.object(notion_sync, 'load_json', return_value={'companies': companies}):
            self.assertEqual(notion_sync._config_boards(), {'acme': ('greenhouse', 'acme'), 'nvidia': ('workday', BOARD)})

    def test_config_and_verifier(self):
        company = {'name': 'NVIDIA', 'ats': 'workday', 'tenant': 'nvidia', 'site': 'NVIDIAExternalCareerSite', 'host': 'wd5'}
        validate_config({'companies': [company]})
        for key in ('tenant', 'site', 'host'):
            bad = dict(company, **{key: '../bad'})
            with self.assertRaises(ValueError):
                validate_config({'companies': [bad]})
        data = fixture(); data['total'] = len(data['jobPostings'])
        with patch.object(watcher.requests, 'post', return_value=self.response(data)):
            self.assertEqual(verify_boards.main(['--candidate', 'workday', BOARD]), 0)
        with patch.object(verify_boards, 'load_json', return_value={'companies': [company]}), patch.object(watcher.requests, 'post', return_value=self.response(data)):
            self.assertEqual(verify_boards.main(['--company', 'NVIDIA']), 0)
        with patch.object(watcher.requests, 'post', return_value=self.response({})):
            self.assertEqual(verify_boards.main(['--candidate', 'workday', BOARD]), 1)


if __name__ == '__main__':
    unittest.main()
