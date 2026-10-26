"""Diff labels stay literal without changing measured transitions or JSON."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diff_scan
import render_report
from lib.report import md_to_html
from test_code_fences import Parsed
from test_plan_literal_paths import CodeText
from test_diff_scope import report, FINDING

PAYLOAD = '`Label```\n\n## Forged diff\n\n[Run](https://other.test)\n<script>bad()</script>\nend`'


class TestDiffLabelPreviews(unittest.TestCase):
    def check_labels(self, render):
        for field in ('url', 'title', 'category'):
            for change in ('added', 'resolved', 'worsened', 'improved'):
                with self.subTest(field=field, change=change):
                    finding = dict(FINDING, severity='medium')
                    value = ('https://example.test/' if field == 'url' else '') + PAYLOAD
                    if field != 'url':
                        finding[field] = value
                    old = [] if change == 'added' else [dict(finding)]
                    new = [] if change == 'resolved' else [dict(finding)]
                    if change == 'worsened':
                        new[0]['severity'] = 'high'
                    if change == 'improved':
                        old[0]['severity'] = 'high'
                    before = report(['technical'], findings=old, score=90)
                    after = report(['technical'], findings=new,
                                   score=80 if change in ('added', 'worsened') else 100)
                    if field == 'url':
                        before['url'] = after['url'] = value
                    inputs = copy.deepcopy((before, after))
                    result = diff_scan.diff_reports(before, after)
                    self.assertEqual('comparable', result['comparison']['status'])
                    self.assertEqual(1, len(result[change]))
                    snapshot = copy.deepcopy(result)
                    html = render(diff_scan.render_markdown(result))
                    codes = CodeText()
                    codes.feed(html)
                    self.assertIn(' '.join(value.split()), codes.values)
                    if field != 'category':
                        self.assertIn('Technical SEO', codes.values)
                    if change in ('added', 'resolved'):
                        self.assertIn('🟡', html)
                    else:
                        transition = 'medium → high' if change == 'worsened' else 'high → medium'
                        self.assertIn(transition, html)
                    self.assertNotIn('a', Parsed(html).tags)
                    self.assertNotIn('script', Parsed(html).tags)
                    self.assertEqual(inputs, (before, after))
                    self.assertEqual(snapshot, json.loads(diff_scan.render_json(result)))

    def test_builtin_renderer_keeps_all_change_labels_literal(self):
        self.check_labels(md_to_html)

    def test_commonmark_renderer_keeps_all_change_labels_literal(self):
        try:
            from markdown_it import MarkdownIt
        except ImportError:
            self.skipTest('optional markdown-it-py is unavailable')
        self.check_labels(MarkdownIt('commonmark', {'html': True}).render)

    def test_branded_export_keeps_document_title_plain(self):
        result = diff_scan.diff_reports(report(['technical']), report(['technical']))
        html = render_report.render(diff_scan.render_markdown(result))
        title = html.partition('<title>')[2].partition('</title>')[0]
        self.assertIn('Narwhal Scan Diff', title)
        self.assertNotIn('`', title)
        codes = CodeText()
        codes.feed(html)
        self.assertIn(result['url'], codes.values)


if __name__ == '__main__':
    unittest.main()
