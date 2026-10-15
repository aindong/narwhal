"""Native score-table HTML changes must not alter report measurements."""

from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from lib.report import Report


class TestNativeScoreTable(unittest.TestCase):
    def test_table_has_a_named_focusable_region_and_accessible_headers(self):
        report = Report('https://example.test/guide', fetched_status=200)
        report.add('content', 'low', 'Synthetic observation')
        output = report.to_html()
        self.assertIn('class="score-table-scroll" tabindex="0" role="region"', output)
        self.assertIn('aria-label="Score breakdown by area; scroll horizontally if needed"', output)
        self.assertIn('Scroll horizontally if needed to view all scores and severity counts.', output)
        headers = re.findall(r'<th scope="col"(?: aria-label="([^"]+)")?>', output)
        self.assertEqual(['', '', 'Critical', 'High', 'Medium', 'Low', 'Passed'], headers)
        self.assertNotIn('class="table-scroll"', output)

    def test_rendering_preserves_json_markdown_scores_and_counts(self):
        report = Report('https://example.test/guide', fetched_status=200)
        for category in ('technical', 'content', 'schema', 'geo'):
            for severity in ('critical', 'high', 'medium', 'low', 'good'):
                report.add(category, severity, 'Synthetic observation')
        before = (report.to_json(), report.to_markdown(), report.score(), report.counts())
        output = report.to_html()
        self.assertIn('<table class="areas">', output)
        self.assertEqual(before, (report.to_json(), report.to_markdown(), report.score(), report.counts()))
        self.assertEqual(1, output.count('class="score-table-scroll"'))

    def test_unmeasured_or_empty_reports_do_not_get_empty_scroll_regions(self):
        for meta in ({}, {'scan_scope': {'requested': ['content'], 'completed': []}}):
            report = Report('https://example.test/guide', fetched_status=200, meta=meta)
            self.assertNotIn('class="score-table-scroll"', report.to_html())


if __name__ == '__main__':
    unittest.main()
