"""Ambiguous JSON cannot silently replace recorded acquisition evidence."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diff_scan
import mcp_server
import plan
from test_diff_scope import report, FINDING
from test_plan_automation_eligibility import baseline


class TestReportDuplicateKeys(unittest.TestCase):
    def test_flat_nested_escaped_and_identical_duplicates_are_rejected(self):
        payloads = ('{"status":503,"status":200}',
                    '{"meta":{"response_truncated":true,"response_truncated":false}}',
                    r'{"status":503,"\u0073tatus":200}',
                    '{"status":200,"status":200}',
                    '{"secret-token":1,"secret-token":2}')
        for raw in payloads:
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'report.json'
                path.write_text(raw, encoding='utf-8')
                for load in (lambda: plan._load_json(str(path)),
                             lambda: diff_scan._decode_report_json(raw, 'Later report')):
                    with self.assertRaisesRegex(ValueError, '(?i)duplicate') as stopped:
                        load()
                    self.assertNotIn('secret-token', str(stopped.exception))
                self.assertEqual(raw, path.read_text(encoding='utf-8'))

    def test_repeated_keys_in_separate_objects_and_json_text_evidence_remain_valid(self):
        data = {'findings': [{'title': 'A', 'evidence': '{"status":503,"status":200}'},
                             {'title': 'B'}], 'meta': {'title': 'Metadata'}}
        raw = json.dumps(data)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'report.json'
            path.write_text(raw, encoding='utf-8')
            self.assertEqual(data, plan._load_json(str(path)))
            self.assertEqual(data, diff_scan._decode_report_json(raw))

    def test_duplicate_acquisition_flags_cannot_produce_diff_claims_or_mcp_results(self):
        before = report(['technical'], findings=[dict(FINDING)], score=94)
        before['status'] = 200
        after = report(['technical'], findings=[], score=100)
        after['status'] = 200
        valid = json.dumps(before)
        ambiguous = '{"status":503,' + json.dumps(after)[1:]
        for side in ('Earlier report', 'Later report'):
            with self.subTest(side=side), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                old, new, output = root / 'before.json', root / 'after.json', root / 'diff.json'
                left, right = (ambiguous, valid) if side == 'Earlier report' else (valid, ambiguous)
                old.write_text(left, encoding='utf-8')
                new.write_text(right, encoding='utf-8')
                output.write_bytes(b'previous output')
                with mock.patch.object(diff_scan, 'diff_reports', wraps=diff_scan.diff_reports) as compare, \
                        contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
                    code = diff_scan.main([str(old), str(new), '-o', str(output),
                                           '--fail-on-regression', '--require-comparable'])
                self.assertEqual(2, code)
                self.assertEqual('', out.getvalue())
                self.assertIn(side, err.getvalue())
                self.assertIn('duplicate', err.getvalue().lower())
                compare.assert_not_called()
                self.assertEqual(b'previous output', output.read_bytes())
                self.assertEqual((left, right), (old.read_text(), new.read_text()))
                with self.assertRaisesRegex(ValueError, '(?i)duplicate'):
                    mcp_server._diff(left, right)

    def test_planner_rejects_duplicate_status_before_inventory_or_output(self):
        data = baseline()
        raw = '{"status":503,' + json.dumps(data)[1:]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'index.html').write_text('<html lang="en"></html>', encoding='utf-8')
            self.assertTrue(next(a for a in plan.build_plan(data, str(root))['actions']
                                 if a['artifact'] == 'viewport')['automation_eligibility']['eligible'])
            source, output = root / 'report.json', root / 'plan.json'
            source.write_text(raw, encoding='utf-8')
            output.write_bytes(b'previous output')
            with mock.patch.object(plan, 'inventory', wraps=plan.inventory) as inventory, \
                    contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
                code = plan.main([str(source), '--repo', str(root), '-o', str(output)])
            self.assertEqual(2, code)
            self.assertEqual('', out.getvalue())
            self.assertIn('duplicate', err.getvalue().lower())
            inventory.assert_not_called()
            self.assertEqual(b'previous output', output.read_bytes())
            self.assertEqual(raw, source.read_text(encoding='utf-8'))
