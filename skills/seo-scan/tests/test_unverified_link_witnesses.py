"""Uncertain link targets survive measurement, reporting and manual planning."""
import copy
import json
from collections import Counter
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import crawl_site as crawl
import plan
import render_report
from lib import http, links
try:
    from .test_code_fences import Parsed
    from .test_plan_sitemap_verification import report
except ImportError:
    from test_code_fences import Parsed
    from test_plan_sitemap_verification import report

BASE = 'https://example.test/'
REPO = Path(__file__).parent / 'fixtures/planner/plain_html'
GAP = 'technical.links.coverage.unverified'


def checked(responses, cap=200, suffix=''):
    targets = [{'url': BASE + str(i) + suffix, 'internal': True} for i in range(len(responses))]
    mapping = {target['url']: response for target, response in zip(targets, responses)}
    source = BASE + 'source' + suffix
    with mock.patch.object(http, 'head', side_effect=lambda url, **kw: mapping[url]) as head:
        result = crawl.check_broken_links({source: targets}, allow_private=False, timeout=1, concurrency=1, max_links=cap)
    return result, head.call_count


def site(info):
    return {'base': BASE, 'pages_scanned': 1, 'avg_score': 100, 'pages': [], 'recurring': Counter(), 'links': info}


class TestUnverifiedLinkWitnesses(unittest.TestCase):
    def test_mixed_responses_retain_all_uncertain_targets_and_close_counts(self):
        info, count = checked([(200, None), (204, None), (403, None), (429, None), (301, None),
                               (0, 'timeout'), (200, 'incomplete'), (404, None), (500, None), (404, 'incomplete')])
        self.assertEqual(10, count)
        self.assertEqual([BASE + str(i) for i in (2, 3, 4, 5, 6, 9)], [row['url'] for row in info['unverified']])
        self.assertEqual({'basis': 'head_responses', 'scope': 'checked_targets', 'successful_2xx': 2,
                          'broken': 2, 'unverified': 6, 'request_failures': 1}, info['coverage'])
        self.assertEqual(info['coverage'], crawl._link_coverage(info))
        self.assertTrue(all(row['sources'] == [BASE + 'source'] for row in info['unverified']))
        self.assertEqual(4, len(info['broken']))  # compatibility problem records remain

    def test_shared_state_rejects_unsupported_errors_and_non_http_statuses(self):
        for status in (None, '200', False, 0, 199, 301, 403, 429, 451, 600, 999):
            self.assertEqual('unverified', links.http_check_state(status, None))
        for error in ('incomplete', False, 0, [], {}):
            for status in (200, 404):
                self.assertEqual('unverified', links.http_check_state(status, error))
        for error in (None, ''):
            self.assertEqual('successful_2xx', links.http_check_state(204, error))
            self.assertEqual('broken', links.http_check_state(404, error))

    def test_caps_do_not_add_requests_or_include_unchecked_targets(self):
        info, count = checked([(403, None)] * 4, cap=2)
        self.assertEqual((2, 2), (count, len(info['unverified'])))
        self.assertEqual(2, info['skipped_over_cap'])
        self.assertNotIn(BASE + '2', json.dumps(info['unverified']))
        empty, count = checked([(403, None)], cap=0)
        self.assertEqual((0, []), (count, empty['unverified']))

    def test_legacy_receipts_stay_scoped_without_inventing_target_records(self):
        info, _ = checked([(403, None), (0, 'timeout')])
        legacy = dict(info); legacy.pop('unverified')
        self.assertEqual(info['coverage'], crawl._link_coverage(legacy))
        self.assertNotIn('Unverified checked targets', crawl.render_markdown(site(legacy)))
        duplicate = [info['unverified'][0], info['unverified'][0]]
        missing_legacy = [dict(row, url=row['url'] + '/changed') for row in info['unverified']]
        for rows in (duplicate, missing_legacy, None, [], [{}], [{'status': 200, 'error': None}], [None]):
            invalid = dict(info, unverified=rows)
            self.assertIsNone(crawl._link_coverage(invalid))

    def test_markdown_bounds_rows_and_urls_and_keeps_metadata_literal(self):
        suffix = '<img src=x>|`literal`' + 'x' * 260 + 'END_OF_FULL_URL'
        info, _ = checked([(403, None)] * 25, suffix=suffix)
        original = copy.deepcopy(info)
        text = crawl.render_markdown(site(info))
        self.assertIn('first 20 of 25', text)
        self.assertNotIn('END_OF_FULL_URL', text)
        self.assertIn('END_OF_FULL_URL', crawl.render_json(site(info)))
        parsed = Parsed(render_report.render(text))
        control, _ = checked([])
        baseline = Parsed(render_report.render(crawl.render_markdown(site(control))))
        self.assertEqual(baseline.tags.count('img'), parsed.tags.count('img'))
        self.assertNotIn('script', parsed.tags)
        self.assertEqual(original, info)

    def test_planner_gets_gated_target_and_sources_without_double_counting_no_response(self):
        info, _ = checked([(403, None), (0, 'secret request detail')])
        data = report(errors=[], fetch_failures=0, sitemaps_attempted=1, sitemaps_fetched=1)
        data['crawl']['links'] = info
        original = copy.deepcopy(data)
        built = plan.build_plan(data, str(REPO))
        action = next(a for a in built['actions'] if a['rule_id'] == GAP)
        self.assertEqual(2, action['occurrences'])
        self.assertIn(BASE + '0', action['evidence'])
        self.assertIn(BASE + 'source', action['evidence'])
        self.assertIn('"status": 403', action['evidence'])
        self.assertIn('first 2 of 2', action['evidence'])
        self.assertNotIn('secret request detail', json.dumps(built))
        self.assertEqual('manual_external', action['safety'])
        self.assertEqual([], action['likely_files'])
        self.assertEqual(original, data)

    def test_planner_rejects_malformed_new_record_shapes(self):
        for rows in (None, {}, [None]):
            info, _ = checked([(403, None)])
            info['unverified'] = rows
            data = report(); data['crawl']['links'] = info
            with self.assertRaisesRegex(ValueError, 'links.unverified'):
                plan.build_plan(data, str(REPO))

    def test_errored_http_status_is_uncertain_even_in_legacy_problem_list(self):
        info, _ = checked([(404, 'incomplete')])
        self.assertEqual(1, len(info['broken']))
        self.assertEqual(1, len(info['unverified']))
        self.assertEqual(0, info['coverage']['broken'])
        self.assertEqual(info['coverage'], crawl._link_coverage(info))
        data = report(errors=[], fetch_failures=0, sitemaps_attempted=1, sitemaps_fetched=1)
        data['crawl']['links'] = info
        actions = plan.build_plan(data, str(REPO))['actions']
        self.assertEqual([GAP], [action['rule_id'] for action in actions])
        self.assertIn('404 (unverified)', render_report.render(crawl.render_markdown(site(info))))


if __name__ == '__main__':
    unittest.main()
