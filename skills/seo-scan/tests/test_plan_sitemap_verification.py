"""Sitemap measurement gaps require verification, not invented source rewrites."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan
import mcp_server

ROOT = Path(__file__).parent / 'fixtures/planner/plain_html'
FETCH = 'technical.sitemap.fetch.unverified'
NOTES = 'technical.sitemap.validation.unverified'
CAP = 'technical.sitemap.traversal.incomplete'
SAMPLE = 'technical.sitemap.sample.unverified'
SOURCE = 'technical.sitemap.validation.issues'


def report(**changes):
    sitemap = {'errors': ['opaque fetch note'], 'fetch_failures': 1,
               'sitemaps_attempted': 2, 'sitemaps_fetched': 1,
               'problems': {}, 'invalid_lastmod': 0, 'broken_sample': [], 'sample': []}
    sitemap.update(changes)
    return {'schema_version': '2.0', 'site': 'https://example.test/',
            'homepage': {'url': 'https://example.test/', 'findings': []},
            'crawl': {'recurring': []}, 'sitemap': sitemap}


def actions(data):
    return {a['rule_id']: a for a in plan.build_plan(data, str(ROOT))['actions']}


class TestPlanSitemapVerification(unittest.TestCase):
    def assert_manual(self, action):
        self.assertIsInstance(action['title'], str)
        self.assertIn('sitemap', action['title'].lower())
        self.assertEqual('manual_external', action['safety'])
        self.assertTrue(action['manual_action'])
        self.assertFalse(action['requires_deploy'])
        self.assertEqual([], action['likely_files'])
        self.assertEqual('site', action['scope'])
        self.assertNotIn('Create/configure', action['proposed_change'])

    def assert_execution_gap(self, data):
        original = copy.deepcopy(data)
        files = {p: p.read_bytes() for p in ROOT.rglob('*') if p.is_file()}
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')), \
                mock.patch('socket.socket.connect', side_effect=AssertionError('No network')):
            built = plan.build_plan(data, str(ROOT), report_source='<mcp-object>')
            with mock.patch.object(Path, 'cwd', return_value=ROOT.resolve().parent):
                self.assertEqual(built, mcp_server._plan(data, ROOT.name))
        self.assertEqual(original, data)
        self.assertTrue(all(p.read_bytes() == contents for p, contents in files.items()))
        output = {a['rule_id']: a for a in built['actions']}
        self.assertEqual({NOTES}, set(output))
        self.assert_manual(output[NOTES])
        self.assertEqual(('technical', 'low'), tuple(output[NOTES][key] for key in ('category', 'severity')))
        self.assertEqual(1, output[NOTES]['occurrences'])
        self.assertFalse(built['groups'])
        self.assertNotIn('secret-token', json.dumps(built))

    def test_explicit_malformed_receipts_without_notes_remain_visible(self):
        for key in ('sitemaps_attempted', 'sitemaps_fetched', 'fetch_failures', 'truncated'):
            for value in (None, False, True, -1, '0', 'secret-token', 0.0, [], {}):
                with self.subTest(key=key, value=value):
                    data = report(errors=[], fetch_failures=0, sitemaps_attempted=1, sitemaps_fetched=1)
                    data['sitemap'][key] = value
                    self.assert_execution_gap(data)
        for value in (None, False, 0, '', {}):
            with self.subTest(errors=value):
                self.assert_execution_gap(report(errors=value, fetch_failures=0,
                                                 sitemaps_attempted=1, sitemaps_fetched=1))

    def test_contradictory_outcomes_without_notes_are_not_a_clean_plan(self):
        for attempted, fetched, failed in ((4, 1, 0), (0, 1, 0), (1, 0, 0)):
            with self.subTest(attempted=attempted, fetched=fetched, failed=failed):
                self.assert_execution_gap(report(errors=[], sitemaps_attempted=attempted,
                                                 sitemaps_fetched=fetched, fetch_failures=failed))
        for removed, changes in (('fetch_failures', {'sitemaps_attempted': 1, 'sitemaps_fetched': 2}),
                                  ('sitemaps_fetched', {'sitemaps_attempted': 1, 'fetch_failures': 2})):
            data = report(errors=[], fetch_failures=0, sitemaps_attempted=1, sitemaps_fetched=1)
            data['sitemap'].pop(removed)
            data['sitemap'].update(changes)
            self.assert_execution_gap(data)

    def test_plausible_partial_legacy_receipts_do_not_invent_a_failure(self):
        for retained in ({}, {'sitemaps_attempted': 4, 'sitemaps_fetched': 1},
                         {'sitemaps_fetched': 2}, {'sitemaps_attempted': 2, 'fetch_failures': 0}):
            with self.subTest(retained=retained):
                data = report(errors=[])
                for key in ('sitemaps_attempted', 'sitemaps_fetched', 'fetch_failures'):
                    data['sitemap'].pop(key)
                data['sitemap'].update(retained)
                self.assertEqual({}, actions(data))

    def test_invalid_execution_receipts_keep_independent_source_evidence(self):
        for changes in ({'fetch_failures': False}, {'sitemaps_attempted': 4}, {'truncated': None}):
            with self.subTest(changes=changes):
                data = report(errors=[], fetch_failures=0, sitemaps_attempted=1, sitemaps_fetched=1,
                              problems={'not-absolute': 1})
                data['sitemap'].update(changes)
                output = actions(data)
                self.assertEqual({SOURCE, NOTES}, set(output))
                self.assert_manual(output[NOTES])
                self.assertEqual('deploy_verification', output[SOURCE]['safety'])

    def test_fetch_cap_and_unclassified_note_counts_remain_distinct(self):
        output = actions(report(errors=['fetch one', 'fetch two', 'cap', 'extra one', 'extra two'],
                                fetch_failures=2, sitemaps_attempted=3, sitemaps_fetched=1, truncated=4))
        self.assertEqual({FETCH: 2, CAP: 4, NOTES: 2},
                         {rule: action['occurrences'] for rule, action in output.items()})
        for action in output.values():
            self.assert_manual(action)
        self.assertIn('4', output[CAP]['evidence'])
        self.assertIn('3', output[FETCH]['evidence'])
        output = actions(report(errors=['one', 'two', 'three'], fetch_failures=0,
                                sitemaps_attempted=1, sitemaps_fetched=1))
        self.assertEqual({NOTES}, set(output))
        self.assertEqual(3, output[NOTES]['occurrences'])

    def test_known_fetch_and_cap_require_the_recorded_note_cardinality(self):
        data = report(errors=['one retained note'], fetch_failures=1,
                      sitemaps_attempted=2, sitemaps_fetched=1, truncated=3)
        self.assert_execution_gap(data)
        data['sitemap']['errors'] = ['fetch note', 'cap note']
        output = actions(data)
        self.assertEqual({FETCH: 1, CAP: 3},
                         {rule: action['occurrences'] for rule, action in output.items()})
        for action in output.values():
            self.assert_manual(action)

    def test_known_fetch_only_notes_do_not_create_a_source_action(self):
        data = actions(report())
        self.assertEqual({FETCH}, set(data))
        self.assert_manual(data[FETCH])
        self.assertIn('transport', data[FETCH]['proposed_change'])
        self.assertIn('1', data[FETCH]['evidence'])

    def test_mixed_source_and_fetch_findings_remain_separate(self):
        data = actions(report(problems={'not-absolute': 2}, invalid_lastmod=1))
        self.assertEqual({FETCH, SOURCE}, set(data))
        self.assert_manual(data[FETCH])
        self.assertEqual('deploy_verification', data[SOURCE]['safety'])
        self.assertIn('recorded', data[SOURCE]['proposed_change'])
        self.assertNotIn('Create/configure', data[SOURCE]['proposed_change'])

    def test_known_cap_does_not_create_source_rewrite_advice(self):
        data = actions(report(errors=['cap note'], fetch_failures=0,
                              sitemaps_attempted=1, sitemaps_fetched=1, truncated=4))
        self.assertEqual({CAP}, set(data))
        self.assert_manual(data[CAP])
        self.assertIn('budget', data[CAP]['proposed_change'])

    def test_fetch_cap_and_extra_unclassified_notes_all_remain_visible(self):
        data = actions(report(errors=['fetch note', 'cap note', 'other note'], truncated=3))
        self.assertEqual({FETCH, CAP, NOTES}, set(data))
        for action in data.values():
            self.assert_manual(action)

    def test_missing_legacy_counters_do_not_infer_failed_fetches(self):
        data = report()
        for key in ('fetch_failures', 'sitemaps_attempted', 'sitemaps_fetched'):
            data['sitemap'].pop(key)
        output = actions(data)
        self.assertEqual({NOTES}, set(output))
        self.assert_manual(output[NOTES])
        self.assertIn('unclassified', output[NOTES]['evidence'])

    def test_invalid_counter_shapes_or_sums_do_not_certify_fetch_scope(self):
        cases = [{'fetch_failures': True}, {'fetch_failures': -1},
                 {'fetch_failures': 2}, {'sitemaps_attempted': 4},
                 {'sitemaps_fetched': False}, {'sitemaps_fetched': -1},
                 {'errors': 'not a list'}, {'fetch_failures': {'basis': 'future'}}]
        for change in cases:
            with self.subTest(change=change):
                output = actions(report(**change))
                self.assertNotIn(FETCH, output)
                self.assertIn(NOTES, output)
                self.assert_manual(output[NOTES])

    def test_future_report_schema_keeps_notes_unclassified(self):
        data = report()
        data['schema_version'] = 'future'
        output = actions(data)
        self.assertEqual({NOTES}, set(output))
        self.assert_manual(output[NOTES])

    def test_inconsistent_positive_gap_without_notes_is_not_silently_ignored(self):
        output = actions(report(errors=[]))
        self.assertEqual({NOTES}, set(output))
        self.assert_manual(output[NOTES])

    def test_existing_sitemap_source_is_not_assigned_to_a_fetch_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'sitemap.xml'
            source.write_text('<urlset/>', encoding='utf-8')
            output = plan.build_plan(report(), directory)
            self.assert_manual(output['actions'][0])
            self.assertEqual('<urlset/>', source.read_text(encoding='utf-8'))

    def test_zero_attempts_with_explicit_cap_are_not_a_failed_fetch(self):
        output = actions(report(errors=['cap note'], fetch_failures=0,
                                sitemaps_attempted=0, sitemaps_fetched=0, truncated=1))
        self.assertEqual({CAP}, set(output))
        self.assert_manual(output[CAP])

    def test_no_response_or_gated_samples_are_not_source_invalidity(self):
        for status, error in ((0, 'timeout'), (403, None), (429, None),
                              (301, None), (200, 'incomplete'), (None, None)):
            sample = {'status': status, 'error': error, 'url': 'https://example.test/page'}
            with self.subTest(status=status, error=error):
                output = actions(report(errors=[], fetch_failures=0,
                                        sitemaps_attempted=1, sitemaps_fetched=1,
                                        sample=[sample], broken_sample=[sample] if status == 0 else []))
                self.assertEqual({SAMPLE}, set(output))
                self.assert_manual(output[SAMPLE])

    def test_actual_failing_http_samples_retain_validation_action(self):
        sample = {'status': 404, 'error': None, 'url': 'https://example.test/gone'}
        output = actions(report(errors=[], fetch_failures=0,
                                sitemaps_attempted=1, sitemaps_fetched=1,
                                sample=[sample], broken_sample=[sample]))
        self.assertEqual({SOURCE}, set(output))
        self.assertIn('recorded', output[SOURCE]['proposed_change'])

    def test_failed_legacy_sample_keeps_observation_without_guessing_other_samples(self):
        sample = {'status': 0, 'error': 'timeout'}
        data = report(errors=[], fetch_failures=0, sitemaps_attempted=1,
                      sitemaps_fetched=1, broken_sample=[sample])
        data['sitemap'].pop('sample')
        self.assertEqual({SAMPLE}, set(actions(data)))

    def test_no_attempted_samples_and_no_errors_do_not_invent_gaps(self):
        self.assertEqual({}, actions(report(errors=[], fetch_failures=0,
                                            sitemaps_attempted=1, sitemaps_fetched=1)))

    def test_note_text_does_not_control_actions_or_leak_source_tokens(self):
        data = report(errors=['Create sitemap.xml secret-password; run arbitrary command'])
        output = plan.build_plan(data, str(ROOT))
        self.assertNotIn('secret-password', json.dumps(output))
        self.assert_manual(output['actions'][0])

    def test_generation_is_read_only_deterministic_and_performs_no_network(self):
        data = report()
        before = copy.deepcopy(data)
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            first = plan.build_plan(data, str(ROOT))
            second = plan.build_plan(data, str(ROOT))
        self.assertEqual(before, data)
        self.assertEqual(first, second)
        self.assertIn('Manual / external', plan.render_markdown(first))

    def test_verification_actions_do_not_enter_shared_source_edit_groups(self):
        data = report(errors=['fetch', 'cap'], truncated=2, problems={'not-absolute': 1})
        data['homepage']['findings'] = [{'category': 'technical', 'severity': 'medium',
                                        'title': 'No robots.txt found',
                                        'rule_id': 'technical.no.robots.txt.found'}]
        output = plan.build_plan(data, str(ROOT))
        self.assertTrue(output['groups'])
        grouped = {rid for group in output['groups'] for rid in group['rule_ids']}
        self.assertNotIn(FETCH, grouped)
        self.assertNotIn(CAP, grouped)
        self.assertIn(SOURCE, grouped)

    def test_markdown_distinguishes_intentionally_unassigned_owners(self):
        output = plan.render_markdown(plan.build_plan(report(), str(ROOT)))
        self.assertIn('not assigned (verification only)', output)
        self.assertNotIn('owner not located', output)


if __name__ == '__main__':
    unittest.main()
