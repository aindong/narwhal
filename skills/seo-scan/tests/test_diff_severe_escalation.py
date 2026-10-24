"""High/critical escalation of an existing rule must not hide behind score gains."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diff_scan
import mcp_server
from lib.report import Report

URL = 'https://example.test/'
RULE = 'technical.existing'


def report(severity, other=False):
    result = Report(URL, fetched_status=200)
    result.meta['scan_scope'] = {'requested': ['technical'], 'completed': ['technical']}
    result.add('technical', severity, 'Existing rule', rule_id=RULE)
    if other:
        result.add('technical', 'critical', 'Other issue', rule_id='technical.other')
    return json.loads(result.to_json())


def cli(before, after, *options):
    with tempfile.TemporaryDirectory() as tmp:
        old, new = Path(tmp) / 'before.json', Path(tmp) / 'after.json'
        old.write_text(json.dumps(before), encoding='utf-8')
        new.write_text(json.dumps(after), encoding='utf-8')
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = diff_scan.main([str(old), str(new), *options])
    return code, out.getvalue(), err.getvalue()


class TestSevereEscalation(unittest.TestCase):
    def test_real_reports_gate_critical_escalation_despite_a_higher_total_score(self):
        before, after = report('low', other=True), report('critical')
        original = copy.deepcopy((before, after))
        result = diff_scan.diff_reports(before, after)
        self.assertEqual((87, 88), (result['old_score'], result['new_score']))
        self.assertEqual('comparable', result['comparison']['status'])
        self.assertEqual([], result['added'])
        self.assertEqual([], result['new_critical_high'])  # this rule already existed
        self.assertTrue(result['regression'])
        self.assertEqual(RULE, result['worsened'][0]['rule_id'])
        self.assertIn('escalated', diff_scan.render_markdown(result))
        self.assertEqual(original, (before, after))
        code, output, error = cli(before, after, '--fail-on-regression', '--format', 'json')
        self.assertEqual(1, code)
        self.assertTrue(json.loads(output)['regression'])
        self.assertIn('escalated', error)
        self.assertEqual(0, cli(before, after)[0])  # viewing a diff alone does not fail CI

    def test_all_severity_transitions_apply_the_high_critical_threshold(self):
        order = ['critical', 'high', 'medium', 'low', 'good']
        for old in order:
            for new in order:
                with self.subTest(old=old, new=new):
                    before, after = report(old), report(new)
                    before['score'] = after['score'] = 50
                    expected = order.index(new) < order.index(old) and new in ('critical', 'high')
                    result = diff_scan.diff_reports(before, after)
                    self.assertEqual(expected, result['regression'])
                    self.assertEqual([], result['new_critical_high'])

    def test_score_floor_repeated_rules_and_legacy_ids_keep_existing_semantics(self):
        before, after = report('medium'), report('high')
        before['score'] = after['score'] = 0
        before['findings'].append(dict(before['findings'][0], severity='low'))
        after['findings'].append(dict(after['findings'][0], severity='low'))
        self.assertTrue(diff_scan.diff_reports(before, after)['regression'])
        after['findings'].reverse()
        self.assertTrue(diff_scan.diff_reports(before, after)['regression'])
        for data in (before, after):
            for finding in data['findings']:
                finding.pop('rule_id')
        self.assertTrue(diff_scan.diff_reports(before, after)['regression'])
        self.assertFalse(diff_scan.diff_reports(after, dict(after, findings=list(reversed(after['findings']))))['regression'])

    def test_known_incomparability_still_withholds_any_regression_verdict(self):
        before, after = report('low'), report('critical')
        after['meta']['response_truncated'] = True
        result = diff_scan.diff_reports(before, after)
        self.assertEqual('incomparable', result['comparison']['status'])
        self.assertIsNone(result['regression'])
        self.assertEqual([], result['worsened'])
        self.assertEqual(2, cli(before, after, '--fail-on-regression')[0])

    def test_mcp_returns_the_same_observed_escalation_policy(self):
        before, after = report('high', other=True), report('critical')
        result = mcp_server._diff(json.dumps(before), json.dumps(after))
        self.assertTrue(result['regression'])
        self.assertGreater(result['score_delta'], 0)
        self.assertEqual('high', result['worsened'][0]['from'])
        self.assertEqual('critical', result['worsened'][0]['to'])


if __name__ == '__main__':
    unittest.main()
