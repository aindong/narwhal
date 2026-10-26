"""Source path spelling remains literal in owner and related-action previews."""
import copy
from html.parser import HTMLParser
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan
from lib.report import md_to_html


class CodeText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == 'code':
            self.current = ''

    def handle_data(self, data):
        if self.current is not None:
            self.current += data

    def handle_endtag(self, tag):
        if tag == 'code' and self.current is not None:
            self.values.append(self.current.strip())  # delimiter padding is layout only
            self.current = None


class TestLiteralPlanPaths(unittest.TestCase):
    def test_route_conventions_preserve_literal_spaces_and_edge_letters(self):
        for framework, url_path, rel in (
                ('plain_html', '/pricing guide', 'pricing guide.htm'),
                ('plain_html', '/XML', 'XML.htm'),
                ('hugo', '/guides/projectX', 'content/guides/projectX.md'),
                ('jekyll', '/Xdocs/projectX', 'Xdocs/projectX.md')):
            with self.subTest(framework=framework, path=url_path):
                self.assertIn(rel, plan._route_candidates('https://example.test' + url_path,
                                                         framework, files=[rel]))

    def test_owner_and_group_paths_survive_markdown_punctuation(self):
        for rel in ('app/layout`_invented_`.tsx', 'app/layout``_invented_``.tsx',
                    'app/layout[ghost](#anchor).tsx', 'app/layout`', '`layout.tsx'):
            with self.subTest(path=rel), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                (root / 'app').mkdir()
                (root / 'package.json').write_text('{"dependencies":{"next":"*"}}', encoding='utf-8')
                source = root / rel
                source.write_text('Fixture source', encoding='utf-8')
                report = {'url': 'https://example.test/', 'findings': [
                    {'rule_id': 'technical.missing.title', 'category': 'technical', 'severity': 'high', 'title': 'Missing title'},
                    {'rule_id': 'technical.missing.meta.description', 'category': 'technical', 'severity': 'high', 'title': 'Missing meta description'}]}
                built = plan.build_plan(report, str(root))
                original = copy.deepcopy(built)
                markdown = plan.render_markdown(built)
                owner_lines = [line for line in markdown.splitlines() if line.startswith('- **Likely owner:**')]
                group_lines = [line for line in markdown.splitlines() if line.startswith('- **shared_head_metadata**')]
                self.assertEqual(2, len(owner_lines))
                self.assertEqual(1, len(group_lines))
                for line in owner_lines + group_lines:
                    parser = CodeText()
                    html = md_to_html(line)
                    parser.feed(html)
                    self.assertIn(rel, parser.values)
                    self.assertNotIn('<em>invented</em>', html)
                group = CodeText()
                group.feed(md_to_html(group_lines[0]))
                self.assertEqual(2, group.values.count(rel))  # union and overlap witness
                self.assertEqual(original, built)
                self.assertEqual('Fixture source', source.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
