"""A changed crawl population cannot prove an overall site-score improvement."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diff_scan
import mcp_server
from lib.report import Report
try:
    from .test_diff_scope import invoke
except ImportError:
    from test_diff_scope import invoke

URL = 'https://example.test/'


def audit(urls, score=60):
    page = Report(URL, fetched_status=200)
    page.meta['scan_scope'] = {'requested': ['schema'], 'completed': ['schema']}
    return {'site': URL, 'overall_score': score, 'homepage': json.loads(page.to_json()),
            'crawl': {'pages': [{'url': url} for url in urls]}}


class TestCrawlSampleDiff(unittest.TestCase):
    def assert_withheld(self, before, after):
        original = copy.deepcopy((before, after))
        result = diff_scan.diff_reports(before, after)
        self.assertEqual('incomparable', result['comparison']['status'])
        self.assertIsNone(result['score_delta'])
        self.assertIsNone(result['regression'])
        for field in ('added', 'resolved', 'worsened', 'improved', 'new_critical_high'):
            self.assertEqual([], result[field])
        self.assertIn('page samples differ', ' '.join(result['comparison']['reasons']))
        self.assertNotIn('**Improved', diff_scan.render_markdown(result))
        self.assertEqual(original, (before, after))
        return result

    def test_removing_weak_page_cannot_become_a_measured_score_gain(self):
        before, after = audit([URL, URL + 'weak']), audit([URL], 100)
        for old, new in ((before, after), (after, before)):
            self.assert_withheld(old, new)
            self.assertEqual(2, invoke(old, new, '--fail-on-regression')[0])
            self.assertEqual(0, invoke(old, new)[0])
            self.assertIsNone(mcp_server._diff(json.dumps(old), json.dumps(new))['regression'])
        before['homepage']['meta'].pop('scan_scope')
        after['homepage']['meta'].pop('scan_scope')
        self.assert_withheld(before, after)  # known sample mismatch survives unknown legacy scope

    def test_equal_counts_different_urls_and_weighting_are_not_same_population(self):
        for urls in ([URL, URL + 'other'], [URL, URL + 'weak', URL + 'weak']):
            self.assert_withheld(audit([URL, URL + 'weak']), audit(urls))
        for path in ('Weak', 'weak/', 'weak?x=1', 'weak#fragment'):
            self.assert_withheld(audit([URL + 'weak']), audit([URL + path]))

    def test_order_does_not_change_sample_and_matching_population_keeps_gates(self):
        before = audit([URL, URL + 'weak'], 60)
        after = audit([URL + 'weak', URL], 70)
        result = diff_scan.diff_reports(before, after)
        self.assertEqual('comparable', result['comparison']['status'])
        self.assertEqual(10, result['score_delta'])
        self.assertFalse(result['regression'])
        self.assertEqual(0, invoke(before, after, '--fail-on-regression')[0])
        self.assertEqual(1, invoke(after, before, '--fail-on-regression')[0])

    def test_recorded_empty_sample_is_distinct_from_a_nonempty_one(self):
        self.assert_withheld(audit([]), audit([URL]))
        self.assertEqual('comparable', diff_scan.diff_reports(audit([]), audit([]))['comparison']['status'])

    def test_incomplete_legacy_samples_are_not_guessed_or_normalized(self):
        for crawl in (None, {}, {'pages': None}, {'pages': {}}, {'pages': [None]},
                      {'pages': [{}]}, {'pages': [{'url': ''}]}, {'pages': [{'url': 3}]},
                      {'pages': [{'url': URL}, None]}):
            old = audit([URL]); old['crawl'] = crawl
            result = diff_scan.diff_reports(old, audit([URL + 'other']))
            self.assertEqual('comparable', result['comparison']['status'])
            self.assertNotIn('page samples differ', ' '.join(result['comparison']['reasons']))
            self.assertIn('Incomplete/malformed crawl samples are not inferred', result['comparison']['basis'])


if __name__ == '__main__':
    unittest.main()
