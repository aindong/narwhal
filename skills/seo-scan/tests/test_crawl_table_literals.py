"""URL data must not become table delimiters or inline report formatting."""

import copy
import sys
import unittest
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit
import crawl_site as crawl
from lib import report
from lib.markdown_text import TABLE_TEXT_MARKER, table_text

BASE = 'https://example.test/'


class Table(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.rows, self.row, self.formatting = [], None, []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        if tag in ('td', 'th') and self.row is not None:
            self.row.append('')
        if self.row is not None and tag in ('a', 'em', 'strong', 'script', 'img'):
            self.formatting.append(tag)

    def handle_endtag(self, tag):
        if tag == 'tr':
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, value):
        if self.row:
            self.row[-1] += value


def site(url):
    return {'base': BASE, 'pages_scanned': 1, 'avg_score': 75,
            'pages': [{'url': url, 'score': 75}], 'recurring': Counter()}


class TestCrawlTableLiterals(unittest.TestCase):
    def test_weakest_page_urls_remain_exactly_two_literal_cells(self):
        for suffix in ('catalog|featured', '[guide](https://outside.test/)', '_topic_/',
                       '**literal**', '`literal`', r'a\|b', r'a\\|b',
                       '<img src=x>&"café🐳"', '|leading||trailing|'):
            with self.subTest(suffix=suffix):
                url = BASE + suffix
                table = Table(report.md_to_html(crawl.render_markdown(site(url))))
                self.assertEqual([['Score', 'URL'], ['75', url]], table.rows)
                self.assertEqual([], table.formatting)

    def test_broken_link_target_source_and_error_keep_four_cells(self):
        data = site(BASE)
        target = BASE + '[link](https://outside.test/)|_target_'
        source = BASE + '`source`|x'
        error = 'request | [error](https://outside.test/)'
        data['links'] = {'checked': 1, 'skipped_over_cap': 0, 'broken': [
            {'status': 0, 'error': error, 'internal': False, 'url': target, 'sources': [source]}]}
        table = Table(report.md_to_html(crawl.render_markdown(data)))
        self.assertEqual([error, 'external', target, source], table.rows[-1])
        self.assertEqual([], table.formatting)

    def test_audit_html_inherits_literal_cells_without_changing_evidence(self):
        data = site(BASE + '[link](https://outside.test/)|_topic_')
        original = copy.deepcopy(data)
        audit_data = {'site': BASE, 'page': report.Report(BASE), 'site_result': data,
                      'sitemap': {'start': BASE, 'seeds': []}}
        html = audit.render_html(audit_data)
        self.assertNotIn('href="https://outside.test/"', html)
        self.assertIn('example.test/[link](https://outside.test/)|_topic_', html)
        self.assertEqual(original, data)
        self.assertEqual(75, data['avg_score'])

    def test_inline_backslash_escapes_are_literal_outside_code(self):
        self.assertEqual('*literal* _literal_ [x](https://outside.test/) `tick`',
                         report._inline_md(r'\*literal\* \_literal\_ \[x\]\(https://outside.test/\) \`tick\`', unescape=True))
        self.assertEqual('<code>\\*literal\\*</code>', report._inline_md(r'`\*literal\*`', unescape=True))
        self.assertEqual(r'\q', report._inline_md(r'\q'))

    def test_even_backslashes_keep_code_opening_and_escaped_href_is_safe(self):
        self.assertEqual('\\<code>literal</code>', report._inline_md(r'\\`literal`', unescape=True))
        rendered = report._inline_md(r'[label](https://example.test/a\_b\(c\))', unescape=True)
        self.assertEqual('<a href="https://example.test/a_b(c)">label</a>', rendered)

    def test_escape_opt_in_does_not_leak_to_legacy_tables_text_or_fences(self):
        table = '| Header |\n|:--|\n| \\#literal |'
        md = TABLE_TEXT_MARKER + '\n' + table + '\n\n' + table + '\n\nOutside a\\|b\n\n```\n' + TABLE_TEXT_MARKER + '\n' + table + '\n```'
        rendered = report.md_to_html(md)
        self.assertEqual([['Header'], ['#literal'], ['Header'], [r'\#literal']], Table(rendered).rows)
        self.assertIn('<p>Outside a\\|b</p>', rendered)
        self.assertIn('&lt;!-- narwhal: escaped-table-cells-v1 --&gt;', rendered)

    def test_generated_cells_keep_backslash_pipe_and_backtick_runs_literal(self):
        for slash_count in range(9):
            for tick_count in range(7):
                value = BASE + '\\' * slash_count + '|' + '`' * tick_count + '_x_|'
                md = TABLE_TEXT_MARKER + '\n| Value |\n|:--|\n| ' + table_text(value) + ' |'
                with self.subTest(slashes=slash_count, ticks=tick_count):
                    parsed = Table(report.md_to_html(md))
                    self.assertEqual([['Value'], [value]], parsed.rows)
                    self.assertEqual([], parsed.formatting)

    def test_entities_quotes_and_reserved_tokens_cannot_create_markup(self):
        value = '<narwhal-escape-0> &lt;narwhal-escape-1&gt; &amp; <img src=x> "café 🐳"'
        md = TABLE_TEXT_MARKER + '\n| Value |\n|:--|\n| ' + table_text(value) + ' |'
        parsed = Table(report.md_to_html(md))
        self.assertEqual([['Value'], [value]], parsed.rows)
        self.assertEqual([], parsed.formatting)

    def test_multiline_data_is_one_cell_and_marker_requires_adjacent_table(self):
        self.assertEqual('a b', table_text('  a\n\tb  '))
        rendered = report.md_to_html(TABLE_TEXT_MARKER + '\n\n| Value |\n|:--|\n| \\#literal |')
        self.assertEqual([['Value'], [r'\#literal']], Table(rendered).rows)
        self.assertIn('&lt;!-- narwhal: escaped-table-cells-v1 --&gt;', rendered)


if __name__ == '__main__':
    unittest.main()
