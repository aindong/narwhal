"""Crawl/audit handoffs retain and compare explicit per-page auditor execution."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import crawl_site
import diff_scan
import mcp_server
import plan
from lib.report import Report
from test_crawl_rule_handoff import crawl_reports
from test_diff_crawl_rules import report
from test_diff_severe_escalation import cli

SCOPE = {'requested': ['technical', 'schema'], 'completed': ['technical', 'schema']}


class TestCrawlExecutionScope(unittest.TestCase):
    def test_crawl_serializes_recorded_scope_without_inference_or_report_mutation(self):
        pages = [Report('https://example.test/' + str(i), fetched_status=200) for i in range(3)]
        pages[0].meta['scan_scope'] = copy.deepcopy(SCOPE)
        pages[1].meta['scan_scope'] = dict(SCOPE, completed=[])
        original = copy.deepcopy([p.meta for p in pages])
        with mock.patch.object(crawl_site.time, 'sleep', side_effect=AssertionError('Default zero-delay crawl must not sleep')) as sleep:
            result = json.loads(crawl_site.render_json(crawl_reports(pages)))
        sleep.assert_not_called()
        self.assertEqual(SCOPE, result['pages'][0]['scan_scope'])
        self.assertEqual([], result['pages'][1]['scan_scope']['completed'])
        self.assertNotIn('scan_scope', result['pages'][2])
        self.assertEqual(original, [p.meta for p in pages])

    def test_partial_invalid_changed_and_one_sided_inner_scope_withhold_verdicts(self):
        for change in ('partial', 'invalid', 'matching_partial', 'matching_invalid',
                       'changed', 'missing', 'contradictory_duplicate'):
            old, new = report([]), report([])
            for data in (old, new):
                data['crawl']['pages'][1]['scan_scope'] = copy.deepcopy(SCOPE)
            if change in ('partial', 'matching_partial'):
                new['crawl']['pages'][1]['scan_scope']['completed'] = []
            elif change in ('invalid', 'matching_invalid'):
                new['crawl']['pages'][1]['scan_scope'] = {'requested': 'technical', 'completed': []}
            elif change == 'changed':
                new['crawl']['pages'][1]['scan_scope'] = {'requested': ['technical'], 'completed': ['technical']}
            elif change == 'missing':
                old['crawl']['pages'][1].pop('scan_scope')
            else:
                for data in (old, new):
                    data['crawl']['pages'].append(copy.deepcopy(data['crawl']['pages'][1]))
                new['crawl']['pages'][2]['scan_scope'] = {'requested': ['technical'], 'completed': ['technical']}
            if change.startswith('matching_'):
                old = copy.deepcopy(new)
            for before, after in ((old, new), (new, old)):
                with self.subTest(change=change):
                    original = copy.deepcopy((before, after))
                    result = diff_scan.diff_reports(before, after)
                    self.assertEqual('incomparable', result['comparison']['status'])
                    self.assertIsNone(result['score_delta'])
                    self.assertIsNone(result['regression'])
                    self.assertEqual('unverified', result['crawl_rule_changes']['status'])
                    self.assertEqual(2, cli(before, after, '--fail-on-regression', '--require-comparable')[0])
                    self.assertEqual(result, mcp_server._diff(json.dumps(before), json.dumps(after)))
                    self.assertEqual(original, (before, after))

    def test_matching_reordered_scopes_and_absent_legacy_scopes_are_distinct(self):
        old, new = report([]), report([])
        for data in (old, new):
            data['crawl']['pages'][1]['scan_scope'] = copy.deepcopy(SCOPE)
        new['crawl']['pages'][1]['scan_scope']['completed'].reverse()
        new['crawl']['pages'][1]['scan_scope']['requested'].reverse()
        self.assertEqual('comparable', diff_scan.diff_reports(old, new)['comparison']['status'])
        legacy = diff_scan.diff_reports(report([]), report([]))
        self.assertEqual('comparable', legacy['comparison']['status'])
        self.assertIn('missing legacy page scopes remain unverified', legacy['comparison']['basis'])

    def test_recorded_unfinished_technical_check_blocks_existing_planner_automation(self):
        data = report([{'category': 'technical', 'severity': 'high',
                       'rule_id': 'technical.no.responsive.viewport.tag', 'title': 'No responsive viewport tag',
                       'count': 1, 'url_sample': {'basis': 'recorded_crawl_rule_url_labels_v1',
                       'urls': ['https://example.test/pricing/'], 'truncated': False, 'omitted': 0}}])
        data['crawl']['pages'][1]['scan_scope'] = dict(SCOPE, completed=[])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'pricing').mkdir()
            (root / 'pricing/index.html').write_text('<html></html>', encoding='utf-8')
            action = plan.build_plan(data, tmp)['actions'][0]
        self.assertEqual(['pricing/index.html'], [owner['path'] for owner in action['likely_files']])
        self.assertFalse(action['automation_eligibility']['eligible'])
        self.assertIn('known_incomplete_source_evidence', action['automation_eligibility']['blockers'])


if __name__ == '__main__':
    unittest.main()
