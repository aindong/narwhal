"""Comparison decisions need readable, consistent explanations across interfaces."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diff_scan
import mcp_server
from lib import hreflang, links
from test_diff_scope import ALL, FINDING, invoke, report


class TestDiffExplanations(unittest.TestCase):
    def assert_explained(self, old, new, status, exit_code=2):
        saved = copy.deepcopy((old, new))
        result = diff_scan.diff_reports(old, new)
        self.assertEqual(status, result['comparison']['status'])
        reasons = result['comparison']['reasons']
        self.assertIsInstance(reasons, list)
        if status == 'comparable':
            self.assertEqual([], reasons)
        else:
            self.assertTrue(reasons)
            for reason in reasons:
                self.assertIsInstance(reason, str)
                self.assertTrue(reason.strip())
        if status == 'incomparable':
            self.assertIsNone(result['score_delta'])
            self.assertIsNone(result['regression'])
            self.assertEqual([], result['resolved'])
        self.assertEqual(result, mcp_server._diff(json.dumps(old), json.dumps(new)))
        flags = ('--require-comparable', '--fail-on-regression')
        code, text, _ = invoke(old, new, *flags)
        self.assertEqual(exit_code, code)
        self.assertTrue(text.strip())
        for reason in reasons:
            self.assertIn(reason, text)
        code, text, _ = invoke(old, new, *flags, '--format', 'json')
        self.assertEqual(exit_code, code)
        self.assertEqual(result, json.loads(text))
        self.assertEqual(saved, (old, new))
        return result

    def test_matching_execution_has_no_spurious_missing_scope_explanation(self):
        old = report(ALL, findings=[FINDING], score=94)
        new = report(ALL)
        result = self.assert_explained(old, new, 'comparable', 0)
        self.assertEqual(6, result['score_delta'])
        self.assertEqual([FINDING], result['resolved'])
        self.assert_explained(new, old, 'comparable', 1)

    def test_legacy_unknown_scope_has_a_readable_reason_and_keeps_its_gate(self):
        for earlier, later in ((None, None), (ALL, None), (None, ALL)):
            with self.subTest(earlier=earlier, later=later):
                old = report(earlier, findings=[FINDING], score=94)
                new = report(later)
                result = self.assert_explained(old, new, 'unknown')
                self.assertEqual(6, result['score_delta'])
                self.assertEqual([FINDING], result['resolved'])
                self.assertEqual(0, invoke(old, new, '--fail-on-regression')[0])

    def test_policy_gaps_have_readable_json_and_markdown_explanations(self):
        for key, basis in (('anchor_resolution_basis', links.RESOLUTION_BASIS),
                           ('hreflang_policy_basis', hreflang.EXTRACTION_BASIS)):
            with self.subTest(key=key):
                old = report(ALL, findings=[FINDING], score=94)
                old['meta'][key] = basis
                self.assert_explained(old, report(ALL), 'incomparable')
        old = {'site': 'https://example.test/', 'overall_score': 94,
               'homepage': report(ALL, findings=[FINDING], score=94),
               'crawl': {'pages': [], 'pages_scanned': 0, 'recurring': [],
                         'hreflang_acquisition_basis': hreflang.SNAPSHOT_BASIS}}
        new = copy.deepcopy(old)
        new.update(overall_score=100, homepage=report(ALL))
        new['crawl'].pop('hreflang_acquisition_basis')
        self.assert_explained(old, new, 'incomparable')

    def test_failed_and_truncated_acquisitions_explain_withheld_claims(self):
        for changes in ({'status': 503}, {'hard_fail': True}, {'response_truncated': True}):
            with self.subTest(changes=changes):
                old = report(ALL, findings=[FINDING], score=94)
                old.update(changes)
                self.assert_explained(old, report(ALL), 'incomparable')
