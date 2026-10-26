"""Oversized comparison inputs cannot produce verdicts or overwrite output."""
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
from test_diff_scope import report


class TestDiffReadBudget(unittest.TestCase):
    def test_stream_reads_are_bounded_and_overflow_precedes_utf8_decode(self):
        case = self
        class Stream(io.BytesIO):
            def read(self, size=-1):
                case.assertGreaterEqual(size, 0)
                case.assertLessEqual(size, 33)
                return super().read(size)
        for payload in (b'{}' + b' ' * 31, json.dumps({'x': 'é' * 20}, ensure_ascii=False).encode('utf-8')):
            with self.subTest(payload_bytes=len(payload)), \
                    mock.patch.object(diff_scan, 'MAX_REPORT_BYTES', 32), \
                    mock.patch('builtins.open', return_value=Stream(payload)), \
                    self.assertRaisesRegex(ValueError, 'Earlier report.*safety limit'):
                diff_scan._load('controlled.json', 'Earlier report')

    def test_utf8_exact_byte_limit_and_invalid_encoding_controls(self):
        data = {'label': 'é'}
        raw = json.dumps(data, ensure_ascii=False).encode('utf-8')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'report.json'
            with mock.patch.object(diff_scan, 'MAX_REPORT_BYTES', len(raw)):
                path.write_bytes(raw)
                self.assertEqual(data, diff_scan._load(str(path)))
                path.write_bytes(raw + b' ')
                with self.assertRaisesRegex(ValueError, 'safety limit'):
                    diff_scan._load(str(path))
                path.write_bytes(b'\xff')
                with self.assertRaisesRegex(ValueError, '(?i)utf-8'):
                    diff_scan._load(str(path))

    def test_either_oversized_input_exits_before_comparison_or_output_changes(self):
        raw = json.dumps(report(['technical'])).encode('utf-8')
        for side in (None, 'Earlier report', 'Later report'):
            with self.subTest(side=side), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                old, new, output = root / 'before.json', root / 'after.json', root / 'diff.json'
                old.write_bytes(raw + (b' ' if side == 'Earlier report' else b''))
                new.write_bytes(raw + (b' ' if side == 'Later report' else b''))
                output.write_bytes(b'previous output')
                originals = old.read_bytes(), new.read_bytes()
                with mock.patch.object(diff_scan, 'MAX_REPORT_BYTES', len(raw)), \
                        mock.patch.object(diff_scan, 'diff_reports', wraps=diff_scan.diff_reports) as compare, \
                        mock.patch.object(diff_scan, '_write_output', wraps=diff_scan._write_output) as writer, \
                        contextlib.redirect_stdout(io.StringIO()) as out, \
                        contextlib.redirect_stderr(io.StringIO()) as err:
                    code = diff_scan.main([str(old), str(new), '--format', 'json', '-o', str(output),
                                           '--fail-on-regression', '--require-comparable'])
                if side is None:
                    self.assertEqual(0, code)
                    self.assertEqual('', err.getvalue())
                    compare.assert_called_once()
                    writer.assert_called_once()
                    self.assertEqual('comparable', json.loads(output.read_text())['comparison']['status'])
                else:
                    self.assertEqual(2, code)
                    self.assertEqual('', out.getvalue())
                    self.assertIn(side, err.getvalue())
                    self.assertIn('safety limit', err.getvalue())
                    compare.assert_not_called()
                    writer.assert_not_called()
                    self.assertEqual(b'previous output', output.read_bytes())
                self.assertEqual(originals, (old.read_bytes(), new.read_bytes()))
