"""Rejected discovered sitemap URLs do not abort usable site measurements."""

import json
import sys
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_technical
import crawl_site
import scan
import plan
import validate_sitemap
from lib import http, sitemap as sm
from lib.report import Report

BASE = 'https://example.test/'
INDEX = BASE + 'sitemap.xml'
CHILD = BASE + 'pages.xml'
PAGE = BASE + 'valid'
BAD = 'http://secret:password@['
ROBOT = 'User-agent: *\nSitemap: ' + BAD + '\nSitemap: ' + INDEX + '\n'


def xml(kind, values):
    tag = 'sitemap' if kind == 'sitemapindex' else 'url'
    return '<' + kind + '>' + ''.join('<' + tag + '><loc>' + v + '</loc></' + tag + '>' for v in values) + '</' + kind + '>'


def text_fetch(url, **kwargs):
    http.normalize_url(url)  # preserve the real input boundary without network
    return {BASE + 'robots.txt': ROBOT, INDEX: xml('sitemapindex', [BAD, CHILD]),
            CHILD: xml('urlset', [BAD, PAGE])}.get(url)


def bytes_fetch(url, **kwargs):
    text = text_fetch(url, **kwargs)
    return (text.encode(), None) if text is not None else (None, 'HTTP 404')


class TestSitemapReferences(unittest.TestCase):
    def test_loc_problem_handles_lazy_port_brackets_and_nfkc_errors(self):
        for value in (BAD, 'https://example.test:nope/p', 'https://example.test:65536/p',
                      'https://exa／mple.test/p'):
            with self.subTest(value=value):
                self.assertEqual('invalid-url', sm.loc_problem(value))
        self.assertEqual('not-absolute', sm.loc_problem('/relative'))
        self.assertEqual('cross-host', sm.loc_problem('https://other.test/a', 'example.test'))
        self.assertIsNone(sm.loc_problem('https://[2001:db8::1]:8080/a%2fb'))

    def test_robots_sitemaps_filter_before_fetch_without_leaking_errors(self):
        diagnostics = {}
        values = sm.robots_sitemaps(ROBOT + ' Sitemap: /relative\nSITEMAP: ftp://files.test/a\n',
                                     diagnostics=diagnostics)
        self.assertEqual([INDEX], values)
        self.assertEqual({'robots_directives': 3}, diagnostics)
        receipt = sm.reference_diagnostics(diagnostics)
        self.assertNotIn('password', json.dumps(receipt))

    def test_context_continues_after_bad_directive_and_reports_source_scope(self):
        with mock.patch.object(http, 'fetch_text', side_effect=text_fetch) as fetch, \
                mock.patch.object(http, 'fetch_bytes', side_effect=bytes_fetch):
            ctx = scan.gather_context(BASE, allow_private=False, timeout=1)
        self.assertTrue(ctx['sitemap_found'])
        self.assertEqual(INDEX, ctx['sitemap_url'])
        self.assertEqual({'robots_directives': 1}, ctx['sitemap_references']['rejected'])
        self.assertNotIn(BAD, [call.args[0] for call in fetch.call_args_list])

    def test_crawl_filters_index_children_and_page_locs_before_using_them(self):
        diagnostics = {}
        with mock.patch.object(http, 'fetch_text', side_effect=text_fetch), \
                mock.patch.object(http, 'fetch_bytes', side_effect=bytes_fetch), \
                mock.patch.object(http, 'fetch') as fetch_page:
            urls = crawl_site.discover(BASE, allow_private=False, timeout=1, limit=5,
                                       robots_txt=ROBOT, diagnostics=diagnostics)
        self.assertEqual([BASE, PAGE], urls)
        self.assertEqual({'robots_directives': 1, 'index_locations': 1, 'page_locations': 1}, diagnostics)
        fetch_page.assert_not_called()

    def test_invalid_index_entries_do_not_consume_the_five_child_fetch_budget(self):
        def fetch(url, **kwargs):
            if url == INDEX:
                return xml('sitemapindex', [BAD] * 6 + [CHILD])
            return xml('urlset', [PAGE]) if url == CHILD else None
        with mock.patch.object(http, 'fetch_bytes', side_effect=lambda url, **kw:
                               (fetch(url).encode(), None) if fetch(url) is not None else (None, 'HTTP 404')) as calls:
            urls = crawl_site.discover(BASE, allow_private=False, timeout=1, limit=5,
                                       robots_txt='Sitemap: ' + INDEX)
        self.assertEqual([BASE, PAGE], urls)
        self.assertEqual([INDEX, CHILD], [call.args[0] for call in calls.call_args_list])

    def test_all_invalid_page_locations_allow_homepage_link_fallback(self):
        body = '<html><a href="/valid">Valid page</a></html>'
        with mock.patch.object(http, 'fetch_text', return_value=xml('urlset', [BAD])), \
                mock.patch.object(http, 'fetch_bytes', return_value=(xml('urlset', [BAD]).encode(), None)), \
                mock.patch.object(http, 'fetch', return_value=http.Response(BASE, BASE, 200, {}, body, 1)):
            urls = crawl_site.discover(BASE, allow_private=False, timeout=1, limit=5, robots_txt='')
        self.assertEqual([BASE, PAGE], urls)

    def test_validator_keeps_raw_page_count_but_never_samples_invalid_locs(self):
        def binary(url, **kwargs):
            return text_fetch(url).encode(), None
        with mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, 'fetch_text', side_effect=text_fetch), \
                mock.patch.object(http, 'fetch_bytes', side_effect=binary) as fetched, \
                mock.patch.object(http, 'head', return_value=(200, None)) as head:
            result = validate_sitemap.analyze(BASE, sample=5)
        self.assertEqual(2, result['sitemaps_fetched'])
        self.assertEqual(2, result['total_urls'])
        self.assertEqual({'invalid-url': 1}, result['problems'])
        self.assertEqual({'robots_directives': 1, 'index_locations': 1, 'page_locations': 1},
                         result['sitemap_references']['rejected'])
        self.assertEqual([INDEX, CHILD], [call.args[0] for call in fetched.call_args_list])
        self.assertEqual([PAGE], [call.args[0] for call in head.call_args_list])
        self.assertFalse(result['broken_sample'])
        self.assertNotIn('password', validate_sitemap.render_json(result))
        self.assertNotIn('Sitemap looks healthy', validate_sitemap.render_markdown(result))

    def test_bad_only_robots_directives_do_not_prevent_common_path_discovery(self):
        def fetch(url, **kwargs):
            if url.endswith('/robots.txt'):
                return 'Sitemap: ' + BAD
            return xml('urlset', [PAGE]) if url == INDEX else None
        diagnostics = {}
        with mock.patch.object(http, 'fetch_text', side_effect=fetch), \
                mock.patch.object(http, 'fetch_bytes', side_effect=lambda url, **kw:
                                  (fetch(url).encode(), None) if fetch(url) is not None else (None, 'HTTP 404')):
            self.assertEqual([INDEX], validate_sitemap.discover(BASE, allow_private=False,
                                                               timeout=1, diagnostics=diagnostics))
        self.assertEqual({'robots_directives': 1}, diagnostics)

    def test_no_seed_output_still_explains_rejected_source_references(self):
        def fetch(url, **kwargs):
            return 'Sitemap: ' + BAD if url.endswith('/robots.txt') else None
        with mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, 'fetch_text', side_effect=fetch), \
                mock.patch.object(http, 'fetch_bytes', return_value=(None, 'HTTP 404')):
            result = validate_sitemap.analyze(BASE)
        self.assertFalse(result['seeds'])
        text = validate_sitemap.render_markdown(result)
        self.assertIn('Rejected sitemap URL references', text)
        self.assertIn('No sitemap found', text)
        self.assertNotIn('healthy', text)

    def test_failed_fetch_without_rejections_is_not_a_healthy_sitemap(self):
        with mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, 'fetch_bytes', return_value=(None, 'HTTP 503')):
            result = validate_sitemap.analyze(INDEX)
        self.assertNotIn('Sitemap looks healthy', validate_sitemap.render_markdown(result))

    def test_no_dns_or_host_authorization_is_added_to_source_syntax_checks(self):
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            self.assertIsNone(sm.loc_problem('http://127.0.0.1/private.xml'))
            self.assertEqual(['http://127.0.0.1/private.xml'],
                             sm.robots_sitemaps('Sitemap: http://127.0.0.1/private.xml'))
        with mock.patch.object(http, 'fetch_text', side_effect=http.SSRFError('guard')):
            with self.assertRaises(http.SSRFError):
                scan.gather_context(BASE, allow_private=False, timeout=1)

    def test_direct_user_sitemap_url_errors_remain_errors(self):
        with mock.patch.object(http, 'fetch_bytes') as fetched:
            with self.assertRaises(http.URLInputError):
                validate_sitemap.analyze(BAD)
        fetched.assert_not_called()

    def test_unknown_failures_are_not_hidden_as_rejected_source_references(self):
        with mock.patch.object(http, 'fetch_text', side_effect=RuntimeError('bug')):
            with self.assertRaisesRegex(RuntimeError, 'bug'):
                scan.gather_context(BASE, allow_private=False, timeout=1)

    def test_scan_records_receipt_and_does_not_endorse_bad_robots_reference(self):
        counts = {'robots_directives': 1}
        ctx = {'robots_txt': ROBOT, 'sitemap_found': True,
               'sitemap_references': {'basis': 'absolute_http_url_syntax', 'rejected': counts}}
        body = '<html><title>Reference fixture</title><h1>Fixture</h1></html>'
        with mock.patch.object(http, 'fetch', return_value=http.Response(BASE, BASE, 200, {}, body, 1)):
            report = scan.scan(BASE, ctx=ctx, check_images=False)
        self.assertIn('technical.sitemap.invalid.references', {f.rule_id for f in report.findings})
        finding = next(f for f in report.findings if f.rule_id == 'technical.sitemap.invalid.references')
        self.assertEqual('robots_txt', plan.classify_artifact(asdict(finding)))
        self.assertNotIn('robots.txt references a sitemap', {f.title for f in report.findings})
        counts['robots_directives'] = 99
        self.assertEqual(1, report.meta['sitemap_references']['rejected']['robots_directives'])

    def test_receipts_are_bounded_scalar_counts_not_arbitrary_context(self):
        self.assertIsNone(sm.reference_diagnostics({}))
        self.assertIsNone(sm.recorded_reference_diagnostics({'rejected': {'robots_directives': 1}}))
        receipt = sm.reference_diagnostics({'robots_directives': 2, 'page_locations': True,
                                             'index_locations': -1, 'secret': 'password'})
        self.assertEqual({'basis': 'absolute_http_url_syntax', 'rejected': {'robots_directives': 2}}, receipt)
        self.assertIn('not HTTP failures', sm.reference_note(receipt))

    def test_crawl_does_not_multiply_shared_robots_counts_by_scanned_pages(self):
        body = '<html><title>Reference fixture</title><h1>Fixture</h1><a href="/valid">Valid</a></html>'
        with mock.patch.object(http, 'fetch_text', side_effect=text_fetch), \
                mock.patch.object(http, 'fetch_bytes', side_effect=bytes_fetch), \
                mock.patch.object(http, 'fetch', side_effect=lambda url, **kw: http.Response(url, url, 200, {}, body, 1)):
            result = crawl_site.crawl(BASE, max_pages=2, concurrency=1, detect_dupes=False)
        self.assertEqual(2, result['pages_scanned'])
        self.assertEqual({'robots_directives': 1, 'index_locations': 1, 'page_locations': 1},
                         result['sitemap_references']['rejected'])
        self.assertIn('Rejected sitemap URL references', crawl_site.render_markdown(result))

    def test_focused_scan_keeps_source_receipt_without_inventing_technical_execution(self):
        ctx = {'robots_txt': ROBOT, 'sitemap_found': True}
        body = '<html><title>Reference fixture</title><h1>Fixture</h1></html>'
        with mock.patch.object(http, 'fetch', return_value=http.Response(BASE, BASE, 200, {}, body, 1)):
            report = scan.scan(BASE, ctx=ctx, only=['content'], check_images=False)
        self.assertEqual({'robots_directives': 1}, report.meta['sitemap_references']['rejected'])
        self.assertEqual(['content'], report.meta['scan_scope']['completed'])
        self.assertNotIn('technical.sitemap.invalid.references', {f.rule_id for f in report.findings})

    def test_valid_sitemap_output_remains_healthy_without_empty_receipts(self):
        with mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, 'fetch_bytes', return_value=(xml('urlset', [PAGE]).encode(), None)), \
                mock.patch.object(http, 'head', return_value=(200, None)):
            result = validate_sitemap.analyze(INDEX)
        self.assertNotIn('sitemap_references', result)
        self.assertIn('Sitemap looks healthy', validate_sitemap.render_markdown(result))

    def test_directive_parser_handles_comments_without_parsing_unrelated_agent_rules(self):
        robots = '# Sitemap: ' + BAD + '\n sItEmAp : ' + INDEX + ' # comment\n'
        diagnostics = {}
        with mock.patch('lib.robots.RobotsTxt.parse', side_effect=AssertionError('Do not parse bot rules')):
            self.assertEqual([INDEX], sm.robots_sitemaps(robots, diagnostics=diagnostics))
        self.assertFalse(diagnostics)
        report = Report(BASE)
        audit_technical._robots_txt({'robots_txt': robots}, report)
        self.assertEqual(['robots.txt references a sitemap'], [f.title for f in report.findings])


if __name__ == '__main__':
    unittest.main()
