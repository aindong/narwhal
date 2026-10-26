"""Native recurring rules must not hide inner-page regressions behind site scores."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diff_scan
import mcp_server
from test_diff_crawl_sample import audit, URL
from test_diff_severe_escalation import cli


def report(rows):
    data = audit([URL, URL + 'pricing/'], 90)
    data['homepage']['meta']['scan_scope'] = {'requested': ['technical'], 'completed': ['technical']}
    data['crawl']['recurring'] = rows
    return data


def row(severity='critical', count=1):
    return {'category': 'technical', 'rule_id': 'technical.missing.title',
            'title': 'Missing <title>', 'severity': severity, 'count': count}


class TestCrawlRuleDiff(unittest.TestCase):
    def test_new_inner_rule_fails_cli_and_mcp_even_when_score_rises(self):
        old, new = report([]), report([row()])
        new['overall_score'] = 95
        original = copy.deepcopy((old, new))
        result = diff_scan.diff_reports(old, new)
        self.assertTrue(result['regression'])
        self.assertEqual([], result['added'])
        self.assertEqual([row()], result['crawl_rule_changes']['added'])
        self.assertEqual('compared', result['crawl_rule_changes']['status'])
        self.assertEqual('native_category_rule_worst_severity_and_observation_totals_v1',
                         result['crawl_rule_changes']['basis'])
        self.assertIn('matching crawl sample', diff_scan.render_markdown(result))
        self.assertEqual(1, cli(old, new, '--fail-on-regression')[0])
        self.assertEqual(result, mcp_server._diff(json.dumps(old), json.dumps(new)))
        self.assertEqual(original, (old, new))

    def test_removed_rule_is_sample_observation_not_page_resolution(self):
        result = diff_scan.diff_reports(report([row()]), report([]))
        self.assertEqual([], result['resolved'])
        self.assertEqual([row()], result['crawl_rule_changes']['removed'])
        self.assertFalse(result['regression'])
        self.assertIn('not a per-page fix', result['crawl_rule_changes']['scope'])

    def test_worst_severity_and_counts_are_order_independent(self):
        old, new = report([row('medium', 2)]), report([row('high'), row('critical', 2)])
        result = diff_scan.diff_reports(old, new)
        changed = result['crawl_rule_changes']
        self.assertTrue(changed['regression'])
        self.assertEqual('critical', changed['worsened'][0]['to'])
        self.assertEqual({'category': 'technical', 'rule_id': 'technical.missing.title',
                          'title': 'Missing <title>', 'from': 'medium', 'to': 'critical'}, changed['worsened'][0])
        self.assertEqual({'category': 'technical', 'rule_id': 'technical.missing.title', 'from': 2, 'to': 3},
                         changed['count_changed'][0])
        new['crawl']['recurring'].reverse()
        self.assertEqual(result, diff_scan.diff_reports(old, new))
        self.assertEqual('medium', diff_scan.diff_reports(new, old)['crawl_rule_changes']['improved'][0]['to'])

    def test_unknown_or_changed_coverage_withholds_crawl_classifications(self):
        for change in ('sample', 'empty', 'missing', 'scope', 'partial'):
            old, new = report([row()]), report([])
            if change == 'sample':
                new['crawl']['pages'].pop()
            elif change == 'empty':
                old['crawl']['pages'] = new['crawl']['pages'] = []
            elif change == 'missing':
                old['crawl'].pop('pages')
            elif change == 'scope':
                old['homepage']['meta'].pop('scan_scope')
            else:
                new['crawl']['pages'][1]['response_partial'] = True
            with self.subTest(change=change):
                receipt = diff_scan.diff_reports(old, new)['crawl_rule_changes']
                self.assertEqual('unverified', receipt['status'])
                self.assertEqual([], receipt['removed'])
                self.assertIsNone(receipt['regression'])
                self.assertIsInstance(receipt['reason'], str)
                self.assertTrue(receipt['reason'])

    def test_legacy_and_malformed_aggregate_rows_are_not_repaired(self):
        for bad in (None, {}, [None], [dict(row(), rule_id=None)], [dict(row(), count=True)],
                    [dict(row(), count=0)], [dict(row(), severity='low')], [dict(row(), category='schema')],
                    [dict(row(), rule_id=' ')], [dict(row(), title=None)], [dict(row(), category=3)]):
            old, new = report([]), report([])
            old['crawl']['recurring'] = bad
            with self.subTest(bad=bad):
                receipt = diff_scan.diff_reports(old, new)['crawl_rule_changes']
                self.assertEqual('unverified', receipt['status'])
                self.assertIsNone(receipt['regression'])
                self.assertIsInstance(receipt['reason'], str)
                self.assertTrue(receipt['reason'])

    def test_nonregressing_crawl_changes_keep_an_explicit_sample_headline(self):
        for old, new in ((report([]), report([row('medium')])),
                         (report([row()]), report([])),
                         (report([row('high')]), report([row('medium')])),
                         (report([row()]), report([row(count=2)]))):
            result = diff_scan.diff_reports(old, new)
            self.assertFalse(result['regression'])
            self.assertEqual(([], [], [], []),
                             (result['added'], result['resolved'], result['worsened'], result['improved']))
            self.assertIn('Changed crawl-rule observations', diff_scan._verdict(result))

    def test_every_supported_severity_addition_and_transition_obeys_the_gate(self):
        severities = ('critical', 'high', 'medium')
        for severity in severities:
            receipt = diff_scan.diff_reports(report([]), report([row(severity)]))['crawl_rule_changes']
            self.assertEqual(severity != 'medium', receipt['regression'])
        for before in severities:
            for after in severities:
                with self.subTest(before=before, after=after):
                    receipt = diff_scan.diff_reports(report([row(before)]), report([row(after)]))['crawl_rule_changes']
                    worse = severities.index(after) < severities.index(before)
                    better = severities.index(after) > severities.index(before)
                    self.assertEqual(worse, receipt['regression'])
                    self.assertEqual(int(worse), len(receipt['worsened']))
                    self.assertEqual(int(better), len(receipt['improved']))
                    self.assertEqual([], receipt['count_changed'])

    def test_strict_gate_requires_verified_crawl_rules_without_breaking_legacy_viewing(self):
        for change in ('missing', 'malformed', 'sample_missing', 'empty_sample'):
            old, new = report([]), report([])
            if change == 'missing':
                old['crawl'].pop('recurring')
            elif change == 'malformed':
                new['crawl']['recurring'] = [dict(row(), count=True)]
            elif change == 'sample_missing':
                old['crawl'].pop('pages')
            else:
                old['crawl']['pages'] = new['crawl']['pages'] = []
            with self.subTest(change=change):
                code, output, error = cli(old, new, '--require-comparable', '--fail-on-regression', '--format', 'json')
                self.assertEqual(2, code)
                self.assertEqual('unverified', json.loads(output)['crawl_rule_changes']['status'])
                self.assertIn('crawl-rule', error)
                for flags in ((), ('--fail-on-regression',)):
                    code, _, error = cli(old, new, *flags)
                    self.assertEqual(0, code)
                    self.assertIn('WARNING: crawl-rule', error)
        self.assertEqual(0, cli(report([]), report([]), '--require-comparable', '--fail-on-regression')[0])
        self.assertEqual(1, cli(report([]), report([row()]), '--require-comparable', '--fail-on-regression')[0])

    def test_recorded_count_requires_a_list_but_omission_stays_legacy(self):
        for crawl in ({}, {'pages': []}, {'pages': [], 'pages_scanned': 0}):
            data = report([]); data['crawl'] = crawl
            self.assertEqual('comparable', diff_scan.diff_reports(data, data)['comparison']['status'])
        for crawl in ({'pages_scanned': 0}, {'pages_scanned': 2}, {'pages_scanned': None},
                      {'pages_scanned': 0, 'pages': {}}, {'pages_scanned': 0, 'pages': None}):
            data = report([]); data['crawl'] = crawl
            result = diff_scan.diff_reports(data, data)
            self.assertEqual('incomparable', result['comparison']['status'])
            self.assertIsNone(result['score_delta'])
            self.assertEqual(2, cli(data, data, '--fail-on-regression')[0])

    def test_explicit_page_count_must_match_the_recorded_sample(self):
        for count in (True, '2', 2.0, -1, 0, 1, 3, 99):
            for side in ('old', 'new'):
                old, new = report([]), report([])
                old['overall_score'], new['overall_score'] = 0, 100
                old['homepage']['findings'] = [{'category': 'technical', 'severity': 'high',
                    'title': 'Missing title', 'rule_id': 'technical.title.missing'}]
                (old if side == 'old' else new)['crawl']['pages_scanned'] = count
                with self.subTest(count=count, side=side):
                    original = copy.deepcopy((old, new))
                    result = diff_scan.diff_reports(old, new)
                    self.assertEqual('incomparable', result['comparison']['status'])
                    self.assertIsNone(result['score_delta'])
                    self.assertIsNone(result['regression'])
                    self.assertEqual([], result['resolved'])
                    self.assertEqual([], result['added'])
                    self.assertEqual(result, mcp_server._diff(json.dumps(old), json.dumps(new)))
                    self.assertEqual(2, cli(old, new, '--fail-on-regression')[0])
                    self.assertEqual('unverified', result['crawl_rule_changes']['status'])
                    self.assertIn('pages_scanned', result['crawl_rule_changes']['reason'])
                    self.assertIsNone(result['crawl_rule_changes']['regression'])
                    self.assertEqual(2, cli(old, new, '--require-comparable')[0])
                    self.assertEqual(original, (old, new))
        old, new = report([]), report([])
        for data in (old, new):
            data['crawl']['pages_scanned'] = 2
        self.assertEqual('compared', diff_scan.diff_reports(old, new)['crawl_rule_changes']['status'])
        self.assertEqual(0, cli(old, new, '--require-comparable')[0])


if __name__ == '__main__':
    unittest.main()
