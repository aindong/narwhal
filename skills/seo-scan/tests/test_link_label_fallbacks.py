"""Source link checks recognize documented image-alt and title fallbacks."""

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_technical
from lib import htmlx, http
from lib.report import Report

URL = 'https://example.test/'
HAS_BS4 = importlib.util.find_spec('bs4') is not None


def findings(source, parser=htmlx._parse_stdlib):
    doc = parser(source, URL)
    report = Report(URL)
    response = http.Response(URL, URL, 200, {}, source, 0)
    audit_technical._links(doc, response, report)
    return doc, report


class TestLinkLabelFallbacks(unittest.TestCase):
    def test_image_only_link_with_descriptive_alt_is_not_empty(self):
        doc, report = findings('<a href="/home"><img src="/logo.png" alt="Acme home"></a>')
        self.assertFalse(report.findings)
        self.assertEqual('', doc.links[0].text)
        self.assertEqual('Acme home', doc.links[0].image_alt_text)

    def test_title_is_a_fallback_for_an_otherwise_empty_link(self):
        _, report = findings('<a href="/guide" title="Read the installation guide"></a>')
        self.assertFalse(report.findings)

    def test_generic_image_alt_still_gets_generic_text_advice(self):
        _, report = findings('<a href="/guide"><img alt=" Click here "></a>')
        self.assertEqual(['Generic anchor text'], [f.title for f in report.findings])

    def test_generic_title_fallback_still_gets_generic_text_advice(self):
        _, report = findings('<a href="/guide" title=" Read more "></a>')
        self.assertEqual(['Generic anchor text'], [f.title for f in report.findings])

    def test_blank_missing_and_whitespace_labels_remain_empty(self):
        for label in ('', '<img>', '<img alt="">', '<img alt=" \n ">'):
            with self.subTest(label=label):
                _, report = findings('<a href="/guide" title="  ">' + label + '</a>')
                self.assertEqual(['Links with no anchor text'], [f.title for f in report.findings])
                self.assertEqual('technical.links.with.no.anchor.text', report.findings[0].rule_id)

    def test_title_does_not_override_visible_or_image_link_text(self):
        for source in ('<a href="/guide" title="Installation guide">Click here</a>',
                       '<a href="/guide" title="Installation guide"><img alt="Click here"></a>'):
            with self.subTest(source=source):
                _, report = findings(source)
                self.assertEqual(['Generic anchor text'], [f.title for f in report.findings])

    def test_nested_images_normalize_entities_whitespace_and_multiple_alts(self):
        doc, report = findings('<a href="/home"><picture><img alt="Acme &amp; Co"></picture>'
                               '<span><img alt=" home "></span></a>')
        self.assertFalse(report.findings)
        self.assertEqual('Acme & Co home', doc.links[0].image_alt_text)

    def test_alts_do_not_leak_into_visible_text_headings_or_other_links(self):
        doc, report = findings('<h1><a href="/home"><img alt="Acme home">Welcome</a></h1>'
                               '<img alt="Outside image"><a href="/empty"></a>')
        self.assertEqual('Welcome', doc.text)
        self.assertEqual([(1, 'Welcome')], doc.headings)
        self.assertEqual(['Welcome', ''], [a.text for a in doc.links])
        self.assertEqual(['Acme home', ''], [a.image_alt_text for a in doc.links])
        self.assertEqual(1, len(report.findings))

    def test_template_and_script_examples_do_not_supply_link_labels(self):
        doc, report = findings('<a href="/empty"><template><img alt="Fake home"></template>'
                               '<script>"<img alt=\"Fake guide\">"</script></a>')
        self.assertEqual('', doc.links[0].image_alt_text)
        self.assertEqual(['Links with no anchor text'], [f.title for f in report.findings])

    def test_programmatic_tag_contract_remains_compatible(self):
        doc = htmlx.Doc(URL, links=[htmlx.Tag('a', {'href': '/guide', 'title': 'Guide'})])
        report = Report(URL)
        audit_technical._links(doc, http.Response(URL, URL, 200, {}, '', 0), report)
        self.assertFalse(report.findings)

    def test_image_alt_attribute_check_stays_independent(self):
        doc, report = findings('<a href="/guide" title="Installation guide"><img></a>')
        self.assertFalse(report.findings)
        audit_technical._images(doc, report)
        self.assertEqual(['Images missing alt text'], [f.title for f in report.findings])

    def test_malformed_nested_anchors_do_not_duplicate_image_labels(self):
        source = '<a href="/outer"><a href="/inner"><img alt="Inner guide"></a></a>'
        doc, _ = findings(source)
        self.assertEqual({'/outer': '', '/inner': 'Inner guide'},
                         {a.get('href'): a.image_alt_text for a in doc.links})

    @unittest.skipUnless(HAS_BS4, 'optional BeautifulSoup backend is not installed')
    def test_bs4_stdlib_backend_keeps_nearest_anchor_ownership(self):
        import bs4
        original = bs4.BeautifulSoup
        source = '<a href="/outer"><a href="/inner"><img alt="Inner guide"></a></a>'
        with mock.patch('bs4.BeautifulSoup', side_effect=lambda text, *args: original(text, 'html.parser')):
            doc, _ = findings(source, htmlx._parse_bs4)
        self.assertEqual({'/outer': '', '/inner': 'Inner guide'},
                         {a.get('href'): a.image_alt_text for a in doc.links})

    @unittest.skipUnless(HAS_BS4, 'optional BeautifulSoup backend is not installed')
    def test_parser_backends_agree_on_fallbacks_and_keep_text_separate(self):
        source = ('<h1><a href="/home"><picture><img alt="Acme &amp; Co home"></picture></a></h1>'
                  '<a href="/guide" title="Read more"></a><a href="/blank"><img alt=""></a>'
                  '<a href="/inert"><template><img alt="Fake home"></template></a>')
        stdlib, left = findings(source)
        extras, right = findings(source, htmlx._parse_bs4)
        self.assertEqual([(a.text, a.image_alt_text) for a in stdlib.links],
                         [(a.text, a.image_alt_text) for a in extras.links])
        self.assertEqual(stdlib.text, extras.text)
        self.assertEqual(stdlib.headings, extras.headings)
        self.assertEqual([(f.rule_id, f.detail) for f in left.findings],
                         [(f.rule_id, f.detail) for f in right.findings])


if __name__ == '__main__':
    unittest.main()
