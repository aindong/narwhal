"""Sitemap reporting and planning share conservative HTTP outcome semantics."""
import copy
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan
import validate_sitemap as sitemap
from lib import http, links
try:
    from .test_plan_sitemap_verification import report, SOURCE, SAMPLE
except ImportError:
    from test_plan_sitemap_verification import report, SOURCE, SAMPLE

BASE = 'https://example.test/'
REPO = Path(__file__).parent / 'fixtures/planner/plain_html'
XML = b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.test/target</loc></url></urlset>'


def measured(status, error):
    with mock.patch.object(http, 'normalize_url', side_effect=lambda value: value), \
            mock.patch.object(http, 'assert_public_host'), \
            mock.patch.object(http, 'fetch_bytes', return_value=(XML, None)), \
            mock.patch.object(http, 'head', return_value=(status, error)) as head:
        result = sitemap.analyze(BASE + 'sitemap.xml', sample=1)
    return result, head.call_count


def actions(sitemap_result):
    data = report(); data['sitemap'] = sitemap_result
    return {a['rule_id']: a for a in plan.build_plan(data, str(REPO))['actions']}


class TestSitemapResponseStates(unittest.TestCase):
    def test_report_and_planner_match_shared_explicit_status_matrix(self):
        cases = [(200, None, 'successful_2xx'), (204, '', 'successful_2xx'),
                 (404, None, 'broken'), (500, '', 'broken'), (599, None, 'broken'),
                 (0, 'timeout', 'unverified'), (403, None, 'unverified'),
                 (301, None, 'unverified'), (700, None, 'unverified'),
                 (999, None, 'unverified'), (200, {}, 'unverified'),
                 (404, False, 'unverified'), (404, 'incomplete', 'unverified'),
                 (200, 0, 'unverified'), (200.0, None, 'unverified'),
                 ('200', None, 'unverified'), (False, None, 'unverified')]
        for status, error, expected in cases:
            with self.subTest(status=status, error=type(error).__name__):
                entry = {'url': BASE + 'target', 'status': status, 'error': error}
                self.assertEqual(expected, links.http_check_state(status, error))
                self.assertEqual(expected == 'successful_2xx', sitemap._sample_succeeded(entry))
                failures, unverified = plan._sitemap_sample_evidence({'sample': [entry]})
                self.assertEqual([entry] if expected == 'broken' else [], failures)
                self.assertEqual(int(expected == 'unverified'), unverified)

    def test_unsupported_or_errored_problem_records_stay_raw_but_unverified(self):
        for status, error in ((700, None), (404, 'incomplete'), (404, False)):
            result, checks = measured(status, error)
            self.assertEqual(1, checks)
            self.assertEqual({'basis': 'shared_http_check_state_v1', 'scope': 'selected_targets',
                              'successful_2xx': 0, 'broken': 0, 'unverified': 1}, result['sample_response_coverage'])
            self.assertEqual(status, result['sample'][0]['status'])
            self.assertEqual(error, result['sample'][0]['error'])
            self.assertEqual(result['sample'], result['broken_sample'])  # compatibility record retained
            text = sitemap.render_markdown(result)
            self.assertIn('1 response(s) leave reachability unverified', text)
            self.assertIn('Reported problem samples', text)
            self.assertIn('(unverified)', text)
            self.assertNotIn('Sitemap looks healthy', text)
            output = actions(result)
            self.assertEqual({SAMPLE}, set(output))
            self.assertTrue(output[SAMPLE]['manual_action'])
            self.assertEqual([], output[SAMPLE]['likely_files'])

    def test_falsey_unsupported_errors_cannot_create_success_or_source_edits(self):
        for error in (False, 0, [], {}):
            result, _ = measured(200, error)
            self.assertEqual([], result['broken_sample'])
            text = sitemap.render_markdown(result)
            self.assertIn('0/1 URLs returned successful 2xx', text)
            self.assertNotIn('Sitemap looks healthy', text)
            self.assertEqual({SAMPLE}, set(actions(result)))

    def test_genuine_success_and_failing_http_keep_existing_actions(self):
        for status, expected in ((200, set()), (204, set()), (404, {SOURCE}), (500, {SOURCE})):
            result, count = measured(status, None)
            self.assertEqual(1, count)
            self.assertEqual(expected, set(actions(result)))
        result, _ = measured(200, None)
        self.assertIn('1/1 URLs returned successful 2xx', sitemap.render_markdown(result))
        self.assertIn('healthy for the checks performed', sitemap.render_markdown(result))

    def test_mixed_known_failure_and_unsupported_probe_remain_separate(self):
        samples = [{'url': BASE + 'gone', 'status': 404, 'error': None},
                   {'url': BASE + 'unsupported', 'status': 700, 'error': None}]
        data = report(errors=[], fetch_failures=0, sitemaps_attempted=1, sitemaps_fetched=1,
                      sample=samples, broken_sample=samples)
        built = {a['rule_id']: a for a in plan.build_plan(data, str(REPO))['actions']}
        self.assertEqual({SOURCE, SAMPLE}, set(built))
        self.assertIn(BASE + 'gone', built[SOURCE]['evidence'])
        self.assertNotIn(BASE + 'unsupported', built[SOURCE]['evidence'])
        self.assertEqual('manual_external', built[SAMPLE]['safety'])

    def test_legacy_problem_only_record_is_not_promoted_to_source_invalidity(self):
        entry = {'url': BASE + 'target', 'status': 700, 'error': None}
        data = report(errors=[], fetch_failures=0, sitemaps_attempted=1, sitemaps_fetched=1, broken_sample=[entry])
        data['sitemap'].pop('sample')
        original = copy.deepcopy(data)
        built = plan.build_plan(data, str(REPO))
        self.assertEqual([SAMPLE], [a['rule_id'] for a in built['actions']])
        self.assertEqual(original, data)
        data['sitemap']['sample_response_coverage'] = {'successful_2xx': 1, 'broken': 0, 'unverified': 0}
        self.assertEqual([SAMPLE], [a['rule_id'] for a in plan.build_plan(data, str(REPO))['actions']])

    def test_mcp_has_same_manual_result_without_network_or_input_mutation(self):
        result, _ = measured(700, None)
        with mock.patch.object(sitemap, 'analyze', return_value=result):
            exported = mcp_server._sitemap(BASE)
        self.assertEqual(result['sample_response_coverage'], exported['sample_response_coverage'])
        data = report(); data['sitemap'] = result
        original = copy.deepcopy(data)
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            built = mcp_server._plan(data, 'skills/seo-scan/tests/fixtures/planner/plain_html')
        self.assertEqual([SAMPLE], [a['rule_id'] for a in built['actions']])
        self.assertEqual('manual_external', built['actions'][0]['safety'])
        self.assertEqual(original, data)


if __name__ == '__main__':
    unittest.main()
