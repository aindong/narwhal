"""Report admission limits apply to opened bytes, not just preflight metadata."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan


class TestPlanReadBudget(unittest.TestCase):
    def test_opened_stream_is_bounded_when_preflight_reports_a_smaller_file(self):
        case = self
        class Stream(io.BytesIO):
            def read(self, size=-1):
                case.assertGreaterEqual(size, 0, 'Report reads must be bounded')
                case.assertLessEqual(size, 33)
                return super().read(size)
        payloads = (b'{}' + b' ' * 31, json.dumps({'x': 'é' * 20}, ensure_ascii=False).encode('utf-8'))
        for payload in payloads:
            with self.subTest(payload_bytes=len(payload)), tempfile.TemporaryDirectory() as tmp:
                report = Path(tmp) / 'report.json'
                report.write_bytes(b'{}')
                with mock.patch.object(plan, 'MAX_REPORT_BYTES', 32), \
                        mock.patch.object(Path, 'open', return_value=Stream(payload)), \
                        self.assertRaisesRegex(ValueError, 'safety limit'):
                    plan._load_json(str(report))

    def test_exact_utf8_byte_limit_is_accepted_and_one_extra_byte_is_rejected(self):
        data = {'findings': [], 'label': 'é'}
        raw = json.dumps(data, ensure_ascii=False).encode('utf-8')
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / 'report.json'
            with mock.patch.object(plan, 'MAX_REPORT_BYTES', len(raw)):
                report.write_bytes(raw)
                self.assertEqual(data, plan._load_json(str(report)))
                report.write_bytes(raw + b' ')
                with self.assertRaisesRegex(ValueError, 'safety limit'):
                    plan._load_json(str(report))

    def test_invalid_utf8_under_budget_retains_controlled_guidance(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / 'report.json'
            report.write_bytes(b'{"label":"\xff"}')
            with mock.patch.object(plan, 'MAX_REPORT_BYTES', 32), \
                    self.assertRaisesRegex(ValueError, '(?i)utf-8'):
                plan._load_json(str(report))

    def test_grown_input_is_rejected_before_inventory_or_output_changes(self):
        original_stat = Path.stat
        def stale_stat(path, *args, **kwargs):
            value = original_stat(path, *args, **kwargs)
            return SimpleNamespace(st_mode=value.st_mode, st_size=0) if path == report else value
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, output = root / 'report.json', root / 'plan.json'
            report.write_bytes(b'{"findings":[]}' + b' ' * 32)
            output.write_bytes(b'previous output')
            with mock.patch.object(plan, 'MAX_REPORT_BYTES', 32), \
                    mock.patch.object(Path, 'stat', stale_stat), \
                    mock.patch.object(plan, 'inventory', wraps=plan.inventory) as inventory, \
                    mock.patch.object(plan, 'write_output', wraps=plan.write_output) as writer, \
                    contextlib.redirect_stdout(io.StringIO()) as out, \
                    contextlib.redirect_stderr(io.StringIO()) as err:
                code = plan.main([str(report), '--repo', str(root), '--format', 'json', '-o', str(output)])
            self.assertEqual(2, code)
            self.assertEqual('', out.getvalue())
            self.assertIn('safety limit', err.getvalue())
            inventory.assert_not_called()
            writer.assert_not_called()
            self.assertEqual(b'previous output', output.read_bytes())
