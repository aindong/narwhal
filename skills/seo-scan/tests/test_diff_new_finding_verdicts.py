"""New lower-severity issues remain visible even when the score cannot fall."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diff_scan
import mcp_server
from lib.report import Report
from test_diff_severe_escalation import cli

URL = 'https://example.test/'


def native(extras=(), count=20, first='critical', repeated=False, prefix='technical.new.'):
    result = Report(URL, fetched_status=200)
    result.meta['scan_scope'] = {'requested': ['technical'], 'completed': ['technical']}
    for i in range(count):
        result.add('technical', first if i == 0 else 'critical', 'Existing issue',
                   rule_id='technical.existing' if repeated else 'technical.existing.' + str(i))
    for i, severity in enumerate(extras):
        result.add('technical', severity, 'New observation', rule_id=prefix + str(i))
    return json.loads(result.to_json())


class TestNewFindingVerdicts(unittest.TestCase):
    def test_new_low_medium_findings_at_score_floor_are_not_no_material_change(self):
        for severity in ('low', 'medium'):
            with self.subTest(severity=severity):
                before, after = native(), native([severity])
                original = copy.deepcopy((before, after))
                result = diff_scan.diff_reports(before, after)
                self.assertEqual((0, 0, 0), (result['old_score'], result['new_score'], result['score_delta']))
                self.assertEqual('comparable', result['comparison']['status'])
                self.assertEqual(1, len(result['added']))
                self.assertFalse(result['regression'])
                self.assertIn('New reported findings', diff_scan._verdict(result))
                self.assertNotIn('No material change', diff_scan.render_markdown(result))
                self.assertEqual(0, cli(before, after, '--fail-on-regression', '--require-comparable')[0])
                self.assertEqual(result, mcp_server._diff(json.dumps(before), json.dumps(after)))
                self.assertEqual(original, (before, after))

    def test_new_issues_with_score_or_identity_improvements_get_a_mixed_headline(self):
        for severity in ('low', 'medium'):
            cases = (
                ('score_gain', native(), native([severity, 'good'], count=0)),
                ('score_only', native(repeated=True), native([severity, 'good'], count=1, repeated=True)),
                ('resolved_floor', native(), native([severity, 'good'], count=19)),
                ('resolved_with_good', native(['good'], prefix='technical.passed.'),
                 native([severity, 'good'], count=19)),
                ('improved_floor', native(), native([severity, 'good'], first='low')),
            )
            for label, before, after in cases:
                with self.subTest(severity=severity, case=label):
                    result = diff_scan.diff_reports(before, after)
                    snapshot = copy.deepcopy(result)
                    self.assertFalse(result['regression'])
                    self.assertEqual(2, len(result['added']))
                    if label.startswith('score'):
                        self.assertGreater(result['score_delta'], 0)
                    else:
                        self.assertEqual(0, result['score_delta'])
                        self.assertTrue(result['resolved'] if label.startswith('resolved') else result['improved'])
                    if label == 'score_only':
                        self.assertEqual(([], []), (result['resolved'], result['improved']))
                    self.assertIn('Mixed reported finding changes', diff_scan._verdict(result))
                    self.assertNotIn('**Improved reported findings**', diff_scan.render_markdown(result))
                    self.assertEqual(snapshot, json.loads(diff_scan.render_json(result)))
                    self.assertEqual(0, cli(before, after, '--fail-on-regression', '--require-comparable')[0])

    def test_new_good_observations_do_not_become_new_issues_or_mixed_changes(self):
        before = native()
        for count, expected in ((20, 'No material change'), (0, 'Improved reported findings')):
            with self.subTest(count=count):
                result = diff_scan.diff_reports(before, native(['good'], count=count))
                self.assertIn(expected, diff_scan._verdict(result))
                self.assertFalse(result['regression'])

    def test_imported_fractional_and_one_point_gains_still_disclose_new_issues(self):
        for gain in (0.5, 1):
            with self.subTest(gain=gain):
                before = native(repeated=True)
                after = native(['medium'], count=1, repeated=True)
                before['score'], after['score'] = 50, 50 + gain
                result = diff_scan.diff_reports(before, after)
                self.assertEqual(gain, result['score_delta'])
                self.assertEqual(([], []), (result['resolved'], result['improved']))
                self.assertFalse(result['regression'])
                self.assertIn('Mixed reported finding changes', diff_scan._verdict(result))

    def test_removed_good_observations_are_not_reported_fixes(self):
        before = native(['good'], prefix='technical.passed.')
        for extras, expected in (([], 'No material change'), (['low'], 'New reported findings')):
            with self.subTest(extras=extras):
                after = native(extras)
                result = diff_scan.diff_reports(before, after)
                self.assertEqual(0, result['score_delta'])
                self.assertEqual(['good'], [f['severity'] for f in result['resolved']])
                self.assertFalse(result['regression'])
                self.assertIn(expected, diff_scan._verdict(result))
                self.assertNotIn('Improved reported findings', diff_scan._verdict(result))

    def test_worsening_and_new_issues_are_both_disclosed(self):
        before = native(first='low')
        for count in (20, 19, 1):
            with self.subTest(count=count):
                after = native(['medium', 'good'], count=count, first='medium')
                result = diff_scan.diff_reports(before, after)
                self.assertEqual(1, len(result['worsened']))
                self.assertFalse(result['regression'])
                if count >= 19:
                    self.assertEqual(0, result['score_delta'])
                else:
                    self.assertGreater(result['score_delta'], 0)
                verdict = diff_scan._verdict(result)
                expected = 'New findings and worsened severity' if count == 20 else 'Mixed reported finding changes'
                self.assertIn(expected, verdict)
                self.assertIn('new actionable findings', verdict.lower())
                self.assertIn('severity increases', verdict.lower())
                self.assertEqual(0, cli(before, after, '--fail-on-regression', '--require-comparable')[0])
        good_only = diff_scan.diff_reports(before, native(['good'], first='medium'))
        self.assertIn('Worsened reported severity', diff_scan._verdict(good_only))
        severe = native(['high'], first='medium')
        self.assertIn('**Regressed**', diff_scan._verdict(diff_scan.diff_reports(before, severe)))
        self.assertEqual(1, cli(before, severe, '--fail-on-regression', '--require-comparable')[0])

    def test_severe_additions_and_incomparability_keep_verdict_and_gate_priority(self):
        before = native()
        for severity in ('high', 'critical'):
            after = native([severity])
            verdict = diff_scan._verdict(diff_scan.diff_reports(before, after))
            self.assertIn('**Regressed**', verdict)
            self.assertIn('1 new high-severity issue', verdict)
            self.assertNotIn('score dropped', verdict)
            self.assertEqual(1, cli(before, after, '--fail-on-regression', '--require-comparable')[0])
        escalated = diff_scan.diff_reports(native(first='low'), native(first='high'))
        self.assertEqual(0, escalated['score_delta'])
        self.assertIn('escalated to critical/high', diff_scan._verdict(escalated))
        self.assertNotIn('score dropped', diff_scan._verdict(escalated))
        after = native(['medium'])
        after['meta']['response_truncated'] = True
        result = diff_scan.diff_reports(before, after)
        self.assertIsNone(result['regression'])
        self.assertIsNone(result['score_delta'])
        self.assertIn('Not comparable', diff_scan._verdict(result))
        self.assertEqual(2, cli(before, after, '--fail-on-regression', '--require-comparable')[0])


if __name__ == '__main__':
    unittest.main()
