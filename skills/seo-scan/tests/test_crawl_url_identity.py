"""Crawl/graph address identity must not hide distinct observed page URLs."""
from collections import Counter
import copy
from html import escape
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import crawl_site as crawl
import diff_scan
from lib import hreflang, http, sitegraph
from lib.report import Report

BASE = 'https://example.test/'
VARIANTS = [BASE + suffix for suffix in ('guide', 'guide/', 'guide;v=1', 'guide;v=2')]


def links(*urls):
    return [{'url': url, 'internal': True} for url in urls]


def graph():
    return sitegraph.analyze(BASE, [BASE] + VARIANTS, {BASE: links(VARIANTS[0])}, [], False)


def discovered(locations, limit=20):
    xml = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(
        '<url><loc>' + escape(url) + '</loc></url>' for url in locations) + '</urlset>'
    sample = []
    with mock.patch.object(crawl.http, 'fetch_bytes', return_value=(xml.encode('utf-8'), None)) as fetch, \
            mock.patch.object(crawl.http, 'fetch', side_effect=AssertionError('No fallback needed')), \
            mock.patch.object(socket, 'socket', side_effect=AssertionError('No network')):
        result = crawl.discover(BASE, allow_private=False, timeout=1, limit=limit,
                                robots_txt='Sitemap: ' + BASE + 'sitemap.xml', discovered_sitemap=sample)
    fetch.assert_called_once()
    return result, sample


class TestCrawlURLIdentity(unittest.TestCase):
    def test_path_separators_and_semicolon_data_are_distinct(self):
        self.assertEqual(4, len({sitegraph.norm(url) for url in VARIANTS}))
        for url in VARIANTS:
            self.assertEqual(url, sitegraph.norm(url))

    def test_query_value_slashes_empty_delimiters_order_and_case_survive(self):
        variants = [BASE + tail for tail in ('p?next=/', 'p?next=', 'p?', 'p',
                    'p?x=A', 'p?x=a', 'p?x=1&y=2', 'p?y=2&x=1')]
        self.assertEqual(8, len({sitegraph.norm(url) for url in variants}))
        for url in variants:
            self.assertEqual(url, sitegraph.norm(url))

    def test_only_fragments_scheme_host_case_and_empty_root_group(self):
        for alias in ('HTTPS://EXAMPLE.TEST', BASE, BASE + '#part', BASE + '#'):
            self.assertEqual(BASE, sitegraph.norm(alias))
        self.assertNotEqual(sitegraph.norm(BASE + 'Guide'), sitegraph.norm(BASE + 'guide'))
        self.assertNotEqual(sitegraph.norm(BASE.replace('https:', 'http:')), sitegraph.norm(BASE))
        self.assertNotEqual(sitegraph.norm(BASE + 'a%23b'), sitegraph.norm(BASE + 'a#b'))

    def test_userinfo_case_is_not_accidentally_lowercased_with_host(self):
        url = 'HTTPS://Owner:SeCrEt@EXAMPLE.TEST/a;v=1/?x=/#part'
        self.assertEqual('https://Owner:SeCrEt@example.test/a;v=1/?x=/', sitegraph.norm(url))

    def test_five_supplied_pages_are_five_graph_nodes_not_two(self):
        result = graph()
        self.assertEqual(5, result['pages_in_graph'])
        self.assertEqual(1, result['internal_edges'])
        self.assertEqual(1, result['max_depth'])
        self.assertEqual(sorted(VARIANTS[1:]), result['zero_inbound'])
        self.assertEqual(sorted(VARIANTS[1:]), result['unreachable_from_start'])
        self.assertEqual([{'url': VARIANTS[0], 'inbound': 1}], result['top_linked'])
        self.assertEqual(sitegraph.URL_IDENTITY_BASIS, result['url_identity_basis'])

    def test_deep_path_variants_are_not_shortcut_through_an_alias(self):
        nodes = [BASE] + [BASE + suffix for suffix in ('a', 'b', 'c', 'guide', 'guide/')]
        paths = {BASE: links(nodes[1], nodes[4]), nodes[1]: links(nodes[2]),
                 nodes[2]: links(nodes[3]), nodes[3]: links(nodes[5])}
        result = sitegraph.analyze(BASE, nodes, paths, [], False)
        self.assertEqual([{'url': nodes[5], 'depth': 4}], result['deep_pages'])
        self.assertEqual(4, result['max_depth'])

    def test_link_to_one_variant_does_not_hide_unscanned_orphan_variants(self):
        result = sitegraph.analyze(BASE, [BASE, VARIANTS[0]], {BASE: links(VARIANTS[0])}, VARIANTS, True)
        self.assertEqual(VARIANTS[1:], result['orphans']['candidates'])
        self.assertEqual(3, result['orphans']['total'])

    def test_orphan_fragment_aliases_count_once_but_slash_and_parameter_variants_remain(self):
        urls = [BASE + suffix for suffix in ('orphan#one', 'orphan#two', 'orphan/', 'orphan;v=1')]
        result = sitegraph.analyze(BASE, [BASE], {}, urls, True)
        self.assertEqual([urls[0], urls[2], urls[3]], result['orphans']['candidates'])
        self.assertEqual(3, result['orphans']['total'])

    def test_no_additional_orphans_does_not_claim_crawled_urls_were_linked(self):
        result = sitegraph.analyze(BASE, [BASE, VARIANTS[0], VARIANTS[1]],
                                   {BASE: links(VARIANTS[0])}, [VARIANTS[1]], True)
        self.assertEqual([], result['orphans']['candidates'])
        self.assertEqual([VARIANTS[1]], result['zero_inbound'])
        text = '\n'.join(sitegraph.render_markdown(result))
        self.assertIn('this does not prove every sitemap URL is linked', text)
        self.assertNotIn('every checked sitemap URL is linked', text)

    def test_discovery_preserves_source_variants_and_sitemap_attribution(self):
        urls = VARIANTS + [BASE + 'p?next=/', BASE + 'p?next=', BASE + 'p?', BASE + 'p']
        result, sample = discovered(urls)
        self.assertEqual([BASE] + urls, result)
        self.assertEqual(urls, sample)

    def test_discovery_fragment_aliases_do_not_consume_page_slots(self):
        urls = [VARIANTS[0] + '#one', VARIANTS[0] + '#two', VARIANTS[1], VARIANTS[2]]
        result, sample = discovered(urls, limit=4)
        self.assertEqual([BASE, VARIANTS[0], VARIANTS[1], VARIANTS[2]], result)
        self.assertEqual(VARIANTS[:3], sample)

    def test_discovery_root_base_override_order_and_asset_filter_stay_bounded(self):
        result, sample = discovered([BASE + '#part', BASE + 'image.png'] + VARIANTS, limit=3)
        self.assertEqual([BASE, VARIANTS[0], VARIANTS[1]], result)
        self.assertEqual([BASE, VARIANTS[0], VARIANTS[1]], sample)

    def test_link_fallback_dedup_preserves_trailing_query_value_slashes(self):
        html = '<a href="/p?next=/">One</a><a href="/p?next=">Two</a>'
        response = http.Response(BASE, BASE, 200, {'content-type': 'text/html'}, html, 0)
        with mock.patch.object(crawl.Discovery, 'read', return_value=None), \
                mock.patch.object(crawl.http, 'fetch', return_value=response):
            result = crawl.discover(BASE, allow_private=False, timeout=1, limit=3, robots_txt='')
        self.assertEqual([BASE, BASE + 'p?next=/', BASE + 'p?next='], result)

    def test_hreflang_self_reference_does_not_match_a_trailing_slash_variant(self):
        result = hreflang.analyze({VARIANTS[1]: [{'lang': 'en', 'href': VARIANTS[0]}]})
        self.assertEqual([VARIANTS[1]], result['missing_self'])
        self.assertEqual(1, result['unverified_targets'])
        self.assertEqual([], result['missing_return'])

    def test_hreflang_parameter_variants_preserve_precise_missing_return_pair(self):
        one, two = VARIANTS[2:]
        result = hreflang.analyze({one: [{'lang': 'en', 'href': one}, {'lang': 'fr', 'href': two}],
                                  two: [{'lang': 'fr', 'href': two}]})
        self.assertEqual([{'page': one, 'target': two, 'lang': 'fr'}], result['missing_return'])
        self.assertEqual([], result['missing_self'])

    def test_hreflang_probe_keeps_same_host_cap_and_fragment_dedup(self):
        pages = {VARIANTS[0]: [{'lang': 'fr', 'href': VARIANTS[1] + '#one'},
                              {'lang': 'fr', 'href': VARIANTS[1] + '#two'},
                              {'lang': 'de', 'href': VARIANTS[2]},
                              {'lang': 'it', 'href': VARIANTS[3]},
                              {'lang': 'es', 'href': 'https://outside.test/es'}]}
        called = []
        def fetch(url): called.append(url); return '<link rel="alternate" hreflang="en" href="' + VARIANTS[0] + '">'
        result = hreflang.probe(pages, cap=2, fetch_text=fetch)
        self.assertEqual([VARIANTS[1] + '#one', VARIANTS[2]], called)
        self.assertEqual(2, len(result))

    def test_report_discloses_identity_basis_and_legacy_unknown_without_mutation(self):
        result = graph(); before = copy.deepcopy(result)
        text = '\n'.join(sitegraph.render_markdown(result))
        self.assertIn('Other path/query literals remain distinct', text)
        self.assertIn('server equivalence are not inferred', text)
        self.assertEqual(before, result)
        del result['url_identity_basis']
        self.assertIn('URL identity policy was not recorded', '\n'.join(sitegraph.render_markdown(result)))

    def test_known_current_vs_unrecorded_audit_identity_policy_blocks_fix_claims(self):
        page = Report(BASE, fetched_status=200)
        page.meta['scan_scope'] = {'requested': ['technical'], 'completed': ['technical']}
        after = {'site': BASE, 'overall_score': 100, 'homepage': json.loads(page.to_json()),
                 'crawl': {'pages': [], 'graph': graph()}}
        before = copy.deepcopy(after); before['overall_score'] = 90
        del before['crawl']['graph']['url_identity_basis']
        delta = diff_scan.diff_reports(before, after)
        self.assertEqual('incomparable', delta['comparison']['status'])
        self.assertTrue(any('URL-identity policy' in reason for reason in delta['comparison']['reasons']))
        delta = diff_scan.diff_reports(after, after)
        self.assertEqual('comparable', delta['comparison']['status'])
