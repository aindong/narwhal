"""Known named-crawler metadata is observed without becoming a generic block."""

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_technical
import scan
from lib import htmlx, http
from lib.report import Report

URL = 'https://example.test/'


def report_for(markup, parser=htmlx._parse_stdlib):
    doc = parser('<html><head>' + markup + '</head><body><h1>Example</h1></body></html>', URL)
    rep = Report(URL)
    audit_technical._robots_directives(doc, rep)
    return rep


class TestCrawlerMeta(unittest.TestCase):
    def test_googlebot_none_is_visible_but_not_generic_or_scored(self):
        rep = report_for('<meta name="GoogleBot" content="NONE">')
        self.assertEqual(['technical.page.is.indexable'], [f.rule_id for f in rep.findings])
        self.assertEqual(100, rep.score())
        receipt = rep.meta['crawler_meta_robots']
        self.assertEqual(1, receipt['version'])
        self.assertEqual('active_document_meta', receipt['basis'])
        self.assertEqual(['googlebot', 'googlebot-news'], receipt['checked_agents'])
        self.assertEqual([{'agent': 'googlebot', 'directives': ['nofollow', 'noindex'], 'tag_positions': [1]}], receipt['observations'])
        self.assertTrue(receipt['source'].startswith('https://developers.google.com/'))

    def test_news_scope_is_distinct_and_multiple_tags_accumulate(self):
        markup = '<meta name="googlebot" content="index"><meta name="googlebot-news" content="noindex"><meta name="googlebot" content="nofollow"><meta name="googlebot-news" content="nofollow">'
        items = report_for(markup).meta['crawler_meta_robots']['observations']
        self.assertEqual([{'agent': 'googlebot', 'directives': ['nofollow'], 'tag_positions': [3]},
                          {'agent': 'googlebot-news', 'directives': ['nofollow', 'noindex'], 'tag_positions': [2, 4]}], items)

    def test_parameters_lookalikes_and_allowing_tags_do_not_invent_restrictions(self):
        for content in ('all', 'index, follow', 'max-image-preview: none', 'x-noindex, x-nofollow'):
            with self.subTest(content=content):
                rep = report_for('<meta name="googlebot" content="' + content + '">')
                self.assertNotIn('crawler_meta_robots', rep.meta)
        rep = report_for('<meta name="googlebot" content="noindex max-image-preview:none">')
        self.assertEqual(['noindex'], rep.meta['crawler_meta_robots']['observations'][0]['directives'])

    def test_unrecognized_names_are_not_assumed_to_be_crawler_policies(self):
        for name in ('author', 'description', 'bingbot', 'googlebot-image', 'somebot', 'robots-extra'):
            with self.subTest(name=name):
                self.assertNotIn('crawler_meta_robots', report_for('<meta name="' + name + '" content="none">').meta)

    def test_generic_rules_keep_existing_severity_and_identity(self):
        rep = report_for('<meta name="robots" content="nofollow"><meta name="googlebot" content="noindex">')
        self.assertEqual([('technical.page.level.nofollow', 'medium'), ('technical.page.is.indexable', 'good')],
                         [(f.rule_id, f.severity) for f in rep.findings])
        self.assertEqual(97, rep.score())
        self.assertEqual(['noindex'], rep.meta['crawler_meta_robots']['observations'][0]['directives'])

    def test_later_allowing_tag_does_not_erase_observed_restriction(self):
        rep = report_for('<meta name="googlebot" content="noindex"><meta name="googlebot" content="all, index, follow">')
        self.assertEqual([{'agent': 'googlebot', 'directives': ['noindex'], 'tag_positions': [1]}],
                         rep.meta['crawler_meta_robots']['observations'])

    def test_witnesses_are_bounded_and_late_restriction_survives(self):
        rep = report_for('<meta name="googlebot" content="nofollow">' * 1500 + '<meta name="googlebot" content="noindex">')
        observation = rep.meta['crawler_meta_robots']['observations'][0]
        self.assertEqual([1, 1501], observation['tag_positions'])
        self.assertEqual(['nofollow', 'noindex'], observation['directives'])

    def test_inert_nested_template_meta_is_not_a_policy_observation(self):
        rep = report_for('<template><template><meta name="googlebot" content="none"></template></template>')
        self.assertNotIn('crawler_meta_robots', rep.meta)

    @unittest.skipUnless(importlib.util.find_spec('bs4'), 'optional BeautifulSoup backend absent')
    def test_optional_and_stdlib_parsers_agree(self):
        for markup in ('<meta name="googlebot" content="none">',
                       '<template><meta name="googlebot-news" content="noindex"></template>',
                       '<meta name="googlebot-news" content="noindex max-image-preview:none">'):
            with self.subTest(markup=markup):
                self.assertEqual(report_for(markup).meta, report_for(markup, htmlx._parse_bs4).meta)

    def test_observation_reaches_json_markdown_and_html_without_score_change(self):
        rep = report_for('<meta name="googlebot-news" content="noindex">')
        self.assertIn('crawler_meta_robots', json.loads(rep.to_json())['meta'])
        for output in (rep.to_markdown(), rep.to_html()):
            self.assertIn('Crawler-specific meta observations (not scored)', output)
            self.assertIn('googlebot-news', output)
            self.assertIn('not proof', output)
        self.assertEqual(100, rep.score())

    def test_unknown_or_malformed_receipts_do_not_render_policy_claims(self):
        rep = Report(URL)
        for receipt in ({'version': 99, 'basis': 'active_document_meta', 'observations': []},
                        {'version': True, 'basis': 'active_document_meta', 'observations': []},
                        {'version': 1, 'basis': 'unknown', 'observations': []},
                        {'version': 1, 'basis': 'active_document_meta', 'observations': [{'agent': '<script>', 'directives': ['noindex'], 'tag_positions': [1]}]}):
            with self.subTest(receipt=receipt):
                rep.meta['crawler_meta_robots'] = receipt
                self.assertNotIn('Crawler-specific meta observations', rep.to_html())
                self.assertNotIn('<script>', rep.to_html())

    def test_selected_technical_group_owns_the_observation(self):
        body = '<html><head><title>Example article title</title><meta name="googlebot" content="none"></head><body><h1>Example</h1></body></html>'
        resp = http.Response(URL, URL, 200, {'content-type': 'text/html'}, body, 0)
        for groups, expected in ((['technical'], True), (['content'], False)):
            with mock.patch.object(http, 'fetch', return_value=resp):
                rep = scan.scan(URL, only=groups, ctx={}, check_images=False)
            self.assertEqual(expected, 'crawler_meta_robots' in rep.meta)


if __name__ == '__main__':
    unittest.main()
