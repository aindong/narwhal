"""Repeated rule identities must not hide severe evidence or invent changes."""

import copy
import itertools
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diff_scan
import mcp_server
from lib.report import Report
from test_diff_scope import invoke, report


def finding(severity='high', **fields):
    return dict({'category': 'schema', 'rule_id': 'schema.repeated',
                 'title': 'Repeated schema observation', 'severity': severity}, **fields)


def scan(findings):
    return report(['schema'], findings=list(findings), score=0)


class TestRepeatedRuleDiffs(unittest.TestCase):
    def test_serialized_report_model_preserves_gate_at_the_score_floor(self):
        before = Report(url='https://example.test/', fetched_status=200)
        before.meta['scan_scope'] = {'requested': ['schema'], 'completed': ['schema']}
        for index in range(17):
            before.add('schema', 'high', 'Existing controlled finding', rule_id='schema.existing.' + str(index))
        after = copy.deepcopy(before)
        for severity in ('critical', 'high', 'low', 'good'):
            after.add(**finding(severity))
        self.assertEqual(0, before.score())
        self.assertEqual(0, after.score())
        result = diff_scan.diff_reports(json.loads(before.to_json()), json.loads(after.to_json()))
        self.assertEqual(0, result['score_delta'])
        self.assertTrue(result['regression'])
        self.assertEqual('critical', result['added'][0]['severity'])
        self.assertEqual(3, result['finding_identity']['new']['repeated_entries'])

    def test_reordering_repeated_rules_cannot_invent_severity_changes(self):
        entries = [finding('high'), finding('medium'), finding('low')]
        before = scan(entries)
        expected = diff_scan.diff_reports(before, before)
        for order in itertools.permutations(entries):
            with self.subTest(order=[item['severity'] for item in order]):
                result = diff_scan.diff_reports(before, scan(order))
                self.assertEqual([], result['worsened'])
                self.assertEqual([], result['improved'])
                self.assertEqual(1, result['unchanged'])
                self.assertEqual(expected, result)

    def test_new_high_rule_is_not_hidden_when_reported_score_is_already_zero(self):
        for entries in ([finding('high'), finding('low')], [finding('low'), finding('high')]):
            before, after = scan([]), scan(entries)
            result = diff_scan.diff_reports(before, after)
            self.assertEqual([finding('high')], result['added'])
            self.assertEqual([finding('high')], result['new_critical_high'])
            self.assertEqual(0, result['score_delta'])
            self.assertTrue(result['regression'])
            code, output, _ = invoke(before, after, '--fail-on-regression', '--format', 'json')
            self.assertEqual(1, code)
            self.assertTrue(json.loads(output)['regression'])

    def test_real_severity_transitions_use_each_rules_worst_observed_severity(self):
        before = scan([finding('high'), finding('low')])
        after = scan([finding('medium'), finding('low')])
        improved = diff_scan.diff_reports(before, after)
        self.assertEqual('high', improved['improved'][0]['from'])
        self.assertEqual('medium', improved['improved'][0]['to'])
        self.assertEqual('schema.repeated', improved['improved'][0]['rule_id'])
        worsened = diff_scan.diff_reports(after, before)
        self.assertEqual('medium', worsened['worsened'][0]['from'])
        self.assertEqual('high', worsened['worsened'][0]['to'])
        self.assertTrue(worsened['regression'])  # existing rules escalating to high now trigger the gate
        self.assertIn('escalated to critical/high', diff_scan.render_markdown(worsened))
        self.assertNotIn('No material change', diff_scan.render_markdown(worsened))

    def test_equal_severity_uses_a_stable_representative_without_mutation(self):
        entries = [finding(detail='z node'), finding(detail='a node')]
        before = scan([])
        original = copy.deepcopy(entries)
        forward = diff_scan.diff_reports(before, scan(entries))
        reverse = diff_scan.diff_reports(before, scan(reversed(entries)))
        self.assertEqual(forward, reverse)
        self.assertEqual(original, entries)
        self.assertEqual(1, len(forward['added']))

    def test_repeated_entry_receipt_discloses_identity_not_instance_matching(self):
        before = scan([finding('high'), finding('low')])
        result = diff_scan.diff_reports(before, scan([]))
        self.assertEqual([finding('high')], result['resolved'])
        receipt = result['finding_identity']
        self.assertEqual({'raw_findings': 2, 'distinct_identities': 1, 'repeated_entries': 1}, receipt['old'])
        self.assertEqual({'raw_findings': 0, 'distinct_identities': 0, 'repeated_entries': 0}, receipt['new'])
        text = diff_scan.render_markdown(result)
        self.assertIn('Repeated finding identities', text)
        self.assertIn('individual instances are not matched', text)

    def test_distinct_categories_ids_and_legacy_titles_preserve_their_identity(self):
        entries = [finding(rule_id='schema.z'), finding(rule_id='schema.a'),
                   finding(category='technical', rule_id='schema.a')]
        result = diff_scan.diff_reports(scan([]), scan(entries))
        self.assertEqual(['schema.a', 'schema.z', 'schema.a'], [item['rule_id'] for item in result['added']])
        legacy = [finding('high', rule_id='', title='Node issue (one)'),
                  finding('low', rule_id='', title='Node issue (two)')]
        result = diff_scan.diff_reports(scan(legacy), scan(reversed(legacy)))
        self.assertEqual([], result['worsened'])
        self.assertEqual([], result['improved'])
        self.assertEqual(1, result['unchanged'])

    def test_mcp_audit_and_incomparability_keep_the_same_boundary(self):
        old = {'site': 'https://example.test/', 'overall_score': 0, 'homepage': scan([])}
        new = copy.deepcopy(old)
        new['homepage'] = scan([finding('high'), finding('low')])
        result = mcp_server._diff(json.dumps(old), json.dumps(new))
        self.assertTrue(result['regression'])
        new['homepage']['meta']['scan_scope']['completed'] = []
        result = diff_scan.diff_reports(old, new)
        self.assertEqual('incomparable', result['comparison']['status'])
        self.assertIsNone(result['regression'])
        self.assertEqual([], result['added'])
        self.assertNotIn('finding_identity', result)

    def test_mixed_changes_do_not_claim_only_improvement(self):
        before = scan([finding('low'), finding('low', rule_id='schema.other')])
        after = scan([finding('medium')])
        result = diff_scan.diff_reports(before, after)
        self.assertTrue(result['worsened'])
        self.assertTrue(result['resolved'])
        self.assertFalse(result['regression'])
        text = diff_scan.render_markdown(result)
        self.assertIn('Mixed reported finding changes', text)
        self.assertNotIn('**Improved reported findings**', text)


if __name__ == '__main__':
    unittest.main()
