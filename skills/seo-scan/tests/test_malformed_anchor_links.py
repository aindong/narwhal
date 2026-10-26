"""Malformed source hrefs are syntax omissions, not failed HTTP requests."""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_technical
import crawl_site
import scan
from lib import config, htmlx, http, links
from lib.report import Report

BASE = 'https://example.test/'
CHILD = BASE + 'valid'
BAD = ('http://[', '//[broken', 'https://example.test:nope/path',
       'https://example.test:65536/path', 'https://exa／mple.test/path')
HTML = '<html lang="en"><title>Source links fixture</title><h1>Links</h1>{}</html>'


def source(*hrefs):
    return HTML.format(''.join('<a href="' + href + '">Destination</a>' for href in hrefs))


def response(url, body):
    return http.Response(url, url, 200, {'content-type': 'text/html'}, body, 1)


class TestMalformedAnchorLinks(unittest.TestCase):
    def test_technical_source_check_survives_known_host_and_port_errors(self):
        for href in BAD:
            with self.subTest(href=href):
                body = source(href, '/valid')
                report = Report(BASE)
                audit_technical._links(htmlx._parse_stdlib(body, BASE), response(BASE, body), report)
                self.assertEqual(['technical.links.invalid.url'], [f.rule_id for f in report.findings])
                self.assertEqual('low', report.findings[0].severity)
                self.assertIn('No network failure', report.findings[0].detail)

    def test_collector_skips_invalid_hrefs_but_keeps_later_valid_targets(self):
        doc = htmlx._parse_stdlib(source(*BAD, '/valid', '/valid#again'), BASE)
        diagnostics = {}
        self.assertEqual([{'url': CHILD, 'internal': True}],
                         links.extract_links(doc, BASE, diagnostics=diagnostics))
        self.assertEqual(len(BAD), diagnostics['invalid_url_occurrences'])

    def test_discovery_continues_after_malformed_anchor_hrefs(self):
        with mock.patch.object(http, 'fetch_text', return_value=''), \
                mock.patch.object(http, 'fetch', return_value=response(BASE, source(*BAD, '/valid'))):
            found = crawl_site.discover(BASE, allow_private=False, timeout=1, limit=5, robots_txt='')
        self.assertEqual([BASE, CHILD], found)

    def test_scan_records_syntax_only_omissions_and_completes(self):
        with mock.patch.object(http, 'fetch', return_value=response(BASE, source(*BAD, '/valid'))):
            report = scan.scan(BASE, ctx={}, collect_links=True, check_images=False)
        self.assertEqual([{'url': CHILD, 'internal': True}], report.meta['links'])
        self.assertEqual({'invalid_url_occurrences': len(BAD), 'basis': 'url_syntax_only'},
                         report.meta['link_extraction'])
        self.assertEqual(['technical', 'content', 'schema', 'geo'], report.meta['scan_scope']['completed'])
        self.assertIn('technical.links.invalid.url', {f.rule_id for f in report.findings})

    def test_good_link_outputs_have_no_new_empty_receipt(self):
        with mock.patch.object(http, 'fetch', return_value=response(BASE, source('/valid'))):
            report = scan.scan(BASE, ctx={}, collect_links=True, check_images=False)
        self.assertNotIn('link_extraction', report.meta)
        self.assertEqual([{'url': CHILD, 'internal': True}], report.meta['links'])

    def test_non_http_and_fragment_links_are_not_malformed_http_observations(self):
        for href in ('', '#section', 'mailto:a@example.test', 'javascript:void(0)',
                     'FTP://[', 'data:text/plain,hello', 'tel:+123'):
            with self.subTest(href=href):
                self.assertIsNone(links.resolve_http_link(href, BASE))
        diagnostics = {}
        links.extract_links(htmlx._parse_stdlib(source('mailto:a@example.test', '#x'), BASE),
                            BASE, diagnostics=diagnostics)
        self.assertFalse(diagnostics)

    def test_valid_relative_encoded_and_ipv6_targets_keep_their_spelling(self):
        cases = [('/a%2fb?q=one#fragment', BASE + 'a%2fb?q=one'),
                 ('//other.test:65535/path', 'https://other.test:65535/path'),
                 ('http://[2001:db8::1]:8080/x', 'http://[2001:db8::1]:8080/x')]
        for href, target in cases:
            with self.subTest(href=href):
                self.assertEqual(target, links.resolve_http_link(href, BASE))

    def test_syntax_collection_does_not_resolve_dns_or_grant_private_host_permission(self):
        with mock.patch.object(http, 'assert_public_host', side_effect=AssertionError('No DNS here')), \
                mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS here')):
            self.assertEqual('http://127.0.0.1/private',
                             links.resolve_http_link('http://127.0.0.1/private', BASE))
            self.assertEqual(1, len(links.extract_links(
                htmlx._parse_stdlib(source('http://127.0.0.1/private'), BASE), BASE)))

    def test_source_diagnostics_do_not_echo_credentials_or_parser_exception_text(self):
        href = 'http://secret:password@[broken'
        with mock.patch.object(http, 'fetch', return_value=response(BASE, source(href))):
            report = scan.scan(BASE, ctx={}, collect_links=True, check_images=False)
        payload = report.to_json()
        self.assertNotIn('password', payload)
        self.assertNotIn('secret:', payload)
        self.assertIn('invalid_url_occurrences', payload)

    def test_direct_user_url_errors_still_raise_before_page_fetch(self):
        with mock.patch.object(http, 'fetch') as fetch:
            with self.assertRaises(http.URLInputError):
                crawl_site.crawl('http://[')
        fetch.assert_not_called()
        with self.assertRaises(http.URLInputError):
            http.normalize_url('http://[')

    def test_unexpected_resolver_errors_are_not_silenced(self):
        body = source('/valid')
        doc = htmlx._parse_stdlib(body, BASE)
        with mock.patch.object(links, 'resolve_http_link', side_effect=RuntimeError('bug')):
            with self.assertRaisesRegex(RuntimeError, 'bug'):
                links.extract_links(doc, BASE)
            with self.assertRaisesRegex(RuntimeError, 'bug'):
                audit_technical._links(doc, response(BASE, body), Report(BASE))
            with mock.patch.object(http, 'fetch_text', return_value=''), \
                    mock.patch.object(http, 'fetch', return_value=response(BASE, body)):
                with self.assertRaisesRegex(RuntimeError, 'bug'):
                    crawl_site.discover(BASE, allow_private=False, timeout=1, limit=5, robots_txt='')

    def test_crawl_reports_omissions_without_fabricating_dead_links(self):
        pages = {BASE: source('http://[', 'http://[', '/valid'),
                 CHILD: source('https://example.test:nope/path', '/')}
        with mock.patch.object(scan, 'gather_context', return_value={}), \
                mock.patch.object(crawl_site, 'discover', return_value=[BASE, CHILD]), \
                mock.patch.object(http, 'fetch', side_effect=lambda url, **kw: response(url, pages[url])), \
                mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')), \
                mock.patch.object(http, 'head', return_value=(200, None)) as head:
            data = crawl_site.crawl(BASE, max_pages=2, concurrency=1, check_links=True, detect_dupes=False)
        self.assertEqual(2, data['pages_scanned'])
        self.assertEqual({BASE: {'invalid_url_occurrences': 2, 'basis': 'url_syntax_only'},
                          CHILD: {'invalid_url_occurrences': 1, 'basis': 'url_syntax_only'}},
                         {page['url']: page['link_extraction'] for page in data['pages']})
        self.assertEqual({'invalid_url_occurrences': 3, 'affected_pages': 2, 'basis': 'url_syntax_only'},
                         data['link_extraction'])
        self.assertEqual({BASE, CHILD}, {call.args[0] for call in head.call_args_list})
        self.assertFalse(data['links']['broken'])
        self.assertEqual(2, data['links']['checked'])
        self.assertIn('3 malformed HTTP href occurrence(s)', crawl_site.render_markdown(data))
        self.assertIn('not network failures', crawl_site.render_markdown(data))
        self.assertIn('among HTTP-checked targets', crawl_site.render_markdown(data))
        self.assertNotIn('No broken links found. 🟢', crawl_site.render_markdown(data))
        serialized = json.loads(crawl_site.render_json(data))
        self.assertEqual(3, serialized['link_extraction']['invalid_url_occurrences'])

    def test_duplicate_invalid_values_are_counted_as_occurrences_not_unique_targets(self):
        diagnostics = {}
        links.extract_links(htmlx._parse_stdlib(source('http://[', 'http://['), BASE),
                            BASE, diagnostics=diagnostics)
        self.assertEqual(2, diagnostics['invalid_url_occurrences'])

    def test_suppression_and_unselected_technical_checks_do_not_hide_collection_omissions(self):
        cfg = config.Config({'ignore': {'titles': ['Malformed HTTP link URLs']}})
        with mock.patch.object(http, 'fetch', return_value=response(BASE, source('http://[', '/valid'))):
            ignored = scan.scan(BASE, ctx={}, collect_links=True, check_images=False, config=cfg)
            focused = scan.scan(BASE, ctx={}, collect_links=True, check_images=False, only=['content'])
        for report in (ignored, focused):
            self.assertNotIn('technical.links.invalid.url', {f.rule_id for f in report.findings})
            self.assertEqual(1, report.meta['link_extraction']['invalid_url_occurrences'])
            self.assertEqual([{'url': CHILD, 'internal': True}], report.meta['links'])

    def test_valid_crawl_does_not_add_empty_omission_metadata(self):
        with mock.patch.object(scan, 'gather_context', return_value={}), \
                mock.patch.object(http, 'fetch_text', return_value=''), \
                mock.patch.object(http, 'fetch', return_value=response(BASE, source('/valid'))):
            data = crawl_site.crawl(BASE, max_pages=1, concurrency=1, detect_dupes=False)
        self.assertNotIn('link_extraction', data)
        self.assertNotIn('link_extraction', data['pages'][0])


if __name__ == '__main__':
    unittest.main()
