"""Crawl link observations survive audit-to-plan without authorizing source edits."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import crawl_site
import mcp_server
import plan
from lib import http
try:
    from .test_plan_sitemap_verification import report
except ImportError:
    from test_plan_sitemap_verification import report

REPO = Path(__file__).parent / 'fixtures/planner/plain_html'
BASE = 'https://example.test/'
FAIL = 'technical.links.http.failures'
GAP = 'technical.links.coverage.unverified'


def checked(responses, cap=200, source_count=1):
    targets = [{'url': BASE + str(i), 'internal': i % 2 == 0} for i in range(len(responses))]
    sources = {BASE + 'source' + str(i): targets for i in range(source_count)}
    by_url = {target['url']: response for target, response in zip(targets, responses)}
    with mock.patch.object(http, 'head', side_effect=lambda url, **kw: by_url[url]):
        return crawl_site.check_broken_links(sources, allow_private=False, timeout=1, concurrency=1, max_links=cap)


def data(info=None):
    result = report(errors=[], fetch_failures=0, sitemaps_attempted=1, sitemaps_fetched=1)
    if info is not None:
        result['crawl']['links'] = info
    return result


def actions(payload):
    return {action['rule_id']: action for action in plan.build_plan(payload, str(REPO))['actions']}


class TestPlanCrawlLinks(unittest.TestCase):
    def assert_manual(self, action):
        self.assertEqual('links', action['artifact'])
        self.assertEqual('manual_external', action['safety'])
        self.assertTrue(action['manual_action'])
        self.assertFalse(action['requires_deploy'])
        self.assertEqual([], action['likely_files'])

    def test_mixed_real_checker_evidence_separates_http_failures_and_uncertainty(self):
        info = checked([(404, None), (500, None), (0, 'secret transport detail'), (403, None), (200, None)])
        result = actions(data(info))
        self.assertEqual({FAIL, GAP}, set(result))
        for action in result.values():
            self.assert_manual(action)
        self.assertEqual(2, result[FAIL]['occurrences'])
        self.assertIn('"status": 404', result[FAIL]['evidence'])
        self.assertIn('"status": 500', result[FAIL]['evidence'])
        self.assertIn(BASE + 'source0', result[FAIL]['evidence'])
        self.assertNotIn('"status": 0', result[FAIL]['evidence'])
        self.assertEqual(2, result[GAP]['occurrences'])
        self.assertIn('"status": 0', result[GAP]['evidence'])
        self.assertNotIn('secret transport detail', json.dumps(result))
        self.assertIn('HEAD/GET', result[FAIL]['proposed_change'])

    def test_disabled_empty_and_successful_checks_do_not_invent_actions(self):
        self.assertEqual({}, actions(data()))
        for info in (checked([]), checked([(200, None), (204, None)])):
            self.assertEqual({}, actions(data(info)))
        payload = data(); payload['crawl']['links'] = None
        self.assertEqual({}, actions(payload))

    def test_caps_and_gating_are_verification_only_including_zero_budget(self):
        for info, expected in ((checked([(200, None)] * 3, cap=1), 2),
                               (checked([(200, None)] * 3, cap=0), 3),
                               (checked([(403, None), (429, None)]), 2)):
            result = actions(data(info))
            self.assertEqual({GAP}, set(result))
            self.assert_manual(result[GAP])
            self.assertEqual(expected, result[GAP]['occurrences'])
            self.assertIn('do not establish dead destinations', result[GAP]['proposed_change'])

    def test_legacy_and_contradictory_coverage_do_not_certify_request_scope(self):
        legacy = {'broken': [{'url': BASE + 'gone', 'status': 404, 'error': None}]}
        result = actions(data(legacy))
        self.assertEqual({FAIL, GAP}, set(result))
        self.assertIn('unrecorded or inconsistent', result[GAP]['evidence'])
        for error in (False, 0, [], {}):
            unsupported = {'broken': [{'url': BASE + 'unknown', 'status': 404, 'error': error}]}
            self.assertEqual({GAP}, set(actions(data(unsupported))))
        contradictory = checked([(200, None)])
        contradictory['coverage'].update(successful_2xx=0, broken=1)
        for info in (contradictory, checked([(404, 'incomplete')]),
                     dict(checked([(200, None)]), skipped_over_cap=999),
                     dict(checked([(200, None)]), coverage={'basis': 'future'}),
                     {'broken': [{'status': False}]}):
            result = actions(data(info))
            self.assertEqual({GAP}, set(result))
            self.assertEqual(1, result[GAP]['occurrences'])

    def test_bounded_target_and_source_witnesses_disclose_full_counts(self):
        result = actions(data(checked([(404, None)] * 7, source_count=5)))
        self.assertEqual({FAIL}, set(result))
        evidence = result[FAIL]['evidence']
        self.assertIn('first 5 of 7', evidence)
        self.assertIn('up to 3 source URLs each', evidence)
        self.assertIn('"source_count": 5', evidence)
        self.assertIn(BASE + 'source2', evidence)
        self.assertNotIn(BASE + 'source3', evidence)
        self.assertEqual(7, result[FAIL]['occurrences'])

    def test_malformed_consumed_link_data_is_a_bounded_error_before_output(self):
        for info in ('secret', {'broken': None}, {'broken': [None]}, {'checked': True}, {'skipped_over_cap': -1}):
            payload = data(info)
            with self.assertRaisesRegex(ValueError, 'Report.crawl.links') as error:
                plan.build_plan(payload, str(REPO))
            self.assertNotIn('secret', str(error.exception))
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'audit.json'; output = Path(tmp) / 'plan.json'
            source.write_text(json.dumps(data({'broken': [None]})), encoding='utf-8')
            output.write_bytes(b'prior plan')
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = plan.main([str(source), '--repo', str(REPO), '-o', str(output)])
            self.assertEqual((2, ''), (code, out.getvalue()))
            self.assertEqual(b'prior plan', output.read_bytes())

    def test_generation_is_read_only_deterministic_and_excluded_from_source_groups(self):
        payload = data(checked([(404, None), (0, 'timeout')]))
        original = copy.deepcopy(payload)
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            first = plan.build_plan(payload, str(REPO))
            second = plan.build_plan(payload, str(REPO))
        self.assertEqual(first, second)
        self.assertEqual(original, payload)
        self.assertEqual([], first['groups'])
        text = plan.render_markdown(first)
        self.assertIn('not assigned (verification only)', text)
        self.assertIn(BASE + 'source0', text)

    def test_mcp_retains_the_same_manual_actions_and_witnesses(self):
        payload = data(checked([(404, None), (0, 'timeout')]))
        original = copy.deepcopy(payload)
        built = mcp_server._plan(payload, 'skills/seo-scan/tests/fixtures/planner/plain_html')
        expected = actions(payload)
        for action in built['actions']:
            self.assert_manual(action)
            self.assertEqual(expected[action['rule_id']]['evidence'], action['evidence'])
        self.assertEqual(original, payload)


if __name__ == '__main__':
    unittest.main()
