"""Absence of observations is not proof of successful crawl measurements."""

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
from lib import http
from lib.report import Report

BASE = 'https://example.test/'


def result():
    return {'base': BASE, 'pages_scanned': 1, 'avg_score': 100,
            'pages': [], 'recurring': Counter()}


def checked(responses, cap=200):
    targets = [{'url': BASE + str(i), 'internal': True} for i in range(len(responses))]
    by_url = {target['url']: response for target, response in zip(targets, responses)}
    with mock.patch.object(http, 'head', side_effect=lambda url, **kw: by_url[url]) as head:
        data = crawl.check_broken_links({BASE: targets}, allow_private=False,
                                       timeout=1, concurrency=1, max_links=cap)
    return data, head


class TestCrawlMeasurementCoverage(unittest.TestCase):
    def test_native_crawl_collects_graph_without_default_resource_probes(self):
        child = BASE + 'child'
        bodies = {BASE: '<html><title>Guide</title><h1>Guide</h1>'
                  '<a href="/child">Child</a><a href="https://outside.test/guide">External</a>'
                  '<img src="/hero.png" width="900" height="500" alt="Guide"></html>',
                  child: '<html><title>Child</title><h1>Child</h1><p>Reader guidance.</p></html>'}
        def fetch(url, **kwargs):
            return http.Response(url, url, 200, {'content-type': 'text/html'}, bodies[url], 1)
        for options in ({}, {'check_links': True, 'max_links': 1}, {'check_links': True, 'max_links': 0}):
            with self.subTest(options=options), \
                    mock.patch.object(crawl.scanner, 'gather_context', return_value={}), \
                    mock.patch.object(crawl, 'discover', return_value=[BASE, child]), \
                    mock.patch.object(http, 'fetch', side_effect=fetch) as page_fetch, \
                    mock.patch.object(http, 'head', return_value=(200, None)) as link_head, \
                    mock.patch.object(http, 'head_info', return_value=(200, {
                        'content-type': 'image/png', 'content-length': '40960'}, None)) as image_head, \
                    mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
                data = crawl.crawl(BASE, max_pages=2, concurrency=1, detect_dupes=False, **options)
                self.assertEqual(2, page_fetch.call_count)
                self.assertEqual({BASE, child}, {call.args[0] for call in page_fetch.call_args_list})
                self.assertEqual(1, data['graph']['internal_edges'])
                self.assertEqual(1, data['graph']['max_depth'])
                self.assertEqual([], data['graph']['unreachable_from_start'])
                image_head.assert_not_called()
                self.assertTrue(all(page['scan_settings']['image_checks'] is False for page in data['pages']))
                self.assertTrue(all(page['scan_settings']['render_requested'] is False for page in data['pages']))
                if options:
                    self.assertEqual(options['max_links'], link_head.call_count)
                    self.assertEqual(options['max_links'], data['links']['checked'])
                    self.assertEqual(2, data['links']['unique_links'])
                    self.assertEqual(2 - options['max_links'], data['links']['skipped_over_cap'])
                else:
                    link_head.assert_not_called()
                    self.assertNotIn('links', data)

    def test_zero_targets_are_not_a_green_pass(self):
        data = result()
        data['links'], head = checked([])
        text = crawl.render_markdown(data)
        self.assertIn('No HTTP link targets were checked', text)
        self.assertNotIn('🟢', text)
        head.assert_not_called()

    def test_gated_and_other_nonbroken_responses_remain_unverified(self):
        data = result()
        data['links'], _ = checked([(403, None), (429, None), (301, None), (200, 'incomplete')])
        self.assertEqual([], data['links']['broken'])
        self.assertEqual(4, data['links']['coverage']['unverified'])
        text = crawl.render_markdown(data)
        self.assertIn('4 response(s) leave reachability unverified', text)
        self.assertNotIn('🟢', text)

    def test_mixed_status_counts_preserve_actual_broken_links(self):
        data, _ = checked([(200, None), (204, None), (403, None), (404, None), (0, 'timeout')])
        self.assertEqual({'basis': 'head_responses', 'scope': 'checked_targets',
                          'successful_2xx': 2, 'unverified': 2, 'broken': 1,
                          'request_failures': 1}, data['coverage'])
        self.assertEqual([404, 0], [entry['status'] for entry in data['broken']])

    def test_no_http_response_is_unverified_without_losing_unreachable_entries(self):
        data = result()
        data['links'], _ = checked([(0, 'timeout')])
        self.assertEqual(1, len(data['links']['broken']))
        self.assertEqual(0, data['links']['coverage']['broken'])
        self.assertEqual(1, data['links']['coverage']['unverified'])
        self.assertEqual(1, data['links']['coverage']['request_failures'])
        self.assertIn('0 observed / 1 checked (1 unverified; 1 no HTTP response)',
                      crawl.link_summary(data['links']))
        text = crawl.render_markdown(data)
        self.assertIn('produced no HTTP response', text)
        self.assertIn('timeout', text)

    def test_positive_checks_are_scoped_and_caps_remain_visible(self):
        data = result()
        data['links'], head = checked([(200, None), (200, None)], cap=1)
        text = crawl.render_markdown(data)
        self.assertIn('among HTTP-checked targets', text)
        self.assertIn('1 over cap', text)
        self.assertIn('1 successful 2xx', text)
        self.assertNotIn('No broken links found. 🟢', text)
        self.assertEqual(1, head.call_count)

    def test_legacy_and_inconsistent_response_receipts_are_not_inferred(self):
        data = result()
        info, _ = checked([(200, None)])
        valid = info.get('coverage', {})
        for receipt in (None, {**valid, 'basis': 'future'}, {**valid, 'successful_2xx': True},
                        {**valid, 'unverified': 1}, {**valid, 'broken': 1},
                        {**valid, 'request_failures': True}, {**valid, 'request_failures': 1}):
            with self.subTest(receipt=receipt):
                data['links'] = {**info, 'coverage': receipt}
                text = crawl.render_markdown(data)
                self.assertIn('response coverage was not recorded', text)
                self.assertNotIn('🟢', text)

    def test_crawl_records_actual_duplicate_inputs_and_omits_disabled_receipts(self):
        for fingerprints in ([], [17], [17, 18]):
            reports = []
            for i, fingerprint in enumerate(fingerprints or [None]):
                page = Report(BASE + str(i))
                if fingerprint is not None:
                    page.meta['fingerprint'] = fingerprint
                reports.append(page)
            with self.subTest(fingerprints=fingerprints), \
                    mock.patch.object(crawl.scanner, 'gather_context', return_value={}), \
                    mock.patch.object(crawl, 'discover', return_value=[page.url for page in reports]), \
                    mock.patch.object(crawl.scanner, 'scan', side_effect=reports):
                data = crawl.crawl(BASE, max_pages=len(reports), concurrency=1)
            self.assertEqual(len(fingerprints), data['duplicate_coverage']['eligible_pages'])
            self.assertEqual(len(reports), data['duplicate_coverage']['scanned_pages'])
            if len(fingerprints) < 2:
                self.assertIn('fewer than two eligible fingerprints', crawl.render_markdown(data))
                self.assertNotIn('No near-duplicate pages detected. 🟢', crawl.render_markdown(data))
        with mock.patch.object(crawl.scanner, 'gather_context', return_value={}), \
                mock.patch.object(crawl, 'discover', return_value=[]):
            data = crawl.crawl(BASE, detect_dupes=False)
        self.assertNotIn('duplicate_coverage', data)
        self.assertNotIn('duplicates', data)

    def test_duplicate_zero_is_scoped_to_measured_pairs_not_whole_site(self):
        data = result()
        data.update(pages_scanned=2, duplicates=[], duplicate_coverage={
            'basis': 'simhash_fingerprints', 'scope': 'scanned_pages',
            'eligible_pages': 2, 'scanned_pages': 2})
        text = crawl.render_markdown(data)
        self.assertIn('among 2 eligible page fingerprints', text)
        self.assertIn('sampled pages only', text)
        self.assertNotIn('No near-duplicate pages detected. 🟢', text)

    def test_known_failed_and_partial_pages_do_not_establish_duplicate_coverage(self):
        reports = [Report(BASE + str(i)) for i in range(3)]
        for page in reports:
            page.meta['fingerprint'] = 17
        reports[1].hard_fail = True
        reports[2].meta['coverage'] = {'response_truncated': True}
        with mock.patch.object(crawl.scanner, 'gather_context', return_value={}), \
                mock.patch.object(crawl, 'discover', return_value=[page.url for page in reports]), \
                mock.patch.object(crawl.scanner, 'scan', side_effect=reports):
            data = crawl.crawl(BASE, max_pages=3, concurrency=1)
        self.assertEqual(1, data['duplicate_coverage']['eligible_pages'])
        self.assertEqual([], data['duplicates'])
        self.assertIn('insufficient data', crawl.render_markdown(data))

    def test_duplicate_legacy_unknown_receipts_do_not_infer_from_pages_scanned(self):
        data = result()
        data.update(pages_scanned=20, duplicates=[])
        for receipt in (None, {}, {'basis': 'future'},
                        {'basis': 'simhash_fingerprints', 'scope': 'scanned_pages',
                         'eligible_pages': True, 'scanned_pages': 20}):
            data['duplicate_coverage'] = receipt
            text = crawl.render_markdown(data)
            self.assertIn('Duplicate-comparison coverage was not recorded', text)
            self.assertNotIn('🟢', text)

    def test_audit_summary_distinguishes_disabled_and_insufficient_measurements(self):
        data = result()
        report = {'site': BASE, 'page': Report(BASE), 'site_result': data,
                  'sitemap': {'start': BASE, 'seeds': []}}
        for renderer in (audit.render_markdown, audit.render_html):
            text = renderer(report)
            self.assertIn('not run', text)
        data['links'], _ = checked([])
        data.update(duplicates=[], duplicate_coverage={
            'basis': 'simhash_fingerprints', 'scope': 'scanned_pages',
            'eligible_pages': 1, 'scanned_pages': 1})
        for renderer in (audit.render_markdown, audit.render_html):
            text = renderer(report)
            self.assertIn('0 checked', text)
            self.assertIn('insufficient data', text)

    def test_rendering_is_read_only_and_json_retains_evidence(self):
        data = result()
        data['links'], _ = checked([(403, None)])
        before = copy.deepcopy(data)
        crawl.render_markdown(data)
        self.assertEqual(before, data)
        self.assertEqual(1, json.loads(crawl.render_json(data))['links']['coverage']['unverified'])


if __name__ == '__main__':
    unittest.main()
