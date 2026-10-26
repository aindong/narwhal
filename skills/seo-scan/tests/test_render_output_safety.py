"""Rendering must preserve the file-backed report used as its evidence."""
import contextlib
import io
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import render_report
from lib import report


class TestRenderOutputSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'report.md'
        self.original = b'# Controlled report\n\nEvidence to preserve.\n'
        self.source.write_bytes(self.original)

    def invoke(self, target=None, fmt='html', source=None):
        args = [str(source or self.source), '--format', fmt]
        if target is not None:
            args += ['-o', str(target)]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = render_report.main(args)
        return code, out.getvalue(), err.getvalue()

    def reject(self, target, fmt='html', source=None):
        code, out, err = self.invoke(target, fmt, source)
        self.assertEqual(2, code)
        self.assertEqual('', out)
        self.assertIn('input snapshot', err)
        self.assertEqual(self.original, self.source.read_bytes())

    def test_direct_relative_and_link_aliases_preserve_source(self):
        self.reject(self.source)
        previous = os.getcwd()
        try:
            os.chdir(self.root)
            self.reject('report.md')
        finally:
            os.chdir(previous)
        for kind in ('symlink', 'hardlink'):
            alias = self.root / kind
            try:
                alias.symlink_to(self.source) if kind == 'symlink' else os.link(self.source, alias)
            except OSError:
                continue
            self.reject(alias)
            self.reject(self.source, source=alias)

    def test_regular_file_stdin_rejects_html_pdf_and_link_alias_outputs(self):
        targets = [self.source]
        for kind in ('symlink', 'hardlink'):
            alias = self.root / ('stdin-' + kind)
            try:
                alias.symlink_to(self.source) if kind == 'symlink' else os.link(self.source, alias)
            except OSError:
                continue
            targets.append(alias)
        def pdf(html, path):
            Path(path).write_bytes(b'%PDF-1.7\ncontrolled')
            return True
        for fmt in ('html', 'pdf'):
            for target in targets:
                with self.subTest(fmt=fmt, target=target):
                    self.source.write_bytes(self.original)
                    with self.source.open('r', encoding='utf-8') as stdin, \
                            mock.patch.object(render_report.sys, 'stdin', stdin), \
                            mock.patch.object(report, 'pdf_from_html', side_effect=pdf):
                        self.reject(target, fmt, source='-')
            with self.source.open('r', encoding='utf-8') as stdin, \
                    mock.patch.object(render_report.sys, 'stdin', stdin), \
                    mock.patch.object(report, 'pdf_from_html', side_effect=pdf):
                self.assertEqual(0, self.invoke(self.root / ('stdin-output.' + fmt), fmt, source='-')[0])
            self.assertEqual(self.original, self.source.read_bytes())

    def test_shell_style_stdin_redirection_preserves_source(self):
        with self.source.open('rb') as stdin:
            run = subprocess.run([sys.executable, render_report.__file__, '-', '-o', str(self.source)],
                                 stdin=stdin, capture_output=True, text=True, timeout=5)
        self.assertEqual(2, run.returncode)
        self.assertEqual('', run.stdout)
        self.assertIn('input snapshot', run.stderr)
        self.assertEqual(self.original, self.source.read_bytes())
        piped = subprocess.run([sys.executable, render_report.__file__, '-', '-o', str(self.root / 'piped.html')],
                               input=self.original.decode('utf-8'), capture_output=True, text=True, timeout=5)
        self.assertEqual(0, piped.returncode)
        self.assertEqual(self.original, self.source.read_bytes())

    def test_renamed_source_identity_is_pinned_before_rendering(self):
        moved = self.root / 'moved.md'
        render = render_report.render
        def rename(*args, **kwargs):
            self.source.rename(moved)
            self.source.write_text('replacement', encoding='utf-8')
            return render(*args, **kwargs)
        with mock.patch.object(render_report, 'render', side_effect=rename):
            code, out, err = self.invoke(moved)
        self.assertEqual(2, code)
        self.assertEqual('', out)
        self.assertIn('input snapshot', err)
        self.assertEqual(self.original, moved.read_bytes())
        self.assertEqual('replacement', self.source.read_text(encoding='utf-8'))

    def test_pdf_bytes_are_staged_before_source_alias_check(self):
        staged = []
        def pdf(html, path):
            staged.append(path)
            self.assertNotEqual(str(self.source), path)
            Path(path).write_bytes(b'%PDF-1.7\ncontrolled\x00\xff')
            return True
        with mock.patch.object(report, 'pdf_from_html', side_effect=pdf):
            self.reject(self.source, 'pdf')
            target = self.root / 'out.pdf'
            self.assertEqual(0, self.invoke(target, 'pdf')[0])
            self.assertEqual(b'%PDF-1.7\ncontrolled\x00\xff', target.read_bytes())
        self.assertTrue(staged)
        self.assertTrue(all(not Path(p).exists() for p in staged))

    def test_pdf_engine_failure_preserves_existing_destination_and_cleans_staging(self):
        target = self.root / 'out.pdf'
        target.write_bytes(b'prior PDF')
        staged = []
        def fail(html, path):
            staged.append(path)
            Path(path).write_bytes(b'partial PDF')
            raise OSError('controlled engine failure')
        with mock.patch.object(report, 'pdf_from_html', side_effect=fail):
            code, out, err = self.invoke(target, 'pdf')
        self.assertEqual(2, code)
        self.assertEqual('', out)
        self.assertIn('controlled engine failure', err)
        self.assertEqual(b'prior PDF', target.read_bytes())
        self.assertEqual(self.original, self.source.read_bytes())
        self.assertTrue(all(not Path(p).exists() for p in staged))

    def test_pdf_fallback_checks_actual_html_destination(self):
        source = self.root / 'fallback.html'
        source.write_bytes(self.original)
        output = self.root / 'fallback.pdf'
        with mock.patch.object(report, 'pdf_from_html', return_value=False):
            code, out, err = self.invoke(output, 'pdf', source)
            self.assertEqual(2, code)
            self.assertEqual('', out)
            self.assertIn('input snapshot', err)
            self.assertEqual(self.original, source.read_bytes())
            self.assertFalse(output.exists())
            target = self.root / 'distinct.pdf'
            code, out, err = self.invoke(target, 'pdf')
            self.assertEqual(0, code)
            self.assertIn('No PDF engine available', err)
            self.assertEqual(render_report.render(self.original.decode()), target.with_suffix('.html').read_text(encoding='utf-8'))

    def test_html_and_stdout_retain_exact_content(self):
        expected = render_report.render(self.original.decode())
        code, out, err = self.invoke()
        self.assertEqual((0, expected + '\n', ''), (code, out, err))
        target = self.root / 'out.html'
        target.write_text('old output' * 10000, encoding='utf-8')
        self.assertEqual(0, self.invoke(target)[0])
        self.assertEqual(expected, target.read_text(encoding='utf-8'))
        self.assertEqual(self.original, self.source.read_bytes())

    def test_invalid_input_and_failed_output_are_controlled(self):
        target = self.root / 'out.html'
        target.write_bytes(b'prior')
        self.source.write_bytes(b'\xff')
        code, out, err = self.invoke(target)
        self.assertEqual(2, code)
        self.assertEqual('', out)
        self.assertNotIn('Traceback', err)
        self.assertEqual(b'prior', target.read_bytes())
        self.source.write_bytes(self.original)
        self.assertEqual(2, self.invoke(self.root / 'missing' / 'out.html')[0])

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'named pipes unavailable')
    def test_nonregular_output_is_rejected_without_blocking(self):
        fifo = self.root / 'pipe'
        os.mkfifo(fifo)
        reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
        try:
            code, out, err = self.invoke(fifo)
        finally:
            os.close(reader)
        self.assertEqual(2, code)
        self.assertEqual('', out)
        self.assertIn('regular file', err)
        self.assertEqual(self.original, self.source.read_bytes())


if __name__ == '__main__':
    unittest.main()
