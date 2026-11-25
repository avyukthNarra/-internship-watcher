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
        pages = [{'total': 2, 'jobPostings': [a]}, {'total': 0, 'jobPostings': [b]}]
        with patch.object(watcher.requests, 'post', side_effect=[self.response(p) for p in pages]) as post:
            jobs = watcher.fetch_workday(BOARD)
        self.assertEqual([c.kwargs['json']['offset'] for c in post.call_args_list], [0, 20])
        self.assertEqual(len(jobs), 2)
        with patch.object(watcher.requests, 'post', return_value=self.response({'total': 2, 'jobPostings': [b, a]})):
            reverse = watcher.fetch_workday(BOARD)
        self.assertEqual({j['id'] for j in jobs}, {j['id'] for j in reverse})
        self.assertTrue(jobs[0]['url'].startswith('https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/'))

    def test_dates(self):
        now = datetime(2026, 11, 24, tzinfo=timezone.utc)
        for text, expected in [('Posted Today', '2026-11-24'), ('Posted Yesterday', '2026-11-23'),
                               ('Posted 3 Days Ago', '2026-11-21'), ('Posted 30+ Days Ago', '2026-10-25'),
                               ('unknown', None), (None, None)]:
            self.assertEqual(watcher.workday_posted_date(text, now), expected)

    def test_malformed_or_incomplete_pages_are_unhealthy(self):
        good = fixture()['jobPostings'][0]
        bad = copy.deepcopy(good)
        del bad['externalPath']
        for data in ({}, {'total': 1, 'jobPostings': [bad]}, {'total': 1, 'jobPostings': []}):
            with self.subTest(data=data), patch.object(watcher.requests, 'post', return_value=self.response(data)):
                self.assertEqual(watcher.fetch_workday(BOARD), [])
                self.assertFalse(watcher.SOURCE_HEALTH[board_url('workday', BOARD)]['ok'])
        with patch.object(watcher, 'WORKDAY_PAGE_CAP', 1), patch.object(watcher.requests, 'post', return_value=self.response({'total': 2, 'jobPostings': [good]})):
            self.assertEqual(watcher.fetch_workday(BOARD), [])
            self.assertFalse(watcher.SOURCE_HEALTH[board_url('workday', BOARD)]['ok'])

    def test_notion_board_mapping_accepts_workday(self):
        companies = [{'name': 'NVIDIA', 'ats': 'workday', 'tenant': 'nvidia',
                      'site': 'NVIDIAExternalCareerSite', 'host': 'wd5'},
                     {'name': 'Acme', 'ats': 'greenhouse', 'board': 'acme'}]
        with patch.object(notion_sync, 'load_json', return_value={'companies': companies}):
            self.assertEqual(notion_sync._config_boards(), {'acme': ('greenhouse', 'acme')})

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
