"""Discovery uses complete bounded XML, not marker text or bare loc guesses."""

import gzip
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_technical
import brief
import compare
import crawl_site
import diff_scan
import plan
import scan
import validate_sitemap
from lib import htmlx, http, sitemap as sm
from lib.report import Report, recorded_sitemap_discovery_problem
from lib.sitemap_discovery import Discovery

BASE = 'https://example.test/'
INDEX = BASE + 'sitemap.xml'
CHILD = BASE + 'pages.xml.gz'
PAGE = BASE + 'child?a=1&b=2'
NS = 'http://www.sitemaps.org/schemas/sitemap/0.9'
PREFIXED = '<s:urlset xmlns:s="' + NS + '"><s:url><s:loc>https://example.test/child?a=1&amp;b=2</s:loc></s:url></s:urlset>'
HTML = '<html lang="en"><title>Fixture</title><h1>Source</h1><a href="/fallback">Fallback</a></html>'


def fetcher(bodies):
    def fetch(url, **kwargs):
        body = bodies.get(url)
        if isinstance(body, tuple):
            return body
        return (body if isinstance(body, bytes) else body.encode(), None) if body is not None else (None, 'HTTP 404')
    return fetch


def page(receipt, only='technical'):
    report = Report(BASE, final_url=BASE, fetched_status=200)
    report.meta['scan_scope'] = {'requested': [only], 'completed': [only]}
    report._doc = htmlx.parse(HTML, BASE)
    audit_technical._sitemap({'sitemap_found': False, 'sitemap_discovery': receipt}, report)
    return report


class TestSitemapDiscoveryXML(unittest.TestCase):
    def test_prefixed_namespaces_and_xml_escaping_work_across_consumers(self):
        for body in (PREFIXED, gzip.compress(PREFIXED.encode())):
            with self.subTest(gzip=isinstance(body, bytes)), \
                    mock.patch.object(http, 'fetch_text', return_value=''), \
                    mock.patch.object(http, 'fetch_bytes', side_effect=fetcher({INDEX: body})), \
                    mock.patch.object(http, 'fetch', side_effect=AssertionError('No anchor fallback')):
                context = scan.gather_context(BASE, allow_private=False, timeout=1)
                self.assertTrue(context['sitemap_found'])
                self.assertEqual([INDEX], validate_sitemap.discover(BASE, allow_private=False, timeout=1))
                self.assertEqual([BASE, PAGE], crawl_site.discover(BASE, allow_private=False, timeout=1,
                                                                limit=5, robots_txt=''))

    def test_prefixed_index_reads_gzipped_sibling_and_ignores_extensions(self):
        index = '<s:sitemapindex xmlns:s="' + NS + '"><s:sitemap><s:loc>' + CHILD + '</s:loc></s:sitemap></s:sitemapindex>'
        coverage = {}
        with mock.patch.object(http, 'fetch_bytes', side_effect=fetcher({INDEX: index, CHILD: gzip.compress(PREFIXED.encode())})):
            urls = crawl_site.discover(BASE, allow_private=False, timeout=1, limit=5,
                                       robots_txt='Sitemap: ' + INDEX, coverage=coverage)
        self.assertEqual([BASE, PAGE], urls)
        self.assertEqual(2, coverage['attempted_files'])
        self.assertEqual(2, coverage['verified_files'])

    def test_comment_bait_malformed_prefix_and_unknown_roots_do_not_discover_pages(self):
        cases = ('<html><!-- ' + PREFIXED + ' --></html>', PREFIXED + '<broken>',
                 '<feed><loc>' + BASE + 'hidden</loc></feed>',
                 '<urlset xmlns="urn:foreign"><url><loc>' + BASE + 'hidden</loc></url></urlset>')
        for body in cases:
            coverage = {}
            with self.subTest(body=body[:30]), \
                    mock.patch.object(http, 'fetch_bytes', side_effect=fetcher({INDEX: body})), \
                    mock.patch.object(http, 'fetch', return_value=http.Response(BASE, BASE, 200, {}, HTML, 1)):
                urls = crawl_site.discover(BASE, allow_private=False, timeout=1, limit=5,
                                           robots_txt='', coverage=coverage)
            self.assertEqual([BASE, BASE + 'fallback'], urls)
            self.assertEqual(1, coverage['unverified_files'])

    def test_unknown_discovery_is_not_missing_or_passing_and_does_not_penalize_source(self):
        with mock.patch.object(http, 'fetch_text', return_value=''), \
                mock.patch.object(http, 'fetch_bytes', side_effect=fetcher({INDEX: '<feed>secret-token</feed>'})):
            context = scan.gather_context(BASE, allow_private=False, timeout=1)
        report = page(context['sitemap_discovery'])
        self.assertFalse(report.findings)
        self.assertEqual(100, report.score())
        self.assertIn('Sitemap discovery unverified', report.to_markdown())
        self.assertIn('Sitemap discovery unverified', report.to_html())
        self.assertNotIn('secret-token', report.to_json())
        built = plan.build_plan(json.loads(report.to_json()), str(Path(__file__).parent / 'fixtures/planner/plain_html'))
        action = built['actions'][0]
        self.assertEqual('technical.sitemap.discovery.unverified', action['rule_id'])
        self.assertTrue(action['manual_action'])
        self.assertFalse(action['likely_files'])

    def test_known_absence_retains_checked_location_finding(self):
        with mock.patch.object(http, 'fetch_text', return_value=''), \
                mock.patch.object(http, 'fetch_bytes', return_value=(None, 'HTTP 404')):
            context = scan.gather_context(BASE, allow_private=False, timeout=1)
        report = page(context['sitemap_discovery'])
        self.assertIn('No XML sitemap found', [finding.title for finding in report.findings])
        self.assertIsNone(recorded_sitemap_discovery_problem(report.meta, for_score=True))

    def test_context_deduplicates_declared_and_common_candidates(self):
        with mock.patch.object(http, 'fetch_text', return_value='Sitemap: ' + INDEX), \
                mock.patch.object(http, 'fetch_bytes', side_effect=fetcher({INDEX: PREFIXED})) as fetch:
            context = scan.gather_context(BASE, allow_private=False, timeout=1)
        self.assertEqual(1, fetch.call_count)
        self.assertEqual(1, context['sitemap_discovery']['attempted_files'])

    def test_component_attempt_budget_does_not_turn_unexamined_candidates_into_absence(self):
        discovery = Discovery('context_candidates', max_files=2)
        with mock.patch.object(http, 'fetch_bytes', return_value=(None, 'HTTP 404')) as fetch:
            for i in range(4):
                discovery.read(BASE + str(i), allow_private=False, timeout=1)
        self.assertEqual(2, fetch.call_count)
        self.assertEqual(['file_attempt_budget'], discovery.receipt()['limits'])
        report = page(discovery.receipt())
        self.assertFalse(report.findings)
        self.assertTrue(recorded_sitemap_discovery_problem(report.meta, for_score=True))

    def test_unsupported_candidate_does_not_hide_later_valid_common_path(self):
        with mock.patch.object(http, 'fetch_text', return_value=''), \
                mock.patch.object(http, 'fetch_bytes', side_effect=fetcher({INDEX: '<feed/>', BASE + 'sitemap_index.xml': PREFIXED})):
            context = scan.gather_context(BASE, allow_private=False, timeout=1)
        self.assertTrue(context['sitemap_found'])
        report = page(context['sitemap_discovery'])
        self.assertIn('XML sitemap reachable', [finding.title for finding in report.findings])
        self.assertIsNone(recorded_sitemap_discovery_problem(report.meta, for_score=True))
        self.assertIn('Sitemap discovery unverified', report.to_markdown())

    def test_validator_returns_uncertain_candidate_not_false_no_sitemap_verdict(self):
        with mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, 'fetch_text', return_value=''), \
                mock.patch.object(http, 'fetch_bytes', side_effect=fetcher({INDEX: '<feed/>'})):
            result = validate_sitemap.analyze(BASE)
        self.assertEqual([INDEX], result['seeds'])
        self.assertEqual(1, result['parse_coverage']['unverified_files'])
        self.assertNotIn('No sitemap found', validate_sitemap.render_markdown(result))
        self.assertNotIn('Sitemap looks healthy', validate_sitemap.render_markdown(result))

    def test_index_child_and_depth_limits_remain_explicit(self):
        children = [BASE + 'child' + str(i) + '.xml' for i in range(6)]
        index = '<sitemapindex>' + ''.join('<sitemap><loc>' + url + '</loc></sitemap>' for url in children) + '</sitemapindex>'
        coverage = {}
        bodies = {INDEX: index, **{url: '<sitemapindex><sitemap><loc>' + CHILD + '</loc></sitemap></sitemapindex>' for url in children}}
        with mock.patch.object(http, 'fetch_bytes', side_effect=fetcher(bodies)), \
                mock.patch.object(http, 'fetch', return_value=http.Response(BASE, BASE, 200, {}, HTML, 1)):
            crawl_site.discover(BASE, allow_private=False, timeout=1, limit=5, robots_txt='', coverage=coverage)
        self.assertIn('index_child_budget', coverage['limits'])
        self.assertIn('nested_index_depth', coverage['limits'])
        self.assertEqual(6, coverage['verified_files'])
        self.assertLessEqual(coverage['attempted_files'], len(crawl_site.SITEMAP_CANDIDATES) + 5)

    def test_unverified_availability_blocks_relevant_diff_compare_and_brief_scores(self):
        discovery = Discovery('context_candidates')
        with mock.patch.object(http, 'fetch_bytes', return_value=(b'<feed/>', None)):
            discovery.read(INDEX, allow_private=False, timeout=1)
        report = page(discovery.receipt())
        data = json.loads(report.to_json())
        diff = diff_scan.diff_reports(data, data)
        self.assertEqual('incomparable', diff['comparison']['status'])
        with mock.patch.object(compare.scanner, 'scan', return_value=report):
            result = compare.run([BASE, BASE + 'rival'])
        self.assertNotIn('you', result)
        self.assertTrue(result['failed'][0]['sitemap_discovery_unverified'])
        with mock.patch.object(brief.scanner, 'scan', return_value=report):
            with self.assertRaisesRegex(RuntimeError, 'Sitemap availability'):
                brief._page(BASE)

    def test_content_only_scores_and_legacy_receipt_absence_are_not_guessed_incomplete(self):
        discovery = Discovery('context_candidates')
        with mock.patch.object(http, 'fetch_bytes', return_value=(b'<feed/>', None)):
            discovery.read(INDEX, allow_private=False, timeout=1)
        report = page(discovery.receipt(), only='content')
        self.assertIsNone(recorded_sitemap_discovery_problem(report.meta, for_score=True))
        data = json.loads(report.to_json())
        self.assertEqual('comparable', diff_scan.diff_reports(data, data)['comparison']['status'])
        self.assertIsNone(recorded_sitemap_discovery_problem({}))

    def test_bad_or_future_receipts_are_unrecognized_without_echoing_data(self):
        for receipt in ({'basis': 'future', 'secret': 'password'},
                        {'basis': 'bounded_xml_discovery', 'scope': 'context_candidates', 'attempted_files': True}):
            report = page(receipt)
            self.assertFalse(report.findings)
            self.assertIn('unrecorded/unrecognized', report.to_markdown())
            self.assertNotIn('password', report.to_json())

    def test_duplicates_are_skipped_and_do_not_retain_parsed_entry_buffers(self):
        discovery = Discovery('context_candidates')
        with mock.patch.object(http, 'fetch_bytes', return_value=(PREFIXED.encode(), None)) as fetch:
            self.assertEqual('urlset', discovery.read(INDEX, allow_private=False, timeout=1)[0])
            self.assertIsNone(discovery.read(INDEX, allow_private=False, timeout=1))
        fetch.assert_called_once()
        self.assertEqual({INDEX}, discovery.seen)
        self.assertEqual(1, discovery.receipt()['attempted_files'])
        fetch.assert_called_once_with(INDEX, allow_private=False, timeout=1, max_bytes=5_000_000)

    def test_invalid_component_settings_fail_before_transport(self):
        with mock.patch.object(http, 'fetch_bytes') as fetch:
            for budget in (-1, True, 51, '2', None):
                with self.subTest(budget=budget), self.assertRaises(ValueError):
                    Discovery('context_candidates', max_files=budget)
            with self.assertRaises(ValueError):
                Discovery('unknown')
        fetch.assert_not_called()

    def test_external_dtd_decode_limits_and_http_failures_withhold_extraction(self):
        cases = [(b'<!DOCTYPE urlset SYSTEM "http://127.0.0.1/private"><urlset/>', None),
                 (b'<urlset/>', 'HTTP 403'), (None, 'Response exceeded raw byte limit')]
        for raw, error in cases:
            discovery = Discovery('context_candidates')
            with self.subTest(error=error), mock.patch.object(http, 'fetch_bytes', return_value=(raw, error)), \
                    mock.patch('socket.getaddrinfo', side_effect=AssertionError('No parser DNS')):
                self.assertIsNone(discovery.read(INDEX, allow_private=False, timeout=1))
            self.assertEqual(1, discovery.receipt()['unverified_files'])
        discovery = Discovery('context_candidates')
        with mock.patch.object(http, 'fetch_bytes', return_value=(gzip.compress(PREFIXED.encode()), None)), \
                mock.patch.object(sm, 'MAX_DECODED_BYTES', 16):
            self.assertIsNone(discovery.read(INDEX, allow_private=False, timeout=1))
        self.assertEqual({'decoded_byte_limit': 1}, discovery.receipt()['reasons'])

    def test_receipt_validation_rejects_inconsistent_and_future_counts(self):
        receipt = Discovery('context_candidates').receipt()
        for value in ({**receipt, 'attempted_files': True}, {**receipt, 'verified_files': 1},
                      {**receipt, 'reasons': {'future': 1}}, {**receipt, 'limits': ['future']},
                      {**receipt, 'limits': ['file_attempt_budget', 'file_attempt_budget']}):
            self.assertIsNone(sm.recorded_discovery(value))
        self.assertIsNone(sm.discovery_note(None))

    def test_audit_score_gate_includes_recorded_crawl_availability_gaps(self):
        report = Report(BASE, final_url=BASE, fetched_status=200)
        report.meta['scan_scope'] = {'requested': ['technical'], 'completed': ['technical']}
        audit = {'schema_version': '2.0', 'site': BASE, 'overall_score': 100,
                 'homepage': json.loads(report.to_json()),
                 'crawl': {'pages': [{'url': BASE, 'sitemap_discovery_unverified': True}]}}
        self.assertEqual('incomparable', diff_scan.diff_reports(audit, audit)['comparison']['status'])

    def test_zero_attempts_do_not_certify_absence_and_extra_receipt_data_is_not_retained(self):
        receipt = Discovery('context_candidates').receipt()
        receipt['secret'] = 'password'
        report = page(receipt)
        self.assertFalse(report.findings)
        self.assertIn('No candidate files were examined', report.to_markdown())
        self.assertNotIn('password', report.to_json())
        self.assertTrue(recorded_sitemap_discovery_problem(report.meta, for_score=True))

    def test_missing_declared_candidate_is_not_treated_as_an_absent_optional_path(self):
        discovery = Discovery('crawl_candidates')
        with mock.patch.object(http, 'fetch_bytes', return_value=(None, 'HTTP 404')) as fetch:
            discovery.read(INDEX, allow_private=False, timeout=1)
            self.assertEqual(1, discovery.receipt()['absent_files'])
            discovery.read(INDEX, allow_private=False, timeout=1, declared=True)
            discovery.read(INDEX, allow_private=False, timeout=1, declared=True)
        fetch.assert_called_once()
        receipt = discovery.receipt()
        self.assertEqual(1, receipt['unverified_files'])
        self.assertEqual(0, receipt['absent_files'])
        self.assertEqual({'declared_unavailable': 1}, receipt['reasons'])
        self.assertIn('declared sitemap candidate was unavailable', sm.discovery_note(receipt))

    def test_crawl_graph_sample_excludes_added_seed_and_anchor_fallback(self):
        for body, expected in ((PREFIXED, [PAGE]), ('<urlset/>', []), ('<feed/>', [])):
            sample = []
            with self.subTest(body=body[:20]), mock.patch.object(http, 'fetch_bytes', side_effect=fetcher({INDEX: body})), \
                    mock.patch.object(http, 'fetch', return_value=http.Response(BASE, BASE, 200, {}, HTML, 1)):
                urls = crawl_site.discover(BASE, allow_private=False, timeout=1, limit=5,
                                           robots_txt='', discovered_sitemap=sample)
            self.assertEqual(expected, sample)
            self.assertIn(BASE, urls)

    def test_shared_common_paths_include_hyphenated_sitemap_index(self):
        self.assertEqual(tuple(validate_sitemap.COMMON), tuple(crawl_site.SITEMAP_CANDIDATES))
        self.assertEqual(tuple(scan.SITEMAP_CANDIDATES), tuple(crawl_site.SITEMAP_CANDIDATES))
        url = BASE + 'sitemap-index.xml'
        with mock.patch.object(http, 'fetch_text', return_value=''), \
                mock.patch.object(http, 'fetch_bytes', side_effect=fetcher({url: PREFIXED})):
            self.assertTrue(scan.gather_context(BASE, allow_private=False, timeout=1)['sitemap_found'])
            self.assertEqual([url], validate_sitemap.discover(BASE, allow_private=False, timeout=1))
            self.assertEqual([BASE, PAGE], crawl_site.discover(BASE, allow_private=False, timeout=1, limit=5, robots_txt=''))


if __name__ == '__main__':
    unittest.main()
