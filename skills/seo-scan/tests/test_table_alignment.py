"""Column alignment markers affect presentation, never cell data or attributes."""

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
        self.rows, self.cell = [], None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.rows.append([])
        elif tag in ('th', 'td'):
            self.cell = {'tag': tag, 'attrs': dict(attrs), 'text': ''}
            self.rows[-1].append(self.cell)

    def handle_endtag(self, tag):
        if self.cell and tag == self.cell['tag']:
            self.cell = None

    def handle_data(self, data):
        if self.cell:
            self.cell['text'] += data


class TestTableAlignment(unittest.TestCase):
    def test_markers_align_header_and_each_body_row(self):
        md = '| Left | Center | Right | Default |\n|:--|:--:|--:|--|\n| a | b | 12 | d |\n| e | f | 34 | h |'
        parsed = Parsed(report.md_to_html(md))
        for row in parsed.rows:
            self.assertEqual(['', 'align-center', 'align-right', ''],
                             [cell['attrs'].get('class', '') for cell in row])
        self.assertTrue(all(cell['attrs']['scope'] == 'col' for cell in parsed.rows[0]))
        self.assertEqual(['a', 'b', '12', 'd'], [cell['text'] for cell in parsed.rows[1]])

    def test_repository_short_separator_forms_remain_supported(self):
        for length in (1, 2, 3, 12):
            md = '| A | B |\n|:' + '-' * length + ':|' + '-' * length + ':|\n| 1 | 2 |'
            with self.subTest(length=length):
                parsed = Parsed(report.md_to_html(md))
                self.assertEqual(['align-center', 'align-right'],
                                 [cell['attrs'].get('class') for cell in parsed.rows[1]])

    def test_missing_and_extra_separators_do_not_invent_cell_values(self):
        md = '| A | B | C |\n|--:|\n| 1 | 2 | 3 | 4 |\n| only |'
        rows = Parsed(report.md_to_html(md)).rows
        self.assertEqual([3, 4, 1], [len(row) for row in rows])
        self.assertEqual(['align-right', '', '', ''], [cell['attrs'].get('class', '') for cell in rows[1]])
        self.assertEqual(['1', '2', '3', '4'], [cell['text'] for cell in rows[1]])

    def test_malformed_marker_cells_do_not_inject_alignment(self):
        parsed = Parsed(report.md_to_html('| A | B | C |\n|::-|:--:--|: - :|\n| a | b | c |'))
        self.assertEqual([{}, {}, {}], [cell['attrs'] for cell in parsed.rows[1]])

    def test_alignment_does_not_leak_to_later_tables_or_fenced_text(self):
        md = '| A |\n|--:|\n| 1 |\n\n| B |\n|--|\n| 2 |\n\n```\n|:--:|\n```'
        html = report.md_to_html(md)
        rows = Parsed(html).rows
        self.assertEqual('align-right', rows[1][0]['attrs']['class'])
        self.assertEqual({}, rows[3][0]['attrs'])
        self.assertIn('<pre><code>|:--:|\n</code></pre>', html)

    def test_literal_and_empty_cells_keep_data_and_safe_attributes(self):
        md = '| A | B | C |\n|:--:|--:|:--|\n|| `<script>**x**\\|y</script>` | [link](https://example.test/_x_) |'
        html = report.md_to_html(md)
        row = Parsed(html).rows[1]
        self.assertEqual(['', '<script>**x**|y</script>', 'link'], [cell['text'] for cell in row])
        self.assertEqual([{'class': 'align-center'}, {'class': 'align-right'}, {}], [cell['attrs'] for cell in row])
        self.assertNotIn('<script>', html)
        self.assertIn('href="https://example.test/_x_"', html)

    def test_real_cli_file_stdin_and_pdf_input_keep_alignment(self):
        md = '# Report\n\n| Label | Value |\n|:--|--:|\n| café | 65 |'
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'report.md'
            target = Path(directory) / 'report.html'
            source.write_text(md, encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, render_report.main([str(source), '-o', str(target)]))
            html = target.read_text(encoding='utf-8')
            self.assertEqual({'class': 'align-right'}, Parsed(html).rows[1][1]['attrs'])
            with mock.patch('sys.stdin', io.StringIO(md)), \
                    mock.patch.object(render_report, 'deliver', return_value=0) as deliver:
                self.assertEqual(0, render_report.main(['-', '--format', 'pdf', '-o', str(Path(directory) / 'report.pdf')]))
            self.assertEqual(html, deliver.call_args.args[2])


if __name__ == '__main__':
    unittest.main()
