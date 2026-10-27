"""The shared writer preserves bytes and closes descriptors on setup failure."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from lib import report_output


class TestReportOutput(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / 'report'

    def test_empty_text_and_binary_outputs_remove_previous_bytes(self):
        for value in ('', b''):
            self.path.write_bytes(b'previous report')
            report_output.write_output(str(self.path), value, [])
            self.assertEqual(b'', self.path.read_bytes())

    def test_binary_report_bytes_are_not_decoded_or_transformed(self):
        value = b'%PDF-1.4\r\n\x00\xff\x80\r\n'
        report_output.write_output(str(self.path), value, [])
        self.assertEqual(value, self.path.read_bytes())

    def test_fdopen_failure_closes_descriptor_without_truncating_output(self):
        self.path.write_bytes(b'previous report')
        opened = []
        real_open = os.open

        def open_output(*args, **kwargs):
            descriptor = real_open(*args, **kwargs)
            opened.append(descriptor)
            return descriptor

        with mock.patch.object(report_output.os, 'open', side_effect=open_output), \
                mock.patch.object(report_output.os, 'fdopen', side_effect=OSError('fdopen-fault')):
            with self.assertRaisesRegex(OSError, 'fdopen-fault'):
                report_output.write_output(str(self.path), 'new report', [])
        self.assertEqual(b'previous report', self.path.read_bytes())
        self.assertEqual(1, len(opened))
        with self.assertRaises(OSError):
            os.fstat(opened[0])
