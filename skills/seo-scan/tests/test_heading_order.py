"""Heading sequences must describe document order, not grouped level buckets."""

from importlib.util import find_spec
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_technical
import brief
import scan
from lib import htmlx, http
from lib.report import Report

URL = 'https://example.test/guide'
SKIP = 'technical.heading.levels.skip.a.level'
MIXED = '<h1>Guide</h1><h2>First</h2><h4>Skipped</h4><h2>Second</h2><h3>Nested</h3>'
EXPECTED = [(1, 'Guide'), (2, 'First'), (4, 'Skipped'), (2, 'Second'), (3, 'Nested')]
TOPICS = '<h1>Guide</h1><h2>Alpha methods</h2><h3>Beta details</h3><h2>Gamma methods</h2><h3>Delta details</h3>'


def skip_details(doc):
    report = Report(URL)
    audit_technical._headings(doc, report)
    return [f.detail for f in report.findings if f.rule_id == SKIP]


class TestStdlibHeadingSequence(unittest.TestCase):
    def test_fallback_keeps_nonmonotone_source_order(self):
        doc = htmlx._parse_stdlib(MIXED, URL)
        self.assertEqual(EXPECTED, doc.headings)
        self.assertEqual(['An H2 is followed by an H4.'], skip_details(doc))

    def test_top_level_parse_without_optional_builder_keeps_the_same_order(self):
        with mock.patch.object(htmlx, '_parse_bs4', side_effect=ImportError), \
                mock.patch.object(htmlx, '_main_content', return_value=''):
            self.assertEqual(EXPECTED, htmlx.parse(MIXED, URL).headings)

    def test_brief_subtopics_follow_source_order_across_sibling_sections(self):
        doc = htmlx._parse_stdlib(TOPICS, URL)
        gaps = brief.subtopic_gaps(None, [{'url': URL, 'headings': doc.headings, 'text': ''}])
        self.assertEqual(['Alpha methods', 'Beta details', 'Gamma methods', 'Delta details'],
                         [gap['heading'] for gap in gaps])


@unittest.skipUnless(find_spec('bs4'), 'Optional BeautifulSoup parser not installed')
class TestBeautifulSoupHeadingSequence(unittest.TestCase):
    def test_optional_builder_does_not_sort_headings_by_level(self):
        self.assertEqual(EXPECTED, htmlx._parse_bs4(MIXED, URL).headings)

    def test_nonmonotone_outline_has_the_same_actual_skip_pair(self):
        for source, expected in ((MIXED, ['An H2 is followed by an H4.']),
                                 ('<h4>Lead</h4><h2>Next</h2>', []),
                                 ('<h1>Guide</h1><h3>First</h3><h2>Next</h2><h4>Later</h4>',
                                  ['An H1 is followed by an H3.'])):
            with self.subTest(source=source):
                self.assertEqual(expected, skip_details(htmlx._parse_stdlib(source, URL)))
                self.assertEqual(expected, skip_details(htmlx._parse_bs4(source, URL)))

    def test_html_parser_builder_fallback_preserves_heading_order_too(self):
        from bs4 import BeautifulSoup, FeatureNotFound
        soup = BeautifulSoup(MIXED, 'html.parser')
        with mock.patch('bs4.BeautifulSoup', side_effect=[FeatureNotFound('No lxml'), soup]) as builder:
            doc = htmlx._parse_bs4(MIXED, URL)
        self.assertEqual(['lxml', 'html.parser'], [call.args[1] for call in builder.call_args_list])
        self.assertEqual(EXPECTED, doc.headings)

    def test_inline_unicode_and_inert_templates_keep_existing_text_rules(self):
        markup = ('<template><h6>Inactive</h6></template><h1>Résumé</h1>'
                  '<h2>Première partie</h2><h3><a href="#details">Détails</a></h3>'
                  '<h2>第二部分</h2><h4>Keep <em>level</em></h4>')
        expected = [(1, 'Résumé'), (2, 'Première partie'), (3, 'Détails'), (2, '第二部分'), (4, 'Keep level')]
        for parser in (htmlx._parse_stdlib, htmlx._parse_bs4):
            self.assertEqual(expected, parser(markup, URL).headings)

    def test_scan_uses_document_order_and_preserves_rule_identity(self):
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, MIXED, 1)
        with mock.patch.object(http, 'fetch', return_value=response), \
                mock.patch.object(htmlx, '_main_content', return_value=''), \
                mock.patch('socket.socket', side_effect=AssertionError('No network')):
            report = scan.scan(URL, only=['technical'], ctx={}, check_images=False)
        self.assertEqual(EXPECTED, report._doc.headings)
        finding, = [f for f in report.findings if f.rule_id == SKIP]
        self.assertEqual('low', finding.severity)
        self.assertEqual('An H2 is followed by an H4.', finding.detail)
        self.assertEqual([1, 2, 4, 2, 3], [level for level, _ in report._doc.headings])

    def test_brief_subtopics_are_not_reordered_by_the_optional_parser(self):
        doc = htmlx._parse_bs4(TOPICS, URL)
        gaps = brief.subtopic_gaps(None, [{'url': URL, 'headings': doc.headings, 'text': ''}])
        self.assertEqual(['Alpha methods', 'Beta details', 'Gamma methods', 'Delta details'],
                         [gap['heading'] for gap in gaps])


if __name__ == '__main__':
    unittest.main()
