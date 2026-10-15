"""Sitemap measurement gaps require verification, not invented source rewrites."""

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan

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
        self.assertEqual('manual_external', action['safety'])
        self.assertTrue(action['manual_action'])
        self.assertFalse(action['requires_deploy'])
        self.assertEqual([], action['likely_files'])
        self.assertEqual('site', action['scope'])
        self.assertNotIn('Create/configure', action['proposed_change'])

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
        data = report(errors=[], broken_sample=[sample])
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


if __name__ == '__main__':
    unittest.main()
