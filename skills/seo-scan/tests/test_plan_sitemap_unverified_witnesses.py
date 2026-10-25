"""Uncertain sitemap handoffs retain bounded observations without edit authority."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan
from test_plan_sitemap_verification import report, SOURCE, SAMPLE

REPO = Path(__file__).parent / 'fixtures/planner/plain_html'


def build(rows, legacy=False):
    data = report(errors=[], fetch_failures=0, sitemaps_attempted=1, sitemaps_fetched=1,
                  sample=rows, broken_sample=rows)
    if legacy:
        data['sitemap'].pop('sample')
    return data, plan.build_plan(data, str(REPO))


class TestUnverifiedSitemapWitnesses(unittest.TestCase):
    def test_bounded_targets_preserve_order_and_total_without_source_authority(self):
        rows = [{'url': f'https://example.test/target-{i}', 'status': 700, 'error': None}
                for i in range(8)]
        data, built = build(rows)
        action = built['actions'][0]
        self.assertEqual(SAMPLE, action['rule_id'])
        self.assertIn('first 5 of 8', action['evidence'])
        for i in range(5):
            self.assertIn(rows[i]['url'], action['evidence'])
        self.assertNotIn(rows[5]['url'], action['evidence'])
        self.assertEqual([], action['likely_files'])
        self.assertEqual('manual_external', action['safety'])
        self.assertTrue(action['manual_action'])
        self.assertEqual(rows, data['sitemap']['sample'])
        self.assertIn('target-0', plan.render_markdown(built))

    def test_mixed_outcomes_and_legacy_rows_do_not_cross_failure_boundary(self):
        rows = [{'url': 'https://example.test/gone', 'status': 404, 'error': None},
                {'url': 'https://example.test/gated', 'status': 403, 'error': None},
                {'url': 'https://example.test/ok', 'status': 200, 'error': None}]
        for legacy in (False, True):
            _, built = build(rows, legacy)
            actions = {a['rule_id']: a for a in built['actions']}
            self.assertEqual({SOURCE, SAMPLE}, set(actions))
            evidence = actions[SAMPLE]['evidence']
            self.assertIn(rows[1]['url'], evidence)
            self.assertNotIn(rows[0]['url'], evidence)
            self.assertNotIn(rows[2]['url'], evidence)
            self.assertIn('first 1 of 1', evidence)

    def test_malformed_fields_remain_null_without_inventing_target_or_status(self):
        _, built = build([None, {'url': {'secret': 'not-a-url'}, 'status': True}])
        evidence = built['actions'][0]['evidence']
        self.assertIn('first 2 of 2', evidence)
        self.assertEqual(2, evidence.count('"url": null'))
        self.assertEqual(2, evidence.count('"status": null'))
        self.assertNotIn('not-a-url', evidence)

    def test_mcp_is_read_only_deterministic_and_keeps_literal_witness(self):
        target = 'https://example.test/target?value=</pre><script>bad()</script>'
        data, expected = build([{'url': target, 'status': 0, 'error': 'timeout'}])
        original = copy.deepcopy(data)
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            first = mcp_server._plan(data, 'skills/seo-scan/tests/fixtures/planner/plain_html')
            second = mcp_server._plan(data, 'skills/seo-scan/tests/fixtures/planner/plain_html')
        self.assertEqual(first, second)
        for key in ('evidence', 'safety', 'manual_action', 'likely_files'):
            self.assertEqual(expected['actions'][0][key], first['actions'][0][key])
        self.assertIn(target, first['actions'][0]['evidence'])
        self.assertEqual(original, data)
        self.assertEqual(first, json.loads(json.dumps(first)))


if __name__ == '__main__':
    unittest.main()
