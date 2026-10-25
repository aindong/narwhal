"""Query table cells preserve literal observations without changing JSON."""
import copy
from html.parser import HTMLParser
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import brief
from lib.report import md_to_html
from test_brief_grounding import page, BASE, OWN_HTML


class Table(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.cell = None
        self.tags = []

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.rows.append([])
        if tag == 'td':
            self.rows[-1].append('')
            self.cell = self.rows[-1]
        if self.cell is not None:
            self.tags.append(tag)

    def handle_endtag(self, tag):
        if tag == 'td':
            self.cell = None

    def handle_data(self, text):
        if self.cell is not None:
            self.cell[-1] += text


class TestBriefQueryTable(unittest.TestCase):
    def test_query_cells_keep_literal_punctuation_and_three_columns(self):
        for query in ('widgets | tools', 'widgets\\|tools',
                      'widgets [guide](https://unwanted.test/) `code` *bold* <b>',
                      'widgets\r\n## Extra row\n| other | 1 | 2 |'):
            with self.subTest(query=query):
                gsc = {'found': True, 'capped': False, 'striking': [
                    {'query': query, 'page': BASE, 'position': 9.5, 'impressions': 120}]}
                data = brief.synthesize(page(BASE, OWN_HTML), [], gsc)
                before = copy.deepcopy(data)
                markdown = brief.render_markdown(data)
                section = markdown.split('## Target queries', 1)[1].split('\n## ', 1)[0]
                parsed = Table()
                parsed.feed(md_to_html(section))
                rows = [row for row in parsed.rows if row]
                literal = query.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ')
                self.assertEqual([[literal, '9.5', '120']], rows)
                self.assertEqual(['td', 'td', 'td'], parsed.tags)
                self.assertEqual(before, data)
                self.assertEqual(query, data['gsc']['striking'][0]['query'])


if __name__ == '__main__':
    unittest.main()
