"""Sampled leaf-page policy observations survive the crawl's score summary."""

import copy
import json
import sys
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit
import crawl_site as crawl
from lib import indexing, report

BASE = 'https://example.test/'


def named_receipt():
    return indexing.crawler_meta([{'name': 'googlebot', 'content': 'noindex'}])


def site(pages):
    return {'base': BASE, 'pages_scanned': len(pages), 'avg_score': 100,
            'pages': pages, 'recurring': Counter()}


class TestCrawlIndexing(unittest.TestCase):
    def test_crawl_retains_leaf_receipts_without_new_score_penalties(self):
        pages = [report.Report(BASE), report.Report(BASE + 'leaf')]
        pages[1].meta['crawler_meta_robots'] = named_receipt()
        pages[1].meta['http_robots'] = indexing.http_robots(['googlebot: nofollow'], 'response_header_fields')[0]
        with mock.patch.object(crawl.scanner, 'gather_context', return_value={}), \
                mock.patch.object(crawl, 'discover', return_value=[page.url for page in pages]), \
                mock.patch.object(crawl.scanner, 'scan', side_effect=pages):
            data = crawl.crawl(BASE, max_pages=2, concurrency=1)
        self.assertNotIn('crawler_meta_robots', data['pages'][0])
        self.assertEqual(pages[1].meta['crawler_meta_robots'], data['pages'][1]['crawler_meta_robots'])
        self.assertEqual(pages[1].meta['http_robots'], data['pages'][1]['http_robots'])
        self.assertEqual(100, data['avg_score'])
        self.assertFalse(data['recurring'])
        self.assertEqual(named_receipt(), json.loads(crawl.render_json(data))['pages'][1]['crawler_meta_robots'])

    def test_failed_scan_does_not_retain_stale_policy_receipts(self):
        page = report.Report(BASE)
        page.hard_fail = True
        page.meta['crawler_meta_robots'] = named_receipt()
        with mock.patch.object(crawl.scanner, 'gather_context', return_value={}), \
                mock.patch.object(crawl, 'discover', return_value=[BASE]), \
                mock.patch.object(crawl.scanner, 'scan', return_value=page):
            data = crawl.crawl(BASE, max_pages=1, concurrency=1)
        self.assertNotIn('crawler_meta_robots', data['pages'][0])

    def test_leaf_notes_are_visible_and_scoped_not_recurring_failures(self):
        data = site([{'url': BASE + 'leaf', 'score': 100, 'crawler_meta_robots': named_receipt()}])
        text = crawl.render_markdown(data)
        self.assertIn('Sampled-page indexing observations (not scored)', text)
        self.assertIn(BASE + 'leaf', text)
        self.assertIn('googlebot declares noindex', text)
        self.assertIn('not an all-crawler restriction', text)
        self.assertIn('not effective cross-source policy', text)
        self.assertIn('Partial snapshots', text)
        self.assertNotIn('Priority issues', text)
        self.assertIn('- googlebot declares noindex', text)

    def test_header_generic_and_named_declarations_keep_distinct_scope(self):
        receipt = indexing.http_robots(['none', 'googlebot: nofollow'], 'response_header_fields')[0]
        data = site([{'url': BASE, 'score': 85, 'http_robots': receipt}])
        text = crawl.render_markdown(data)
        self.assertIn('Unprefixed HTTP X-Robots-Tag declares nofollow, noindex', text)
        self.assertIn('Named crawler googlebot declares nofollow', text)
        self.assertIn('findings remain in the score/issue rollup', text)
        self.assertEqual(85, data['pages'][0]['score'])

    def test_unknown_legacy_malformed_and_failed_receipts_make_no_claim(self):
        for page in ({}, {'crawler_meta_robots': {'version': 99}},
                     {'http_robots': {'version': True, 'basis': 'response_header_fields', 'notes': ['unsafe claim']}},
                     {'hard_fail': True, 'crawler_meta_robots': named_receipt()}):
            with self.subTest(page=page):
                self.assertNotIn('Sampled-page indexing observations', crawl.render_markdown(site([dict(page, url=BASE, score=100)])))

    def test_display_caps_do_not_drop_json_or_mutate_input(self):
        receipt = indexing.http_robots(['googlebot: noindex'], 'response_header_fields')[0]
        receipt['notes'] += ['Observation %d' % number for number in range(30)]
        data = site([{'url': BASE + str(number), 'score': 100, 'http_robots': copy.deepcopy(receipt)} for number in range(12)])
        before = copy.deepcopy(data)
        text = crawl.render_markdown(data)
        self.assertEqual(10, text.count('### '))
        self.assertIn('2 more sampled page(s)', text)
        self.assertIn('more notes for this page', text)
        self.assertEqual(before, data)
        payload = json.loads(crawl.render_json(data))
        self.assertEqual(12, len(payload['pages']))
        self.assertEqual(receipt, payload['pages'][-1]['http_robots'])

    def test_new_section_keeps_hostile_url_and_receipt_text_literal(self):
        hostile = '` [click](https://evil.test/) <script>window.policyProbe=true</script>\n### forged'
        receipt = {'version': 1, 'basis': 'merged_or_unknown', 'notes': [hostile]}
        data = site([{'url': BASE + hostile, 'score': 100, 'http_robots': receipt}])
        section = crawl.render_markdown(data).split('## Sampled-page indexing observations', 1)[1]
        rendered = report.md_to_html(section)
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('<a ', rendered)
        self.assertNotIn('<h3>forged', rendered)
        self.assertIn('&lt;script&gt;', rendered)

    def test_comprehensive_audit_inherits_leaf_observation_without_homepage_meta(self):
        data = {'site': BASE, 'page': report.Report(BASE),
                'site_result': site([{'url': BASE + 'leaf', 'score': 100, 'crawler_meta_robots': named_receipt()}]),
                'sitemap': {'start': BASE, 'seeds': []}}
        for renderer in (audit.render_markdown, audit.render_html):
            text = renderer(data)
            self.assertIn('Sampled-page indexing observations (not scored)', text)
            self.assertIn('googlebot declares noindex', text)


if __name__ == '__main__':
    unittest.main()
