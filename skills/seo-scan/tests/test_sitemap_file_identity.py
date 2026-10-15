"""Sitemap fragments must not consume repeated effective-file budget slots."""

import sys
import unittest
from pathlib import Path
from unittest import mock
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import crawl_site
import validate_sitemap as validator
from lib import http, sitemap as sm
from lib.sitemap_discovery import Discovery

BASE = 'https://example.test/'
ROOT, EMPTY, GOOD = (BASE + path for path in ('sitemap.xml', 'empty.xml', 'good.xml'))
PAGE = BASE + 'page'


def xml(kind, locations):
    child = 'sitemap' if kind == 'sitemapindex' else 'url'
    return ('<' + kind + '>' + ''.join('<' + child + '><loc>' + escape(url) + '</loc></' + child + '>'
                                      for url in locations) + '</' + kind + '>').encode()


def fetcher(bodies):
    return lambda url, **kw: (bodies[url], None)


class TestSitemapFileIdentity(unittest.TestCase):
    def test_only_literal_fragment_is_removed_and_page_source_references_are_unchanged(self):
        for source, expected in (
                (GOOD + '#one#two', GOOD),
                (BASE + 'Case%23Name.xml?x=%23one&y=2#fragment', BASE + 'Case%23Name.xml?x=%23one&y=2'),
                (BASE + 'a.xml?', BASE + 'a.xml?'),
                (BASE + 'a.xml?x=one', BASE + 'a.xml?x=one')):
            with self.subTest(source=source):
                self.assertEqual(expected, sm.file_url(source))
                self.assertEqual([source], sm.usable_locations([source]))

    def test_discovery_deduplicates_before_attempt_cap_and_preserves_fetch_policy(self):
        discovery = Discovery('crawl_candidates', max_files=1)
        with mock.patch.object(http, 'fetch_bytes', return_value=(b'<urlset/>', None)) as fetch:
            self.assertEqual(('urlset', []), discovery.read(EMPTY + '#one', allow_private=True, timeout=7))
            for alias in ('#two', '#three', ''):
                self.assertIsNone(discovery.read(EMPTY + alias, allow_private=True, timeout=7))
            self.assertEqual([], discovery.receipt()['limits'])
            self.assertIsNone(discovery.read(GOOD, allow_private=True, timeout=7))
        fetch.assert_called_once_with(EMPTY, allow_private=True, timeout=7, max_bytes=5_000_000)
        receipt = discovery.receipt()
        self.assertEqual(1, receipt['attempted_files'])
        self.assertEqual(['file_attempt_budget'], receipt['limits'])
        self.assertIsNotNone(sm.recorded_discovery(receipt))

    def test_declared_alias_upgrades_optional_absence_once_without_refetch(self):
        discovery = Discovery('context_candidates')
        with mock.patch.object(http, 'fetch_bytes', return_value=(None, 'HTTP 404')) as fetch:
            discovery.read(EMPTY, allow_private=False, timeout=2)
            for alias in ('#one', '#two'):
                discovery.read(EMPTY + alias, allow_private=False, timeout=2, declared=True)
        fetch.assert_called_once()
        receipt = discovery.receipt()
        self.assertEqual((1, 0, 1), (receipt['attempted_files'], receipt['absent_files'], receipt['unverified_files']))
        self.assertEqual({'declared_unavailable': 1}, receipt['reasons'])
        self.assertEqual([EMPTY], discovery.uncertain_urls)

    def test_failed_aliases_do_not_multiply_failures_or_attempts(self):
        discovery = Discovery('crawl_candidates')
        with mock.patch.object(http, 'fetch_bytes', return_value=(None, 'HTTP 503')) as fetch:
            for alias in ('#one', '#two', ''):
                discovery.read(EMPTY + alias, allow_private=False, timeout=2, declared=True)
        fetch.assert_called_once()
        self.assertEqual(1, discovery.receipt()['unverified_files'])
        self.assertEqual({'fetch_unverified': 1}, discovery.receipt()['reasons'])

    def test_crawl_aliases_do_not_crowd_real_sibling_out_of_child_budget(self):
        aliases = [EMPTY + '#alias-' + str(i) for i in range(8)]
        bodies = {ROOT: xml('sitemapindex', aliases + [GOOD]), EMPTY: b'<urlset/>', GOOD: xml('urlset', [PAGE])}
        coverage = {}
        with mock.patch.object(http, 'fetch_bytes', side_effect=fetcher(bodies)) as fetch, \
                mock.patch.object(http, 'fetch') as fallback:
            urls = crawl_site.discover(BASE, robots_txt='', allow_private=False, timeout=2,
                                       limit=2, coverage=coverage)
        self.assertEqual([BASE, PAGE], urls)
        self.assertEqual([ROOT, EMPTY, GOOD], [call.args[0] for call in fetch.call_args_list])
        self.assertEqual(3, coverage['attempted_files'])
        self.assertEqual([], coverage['limits'])
        fallback.assert_not_called()

    def test_crawl_cap_still_applies_to_five_distinct_children(self):
        empty = [BASE + 'empty-' + str(i) + '.xml' for i in range(4)]
        refs = [empty[0] + '#one', empty[0] + '#two'] + empty[1:] + [GOOD, BASE + 'outside.xml']
        bodies = {ROOT: xml('sitemapindex', refs), GOOD: xml('urlset', [PAGE]), **{u: b'<urlset/>' for u in empty}}
        coverage = {}
        with mock.patch.object(http, 'fetch_bytes', side_effect=fetcher(bodies)) as fetch:
            urls = crawl_site.discover(BASE, robots_txt='', allow_private=False, timeout=2,
                                       limit=2, coverage=coverage)
        self.assertEqual([BASE, PAGE], urls)
        self.assertEqual([ROOT] + empty + [GOOD], [call.args[0] for call in fetch.call_args_list])
        self.assertEqual(['index_child_budget'], coverage['limits'])

    def test_validator_three_file_cap_reaches_sibling_after_fragment_aliases(self):
        bodies = {ROOT: xml('sitemapindex', [EMPTY + '#one', EMPTY + '#two', GOOD]),
                  EMPTY: b'<urlset/>', GOOD: xml('urlset', [PAGE + '#section'])}
        with mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, 'fetch_bytes', side_effect=fetcher(bodies)) as fetch:
            result = validator.analyze(ROOT, max_sitemaps=3, sample=0)
        self.assertEqual(1, result['total_urls'])
        self.assertEqual(3, result['sitemaps_attempted'])
        self.assertNotIn('truncated', result)
        self.assertEqual([ROOT, EMPTY, GOOD], [call.args[0] for call in fetch.call_args_list])

    def test_validator_remaining_count_collapses_aliases_not_query_or_encoded_delimiters(self):
        distinct = [GOOD + '?edition=1', GOOD + '?edition=2', BASE + 'good%23part.xml']
        refs = [EMPTY + '#one', EMPTY + '#two'] + distinct + [distinct[0] + '#again']
        bodies = {ROOT: xml('sitemapindex', refs), EMPTY: b'<urlset/>'}
        with mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, 'fetch_bytes', side_effect=fetcher(bodies)):
            result = validator.analyze(ROOT, max_sitemaps=2, sample=0)
        self.assertEqual(3, result['truncated'])
        self.assertEqual(2, result['sitemaps_attempted'])

    def test_validator_fragment_cycle_does_not_hide_sibling_or_multiply_entries(self):
        bodies = {ROOT: xml('sitemapindex', [ROOT + '#cycle', GOOD + '#one', GOOD + '#two']),
                  GOOD: xml('urlset', [PAGE])}
        with mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, 'fetch_bytes', side_effect=fetcher(bodies)) as fetch:
            result = validator.analyze(ROOT, max_sitemaps=2, sample=0)
        self.assertEqual(1, result['total_urls'])
        self.assertEqual(2, result['sitemaps_attempted'])
        self.assertNotIn('truncated', result)
        self.assertEqual(2, fetch.call_count)

    def test_fragment_identity_does_not_grant_private_host_access(self):
        discovery = Discovery('crawl_candidates')
        with mock.patch.object(http, '_requests_safe') as requests, \
                mock.patch.object(http, '_urllib_safe_open') as urllib:
            self.assertIsNone(discovery.read('http://127.0.0.1/private.xml#alias',
                                             allow_private=False, timeout=2))
        requests.assert_not_called()
        urllib.assert_not_called()
        self.assertEqual({'fetch_unverified': 1}, discovery.receipt()['reasons'])


if __name__ == '__main__':
    unittest.main()
