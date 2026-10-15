"""Literal fenced code stays escaped, copyable, and outside title extraction."""

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
from lib.code_fences import closes_fence, markdown_lines, opening_fence


class Parsed(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.blocks, self.tags = [], []
        self.in_pre = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == 'pre':
            self.in_pre = True
            self.blocks.append({'text': '', 'children': [], 'code_attrs': {}})
        elif self.in_pre:
            self.blocks[-1]['children'].append(tag)
            if tag == 'code':
                self.blocks[-1]['code_attrs'] = dict(attrs)

    def handle_endtag(self, tag):
        if tag == 'pre':
            self.in_pre = False

    def handle_data(self, data):
        if self.in_pre:
            self.blocks[-1]['text'] += data


class TestCodeFences(unittest.TestCase):
    def test_markdown_markers_inside_code_remain_literal(self):
        code = '# comment\n- not a list\n| A | B |\n|:--|:--|\n> not a quote\n---\n**not bold** _not italic_ `not inline` [not a link](https://example.test)'
        parsed = Parsed(report.md_to_html('```sh\n' + code + '\n```'))
        self.assertEqual(code + '\n', parsed.blocks[0]['text'])
        self.assertEqual(['pre', 'code'], parsed.tags)
        self.assertEqual({'class': 'language-sh'}, parsed.blocks[0]['code_attrs'])

    def test_html_and_info_strings_cannot_create_active_markup(self):
        code = '<script>window.probe=true</script>\n<img src=x onerror=alert(1)> & "quote"'
        for info in ('sh onload="bad"', '"><img src=x>', 'sh" onclick="bad', 'x' * 100):
            with self.subTest(info=info):
                parsed = Parsed(report.md_to_html('~~~' + info + '\n' + code + '\n~~~'))
                self.assertEqual(code + '\n', parsed.blocks[0]['text'])
                self.assertEqual(['pre', 'code'], parsed.tags)
                self.assertIn(parsed.blocks[0]['code_attrs'], ({}, {'class': 'language-sh'}))

    def test_both_markers_and_longer_closing_fences_are_supported(self):
        for marker in ('`', '~'):
            for length in (3, 4, 12):
                with self.subTest(marker=marker, length=length):
                    md = marker * length + 'c++\n  literal\n' + marker * (length + 2) + '\t '
                    parsed = Parsed(report.md_to_html(md))
                    self.assertEqual('  literal\n', parsed.blocks[0]['text'])
                    self.assertEqual({'class': 'language-c++'}, parsed.blocks[0]['code_attrs'])

    def test_wrong_short_or_annotated_closers_remain_code(self):
        code = '~~~\n```\n````sh\n    ````\n# still code'
        parsed = Parsed(report.md_to_html('````sh\n' + code + '\n````'))
        self.assertEqual(code + '\n', parsed.blocks[0]['text'])
        self.assertEqual(['pre', 'code'], parsed.tags)

    def test_opening_indent_is_removed_without_stripping_literal_whitespace(self):
        for indent in range(4):
            prefix = ' ' * indent
            md = prefix + '```\n' + prefix + '  x\t  \n\tsecond\n' + prefix + '```'
            parsed = Parsed(report.md_to_html(md))
            self.assertEqual('  x\t  \n\tsecond\n', parsed.blocks[0]['text'])

    def test_line_endings_are_normalized_but_other_code_characters_are_retained(self):
        code = 'a\v\f\x85\u2028\u2029b\t '
        for ending in ('\n', '\r\n', '\r'):
            parsed = Parsed(report.md_to_html('```' + ending + code + ending + '```'))
            self.assertEqual(code + '\n', parsed.blocks[0]['text'])
        self.assertEqual(['a', ''], markdown_lines('a\n', terminal_empty=True))
        self.assertEqual(['a'], markdown_lines('a\n'))

    def test_unclosed_block_and_blank_lines_are_preserved_to_eof(self):
        parsed = Parsed(report.md_to_html('```sh\n# comment\n\n'))
        self.assertEqual('# comment\n\n', parsed.blocks[0]['text'])
        self.assertEqual('', Parsed(report.md_to_html('```\n```')).blocks[0]['text'])

    def test_title_extraction_skips_fenced_headings_and_keeps_comment(self):
        for marker in ('```', '~~~'):
            md = 'Intro\n\n' + marker + 'sh\n# Keep this comment\n' + marker + '\n\n# Actual title\n\nBody\n'
            title, body = render_report._split_title(md)
            self.assertEqual('Actual title', title)
            self.assertIn('# Keep this comment', body)
            self.assertNotIn('# Actual title', body)
            parsed = Parsed(render_report.render(md))
            self.assertEqual('# Keep this comment\n', parsed.blocks[0]['text'])

    def test_unclosed_code_cannot_supply_report_title_even_with_override(self):
        md = '```\n# Not a title\n'
        self.assertEqual((None, md), render_report._split_title(md))
        html = render_report.render(md, title='Owner title')
        self.assertIn('<title>Owner title', html)
        self.assertEqual('# Not a title\n', Parsed(html).blocks[0]['text'])

    def test_removing_real_title_does_not_drop_final_code_blank_lines(self):
        html = render_report.render('# Actual title\n\n```\nx\n\n')
        self.assertEqual('x\n\n', Parsed(html).blocks[0]['text'])

    def test_fence_boundaries_share_strict_rules_with_title_extraction(self):
        for invalid in ('``', '~~', '    ```sh', '\t```sh', '```bad`info'):
            self.assertIsNone(opening_fence(invalid))
        fence = opening_fence('```sh')
        for invalid in ('~~~', '``', '```sh', '    ```'):
            self.assertFalse(closes_fence(invalid, fence))
        self.assertTrue(closes_fence('   ````\t', fence))
        md = '```bad`info\n# Real title\n'
        self.assertEqual('Real title', render_report._split_title(md)[0])

    def test_outside_lists_tables_and_notes_still_render_normally(self):
        md = '- before\n```\n# code\n```\n\n## After\n\n| A | B |\n|:--|:--|\n| 1 | 2 |\n\n> **note**'
        html = report.md_to_html(md)
        self.assertIn('</ul>\n<pre>', html)
        self.assertIn('<h2>After</h2>', html)
        self.assertIn('<table class="markdown">', html)
        self.assertIn('<blockquote><strong>note</strong></blockquote>', html)

    def test_real_render_cli_preserves_title_code_and_pdf_input(self):
        md = '```sh\n# code comment\nprintf "<tag> & **literal** café 🐳"\n```\n\n# Actual title\n'
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'report.md'
            target = Path(directory) / 'report.html'
            source.write_text(md, encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, render_report.main([str(source), '-o', str(target)]))
            html = target.read_text(encoding='utf-8')
            self.assertIn('<title>Actual title', html)
            self.assertEqual('# code comment\nprintf "<tag> & **literal** café 🐳"\n', Parsed(html).blocks[0]['text'])
            with mock.patch.object(render_report, 'deliver', return_value=0) as deliver:
                self.assertEqual(0, render_report.main([str(source), '--format', 'pdf', '-o', str(Path(directory) / 'report.pdf')]))
            self.assertEqual(html, deliver.call_args.args[2])


if __name__ == '__main__':
    unittest.main()
