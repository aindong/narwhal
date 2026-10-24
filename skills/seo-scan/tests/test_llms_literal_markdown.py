"""Page metadata remains literal CommonMark text and URLs remain one destination."""
import contextlib
import copy
from html.parser import HTMLParser
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import generate_llms as llms
import mcp_server

URL = 'https://example.test/guide)'
NAME = 'Example [reference](https://unwanted.test/) <img src=x>'
SUMMARY = '# Summary\n\n## Made up\n- [Extra](https://unwanted.test/)'
SECTION = 'Main\n\n## Extra'
TITLE = 'Guide](https://unwanted.test/) [fake `code` *bold* <b>'
DESCRIPTION = 'Read\r\n\r\n## Injected\n<script>window.narwhalProbe=1</script>\n- [Other](https://unwanted.test/)'


def sections(url=URL):
    return [(SECTION, [{'url': url, 'title': TITLE, 'description': DESCRIPTION}])]


class Document(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.headings = []
        self.links = []
        self.heading = None
        self.link = None

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag in ('h1', 'h2'):
            self.headings.append([tag, ''])
            self.heading = self.headings[-1]
        if tag == 'a':
            self.links.append([dict(attrs)['href'], ''])
            self.link = self.links[-1]

    def handle_endtag(self, tag):
        if tag in ('h1', 'h2'):
            self.heading = None
        if tag == 'a':
            self.link = None

    def handle_data(self, text):
        if self.heading is not None:
            self.heading[1] += text
        if self.link is not None:
            self.link[1] += text


class TestLlmsLiteralMarkdown(unittest.TestCase):
    def test_metadata_cannot_add_structural_lines_or_raw_html(self):
        data = sections()
        before = copy.deepcopy(data)
        output = llms.render_llms_txt(NAME, SUMMARY, data)
        self.assertEqual(1, sum(line.startswith('# ') for line in output.splitlines()))
        self.assertEqual(1, sum(line.startswith('## ') for line in output.splitlines()))
        self.assertEqual(1, sum(line.startswith('- [') for line in output.splitlines()))
        self.assertIn(r'\<img', output)
        self.assertIn(r'\<b\>', output)
        self.assertIn(r'Guide\]\(https\://unwanted\.test/\)', output)
        self.assertEqual(before, data)

    def test_summary_leading_markers_and_ascii_controls_are_literal(self):
        expected = {'# Heading': r'\# Heading', '- item': r'\- item', '+ item': r'\+ item',
                    '1. item': r'1\. item', '1) item': r'1\) item', '---': r'\---',
                    '***': r'\*\*\*', 'a\x00b\x1bc\x7fd': 'a b c d'}
        for summary, literal in expected.items():
            with self.subTest(summary=summary):
                output = llms.render_llms_txt('Example', summary, [])
                self.assertIn('> ' + literal + '\n', output)

    def test_destinations_escape_parentheses_entities_and_keep_source_fields(self):
        url = 'https://example.test/a(b)?q=x&amp;y=1#part'
        data = [('Main', [{'url': url, 'title': 'Guide', 'description': ''}])]
        output = llms.render_llms_txt('Example', '', data)
        self.assertIn(r'(https://example.test/a\(b\)?q=x\&amp;y=1#part)', output)
        self.assertEqual(url, data[0][1][0]['url'])
        data[0][1][0]['url'] = 'http://[2001:db8::1]:8080/a(b)'
        self.assertIn(r'(http://[2001:db8::1]:8080/a\(b\))',
                      llms.render_llms_txt('Example', '', data))

    def test_raw_url_whitespace_or_controls_fail_without_echoing_credentials(self):
        for char in (' ', '\n', '\r', '\t', '\x00', '\x7f'):
            url = 'https://fixture-user:FIXTURE_SECRET@example.test/a' + char + 'b'
            with self.subTest(character=repr(char)):
                with self.assertRaises(llms.GenerationError) as error:
                    llms.render_llms_txt('Example', '', sections(url))
                self.assertNotIn('FIXTURE_SECRET', str(error.exception))
                self.assertLess(len(str(error.exception)), 250)

    def test_cli_formatting_failure_keeps_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'llms.txt'
            output.write_bytes(b'curated original')
            data = {'site_name': 'Example', 'description': '', 'sections': sections(URL + '\nextra'), 'pages': 1}
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(llms, 'build', return_value=data), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = llms.main(['https://example.test/', '-o', str(output)])
            self.assertEqual(2, code)
            self.assertEqual('', out.getvalue())
            self.assertNotIn('Traceback', err.getvalue())
            self.assertEqual(b'curated original', output.read_bytes())

    def test_plain_format_and_whitespace_only_fallbacks(self):
        pages = [('Main', [{'url': 'https://example.test/guide', 'title': 'Guide', 'description': 'Read this'}])]
        output = llms.render_llms_txt('Example', 'Useful site', pages)
        self.assertIn('# Example\n\n> Useful site\n', output)
        self.assertIn('- [Guide](https://example.test/guide): Read this\n', output)
        pages[0][1][0].update(title=' \t', description='\r\n')
        output = llms.render_llms_txt(' \t', '\n', pages)
        self.assertIn('# TODO: site name', output)
        self.assertIn('> TODO: one-sentence description of the site.', output)
        self.assertIn('- [Guide](https://example.test/guide)\n', output)

    def test_mcp_renders_the_same_literal_artifact_without_changing_source_data(self):
        data = {'site_name': NAME, 'description': SUMMARY, 'sections': sections(), 'pages': 1}
        original = copy.deepcopy(data)
        with mock.patch.object(llms, 'build', return_value=data):
            output = mcp_server._llms('https://example.test/')
        self.assertEqual(llms.render_llms_txt(NAME, SUMMARY, data['sections']), output)
        self.assertEqual(original, data)

    def test_independent_commonmark_parser_round_trips_metadata_and_hrefs(self):
        try:
            from markdown_it import MarkdownIt
        except ImportError:
            self.skipTest('Optional independent CommonMark verification parser is not installed')
        urls = [URL, 'https://example.test/a(b)?q=x&amp;y=1',
                'https://example.test/a%2Fb?x=A&x=B#part']
        data = [(SECTION, [{'url': url, 'title': TITLE, 'description': DESCRIPTION} for url in urls])]
        document = Document()
        document.feed(MarkdownIt('commonmark').render(llms.render_llms_txt(NAME, SUMMARY, data)))
        self.assertEqual([['h1', NAME], ['h2', 'Main ## Extra']], document.headings)
        self.assertEqual([[url, TITLE] for url in urls], document.links)
        for tag in ('img', 'script', 'b', 'em', 'strong', 'code', 'hr', 'ol'):
            self.assertNotIn(tag, document.tags)


if __name__ == '__main__':
    unittest.main()
