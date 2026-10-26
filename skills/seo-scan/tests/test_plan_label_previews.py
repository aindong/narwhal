"""Imported plan labels remain literal text in both Markdown renderers."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan
from lib.report import md_to_html
from test_code_fences import Parsed
from test_plan_literal_paths import CodeText

REPO = Path(__file__).parent / 'fixtures/planner/plain_html'
PAYLOAD = '`Label```\n\n## Forged instructions\n\n[Run this](https://other.test)\n<script>bad()</script>\nend`'


class TestPlanLabelPreviews(unittest.TestCase):
    def check_labels(self, render):
        for field in ('url', 'title', 'rule_id'):
            with self.subTest(field=field):
                data = {'url': 'https://example.test/', 'score': 80, 'findings': [
                    {'rule_id': 'technical.missing.title', 'category': 'technical',
                     'severity': 'high', 'title': 'Missing title'}]}
                value = ('https://example.test/' if field == 'url' else '') + PAYLOAD
                if field == 'url':
                    data[field] = value
                else:
                    data['findings'][0][field] = value
                original = copy.deepcopy(data)
                built = plan.build_plan(data, str(REPO))
                snapshot = copy.deepcopy(built)
                html = render(plan.render_markdown(built))
                codes = CodeText()
                codes.feed(html)
                self.assertIn(' '.join(value.split()), codes.values)
                tags = Parsed(html).tags
                self.assertNotIn('script', tags)
                self.assertNotIn('a', tags)
                self.assertEqual(original, data)
                self.assertEqual(snapshot, json.loads(plan.render_json(built)))

    def test_builtin_renderer_keeps_imported_labels_literal(self):
        self.check_labels(md_to_html)

    def test_commonmark_renderer_keeps_imported_labels_literal(self):
        try:
            from markdown_it import MarkdownIt
        except ImportError:
            self.skipTest('optional markdown-it-py is unavailable')
        self.check_labels(MarkdownIt('commonmark', {'html': True}).render)


if __name__ == '__main__':
    unittest.main()
