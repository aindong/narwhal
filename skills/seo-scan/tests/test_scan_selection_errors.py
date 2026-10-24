"""Auditor-selection mistakes must fail before HTTP without hiding code defects."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import scan
from lib.report import Report

URL = 'https://example.test/'


class TestScanSelectionErrors(unittest.TestCase):
    def test_invalid_api_entries_are_bounded_value_errors_before_http(self):
        for entry in ('unknown', '', 'schema\nsecret', 'x' * 10000, None, {}, ['schema']):
            with self.subTest(entry=type(entry).__name__), mock.patch.object(scan.http, 'fetch') as fetch:
                with self.assertRaises(scan.AuditorSelectionError) as caught:
                    scan.scan(URL, only=['schema', entry])
                self.assertLess(len(str(caught.exception)), 150)
                self.assertNotIn('secret', str(caught.exception))
                fetch.assert_not_called()

    def test_cli_errors_preserve_existing_artifact_and_emit_no_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'report.json'
            output.write_bytes(b'prior evidence')
            for selection in ('unknown', 'schema,unknown', 'schema,', ',schema', ',', ' '):
                out, err = io.StringIO(), io.StringIO()
                with mock.patch.object(scan.http, 'fetch') as fetch, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = scan.main([URL, '--no-config', '--only', selection, '--format', 'json', '-o', str(output)])
                self.assertEqual(2, code)
                self.assertEqual('', out.getvalue())
                self.assertIn('Unknown auditor', err.getvalue())
                self.assertNotIn('Traceback', err.getvalue())
                self.assertEqual(b'prior evidence', output.read_bytes())
                fetch.assert_not_called()

    def test_mcp_uses_the_same_nonempty_selection_contract(self):
        for selection in ('unknown', 'schema,', ',schema', ',', ' '):
            with mock.patch.object(scan.http, 'fetch') as fetch:
                with self.assertRaises(scan.AuditorSelectionError):
                    mcp_server._scan(URL, only=selection)
                fetch.assert_not_called()
        with mock.patch.object(scan, 'scan', return_value=Report(URL)) as run:
            mcp_server._scan(URL, only='schema, technical,schema')
            self.assertEqual(['schema', 'technical', 'schema'], run.call_args.kwargs['only'])
            mcp_server._scan(URL, only='')
            self.assertIsNone(run.call_args.kwargs['only'])

    def test_cli_does_not_convert_internal_value_errors_into_selection_errors(self):
        with mock.patch.object(scan, 'scan', side_effect=ValueError('auditor defect')):
            with self.assertRaisesRegex(ValueError, 'auditor defect'):
                scan.main([URL, '--no-config', '--only', 'schema'])


if __name__ == '__main__':
    unittest.main()
