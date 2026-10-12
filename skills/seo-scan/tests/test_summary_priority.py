"""A numeric score band is not a verdict that priority findings are safe."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from lib.report import Report, _grade, _score_header


def report(severity='high', focused=True):
    groups = ['schema'] if focused else ['technical', 'content', 'schema', 'geo']
    rep = Report('https://example.test/', fetched_status=200,
                 meta={'scan_scope': {'requested': groups, 'completed': groups}})
    if severity:
        rep.add('schema', severity, 'Price issue', 'Observed issue', 'Fix the price')
    return rep


class TestPrioritySummary(unittest.TestCase):
    def test_high_findings_override_excellent_headline_not_numeric_score(self):
        rep = report(); self.assertGreaterEqual(rep.score(), 90)
        html = rep.to_html()
        self.assertIn('High-priority findings</div>', html)
        self.assertIn('Score band: excellent', html)
        self.assertNotIn('>Excellent</div>', html)
        self.assertIn('Selected-check score', html)

    def test_critical_findings_take_precedence_even_at_a_high_score(self):
        counts = {'critical': 1, 'high': 2, 'medium': 0, 'low': 0, 'good': 0}
        html = _score_header(99, 'excellent', counts, 200, False)
        self.assertIn('Critical findings first</div>', html)
        self.assertIn('Score band: excellent', html)
        self.assertNotIn('High-priority findings</div>', html)

    def test_summary_leads_with_issues_in_completed_scope(self):
        for focused in (True, False):
            rep = report(focused=focused)
            summary = rep._summary_text(rep.score(), _grade(rep.score()), rep.counts())
            self.assertTrue(summary.startswith('**1 high issue(s) need attention in the completed checks'))
            self.assertIn('score band: excellent', summary)
            markdown = rep.to_markdown()
            self.assertIn('score band: excellent', markdown)
            self.assertIn('Top priorities:', markdown)

    def test_highlight_is_not_an_overall_claim_for_focused_or_legacy_reports(self):
        rep = report()
        for text in (rep.to_html(), rep.to_markdown()):
            self.assertIn('not overall page health', text)
            self.assertNotIn('This page scores', text)
        rep.meta = {}
        for text in (rep.to_html(), rep.to_markdown()):
            self.assertIn('Auditor selection was not recorded', text)
            self.assertIn('in the reported findings', text)

    def test_failed_execution_stays_not_measured_not_priority_grade(self):
        rep = report('critical'); rep.hard_fail = True
        rep.meta['scan_scope']['completed'] = []
        html = rep.to_html()
        self.assertIn('Not Measured</div>', html)
        self.assertNotIn('Critical findings first</div>', html)
        self.assertNotIn('Score band:', html)
        self.assertIn('no page health was measured', html)

    def test_no_priority_findings_keep_grade_with_explicit_band_label(self):
        for severity in (None, 'low', 'medium'):
            rep = report(severity)
            self.assertIn('>Excellent</div>', rep.to_html())
            self.assertIn('Score band: excellent', rep.to_html())
            self.assertNotIn('High-priority findings</div>', rep.to_html())

    def test_rendering_does_not_mutate_findings_json_or_score(self):
        rep = report(); before = json.loads(rep.to_json()); score = rep.score()
        rep.to_html(); rep.to_markdown()
        self.assertEqual(before, json.loads(rep.to_json()))
        self.assertEqual(score, rep.score())


if __name__ == '__main__':
    unittest.main()
