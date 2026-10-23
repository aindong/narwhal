"""Declared document bases must not silently invent anchor destinations."""
from pathlib import Path
import copy
import json
import socket
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import crawl_site
import audit_technical
import brief
import compare
import diff_scan
import scan
from lib import htmlx, http, links, merchant_source, microdata
from lib.report import Report

BASE = 'https://example.test/start/page.html'


def doc(head, href='guide'):
    return htmlx.parse('<html><head>' + head + '</head><body><a href="' + href + '">Guide</a></body></html>', BASE)


class TestDocumentBaseLinks(unittest.TestCase):
    def test_same_host_absolute_base_changes_relative_target(self):
        self.assertEqual([{'url': 'https://example.test/catalog/guide', 'internal': True}],
                         links.extract_links(doc('<base href="https://example.test/catalog/">'), BASE))

    def test_external_base_does_not_redefine_which_host_is_internal(self):
        self.assertEqual([{'url': 'https://outside.test/catalog/guide', 'internal': False}],
                         links.extract_links(doc('<base href="https://outside.test/catalog/">'), BASE))

    def test_relative_base_keeps_repeated_separators(self):
        self.assertEqual([{'url': 'https://example.test/start/assets//guide', 'internal': True}],
                         links.extract_links(doc('<base href="./assets//">'), BASE))

    def test_first_href_base_wins_not_last_or_first_nonempty(self):
        for head in ('<base href=""><base href="https://outside.test/">',
                     '<base target="_blank"><base href=""><base href="https://outside.test/">'):
            self.assertEqual([{'url': 'https://example.test/start/guide', 'internal': True}], links.extract_links(doc(head), BASE))
        self.assertEqual([{'url': 'https://example.test/catalog/guide', 'internal': True}],
                         links.extract_links(doc('<base href="/catalog/"><base href="https://outside.test/">'), BASE))

    def test_template_base_is_not_the_document_base(self):
        self.assertEqual([{'url': 'https://example.test/catalog/guide', 'internal': True}],
                         links.extract_links(doc('<template><base href="https://outside.test/"></template><base href="/catalog/">'), BASE))

    def test_absolute_anchor_ignores_declared_base(self):
        self.assertEqual([{'url': 'https://other.test/fixed', 'internal': False}],
                         links.extract_links(doc('<base href="/catalog/">', 'https://other.test/fixed'), BASE))

    def test_fallback_discovery_uses_base_but_keeps_document_host_boundary(self):
        for base_href, expected in (('/catalog/', [BASE, 'https://example.test/catalog/guide']),
                                    ('https://outside.test/catalog/', [BASE])):
            page = doc('<base href="' + base_href + '">')
            response = http.Response(BASE, BASE, 200, {'content-type': 'text/html'}, page.html, 1)
            with mock.patch.object(http, 'fetch_text', return_value=''), mock.patch.object(http, 'fetch', return_value=response):
                result = crawl_site.discover(BASE, allow_private=False, timeout=1, limit=5, robots_txt='')
            self.assertEqual(expected, result)

    def test_base_collection_is_pure_and_never_authorizes_private_host_fetch(self):
        with mock.patch.object(socket, 'getaddrinfo', side_effect=AssertionError('No DNS')), \
                mock.patch.object(http, 'fetch', side_effect=AssertionError('No fetch')):
            self.assertEqual([{'url': 'http://127.0.0.1/private/guide', 'internal': False}],
                             links.extract_links(doc('<base href="http://127.0.0.1/private/">'), BASE))

    def test_stdlib_and_optional_parser_agree_on_base_order_and_entities(self):
        page = doc('<base href="/catalog/?x=1&amp;y=2"><base href="https://outside.test/">')
        standard = htmlx._parse_stdlib(page.html, BASE)
        self.assertEqual('/catalog/?x=1&y=2', standard.base_href)
        self.assertEqual(links.extract_links(standard, BASE), links.extract_links(page, BASE))

    def test_cached_base_is_shared_with_canonical_without_freezing_document_url(self):
        page = doc('<base href="../catalog/"><link rel="canonical" href="guide">')
        with mock.patch.object(htmlx._canonical, 'first_base', wraps=htmlx._canonical.first_base) as first:
            self.assertEqual('../catalog/', page.base_href)
            self.assertEqual('https://example.test/catalog/guide', page.canonical())
            links.extract_links(page, BASE)
            self.assertEqual(1, first.call_count)
        page.base_url = 'https://other.test/start/page.html'
        self.assertEqual('https://other.test/catalog/guide', page.canonical())

    def test_no_base_does_not_add_a_false_declared_base_receipt(self):
        diagnostics = {}
        links.extract_links(doc(''), BASE, diagnostics=diagnostics)
        self.assertEqual({}, diagnostics)

    def test_raw_text_and_rcdata_do_not_inject_a_document_base(self):
        for tag in ('script', 'style', 'title', 'textarea', 'xmp', 'iframe', 'noembed', 'noframes'):
            with self.subTest(tag=tag):
                page = doc('<' + tag + '><base href="https://outside.test/"></' + tag + '><base href="/catalog/">')
                self.assertEqual('/catalog/', page.base_href)
                self.assertEqual([{'url': 'https://example.test/catalog/guide', 'internal': True}], links.extract_links(page, BASE))

    def test_bogus_marked_declaration_cannot_crash_shared_base_reading(self):
        for prefix in ('<![bad]>', '<![bad>'):
            source = prefix + '<base href="/catalog/"><a href="guide">Guide</a>'
            for parser in (htmlx._parse_stdlib, htmlx.parse):
                page = parser(source, BASE)
                self.assertEqual('/catalog/', page.base_href)
                self.assertEqual([{'url': 'https://example.test/catalog/guide', 'internal': True}], links.extract_links(page, BASE))

    def test_bogus_marked_declarations_complete_full_scan_for_both_parser_paths(self):
        for parser in (htmlx._parse_stdlib, htmlx.parse):
            for prefix in ('<![bad]>', '<![bad>'):
                body = prefix + '<base href="/catalog/"><a href="guide">Guide</a>'
                response = http.Response(BASE, BASE, 200, {'content-type': 'text/html'}, body, 1)
                with mock.patch.object(scan.htmlx, 'parse', side_effect=parser), mock.patch.object(http, 'fetch', return_value=response):
                    report = scan.scan(BASE, ctx={}, collect_links=True, check_images=False)
                self.assertEqual(['technical', 'content', 'schema', 'geo'], report.meta['scan_scope']['completed'])
                self.assertEqual([{'url': 'https://example.test/catalog/guide', 'internal': True}], report.meta['links'])

    def test_empty_fragment_and_ignored_data_javascript_bases_use_document_url(self):
        for value in ('', '#part', 'javascript:alert(1)', 'data:text/plain,x'):
            with self.subTest(value=value):
                diagnostics = {}
                result = links.extract_links(doc('<base href="' + value + '">'), BASE, diagnostics=diagnostics)
                self.assertEqual([{'url': 'https://example.test/start/guide', 'internal': True}], result)
                self.assertIn(diagnostics['anchor_base']['status'], ('document_url', 'ignored_scheme'))

    def test_unknown_or_non_http_base_withholds_relative_targets_not_absolute_ones(self):
        for value in ('http://[', 'https://example.test:nope/', 'https://example.test:65536/',
                      '///bad', 'https://example.test/a\\b', 'https://user:secret@example.test/',
                      'mailto:a@example.test', 'ftp://example.test/root/'):
            with self.subTest(value=value):
                page = doc('<base href="' + value + '">')
                page.links += doc('', 'https://fixed.test/absolute').links
                diagnostics = {}
                result = links.extract_links(page, BASE, diagnostics=diagnostics)
                self.assertEqual([{'url': 'https://fixed.test/absolute', 'internal': False}], result)
                self.assertEqual(1, diagnostics['unassessed_base_occurrences'])
                self.assertNotIn('invalid_url_occurrences', diagnostics)
                self.assertIn(diagnostics['anchor_base']['status'], ('unverified', 'non_http'))
                self.assertNotIn('secret', json.dumps(diagnostics))

    def test_unknown_base_does_not_turn_independent_bad_anchor_syntax_into_a_pass(self):
        page = doc('<base href="http://[">', '//example.test:nope/a')
        diagnostics = {}
        self.assertEqual([], links.extract_links(page, BASE, diagnostics=diagnostics))
        self.assertEqual(1, diagnostics['invalid_url_occurrences'])

    def test_header_and_meta_base_uri_policies_are_unassessed_not_assumed_allowed(self):
        for header, head in (("script-src 'none'; BASE-URI 'self'", '<base href="/catalog/">'),
                             ('', '<meta http-equiv="Content-Security-Policy" content="base-uri &apos;none&apos;"><base href="/catalog/">')):
            diagnostics = {}
            self.assertEqual([], links.extract_links(doc(head), BASE, csp=header, diagnostics=diagnostics))
            self.assertEqual('base_uri_policy', diagnostics['anchor_base']['reason'])
            self.assertEqual(1, diagnostics['unassessed_base_occurrences'])

    def test_unrelated_csp_report_only_and_template_meta_do_not_block_base_resolution(self):
        for head in ('<base href="/catalog/">',
                     '<meta http-equiv="Content-Security-Policy-Report-Only" content="base-uri &apos;none&apos;"><base href="/catalog/">',
                     '<template><meta http-equiv="Content-Security-Policy" content="base-uri &apos;none&apos;"></template><base href="/catalog/">'):
            diagnostics = {}
            result = links.extract_links(doc(head), BASE, csp="default-src 'none'; script-src 'none'", diagnostics=diagnostics)
            self.assertEqual([{'url': 'https://example.test/catalog/guide', 'internal': True}], result)
            self.assertEqual('declared_http', diagnostics['anchor_base']['status'])

    def test_technical_source_check_and_collection_share_base_uncertainty(self):
        page = doc('<base href="http://secret:password@[broken">')
        response = http.Response(BASE, BASE, 200, {'content-type': 'text/html'}, page.html, 1)
        report = Report(BASE)
        audit_technical._links(page, response, report)
        self.assertEqual([], report.findings)
        self.assertEqual('unverified', report.meta['anchor_base']['status'])
        self.assertEqual(links.RESOLUTION_BASIS, report.meta['anchor_resolution_basis'])
        self.assertNotIn('password', report.to_json())

    def test_malformed_base_warning_omits_raw_source_values_in_shared_extractors(self):
        source = '<base href="http://secret:password@[broken"><span itemscope itemtype="https://schema.org/Thing"></span>'
        results = (microdata.extract(source, BASE)[1], merchant_source.extract(source, BASE)['warnings'])
        for warnings in results:
            self.assertTrue(warnings)
            self.assertNotIn('password', json.dumps(warnings))
            self.assertNotIn('secret:', json.dumps(warnings))
        response = http.Response(BASE, BASE, 200, {'content-type': 'text/html'}, source, 1)
        with mock.patch.object(http, 'fetch', return_value=response):
            report = scan.scan(BASE, ctx={}, collect_links=True, check_images=False)
        self.assertNotIn('password', report.to_json())

    def test_redacted_url_warnings_keep_deduplication_and_bounded_distinct_detail(self):
        tree = microdata._Tree(BASE, warning_limit=2)
        for value in ('http://secret:password@[broken',) * 5:
            tree.resolve(value)
        self.assertEqual(1, len(tree.warnings))
        for number in range(20): tree.resolve('http://[broken' + str(number))
        self.assertEqual(3, len(tree.warnings))
        self.assertIn('warning limit', tree.warnings[-1])
        self.assertLessEqual(len(tree._unresolved_urls), 3)
        self.assertNotIn('password', json.dumps(tree.warnings))

    def test_scan_keeps_base_scope_separate_from_anchor_syntax_omissions(self):
        page = doc('<base href="http://[">')
        response = http.Response(BASE, BASE, 200, {'content-type': 'text/html'}, page.html, 1)
        with mock.patch.object(http, 'fetch', return_value=response):
            report = scan.scan(BASE, ctx={}, collect_links=True, check_images=False)
        self.assertEqual([], report.meta['links'])
        self.assertEqual('unverified', report.meta['anchor_base']['status'])
        self.assertEqual({'unassessed_base_occurrences': 1, 'basis': 'url_syntax_and_declared_base_scope'}, report.meta['link_extraction'])
        self.assertNotIn('technical.links.invalid.url', {finding.rule_id for finding in report.findings})

    def test_source_check_without_collection_still_exposes_declared_base_scope(self):
        page = doc('<base href="/catalog/">')
        response = http.Response(BASE, BASE, 200, {'content-type': 'text/html'}, page.html, 1)
        with mock.patch.object(http, 'fetch', return_value=response):
            report = scan.scan(BASE, ctx={}, check_images=False)
        self.assertEqual('declared_http', report.meta['anchor_base']['status'])
        self.assertNotIn('links', report.meta)

    def test_crawl_keeps_unassessed_base_visible_without_invalid_url_key_error(self):
        page = doc('<base href="http://[">')
        response = http.Response(BASE, BASE, 200, {'content-type': 'text/html'}, page.html, 1)
        with mock.patch.object(scan, 'gather_context', return_value={}), \
                mock.patch.object(http, 'fetch_text', return_value=''), mock.patch.object(http, 'fetch', return_value=response):
            result = crawl_site.crawl(BASE, max_pages=2, concurrency=1, detect_dupes=False)
        self.assertEqual(1, result['pages_scanned'])
        self.assertNotIn('link_extraction', result)
        self.assertIn('Declared anchor base is unassessed', crawl_site.render_markdown(result))
        self.assertNotIn('malformed HTTP href occurrence(s)', crawl_site.render_markdown(result))

    def test_notes_do_not_mutate_scores_or_echo_receipt_payloads(self):
        report = Report(BASE)
        before = (report.score(), report.counts())
        report.meta['anchor_base'] = {'basis': links.DOCUMENT_BASE_BASIS, 'status': 'unverified', 'reason': '<script>secret</script>'}
        self.assertIn('not reported as dead', report.to_markdown())
        self.assertIn('not reported as dead', report.to_html())
        self.assertNotIn('<script>secret', report.to_html())
        self.assertEqual(before, (report.score(), report.counts()))
        report.meta['anchor_base']['basis'] = 'future'
        self.assertEqual('', links.base_note(report.meta))

    def test_policy_diff_preserves_previous_v1_guard_and_adds_page_v2_guard(self):
        page = Report(BASE, fetched_status=200)
        page.meta['scan_scope'] = {'requested': ['technical'], 'completed': ['technical']}
        after = json.loads(page.to_json()); after['meta']['anchor_resolution_basis'] = links.RESOLUTION_BASIS
        before = json.loads(page.to_json())
        self.assertEqual('incomparable', diff_scan.diff_reports(before, after)['comparison']['status'])
        self.assertEqual('comparable', diff_scan.diff_reports(after, copy.deepcopy(after))['comparison']['status'])
        old_audit = {'site': BASE, 'homepage': before, 'crawl': {'pages': []}}
        prior = copy.deepcopy(old_audit); prior['crawl']['link_resolution_basis'] = links.LEGACY_RESOLUTION_BASIS
        self.assertEqual('incomparable', diff_scan.diff_reports(old_audit, prior)['comparison']['status'])
        current = copy.deepcopy(prior); current['crawl']['link_resolution_basis'] = links.RESOLUTION_BASIS
        self.assertEqual('incomparable', diff_scan.diff_reports(prior, current)['comparison']['status'])

    def test_known_unassessed_base_blocks_identical_report_site_fix_claims(self):
        page = Report(BASE, fetched_status=200)
        page.meta['scan_scope'] = {'requested': ['technical'], 'completed': ['technical']}
        page.meta['anchor_base'] = {'basis': links.DOCUMENT_BASE_BASIS, 'status': 'unverified'}
        payload = json.loads(page.to_json())
        self.assertEqual('incomparable', diff_scan.diff_reports(payload, payload)['comparison']['status'])
        plain = json.loads(Report(BASE, fetched_status=200).to_json())
        audit = {'site': BASE, 'homepage': plain, 'crawl': {'pages': [{'anchor_base': page.meta['anchor_base']}]}}
        self.assertEqual('incomparable', diff_scan.diff_reports(audit, audit)['comparison']['status'])

    def test_compare_and_brief_do_not_promote_unassessed_page_scores(self):
        page = doc('<base href="http://[">')
        report = Report(BASE, fetched_status=200); report._doc = page
        report.meta['anchor_base'] = {'basis': links.DOCUMENT_BASE_BASIS, 'status': 'unverified'}
        with mock.patch.object(compare.scanner, 'scan', return_value=report):
            result = compare.run([BASE, 'https://other.test/'])
        self.assertIn('error', result)
        self.assertTrue(result['failed'][0]['anchor_base_unassessed'])
        with mock.patch.object(brief.scanner, 'scan', return_value=report):
            with self.assertRaisesRegex(RuntimeError, 'Declared anchor-base'):
                brief._page(BASE)

    def test_base_scope_warning_stays_visible_outside_capped_page_lists(self):
        result = {'base': BASE, 'pages_scanned': 8, 'avg_score': 100, 'recurring': {},
                  'pages': [{'url': BASE + str(i), 'score': 100, 'anchor_base': {
                      'basis': links.DOCUMENT_BASE_BASIS, 'status': 'declared_http'}} for i in range(7)]}
        result['pages'].append({'url': BASE + 'unknown', 'score': 100, 'anchor_base': {
            'basis': links.DOCUMENT_BASE_BASIS, 'status': 'unverified'}})
        rendered = crawl_site.render_markdown(result)
        self.assertIn('unassessed on 1 scanned page(s)', rendered)
        self.assertIn('Declared anchor base is unassessed', rendered)
        self.assertIn('… +3 more sampled pages (see JSON)', rendered)


if __name__ == '__main__': unittest.main()
