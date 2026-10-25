"""Optional not-selected receipts cannot contradict requested execution scope."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diff_scan
import plan
from lib.report import CATEGORY_LABELS, Report, recorded_scan_scope
from test_plan_automation_eligibility import baseline, RULE, URL


class TestScopeSelectionConsistency(unittest.TestCase):
    def test_requested_and_completed_require_nonempty_requested_and_list_types(self):
        invalid = [(value, []) for value in (None, 'technical', [], {}, ())]
        invalid += [(['technical'], value) for value in (None, 'technical', (), {}, False)]
        for requested, completed in invalid:
            with self.subTest(requested=requested, completed=completed):
                self.assertIsNone(recorded_scan_scope({'scan_scope': {
                    'requested': requested, 'completed': completed}}))

    def test_valid_complements_and_absent_legacy_field_preserve_scope(self):
        for requested, completed in ((['technical'], ['technical']),
                (list(CATEGORY_LABELS), list(CATEGORY_LABELS)),
                (['technical', 'schema'], ['technical']), (['technical'], [])):
            scope = {'requested': requested, 'completed': completed}
            meta = {'scan_scope': scope}
            self.assertEqual((requested, completed), recorded_scan_scope(meta))
            scope['not_selected'] = [name for name in reversed(CATEGORY_LABELS) if name not in requested]
            original = copy.deepcopy(meta)
            self.assertEqual((requested, completed), recorded_scan_scope(meta))
            self.assertEqual(original, meta)

    def test_malformed_or_contradictory_selection_cannot_certify_scope(self):
        invalid = (None, False, {}, 'content', [], ['technical'], ['content'],
                   ['content', 'schema', 'geo', 'geo'], ['content', 'schema', 'future'],
                   ['content', 'schema', {}], ['content', 'schema', None])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'index.html').write_text('<html lang="en"></html>', encoding='utf-8')
            for skipped in invalid:
                with self.subTest(not_selected=skipped):
                    bad, good = baseline(), baseline()
                    bad['meta']['scan_scope']['not_selected'] = skipped
                    good['findings'] = []
                    original = copy.deepcopy(bad)
                    self.assertIsNone(recorded_scan_scope(bad['meta']))
                    self.assertEqual('Reported-findings score', Report(URL, meta=bad['meta']).score_label())
                    result = diff_scan.diff_reports(bad, good)
                    self.assertNotEqual('comparable', result['comparison']['status'])
                    action = next(a for a in plan.build_plan(bad, str(root))['actions'] if a['rule_id'] == RULE)
                    self.assertFalse(action['automation_eligibility']['eligible'])
                    self.assertTrue(action['likely_files'])
                    paths = [root / name for name in ('before.json', 'after.json')]
                    for path, report in zip(paths, (bad, good)):
                        path.write_text(json.dumps(report), encoding='utf-8')
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        self.assertEqual(2, diff_scan.main([str(p) for p in paths] +
                            ['--format', 'json', '--require-comparable', '--fail-on-regression']))
                    self.assertEqual(original, bad)


if __name__ == '__main__':
    unittest.main()
