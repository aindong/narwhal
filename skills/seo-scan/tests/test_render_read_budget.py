"""Oversized Markdown must fail before rendering or output delivery."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import render_report


class TestRenderReadBudget(unittest.TestCase):
    def test_file_binary_stdin_and_text_stdin_share_utf8_byte_admission(self):
        for source in ('file', 'wrapped_stdin', 'text_stdin'):
            for overflow in (False, True):
                with self.subTest(source=source, overflow=overflow), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    path, output = root / 'report.md', root / 'report.html'
                    text = '# Café\r\n\r\nBody\r\n'
                    raw = text.encode('utf-8')
                    payload = raw + (b' ' if overflow else b'')
                    path.write_bytes(payload)
                    output.write_bytes(b'previous output')
                    stdin = (io.TextIOWrapper(io.BytesIO(payload), encoding='utf-8', newline='') if source == 'wrapped_stdin'
                             else io.StringIO(payload.decode('utf-8')))
                    with mock.patch.object(render_report, 'MAX_INPUT_BYTES', len(raw)), \
                            mock.patch.object(render_report.sys, 'stdin', stdin), \
                            mock.patch.object(render_report, 'render', wraps=render_report.render) as render, \
                            mock.patch.object(render_report, 'deliver', wraps=render_report.deliver) as deliver, \
                            contextlib.redirect_stdout(io.StringIO()) as out, \
                            contextlib.redirect_stderr(io.StringIO()) as err:
                        code = render_report.main([str(path) if source == 'file' else '-', '-o', str(output),
                                                   '--format', 'pdf' if overflow else 'html'])
                    self.assertEqual(2 if overflow else 0, code)
                    if overflow:
                        self.assertEqual('', out.getvalue())
                        self.assertIn('safety limit', err.getvalue())
                        render.assert_not_called()
                        deliver.assert_not_called()
                        self.assertEqual(b'previous output', output.read_bytes())
                    else:
                        self.assertEqual('', err.getvalue())
                        render.assert_called_once()
                        deliver.assert_called_once()
                        self.assertEqual(render_report.render(text), output.read_text(encoding='utf-8'))
                    self.assertEqual(payload, path.read_bytes())

    def test_binary_and_text_read_requests_are_bounded(self):
        for binary in (True, False):
            text = 'é' * 20
            source = io.BytesIO(text.encode('utf-8')) if binary else io.StringIO(text)
            def read(size=-1):
                self.assertGreaterEqual(size, 0)
                self.assertLessEqual(size, 33)
                return source.read(size)
            stream = mock.Mock()
            stream.read.side_effect = read
            with self.subTest(binary=binary), \
                    mock.patch.object(render_report, 'MAX_INPUT_BYTES', 32), \
                    self.assertRaisesRegex(ValueError, 'safety limit'):
                render_report._read_markdown(stream)

    def test_partially_consumed_text_stdin_keeps_already_buffered_content(self):
        text = '# Café\n\nBody\n'
        stdin = io.TextIOWrapper(io.BytesIO(('prefix' + text).encode('utf-8')), encoding='utf-8')
        self.assertEqual('prefix', stdin.read(6))
        with mock.patch.object(render_report.sys, 'stdin', stdin), \
                mock.patch.object(render_report, 'render', wraps=render_report.render) as render, \
                mock.patch.object(render_report, 'deliver', return_value=0), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(0, render_report.main(['-']))
        render.assert_called_once_with(text, title=None, subtitle='')

    def test_invalid_utf8_is_controlled_before_rendering(self):
        with mock.patch.object(render_report.sys, 'stdin', io.TextIOWrapper(io.BytesIO(b'\xff'), encoding='utf-8')), \
                mock.patch.object(render_report, 'render') as render, \
                contextlib.redirect_stdout(io.StringIO()) as out, \
                contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(2, render_report.main(['-']))
        self.assertEqual('', out.getvalue())
        self.assertTrue(err.getvalue().startswith('Error:'))
        render.assert_not_called()
