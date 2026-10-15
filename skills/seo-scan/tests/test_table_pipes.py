"""Escaped pipes and empty edge cells retain report table structure."""

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
        self.rows, self.active, self.tags = [], None, []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == 'tr':
            self.rows.append([])
        elif tag in ('th', 'td'):
            self.rows[-1].append('')
            self.active = tag

    def handle_endtag(self, tag):
        if tag == self.active:
            self.active = None

    def handle_data(self, data):
        if self.active:
            self.rows[-1][-1] += data


class TestTablePipes(unittest.TestCase):
    def test_escaped_pipes_in_header_and_body_do_not_add_columns(self):
        md = '| Rule \\| scope | Evidence |\n|:--|:--|\n| A \\| B | x |'
        self.assertEqual([['Rule | scope', 'Evidence'], ['A | B', 'x']],
                         Parsed(report.md_to_html(md)).rows)

    def test_escaped_pipe_inside_inline_code_stays_in_one_cell(self):
        md = '| Command | Note |\n|:--|:--|\n| `printf x \\| sed y` | literal |'
        html = report.md_to_html(md)
        self.assertEqual([['Command', 'Note'], ['printf x | sed y', 'literal']], Parsed(html).rows)
        self.assertIn('<code>printf x | sed y</code>', html)

    def test_empty_first_and_last_cells_are_not_outer_delimiters(self):
        md = '|| Middle ||\n|:--|:--|:--|\n|| Value ||'
        self.assertEqual([['', 'Middle', ''], ['', 'Value', '']], Parsed(report.md_to_html(md)).rows)

    def test_escaped_trailing_pipe_is_data_with_or_without_outer_delimiter(self):
        for row in ('| end\\|', '| end\\| |'):
            with self.subTest(row=row):
                self.assertEqual([['Header'], ['end|']],
                                 Parsed(report.md_to_html('| Header |\n|:--|\n' + row)).rows)

    def test_even_backslashes_delimit_odd_backslashes_escape(self):
        slash = chr(92)
        for count in range(1, 9):
            with self.subTest(count=count):
                row = '| x' + slash * count + '|y |'
                expected = ['x' + slash * (count - 1) + '|y'] if count % 2 else ['x' + slash * count, 'y']
                self.assertEqual(expected, Parsed(report.md_to_html('| A |\n|:--|\n' + row)).rows[1])

    def test_other_backslashes_and_table_whitespace_keep_existing_behavior(self):
        md = '| A | B |\n|:--|:--|\n|  C:\\temp\\file  | \\#literal |'
        self.assertEqual([['A', 'B'], ['C:\\temp\\file', '\\#literal']], Parsed(report.md_to_html(md)).rows)

    def test_cell_html_is_still_escaped_and_regular_formatting_works(self):
        md = '| A | B |\n|:--|:--|\n| <script>bad\\|code</script> | **bold** [link](https://example.test/_x_) |'
        parsed = Parsed(report.md_to_html(md))
        self.assertEqual('<script>bad|code</script>', parsed.rows[1][0])
        self.assertNotIn('script', parsed.tags)
        self.assertIn('strong', parsed.tags)
        self.assertIn('a', parsed.tags)

    def test_escaped_pipes_outside_tables_and_in_fences_are_not_changed(self):
        html = report.md_to_html('Outside a\\|b\n\n```\n| a\\|b |\n```')
        self.assertIn('<p>Outside a\\|b</p>', html)
        self.assertIn('<pre><code>| a\\|b |\n</code></pre>', html)

    def test_many_escaped_pipes_do_not_create_extra_columns(self):
        value = 'a\\|b ' * 3000
        parsed = Parsed(report.md_to_html('| A | B |\n|:--|:--|\n| ' + value + '| end |'))
        self.assertEqual([value.replace('\\|', '|').strip(), 'end'], parsed.rows[1])

    def test_real_cli_file_stdin_and_pdf_input_preserve_cells(self):
        md = '# Report\n\n| A \\| B | Note |\n|:--|:--|\n| `café\\|🐳` | **literal** |'
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'report.md'
            target = Path(directory) / 'report.html'
            source.write_text(md, encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, render_report.main([str(source), '-o', str(target)]))
            html = target.read_text(encoding='utf-8')
            self.assertEqual([['A | B', 'Note'], ['café|🐳', 'literal']], Parsed(html).rows)
            with mock.patch('sys.stdin', io.StringIO(md)), \
                    mock.patch.object(render_report, 'deliver', return_value=0) as deliver:
                self.assertEqual(0, render_report.main(['-', '--format', 'pdf', '-o', str(Path(directory) / 'report.pdf')]))
            self.assertEqual(html, deliver.call_args.args[2])


if __name__ == '__main__':
    unittest.main()
