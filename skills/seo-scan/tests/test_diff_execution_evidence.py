"""Known failed or explicitly unusable execution is not improvement evidence."""
import copy
import json
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diff_scan
import mcp_server
from test_diff_scope import ALL, FINDING, report, invoke
from lib.report import recorded_execution_problem


class TestDiffExecutionEvidence(unittest.TestCase):
    def test_shared_execution_check_handles_unsupported_shapes_without_guessing(self):
        for value in (None, [], False, 'opaque'):
            self.assertIsNotNone(recorded_execution_problem(value))
        for meta in (None, [], 'unrecorded', {'response_truncated': False, 'response_partial': False}):
            self.assertIsNone(recorded_execution_problem({'meta': meta}))
        for raw in ({'response_truncated': 'false'}, {'response_partial': 0},
                    {'coverage': {'response_truncated': None}}):
            self.assertIsNotNone(recorded_execution_problem(raw))

    def test_failed_or_unusable_page_and_crawl_evidence_withholds_deltas(self):
        changes = [{'hard_fail': value} for value in (True, None, 'false', 'true', 0, [])]
        changes += [{'status': value} for value in (0, 199, 206, 300, 503, None, '200', False, 200.0)]
        changes += [{'meta': {'response_truncated': 'false'}},
                    {'meta': {'response_partial': None}},
                    {'meta': {'coverage': {'response_truncated': 0}}}]
        for change in changes:
            for kind in ('scan', 'audit', 'crawl'):
                bad = report(ALL, findings=[FINDING], score=0)
                bad.update(copy.deepcopy(change))
                if 'meta' in change:
                    bad['meta']['scan_scope'] = {'requested': ALL, 'completed': ALL}
                good = report(ALL)
                old, new = bad, good
                if kind == 'audit':
                    old = {'site': bad['url'], 'overall_score': 0, 'homepage': bad, 'crawl': {}}
                    new = {'site': good['url'], 'overall_score': 100, 'homepage': good, 'crawl': {}}
                elif kind == 'crawl':
                    old = {'site': good['url'], 'overall_score': 0, 'homepage': good,
                           'crawl': {'pages': [bad]}}
                    new = {'site': good['url'], 'overall_score': 100, 'homepage': good,
                           'crawl': {'pages': [good]}}
                for before, after in ((old, new), (new, old)):
                    with self.subTest(change=change, kind=kind, reverse=before is new):
                        original = copy.deepcopy((before, after))
                        result = diff_scan.diff_reports(before, after)
                        self.assertEqual('incomparable', result['comparison']['status'])
                        self.assertIsNone(result['score_delta'])
                        self.assertIsNone(result['regression'])
                        self.assertEqual([], result['resolved'])
                        self.assertEqual([], result['added'])
                        self.assertEqual(result, mcp_server._diff(json.dumps(before), json.dumps(after)))
                        self.assertEqual(original, (before, after))
                with self.subTest(change=change, kind=kind, gate=True):
                    self.assertEqual(2, invoke(old, new, '--require-comparable', '--fail-on-regression')[0])

    def test_absent_legacy_and_valid_success_fields_remain_comparable(self):
        for values in ({}, {'status': 200, 'hard_fail': False}, {'status': 201}, {'status': 299}):
            data = report(ALL)
            data.update(values)
            self.assertEqual('comparable', diff_scan.diff_reports(data, data)['comparison']['status'])


if __name__ == '__main__':
    unittest.main()
