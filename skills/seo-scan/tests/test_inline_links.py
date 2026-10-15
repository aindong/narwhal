"""Link destinations are data, not input to emphasis or code rendering."""

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
        self.links, self.tags = [], []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag == 'a':
            self.links.append(dict(attrs))


class TestInlineLinks(unittest.TestCase):
    def test_underscores_and_asterisks_in_destinations_stay_literal(self):
        for url in ('https://example.test/_draft_/page',
                    'http://example.test/**literal**',
                    'https://example.test/?q=_one_&next=**two**#_three_'):
            with self.subTest(url=url):
                parsed = Parsed(report._inline_md('[Readable label](' + url + ')'))
                self.assertEqual([{'href': url}], parsed.links)
                self.assertEqual([('a', {'href': url})], parsed.tags)

    def test_label_and_surrounding_emphasis_still_work(self):
        html = report._inline_md('**before [**bold** _italic_](https://example.test/_x_) after**')
        self.assertEqual('<strong>before <a href="https://example.test/_x_">'
                         '<strong>bold</strong> <em>italic</em></a> after</strong>', html)

    def test_code_in_label_stays_literal_but_not_in_destination(self):
        html = report._inline_md('[`**literal**`](https://example.test/_x_) '
                                 '[bad](https://example.test/`code`)')
        self.assertIn('<a href="https://example.test/_x_"><code>**literal**</code></a>', html)
        self.assertEqual([{'href': 'https://example.test/_x_'}], Parsed(html).links)

    def test_quotes_ampersands_entities_and_unicode_round_trip(self):
        url = 'https://example.test/café?x="quoted"&y=\'single\'&entity=&amp;#🐳'
        html = report._inline_md('[label](' + url + ')')
        self.assertEqual([{'href': url}], Parsed(html).links)
        self.assertIn('&quot;quoted&quot;', html)
        self.assertIn('&amp;entity=&amp;amp;', html)

    def test_html_like_data_cannot_add_attributes_or_elements(self):
        url = 'https://example.test/?q="onmouseover=bad"&html=<img>'
        label = '<script>window.probe=true</script>'
        parsed = Parsed(report._inline_md('[' + label + '](' + url + ')'))
        self.assertEqual([('a', {'href': url})], parsed.tags)

    def test_placeholder_lookalikes_are_never_substituted(self):
        html = report._inline_md('<narwhal-link-0> &lt;narwhal-link-1&gt; '
                                 '[<narwhal-code-0>](https://example.test/<narwhal-link-0>) '
                                 '`<narwhal-link-0>`')
        self.assertIn('&lt;narwhal-link-0&gt; &amp;lt;narwhal-link-1&amp;gt;', html)
        self.assertIn('>&lt;narwhal-code-0&gt;</a>', html)
        self.assertIn('<code>&lt;narwhal-link-0&gt;</code>', html)
        self.assertEqual([{'href': 'https://example.test/<narwhal-link-0>'}], Parsed(html).links)

    def test_unsupported_schemes_and_incomplete_links_stay_non_links(self):
        for value in ('[x](javascript:alert)', '[x](data:text/html,bad)',
                      '[x](file:///tmp/example)', '[x](//example.test)',
                      '[x](https://example.test/has space)', '[x](https://example.test'):
            with self.subTest(value=value):
                self.assertEqual([], Parsed(report._inline_md(value)).links)

    def test_plain_code_and_fenced_links_are_not_activated(self):
        for md in ('`[label](https://example.test/_x_)`',
                   '```\n[label](https://example.test/_x_)\n```'):
            self.assertEqual([], Parsed(report.md_to_html(md)).links)

    def test_multiple_links_retain_independent_destinations(self):
        urls = ['https://example.test/_%d_/**x**' % index for index in range(150)]
        html = report._inline_md(' '.join('[**label**](' + url + ')' for url in urls))
        self.assertEqual([{'href': url} for url in urls], Parsed(html).links)
        self.assertEqual(150, html.count('<strong>label</strong>'))

    def test_headings_lists_tables_and_quotes_preserve_href(self):
        url = 'https://example.test/_draft_/'
        link = '[**label**](' + url + ')'
        md = '## ' + link + '\n\n- ' + link + '\n\n> ' + link + '\n\n| Link |\n| --- |\n| ' + link + ' |'
        self.assertEqual([{'href': url}] * 4, Parsed(report.md_to_html(md)).links)

    def test_real_cli_file_stdin_and_pdf_input_keep_destination(self):
        url = 'https://example.test/_draft_/?q=**café**&next=🐳'
        md = '# Report\n\n[**label**](' + url + ')'
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'report.md'
            target = Path(directory) / 'report.html'
            source.write_text(md, encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, render_report.main([str(source), '-o', str(target)]))
            html = target.read_text(encoding='utf-8')
            self.assertIn({'href': url}, Parsed(html).links)
            self.assertIn('<strong>label</strong>', html)
            with mock.patch('sys.stdin', io.StringIO(md)), \
                    mock.patch.object(render_report, 'deliver', return_value=0) as deliver:
                self.assertEqual(0, render_report.main(['-', '--format', 'pdf', '-o', str(Path(directory) / 'report.pdf')]))
            self.assertEqual(html, deliver.call_args.args[2])


if __name__ == '__main__':
    unittest.main()
