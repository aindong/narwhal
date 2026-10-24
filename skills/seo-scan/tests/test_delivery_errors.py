"""Report delivery failures cannot claim success or replace PDFs during rendering."""
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit
import scan
from lib import report

URL = 'https://example.test/'


def deliver(*args, **kwargs):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = report.deliver(*args, **kwargs)
    return code, out.getvalue(), err.getvalue()


class TestDeliveryErrors(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_text_formats_preserve_utf8_content_and_truncate_distinct_files(self):
        for fmt in ('markdown', 'json', 'html'):
            target = self.root / fmt
            target.write_bytes(b'old' * 1000)
            content = 'Controlled café — report\n'
            code, out, err = deliver(fmt, str(target), content)
            self.assertEqual(0, code)
            self.assertIn('Wrote ' + fmt, out)
            self.assertEqual('', err)
            self.assertEqual(content, target.read_text(encoding='utf-8'))
        self.assertEqual((0, 'stdout report\n', ''), deliver('markdown', None, 'stdout report'))

    def test_encoding_failure_and_missing_parent_do_not_claim_a_save(self):
        target = self.root / 'report.json'
        target.write_bytes(b'prior report')
        code, out, err = deliver('json', str(target), '\ud800')
        self.assertEqual((2, ''), (code, out))
        self.assertIn('UTF-8', err)
        self.assertEqual(b'prior report', target.read_bytes())
        code, out, err = deliver('html', str(self.root / 'missing' / 'report.html'), 'html')
        self.assertEqual((2, ''), (code, out))
        self.assertIn('output', err)
        self.assertNotIn('Traceback', err)

    def test_pdf_engine_partial_write_failure_preserves_final_destination(self):
        target = self.root / 'report.pdf'
        target.write_bytes(b'prior PDF')
        staged = []
        def fail(html, path):
            staged.append(path)
            self.assertNotEqual(str(target), path)
            Path(path).write_bytes(b'partial PDF')
            raise OSError('controlled engine failure')
        with mock.patch.object(report, 'pdf_from_html', side_effect=fail):
            code, out, err = deliver('pdf', str(target), '<html>report</html>')
        self.assertEqual((2, ''), (code, out))
        self.assertIn('controlled engine failure', err)
        self.assertEqual(b'prior PDF', target.read_bytes())
        self.assertTrue(all(not Path(p).exists() for p in staged))

    def test_pdf_success_is_exact_binary_and_no_engine_fallback_uses_actual_path(self):
        target = self.root / 'report.pdf'
        def pdf(html, path):
            Path(path).write_bytes(b'%PDF-1.7\n\x00\xff')
            return True
        with mock.patch.object(report, 'pdf_from_html', side_effect=pdf):
            self.assertEqual(0, deliver('pdf', str(target), '<html></html>')[0])
        self.assertEqual(b'%PDF-1.7\n\x00\xff', target.read_bytes())
        def unavailable(html, path):
            Path(path).write_bytes(b'partial unavailable engine output')
            return False
        with mock.patch.object(report, 'pdf_from_html', side_effect=unavailable):
            code, out, err = deliver('pdf', str(target), '<html>fallback</html>')
        self.assertEqual((0, ''), (code, out))
        self.assertIn('No PDF engine available', err)
        self.assertEqual('<html>fallback</html>', target.with_suffix('.html').read_text(encoding='utf-8'))
        self.assertEqual(b'%PDF-1.7\n\x00\xff', target.read_bytes())

    def test_scan_and_audit_cli_delivery_error_takes_precedence_over_score_gate(self):
        page = report.Report(URL)
        data = {'page': page, 'site_result': {'avg_score': 0}}
        outpath = self.root / 'missing' / 'report.json'
        for module, function, value in ((scan, 'scan', page), (audit, 'run', data)):
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(module, function, return_value=value), \
                    mock.patch.object(audit, 'render_json', return_value='{}'), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = module.main([URL, '--no-config', '--format', 'json', '-o', str(outpath), '--fail-under', '101'])
            self.assertEqual(2, code)
            self.assertEqual('', out.getvalue())
            self.assertIn('output', err.getvalue())
            self.assertNotIn('below', err.getvalue())
            self.assertFalse(outpath.exists())

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'named pipes unavailable')
    def test_fifo_output_is_rejected_without_blocking(self):
        fifo = self.root / 'pipe'
        os.mkfifo(fifo)
        reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
        try:
            code, out, err = deliver('json', str(fifo), '{}')
        finally:
            os.close(reader)
        self.assertEqual((2, ''), (code, out))
        self.assertIn('regular file', err)


if __name__ == '__main__':
    unittest.main()
