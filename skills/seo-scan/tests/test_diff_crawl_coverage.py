"""Isolate recorded crawl coverage gaps from unrelated malformed evidence."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diff_scan
import mcp_server
from lib import links
try:
    from .test_diff_scope import ALL, FINDING, report, invoke
except ImportError:
    from test_diff_scope import ALL, FINDING, report, invoke


class TestCrawlCoverageDiff(unittest.TestCase):
    def test_independent_coverage_gaps_withhold_site_fix_claims(self):
        gaps = [{key: True} for key in (
            'js_comparison_unverified', 'sitemap_discovery_unverified', 'llms_txt_unverified',
            'canonical_comparison_unverified', 'schema_extraction_unverified',
            'hreflang_comparison_unverified')]
        gaps += [{'anchor_base': {'basis': links.DOCUMENT_BASE_BASIS, 'status': 'unverified'}},
                 {'scan_settings': {'schema_extraction_reviewed': False}}]
        for gap in gaps:
            before = {'site': 'https://example.test/', 'overall_score': 0,
                      'homepage': report(ALL, findings=[FINDING], score=0),
                      'crawl': {'pages': [{'url': 'https://example.test/inner',
                          'scan_scope': {'requested': ALL, 'completed': ALL}}],
                          'pages_scanned': 1, 'recurring': []}}
            after = copy.deepcopy(before)
            after['overall_score'] = 100
            after['homepage'] = report(ALL)
            self.assertEqual('comparable', diff_scan.diff_reports(before, after)['comparison']['status'])
            self.assertEqual(0, invoke(before, after, '--require-comparable', '--fail-on-regression')[0])
            for side in ('earlier', 'later'):
                old, new = copy.deepcopy(before), copy.deepcopy(after)
                (old if side == 'earlier' else new)['crawl']['pages'][0].update(copy.deepcopy(gap))
                with self.subTest(gap=gap, side=side):
                    original = copy.deepcopy((old, new))
                    result = diff_scan.diff_reports(old, new)
                    self.assertEqual('incomparable', result['comparison']['status'])
                    self.assertIsNone(result['score_delta'])
                    self.assertIsNone(result['regression'])
                    for field in ('added', 'resolved', 'improved', 'worsened'):
                        self.assertEqual([], result[field])
                    self.assertEqual(result, mcp_server._diff(json.dumps(old), json.dumps(new)))
                    self.assertEqual(2, invoke(old, new, '--fail-on-regression')[0])
                    self.assertEqual(original, (old, new))


if __name__ == '__main__':
    unittest.main()
