import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
import watcher
import notion_sync as notion
from job_utils import canonical_url, job_identity, job_terms, fingerprint, term_matches, preference_matches, load_json


def job(jid='greenhouse:example:123', **kwargs):
    return dict(id=jid, company='Example', title='SWE Intern', location='Austin, TX',
                url='https://boards.greenhouse.io/example/jobs/123', **kwargs)


def page(j, status='Saved', pid='page-1'):
    return {'id': pid, 'properties': {
        'Link': {'url': j['url']}, 'Status': {'select': {'name': status}},
        'Role': {'title': [{'plain_text': j['title']}]}}}


class UnknownSeasonTests(unittest.TestCase):
    def test_na_is_an_unknown_season_not_a_mismatch(self):
        j = {'title': 'Firmware Intern', 'terms': ['N/A']}
        self.assertEqual(job_terms(j), [])
        self.assertTrue(term_matches(j, ['Summer 2027']))
        self.assertFalse(term_matches(j, ['Summer 2027'], keep_unknown=False))
        self.assertFalse(term_matches({**j, 'terms': ['Summer 2026']}, ['Summer 2027']))
        self.assertFalse(term_matches({**j, 'title': 'Firmware Intern 2026'}, ['Summer 2027']))
        self.assertTrue(term_matches({**j, 'terms': ['N/A', 'Summer 2027']}, ['Summer 2027']))


class CleanJobTests(unittest.TestCase):
    def test_normalizes_nulls_controls_and_schemes(self):
        from job_utils import clean_job
        cleaned = clean_job({'id': 'a', 'company': None, 'title': 'SWE\nIntern\x00', 'location': None,
                             'url': 'ftp://x.example/1', 'terms': ['Summer 2027']})
        self.assertEqual((cleaned['company'], cleaned['title'], cleaned['location'], cleaned['url']),
                         ('', 'SWE Intern', '', ''))
        self.assertEqual(cleaned['terms'], ['Summer 2027'])
        self.assertEqual(clean_job({'id': 'b', 'title': ' '})['title'], 'Untitled')

    def test_valid_job_identity_is_unchanged(self):
        from job_utils import clean_job
        j = job()
        self.assertEqual(job_identity(clean_job(j)), job_identity(j))
        self.assertEqual(fingerprint(clean_job(j)), fingerprint(j))


class KeywordTests(unittest.TestCase):
    INCLUDE = ["intern", "internship", "co-op", "coop"]
    EXCLUDE = ["internal", "sales", "marketing", "mba", " mba", "mba ", "ph.d", "hr intern"]

    def check(self, title):
        return watcher.matches(title, self.INCLUDE, self.EXCLUDE)

    def test_intern_is_a_whole_word(self):
        for title in ("Software Engineer Intern", "Software Engineering Interns",
                      "Data Science Intern, Summer 2027", "Backend Co-op", "SWE Internship"):
            self.assertTrue(self.check(title), title)
        for title in ("International Payments Engineer", "Internet Infrastructure Engineer",
                      "Internal Tools Engineer"):
            self.assertFalse(self.check(title), title)

    def test_exclusions_do_not_hide_engineering_roles(self):
        self.assertTrue(self.check("Salesforce Developer Intern"))
        self.assertFalse(self.check("Sales Intern"))
        self.assertFalse(self.check("Marketing Intern"))
        self.assertFalse(self.check("MBA Intern"))
        self.assertFalse(self.check("HR Intern"))
        self.assertFalse(self.check("PH.D. Research Intern"))

    def test_missing_title_and_empty_lists(self):
        self.assertFalse(watcher.matches(None, self.INCLUDE, self.EXCLUDE))
        self.assertFalse(watcher.matches("SWE Intern", [], []))
        self.assertTrue(watcher.matches("SWE Intern", self.INCLUDE, []))


class IdentityTests(unittest.TestCase):
    def test_preserves_job_query_and_fragments(self):
        url = 'https://careers.example.com/job?gh_jid=123&utm_source=mail&lang=en#/apply'
        clean = canonical_url(url)
        self.assertIn('gh_jid=123', clean)
        self.assertIn('lang=en', clean)
        self.assertTrue(clean.endswith('#/apply'))
        self.assertNotIn('utm_source', clean)
        self.assertNotEqual(clean, canonical_url(url.replace('123', '456')))

    def test_greenhouse_custom_domain_and_native_identity(self):
        j = job()
        other = {**j, 'url': 'https://careers.example.com/job?gh_jid=123'}
        self.assertEqual(job_identity(j), job_identity(other))

    def test_term_filter_all_sources_and_unknown(self):
        j = job()
        j['title'] = 'Summer 2026 SWE Intern'
        self.assertFalse(term_matches(j, ['Summer 2027']))
        j['title'] = 'SWE Intern'
        self.assertTrue(term_matches(j, ['Summer 2027']))
        self.assertFalse(term_matches(j, ['Summer 2027'], False))
        j['terms'] = ['Summer 2027']
        self.assertTrue(term_matches(j, ['Summer 2027']))

    def test_known_wrong_year_is_not_unknown(self):
        j = {**job(), "title": "2026 Software Engineering Intern"}
        self.assertFalse(term_matches(j, ["Summer 2027"]))

    def test_personal_preferences_all_dimensions(self):
        prefs = {'roles': ['SWE'], 'companies': ['Example'], 'locations': ['Austin'], 'terms': ['Summer 2027']}
        self.assertTrue(preference_matches(job(), prefs))
        self.assertFalse(preference_matches({**job(), 'company': 'Other'}, prefs))

    def test_fingerprint_location_and_season(self):
        self.assertNotEqual(fingerprint(job()), fingerprint({**job(), 'location': 'New York, NY'}))
        self.assertNotEqual(fingerprint(job()), fingerprint(job(terms=['Summer 2027'])))

    def test_old_norm_does_not_hide_new_season(self):
        j = job('simplify:new', agg=True, terms=['Summer 2027'])
        seen = {watcher.norm_key(j)}
        self.assertEqual(watcher.select_new([j], seen, {}, 100), [j])

    def test_same_url_cross_source_dedup(self):
        j = job()
        duplicate = {**j, 'id': 'simplify:456', 'agg': True}
        self.assertEqual(watcher.select_new([j, duplicate], set(), {}, 100), [j])

    def test_fuzzy_expiry_and_existing_history_migration(self):
        j = job('jobright:456', agg=True)
        ledger = {'fingerprints': {fingerprint(j): 0}}
        self.assertEqual(watcher.select_new([j], set(), ledger, 31 * 86400), [j])
        old = job()
        j['url'] = 'https://jobright.ai/jobs/info/456'
        self.assertEqual(watcher.select_new([old, j], {old['id']}, {}, 100), [])

    def test_corrupt_state_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'seen.json'
            path.write_text('{')
            with self.assertRaises(json.JSONDecodeError):
                load_json(path, [])


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.patch = patch.multiple(watcher, ROOT=self.root, CONFIG_PATH=self.root/'config.json',
                                    SEEN_PATH=self.root/'seen.json', MSG_MAP_PATH=self.root/'message_map.json')
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.cfg = {'companies': [], 'simplify': {'enabled': False}}
        (self.root/'config.json').write_text(json.dumps(self.cfg))

    @patch('watcher.time.sleep')
    @patch('watcher.requests.post')
    def test_large_batch_failure_not_acknowledged(self, post, sleep):
        post.return_value = Mock(status_code=500, headers={})
        jobs = [{**job(), 'id': str(i)} for i in range(26)]
        records, failed = watcher.notify_discord('https://example.invalid/hook', jobs)
        self.assertEqual(len(failed), 26)
        self.assertEqual(records, [])

    @patch('watcher.time.sleep')
    @patch('watcher.requests.post')
    def test_rate_limit_retry_and_timeout(self, post, sleep):
        post.side_effect = [Mock(status_code=429, headers={'Retry-After': '1'}),
                            Mock(status_code=200, json=lambda: {'id': 'm', 'channel_id': 'c'})]
        records, failed = watcher.notify_discord('https://example.invalid/hook', [job()])
        self.assertFalse(failed)
        self.assertEqual(records[0]['mid'], 'm')
        post.side_effect = requests.Timeout()
        self.assertEqual(watcher.notify_discord('https://example.invalid/hook', [job()])[1], {job()['id']})

    @patch('watcher.time.sleep')
    @patch('watcher.requests.post')
    def test_untrusted_text_cannot_rewrite_discord_link(self, post, sleep):
        post.return_value = Mock(status_code=200, json=lambda: {'id': 'm', 'channel_id': 'c'})
        hostile = {**job(), 'title': 'Intern](https://evil.example) [x', 'url': 'https://a.example/p(1) 2'}
        watcher.notify_discord('https://example.invalid/hook', [hostile])
        content = post.call_args.kwargs['json']['content']
        self.assertIn('[Intern)(https://evil.example) (x](https://a.example/p%281%29%202)', content)
        self.assertEqual(content.count('](http'), 1)

    def test_null_feed_fields_do_not_crash_discovery(self):
        board = [{'id': 'lever:x:1', 'title': None, 'location': None, 'url': 'javascript:alert(1)'},
                 {'id': 'lever:x:2', 'title': 'SWE Intern', 'location': None, 'url': 'https://x.example/2'}]
        cfg = {'companies': [{'name': 'X', 'ats': 'lever', 'board': 'x'}], 'include_keywords': ['intern'],
               'simplify': {'enabled': False}}
        with patch.dict(watcher.ATS_FETCHERS, {'lever': lambda board_name: board}):
            found = watcher.discover(cfg)
        self.assertEqual([j['id'] for j in found], ['lever:x:2'])
        self.assertEqual(found[0]['location'], '')
        fingerprint(found[0])  # previously AttributeError on a null location

    def queue(self, *jobs):
        return {'pending': {j['id']: {'job': j, 'destinations': ['email'], 'created': 0} for j in jobs}}

    def test_unexpected_error_does_not_block_later_jobs(self):
        bad, good = job('a:1'), job('a:2')
        ledger = self.queue(bad, good)
        sent = []
        def send(cfg, jobs):
            if jobs[0]['id'] == 'a:1':
                raise TypeError('boom')
            sent.append(jobs[0]['id'])
        with patch.object(watcher, 'notify_email', side_effect=send):
            watcher.deliver(ledger, {}, {}, lambda: None)
        self.assertEqual(sent, ['a:2'])
        self.assertEqual(list(ledger['pending']), ['a:1'])
        self.assertEqual(ledger['pending']['a:1']['error'], 'TypeError')

    def test_repeated_failure_is_parked_and_stops_failing_runs(self):
        from source_health import build_health, health_exit_code, health_summary
        ledger = self.queue(job('a:1'))
        cfg = {'max_delivery_attempts': 3}
        with patch.object(watcher, 'notify_email', side_effect=ValueError('bad')):
            for _ in range(2):
                watcher.deliver(ledger, cfg, {}, lambda: None)
            self.assertIn('a:1', ledger['pending'])
            watcher.deliver(ledger, cfg, {}, lambda: None)
        self.assertEqual(ledger['pending'], {})
        parked = ledger['dead']['a:1|email']
        self.assertEqual((parked['attempts'], parked['error']), (3, 'ValueError'))
        health = build_health({}, {}, now=1, matching_jobs=0, new_jobs=0, pending_deliveries=0,
                              sync_error=None, dead_deliveries=len(ledger['dead']))
        self.assertEqual(health_exit_code(health), 0)
        self.assertIn('parked: 1', health_summary(health))

    def test_success_clears_attempt_count(self):
        ledger = self.queue(job('a:1'))
        with patch.object(watcher, 'notify_email', side_effect=[ValueError('x'), None]):
            watcher.deliver(ledger, {}, {}, lambda: None)
            self.assertEqual(ledger['pending']['a:1']['tries'], {'email': 1})
            watcher.deliver(ledger, {}, {}, lambda: None)
        self.assertEqual(ledger['pending'], {})
        self.assertEqual(ledger.get('dead', {}), {})

    def test_dry_run_unchanged_even_with_credentials(self):
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        with patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'test'}, clear=True), \
             patch.object(watcher, 'discover', return_value=[job()]), \
             patch.object(watcher, 'notify_discord') as send:
            self.assertEqual(watcher.main(['--dry-run']), 0)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        send.assert_not_called()

    def test_no_credentials_implies_dry_run(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(watcher, 'discover', return_value=[job()]):
            watcher.main([])
        self.assertFalse((self.root/'seen.json').exists())

    def test_destination_retry_survives_disappearing_source(self):
        cfg = self.cfg
        j = job()
        responses = [([], {j['id']}), ([{'mid': 'm', 'cid': 'c', 'ts': 1, 'job': j}], set())]
        with patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'test'}, clear=True), \
             patch.object(watcher, 'discover', side_effect=[[j], []]), \
             patch.object(watcher, 'notify_discord', side_effect=responses) as send:
            self.assertEqual(watcher.main([]), 1)
            ledger = load_json(self.root/'delivery_state.json', {})
            self.assertIn(j['id'], ledger['pending'])
            self.assertEqual(watcher.main([]), 0)
            self.assertEqual(send.call_count, 2)
        self.assertEqual(load_json(self.root/'delivery_state.json', {})['pending'], {})

    def test_destinations_independent_and_budget_preserves_backlog(self):
        j = job()
        ledger = {'pending': {j['id']: {'job': j, 'destinations': ['discord:HOOK', 'notion']}}}
        with patch.dict(os.environ, {'HOOK': 'test'}), \
             patch.object(watcher, 'notify_discord') as send, patch.object(notion, 'log_master', return_value=True):
            watcher.deliver(ledger, {'max_discord_per_run': 0}, {}, lambda: None)
            send.assert_not_called()
        self.assertEqual(ledger['pending'][j['id']]['destinations'], ['discord:HOOK'])

    def test_completed_destinations_not_repeated(self):
        j = job()
        ledger = {'pending': {j['id']: {'job': j, 'destinations': ['discord:HOOK', 'notion']}}}
        with patch.dict(os.environ, {'HOOK': 'test'}), \
             patch.object(watcher, 'notify_discord', return_value=([{'mid': 'm', 'cid': 'c', 'ts': 1, 'job': j}], set())) as send, \
             patch.object(notion, 'log_master', side_effect=[False, True]):
            watcher.deliver(ledger, {}, {}, lambda: None)
            watcher.deliver(ledger, {}, {}, lambda: None)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(ledger['pending'], {})

    def test_source_failure_reported(self):
        watcher.SOURCE_HEALTH.clear()
        with patch.object(watcher.requests, 'get', return_value=Mock(status_code=404)):
            self.assertIsNone(watcher.get('https://example.invalid/jobs'))
        self.assertFalse(watcher.SOURCE_HEALTH['https://example.invalid/jobs']['ok'])

    def test_malformed_feed_schema_is_failure_not_empty_success(self):
        url = 'https://example.invalid/jobs'
        watcher.SOURCE_HEALTH[url] = {'last_success': 42, 'ok': True}
        with patch.object(watcher, 'get', return_value={'unexpected': []}):
            self.assertEqual(watcher.source_items(url, 'jobs'), [])
        self.assertFalse(watcher.SOURCE_HEALTH[url]['ok'])
        self.assertEqual(watcher.SOURCE_HEALTH[url]['last_success'], 42)

    def test_malformed_schema_preserves_outage_age_across_http_success(self):
        url = 'https://example.invalid/jobs'
        watcher.SOURCE_HEALTH[url] = {'last_success': 42, 'ok': False, 'failing_since': 50}
        response = Mock(status_code=200)
        response.json.return_value = {'unexpected': []}
        with patch.object(watcher.requests, 'get', return_value=response):
            self.assertEqual(watcher.source_items(url, 'jobs'), [])
        self.assertEqual(watcher.SOURCE_HEALTH[url]['last_success'], 42)
        self.assertEqual(watcher.SOURCE_HEALTH[url]['failing_since'], 50)

    def test_removed_source_does_not_keep_failing_later_runs(self):
        (self.root/'health.json').write_text(json.dumps({'sources': {
            'old-board': {'ok': False, 'error': 'HTTP 404', 'failing_since': 1}}}))
        with patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'test'}, clear=True), \
             patch.object(watcher, 'discover', return_value=[]):
            self.assertEqual(watcher.main([]), 0)
        self.assertEqual(load_json(self.root/'health.json', {})['sources'], {})

    def run_with_sources(self, sources, previous):
        """Run main() with prior health and a discover() that sets source results."""
        (self.root/'health.json').write_text(json.dumps({'sources': previous}))
        def discover(cfg):
            watcher.SOURCE_HEALTH.update(copy.deepcopy(sources))
            return []
        env = {'DISCORD_WEBHOOK_URL': 'test', 'GITHUB_TOKEN': 't', 'GITHUB_REPOSITORY': 'o/r'}
        with patch.dict(os.environ, env, clear=True), patch.object(watcher, 'discover', side_effect=discover), \
             patch.object(watcher, 'github_api', return_value={'number': 7}) as api:
            code = watcher.main([])
        return code, load_json(self.root/'health.json', {})['sources'], api

    def test_stale_source_opens_one_issue_without_failing_run(self):
        url = 'https://boards-api.greenhouse.io/v1/boards/gone/jobs'
        down = {'ok': False, 'error': 'HTTP 404', 'failing_since': 1}
        # One dead board among many healthy ones, below the broad-outage share.
        healthy = {f'https://example.invalid/{i}': {'ok': True, 'last_success': 1} for i in range(20)}
        code, sources, api = self.run_with_sources({url: down, **healthy}, {url: down})
        self.assertEqual(code, 0)
        self.assertEqual(sources[url]['issue'], 7)
        self.assertEqual(api.call_args.args[:2], ('POST', 'issues'))
        code, _, api = self.run_with_sources({url: dict(sources[url]), **healthy}, sources)
        self.assertEqual(code, 0)
        api.assert_not_called()

    def test_recovered_source_closes_issue(self):
        url = 'https://boards-api.greenhouse.io/v1/boards/back/jobs'
        previous = {url: {'ok': False, 'error': 'HTTP 404', 'failing_since': 1, 'issue': 7}}
        _, sources, api = self.run_with_sources({url: {'ok': True, 'last_success': 1}}, previous)
        self.assertNotIn('issue', sources[url])
        self.assertIn(('PATCH', 'issues/7', {'state': 'closed', 'state_reason': 'completed'}),
                      [c.args for c in api.call_args_list])

    def test_removed_source_closes_issue(self):
        url = 'https://boards-api.greenhouse.io/v1/boards/removed/jobs'
        previous = {url: {'ok': False, 'error': 'HTTP 404', 'failing_since': 1, 'issue': 7}}
        _, sources, api = self.run_with_sources({}, previous)
        self.assertEqual(sources, {})
        self.assertIn(('PATCH', 'issues/7', {'state': 'closed', 'state_reason': 'completed'}),
                      [c.args for c in api.call_args_list])

    def test_broad_outage_still_fails_run(self):
        down = {f'https://example.invalid/{i}': {'ok': False, 'error': 'Timeout', 'failing_since': 1}
                for i in range(watcher.MAX_STALE_SOURCES + 1)}
        code, _, _ = self.run_with_sources(down, down)
        self.assertEqual(code, 1)

    def test_invalid_config_rejected(self):
        with self.assertRaises(ValueError):
            watcher.validate_config({'companies': [], 'max_discord_per_run': -1})
        with self.assertRaises(ValueError):
            watcher.validate_config({'companies': [], 'profiles': {'u': {'roles': 'SWE'}}})

    def test_profile_secret_import_without_workflow_edits(self):
        cfg = {**self.cfg, 'profiles': {'u': {'webhook_env': 'DISCORD_WEBHOOK_MEMBER'}}}
        (self.root/'config.json').write_text(json.dumps(cfg))
        secret = json.dumps({'DISCORD_WEBHOOK_MEMBER': 'https://example.invalid/hook'})
        with patch.dict(os.environ, {'PERSONAL_WEBHOOKS_JSON': secret}, clear=True), \
             patch.object(watcher, 'discover', return_value=[]):
            self.assertEqual(watcher.main([]), 0)
            self.assertEqual(os.environ['DISCORD_WEBHOOK_MEMBER'], 'https://example.invalid/hook')
        self.assertTrue((self.root/'delivery_state.json').exists())


class NotionTests(unittest.TestCase):
    def setUp(self):
        notion._PAGE_CACHE.clear()
        self.addCleanup(notion._PAGE_CACHE.clear)

    def test_saved_row_updated_in_place_with_reminder(self):
        j = job()
        saved = page(j)
        with patch.object(notion, '_notion', side_effect=[{'results': [saved]}, {'id': saved['id']}]) as api, \
             patch.object(notion, '_add_row') as add:
            result = notion._upsert_row('db', j, 'Applied')
        add.assert_not_called()
        self.assertEqual(result['id'], saved['id'])
        props = api.call_args.args[2]['properties']
        self.assertEqual(props['Status']['select']['name'], 'Applied')
        self.assertIn('start', props['Follow-up']['date'])

    def test_late_pin_does_not_downgrade_applied(self):
        j = job()
        with patch.object(notion, '_notion', return_value={'results': [page(j, 'Applied')]}) as api:
            notion._upsert_row('db', j, 'Saved')
        self.assertEqual(api.call_count, 1)

    def test_interview_not_downgraded_on_applied_link(self):
        j = job()
        with patch.object(notion, '_notion', return_value={'results': [page(j, 'Interview')]}) as api:
            notion._upsert_row('db', j, 'Applied')
        self.assertEqual(api.call_count, 1)

    def test_lookup_failure_never_creates_duplicate(self):
        with patch.object(notion, '_notion', return_value=None), patch.object(notion, '_add_row') as add:
            self.assertIsNone(notion._upsert_row('db', job(), 'Saved'))
        add.assert_not_called()

    def test_existing_tracking_parameters_reconcile(self):
        j = job()
        existing = page({**j, 'url': j['url'] + '?utm_source=discord'})
        with patch.object(notion, '_notion', return_value={'results': [existing]}), patch.object(notion, '_add_row') as add:
            self.assertIsNotNone(notion._upsert_row('db', j, 'Saved'))
        add.assert_not_called()

    def test_failed_applied_is_pending_after_cursor_advance(self):
        state = {'users': {}, 'applied_after': '1'}
        msg = {'id': '2', 'author': {'id': 'u', 'username': 'member'},
               'content': 'https://careers.example.com/job?gh_jid=123&utm_source=x'}
        def ensure(u, parent, days):
            u['db'] = 'db'
            return True
        with patch.dict(os.environ, {'APPLIED_CHANNEL_ID': 'c'}), \
             patch.object(notion, '_channel_messages', return_value=[msg]), \
             patch.object(notion, '_save'), patch.object(notion, '_ensure_tracker', side_effect=ensure), \
             patch.object(notion, '_parse_job_from_url', return_value=('Example', 'Intern', 'TX')), \
             patch.object(notion, '_upsert_row', return_value=None), patch.object(notion, '_react') as react:
            notion._sync_applied(state, 'token', 'parent')
        self.assertEqual(state['applied_after'], '2')
        self.assertIn('2:0', state['pending_applied'])
        self.assertIn('gh_jid=123', state['pending_applied']['2:0']['url'])
        react.assert_not_called()
        with patch.dict(os.environ, {'APPLIED_CHANNEL_ID': 'c'}), \
             patch.object(notion, '_channel_messages', return_value=[]), patch.object(notion, '_save'), \
             patch.object(notion, '_ensure_tracker', side_effect=ensure), \
             patch.object(notion, '_upsert_row', return_value={'id': 'page'}), patch.object(notion, '_react'):
            notion._sync_applied(state, 'token', 'parent')
        self.assertEqual(state['pending_applied'], {})

    def test_followups_only_for_due_applied(self):
        due = page(job(), 'Applied')
        due['properties']['Follow-up'] = {'date': {'start': '2000-01-01'}}
        finished = copy.deepcopy(due)
        finished['properties']['Status']['select']['name'] = 'Offer'
        with patch.object(notion, '_pages', return_value=[due, finished]):
            self.assertEqual(notion._follow_ups('db'), ['SWE Intern'])

    def test_master_retry_finds_existing_page(self):
        with patch.object(notion, '_state', return_value={'master_db': 'db'}), \
             patch.object(notion, '_notion', return_value={'results': [page(job())]}), \
             patch.object(notion, '_add_row') as add:
            self.assertTrue(notion.log_master(job()))
        add.assert_not_called()

    def test_ambiguous_create_not_blindly_retried(self):
        with patch.dict(os.environ, {'NOTION_TOKEN': 'test'}), \
             patch.object(notion.requests, 'request', side_effect=requests.Timeout()) as api:
            self.assertIsNone(notion._notion('POST', '/pages', {}))
        self.assertEqual(api.call_count, 1)

    def test_applied_batch_pagination_retains_every_link(self):
        state = {'users': {}, 'applied_after': '1'}
        messages = [{'id': str(i), 'author': {'id': 'u'},
                     'content': f'https://example.com/jobs/{i}'} for i in range(2, 102)]
        second = [{'id': '102', 'author': {'id': 'u'}, 'content': 'https://example.com/jobs/102'}]
        with patch.dict(os.environ, {'APPLIED_CHANNEL_ID': 'c'}), \
             patch.object(notion, '_channel_messages', side_effect=[messages, second]) as fetch, \
             patch.object(notion, 'MAX_APPLIED_LINKS_PER_RUN', 1000), \
             patch.object(notion, '_save'), patch.object(notion, '_ensure_tracker', return_value=False):
            notion._sync_applied(state, 'token', 'parent')
        self.assertEqual(fetch.call_args_list[1].args[2], '101')
        self.assertEqual(len(state['pending_applied']), 101)
        self.assertEqual(state['applied_after'], '102')


if __name__ == '__main__':
    unittest.main()
