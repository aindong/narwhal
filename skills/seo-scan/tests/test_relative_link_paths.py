"""Relative-path merging must not merge distinct observed anchor targets."""
import copy
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import crawl_site
import diff_scan
import scan
from lib import htmlx, http, links, sitegraph
from lib.urlpaths import remove_dot_segments
from lib.report import Report

BASE = 'https://example.test/start/page.html?old=1'
CASES = [
    ('guide/chapter', 'https://example.test/start/guide/chapter'),
    ('guide//chapter', 'https://example.test/start/guide//chapter'),
    ('guide///chapter', 'https://example.test/start/guide///chapter'),
    ('../guide//chapter', 'https://example.test/guide//chapter'),
    ('guide//part/../chapter', 'https://example.test/start/guide//chapter'),
    ('guide//../chapter', 'https://example.test/start/guide/chapter'),
    ('.//guide', 'https://example.test/start//guide'),
    ('../..//guide', 'https://example.test//guide'),
    ('guide//chapter;v=1?next=/#part', 'https://example.test/start/guide//chapter;v=1?next=/'),
    ('guide/%2F//chapter', 'https://example.test/start/guide/%2F//chapter'),
    ('/guide//chapter', 'https://example.test/guide//chapter'),
    ('//other.test/guide//chapter', 'https://other.test/guide//chapter'),
    ('https://other.test/guide//chapter', 'https://other.test/guide//chapter'),
    (';v=1', 'https://example.test/start/;v=1'),
    ('.', 'https://example.test/start/'),
    ('..', 'https://example.test/'),
    ('guide/.', 'https://example.test/start/guide/'),
    ('guide/..', 'https://example.test/start/'),
    ('../../..', 'https://example.test/'),
    ('guide//.', 'https://example.test/start/guide//'),
    ('guide//..', 'https://example.test/start/guide/'),
    ('guide//part/..', 'https://example.test/start/guide//'),
]


def source(*hrefs):
    return '<html><head><title>Path fixture</title></head><body>' + ''.join(
        '<a href="' + href + '">Read path</a>' for href in hrefs) + '</body></html>'


def report(basis=links.RESOLUTION_BASIS):
    page = Report(BASE, fetched_status=200)
    page.meta['scan_scope'] = {'requested': ['technical'], 'completed': ['technical']}
    return {'site': BASE, 'overall_score': 100, 'homepage': json.loads(page.to_json()),
            'crawl': {'pages': [], 'link_resolution_basis': basis}}


class TestRelativeLinkPaths(unittest.TestCase):
    def test_empty_path_root_fallback_and_terminal_dot_segments_are_stable(self):
        for value, expected in (('', '/'), ('/', '/'), ('/a/.', '/a/'),
                                ('/a/..', '/'), ('/a//.', '/a//'),
                                ('/a//..', '/a/'), ('/a//b/..', '/a//'), ('/../../..', '/')):
            with self.subTest(value=value):
                self.assertEqual(expected, remove_dot_segments(value))
                self.assertEqual(expected, remove_dot_segments(expected))

    def test_relative_path_components_and_unchanged_absolute_controls(self):
        for href, expected in CASES:
            with self.subTest(href=href):
                self.assertEqual(expected, links.resolve_http_link(href, BASE))

    def test_base_path_repeated_separators_survive_relative_merge(self):
        self.assertEqual('https://example.test/start//guide/chapter',
                         links.resolve_http_link('guide/chapter', 'https://example.test/start//page.html'))
        self.assertEqual('https://example.test/guide//chapter',
                         links.resolve_http_link('guide//chapter', 'https://example.test/start'))

    def test_empty_base_path_gets_authority_root(self):
        self.assertEqual('https://example.test/guide//chapter',
                         links.resolve_http_link('guide//chapter', 'https://example.test'))

    def test_query_slashes_case_and_escapes_are_not_path_segments(self):
        self.assertEqual('https://example.test/start/Guide//chapter?next=//a/../b&x=%2F',
                         links.resolve_http_link('Guide//chapter?next=//a/../b&x=%2F#ignored', BASE))

    def test_encoded_dot_segments_are_not_decoded_by_path_helper(self):
        self.assertEqual('https://example.test/start/a/%2e//b',
                         links.resolve_http_link('a/%2e//b', BASE))

    def test_distinct_relative_targets_are_collected_in_order_and_fragment_aliases_dedup(self):
        refs = ['guide/chapter', 'guide//chapter', 'guide///chapter', 'guide//chapter#again']
        doc = htmlx._parse_stdlib(source(*refs), BASE)
        self.assertEqual([{'url': expected, 'internal': True} for _, expected in CASES[:3]], links.extract_links(doc, BASE))

    def test_parser_backends_collect_same_distinct_paths(self):
        body = source(*[href for href, _ in CASES[:3]])
        expected = links.extract_links(htmlx._parse_stdlib(body, BASE), BASE)
        self.assertEqual(expected, links.extract_links(htmlx.parse(body, BASE), BASE))

    def test_fallback_discovery_preserves_targets_and_existing_cap(self):
        body = source(*[href for href, _ in CASES[:3]])
        response = http.Response(BASE, BASE, 200, {'content-type': 'text/html'}, body, 1)
        with mock.patch.object(http, 'fetch_text', return_value=''), mock.patch.object(http, 'fetch', return_value=response):
            found = crawl_site.discover(BASE, allow_private=False, timeout=1, limit=4, robots_txt='')
            capped = crawl_site.discover(BASE, allow_private=False, timeout=1, limit=2, robots_txt='')
        self.assertEqual([BASE] + [target for _, target in CASES[:3]], found)
        self.assertEqual(found[:2], capped)

    def test_graph_keeps_three_edges_instead_of_shortcut_alias(self):
        doc = htmlx._parse_stdlib(source(*[href for href, _ in CASES[:3]]), BASE)
        observations = links.extract_links(doc, BASE)
        graph = sitegraph.analyze(BASE, [BASE] + [item['url'] for item in observations], {BASE: observations}, [], False)
        self.assertEqual(4, graph['pages_in_graph'])
        self.assertEqual(3, graph['internal_edges'])
        self.assertEqual(4, graph['depth_coverage']['reachable_nodes'])

    def test_relative_path_merge_cannot_change_authority_or_grant_fetch_permission(self):
        with mock.patch.object(socket, 'getaddrinfo', side_effect=AssertionError('No DNS')), \
                mock.patch.object(http, 'fetch', side_effect=AssertionError('No fetch')):
            result = links.resolve_http_link('../..//127.0.0.1/private', BASE)
            self.assertEqual('example.test', http.urlparse(result).hostname)
            self.assertEqual('https://example.test//127.0.0.1/private', result)
            self.assertEqual('http://127.0.0.1/private', links.resolve_http_link('http://127.0.0.1/private', BASE))

    def test_non_http_fragment_and_malformed_syntax_policy_stays(self):
        for href in ('', '#part', 'mailto:a@example.test', 'javascript:alert(1)', 'data:text/plain,x'):
            self.assertIsNone(links.resolve_http_link(href, BASE))
        for href in ('http://[', 'https://example.test:nope/a//b', '//example.test:65536/a'):
            with self.assertRaises(ValueError): links.resolve_http_link(href, BASE)

    def test_crawl_records_narrow_policy_and_report_note_without_score_rule_changes(self):
        body = source('guide/chapter', 'guide//chapter')
        def response(url, **kwargs):
            return http.Response(url, url, 200, {'content-type': 'text/html'}, body if url == BASE else source(), 1)
        with mock.patch.object(scan, 'gather_context', return_value={}), \
                mock.patch.object(crawl_site, 'discover', return_value=[BASE] + [target for _, target in CASES[:2]]), \
                mock.patch.object(http, 'fetch', side_effect=response), \
                mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            result = crawl_site.crawl(BASE, max_pages=3, concurrency=1, detect_dupes=False)
        self.assertEqual(links.RESOLUTION_BASIS,
                         json.loads(crawl_site.render_json(result))['link_resolution_basis'])
        self.assertEqual(3, result['pages_scanned'])
        self.assertEqual(2, result['graph']['internal_edges'])
        self.assertIn('Relative anchor paths preserve repeated separators', crawl_site.render_markdown(result))
        del result['link_resolution_basis']
        self.assertIn('historical path merging is unverified', crawl_site.render_markdown(result))

    def test_known_current_vs_missing_or_different_resolution_blocks_site_fix_claims(self):
        after = report()
        for before in (report(None), report('future')):
            before['overall_score'] = 90
            for left, right in ((before, after), (after, before)):
                delta = diff_scan.diff_reports(left, right)
                self.assertEqual('incomparable', delta['comparison']['status'])
                self.assertTrue(any('link-resolution policy' in reason for reason in delta['comparison']['reasons']))

    def test_matching_policy_and_legacy_pairs_do_not_gain_a_false_gap(self):
        for value in (report(), report(None)):
            self.assertEqual('comparable', diff_scan.diff_reports(value, copy.deepcopy(value))['comparison']['status'])


if __name__ == '__main__': unittest.main()
