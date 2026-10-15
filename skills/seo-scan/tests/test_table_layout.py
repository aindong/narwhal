"""Markdown tables have scoped display styles and accessible scroll wrappers."""

import contextlib
import io
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import render_report
from lib import report


class Parsed(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.tags, self.ends = [], []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_endtag(self, tag):
        self.ends.append(tag)


class TestTableLayout(unittest.TestCase):
    def test_scroll_region_is_named_keyboard_reachable_and_scoped(self):
        parsed = Parsed(report.md_to_html('| A | B |\n|:--|:--|\n| 1 | 2 |'))
        self.assertEqual(('div', {'class': 'table-scroll', 'tabindex': '0',
                                 'role': 'region', 'aria-label': 'Scrollable report table'}), parsed.tags[0])
        self.assertEqual(('table', {'class': 'markdown'}), parsed.tags[1])
        self.assertEqual(['tbody', 'table', 'div'], parsed.ends[-3:])

    def test_each_heading_is_a_semantic_column_header(self):
        parsed = Parsed(report.md_to_html('| A | B |\n|:--|:--|\n| 1 | 2 |'))
        self.assertEqual([{'scope': 'col'}, {'scope': 'col'}],
                         [attrs for tag, attrs in parsed.tags if tag == 'th'])
        self.assertEqual([{}, {}], [attrs for tag, attrs in parsed.tags if tag == 'td'])

    def test_multiple_tables_get_independent_closed_regions(self):
        table = '| A |\n|:--|\n| value |'
        html = report.md_to_html(table + '\n\nBetween tables\n\n' + table)
        self.assertEqual(2, html.count('<div class="table-scroll"'))
        self.assertEqual(2, html.count('</tbody></table></div>'))
        self.assertIn('</table></div>\n<p>Between tables</p>\n<div', html)

    def test_table_text_cannot_add_wrapper_or_header_attributes(self):
        html = report.md_to_html('| <script>bad</script> |\n|:--|\n| " tabindex="99 |')
        parsed = Parsed(html)
        self.assertEqual(1, sum(tag == 'div' for tag, attrs in parsed.tags))
        self.assertNotIn('script', [tag for tag, attrs in parsed.tags])
        self.assertIn('&lt;script&gt;bad&lt;/script&gt;', html)
        self.assertEqual([{'scope': 'col'}], [attrs for tag, attrs in parsed.tags if tag == 'th'])

    def test_no_table_means_no_scroll_container(self):
        html = report.md_to_html('Body\n\n```\n| not a table |\n```')
        self.assertNotIn('class="table-scroll"', html)
        self.assertNotIn('class="markdown"', html)

    def test_native_score_table_keeps_its_separate_class(self):
        rep = report.Report('https://example.test/')
        rep.add('technical', 'good', 'Example')
        html = rep.to_html()
        self.assertIn('<table class="areas">', html)
        self.assertNotIn('<table class="markdown">', html)
        self.assertNotIn('<div class="table-scroll"', html)

    def test_real_cli_file_stdin_and_pdf_input_include_same_wrappers(self):
        md = '# Report\n\n| Rule | Evidence |\n|:--|:--|\n| Title | `café\\|🐳` |'
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'report.md'
            target = Path(directory) / 'report.html'
            source.write_text(md, encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, render_report.main([str(source), '-o', str(target)]))
            html = target.read_text(encoding='utf-8')
            self.assertIn('<div class="table-scroll" tabindex="0"', html)
            self.assertIn('<th scope="col">Rule</th>', html)
            with mock.patch('sys.stdin', io.StringIO(md)), \
                    mock.patch.object(render_report, 'deliver', return_value=0) as deliver:
                self.assertEqual(0, render_report.main(['-', '--format', 'pdf', '-o', str(Path(directory) / 'report.pdf')]))
            self.assertEqual(html, deliver.call_args.args[2])


if __name__ == '__main__':
    unittest.main()
