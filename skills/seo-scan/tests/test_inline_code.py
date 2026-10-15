"""Inline code stays literal without disabling surrounding report formatting."""

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
        self.spans, self.tags = [], []
        self.in_code = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag == 'code':
            self.in_code = True
            self.spans.append({'text': '', 'children': []})
        elif self.in_code:
            self.spans[-1]['children'].append(tag)

    def handle_endtag(self, tag):
        if tag == 'code':
            self.in_code = False

    def handle_data(self, data):
        if self.in_code:
            self.spans[-1]['text'] += data


class TestInlineCode(unittest.TestCase):
    def test_markdown_in_code_is_literal(self):
        literal = '**literal** _literal_ [literal](https://example.test)'
        parsed = Parsed(report._inline_md('`' + literal + '`'))
        self.assertEqual([{'text': literal, 'children': []}], parsed.spans)
        self.assertEqual([('code', {})], parsed.tags)

    def test_html_entities_unicode_and_quotes_are_escaped_once(self):
        literal = '<script>window.probe=true</script> &amp; "café 🐳"'
        parsed = Parsed(report._inline_md('`' + literal + '`'))
        self.assertEqual([{'text': literal, 'children': []}], parsed.spans)
        self.assertEqual([('code', {})], parsed.tags)

    def test_equal_length_backtick_runs_and_literal_inner_ticks(self):
        for marker, content in (('``', ' `x` **y** '), ('```', ' ``x`` `y` '),
                                ('`', 'x``y'), ('````', 'x```y')):
            with self.subTest(marker=marker):
                parsed = Parsed(report._inline_md(marker + content + marker))
                self.assertEqual([{'text': content, 'children': []}], parsed.spans)

    def test_unmatched_runs_stay_text_and_do_not_hide_later_spans(self):
        self.assertEqual('``unmatched', report._inline_md('``unmatched'))
        self.assertEqual('``unmatched <code>x</code> tail```',
                         report._inline_md('``unmatched `x` tail```'))

    def test_multiple_spans_preserve_order_spaces_and_tabs(self):
        html = report._inline_md('before `  x\t ` middle `` `y` `` after')
        self.assertEqual('before <code>  x\t </code> middle <code> `y` </code> after', html)

    def test_surrounding_and_cross_span_formatting_still_works(self):
        html = report._inline_md('**bold `**literal**` bold** _italic `x_y` italic_ '
                                 '[`label`](https://example.test)')
        self.assertEqual('<strong>bold <code>**literal**</code> bold</strong> '
                         '<em>italic <code>x_y</code> italic</em> '
                         '<a href="https://example.test"><code>label</code></a>', html)

    def test_reserved_token_lookalikes_cannot_replace_user_text(self):
        html = report._inline_md('<narwhal-code-0> &lt;narwhal-code-1&gt; '
                                 '`<narwhal-code-0>` `second`')
        self.assertEqual('&lt;narwhal-code-0&gt; &amp;lt;narwhal-code-1&amp;gt; '
                         '<code>&lt;narwhal-code-0&gt;</code> <code>second</code>', html)

    def test_code_is_not_substituted_into_link_attributes(self):
        html = report._inline_md('[not a link](https://example.test/`" onload="bad`)')
        parsed = Parsed(html)
        self.assertEqual([('code', {})], parsed.tags)
        self.assertEqual('" onload="bad', parsed.spans[0]['text'])

    def test_headings_lists_quotes_and_table_cells_share_literal_spans(self):
        md = '## `**heading**`\n\n- `_list_`\n\n> `[quote](https://example.test)`\n\n| Code |\n| --- |\n| `**cell**` |'
        parsed = Parsed(report.md_to_html(md))
        self.assertEqual(['**heading**', '_list_', '[quote](https://example.test)', '**cell**'],
                         [span['text'] for span in parsed.spans])
        self.assertTrue(all(not span['children'] for span in parsed.spans))

    def test_many_unmatched_runs_and_many_paired_spans(self):
        # Different unmatched lengths must not repeatedly rescan the suffix.
        unmatched = ' '.join('`' * length for length in range(1, 300))
        self.assertEqual(unmatched, report._inline_md(unmatched))
        parsed = Parsed(report._inline_md('`**literal**` ' * 2000))
        self.assertEqual(2000, len(parsed.spans))
        self.assertTrue(all(span == {'text': '**literal**', 'children': []}
                            for span in parsed.spans))

    def test_real_cli_file_stdin_and_pdf_input_agree(self):
        md = '# Report\n\n`**literal** _literal_ café 🐳`\n\nOutside **bold**.'
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'report.md'
            target = Path(directory) / 'report.html'
            source.write_text(md, encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, render_report.main([str(source), '-o', str(target)]))
            html = target.read_text(encoding='utf-8')
            self.assertEqual('**literal** _literal_ café 🐳', Parsed(html).spans[0]['text'])
            self.assertIn('<strong>bold</strong>', html)
            with mock.patch('sys.stdin', io.StringIO(md)), \
                    mock.patch.object(render_report, 'deliver', return_value=0) as deliver:
                self.assertEqual(0, render_report.main(['-', '--format', 'pdf', '-o', str(Path(directory) / 'report.pdf')]))
            self.assertEqual(html, deliver.call_args.args[2])


if __name__ == '__main__':
    unittest.main()
