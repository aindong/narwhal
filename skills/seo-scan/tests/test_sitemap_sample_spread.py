"""Sitemap request budgets cover distinct URLs across the parsed candidate list."""
import copy
from html import escape
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import validate_sitemap as sitemap
from lib import http

ROOT = 'https://example.test/'


def analyze(urls, sample, bad=None):
    xml = ('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' +
           ''.join('<url><loc>' + escape(url) + '</loc></url>' for url in urls) + '</urlset>').encode()
    with mock.patch.object(http, 'normalize_url', side_effect=lambda value: value), \
            mock.patch.object(http, 'assert_public_host'), \
            mock.patch.object(http, 'fetch_bytes', return_value=(xml, None)), \
            mock.patch.object(http, 'head', side_effect=lambda url, **kw: (404 if url == bad else 200, None)) as head:
        result = sitemap.analyze(ROOT + 'sitemap.xml', sample=sample)
    return result, [call.args[0] for call in head.call_args_list]


class TestSitemapSampleSpread(unittest.TestCase):
    def test_awkward_budget_finds_a_failing_url_at_the_tail(self):
        urls = [ROOT + str(i) for i in range(19)]
        result, calls = analyze(urls, 10, bad=urls[-1])
        self.assertEqual([urls[i] for i in range(0, 19, 2)], calls)
        self.assertEqual([{'url': urls[-1], 'status': 404, 'error': None}], result['broken_sample'])
        self.assertIn(urls[-1], sitemap.render_markdown(result))

    def test_duplicate_entries_do_not_consume_repeated_head_requests(self):
        urls = [ROOT + 'a'] * 20 + [ROOT + 'b', ROOT + 'c']
        result, calls = analyze(urls, 10)
        self.assertEqual([ROOT + 'a', ROOT + 'b', ROOT + 'c'], calls)
        self.assertEqual(22, result['total_urls'])  # raw sitemap facts remain raw
        self.assertEqual({'basis': 'unique_exact_urls_evenly_spaced_v1',
                          'eligible_unique_urls': 3, 'requested': 10}, result['sample_selection'])

    def test_budget_cardinality_order_and_endpoints_across_edge_cases(self):
        for size in (0, 1, 2, 9, 10, 11, 19, 25):
            for budget in (0, 1, 2, 10, 100):
                with self.subTest(size=size, budget=budget):
                    urls = [ROOT + str(i) for i in range(size)]
                    result, calls = analyze(urls, budget)
                    self.assertEqual(min(size, budget), len(calls))
                    self.assertEqual(len(calls), len(set(calls)))
                    self.assertEqual(sorted(calls, key=urls.index), calls)
                    self.assertEqual(calls, [entry['url'] for entry in result['sample']])
                    if calls:
                        self.assertEqual(urls[0], calls[0])
                    if len(calls) > 1:
                        self.assertEqual(urls[-1], calls[-1])

    def test_exact_url_distinctions_remain_and_invalid_locs_are_not_probed(self):
        valid = [ROOT + 'a', ROOT + 'a/', ROOT + 'A', ROOT + 'a?x=1&y=2']
        result, calls = analyze(valid + ['relative', 'https://other.test/'] + valid, 100)
        self.assertEqual(valid, calls)
        self.assertEqual(10, result['total_urls'])
        self.assertEqual(4, result['sample_selection']['eligible_unique_urls'])

    def test_policy_note_requires_a_known_consistent_receipt_and_does_not_mutate(self):
        result, _ = analyze([ROOT + str(i) for i in range(19)], 10)
        original = copy.deepcopy(result)
        text = sitemap.render_markdown(result)
        self.assertIn('19 distinct eligible URL strings', text)
        self.assertIn('Not random or statistically representative', text)
        self.assertEqual(original, result)
        for receipt in (None, {}, {'basis': 'future'},
                        dict(result['sample_selection'], eligible_unique_urls=1),
                        dict(result['sample_selection'], requested=11),
                        dict(result['sample_selection'], requested=True)):
            legacy = dict(result, sample_selection=receipt)
            self.assertNotIn('**Sampling policy:**', sitemap.render_markdown(legacy))


if __name__ == '__main__':
    unittest.main()
