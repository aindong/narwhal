"""All remaining CLI report saves share file checks without changing analysis gates."""
import contextlib
from contextlib import ExitStack
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import brief
import compare
import crawl_site
import crux
import generate_llms
import gsc
import psi
import validate_sitemap
from lib import env

URL = 'https://example.test/'
CASES = [
    (crawl_site, [URL, '--no-config', '--fail-under', '80'], 'crawl', {'pages_scanned': 1, 'avg_score': 50}, 1),
    (compare, [URL, URL + 'other', '--no-config'], 'run', {}, 0),
    (brief, [URL, '--no-config', '--no-gsc'], 'run', {}, 0),
    (validate_sitemap, [URL, '--no-config'], 'analyze', {}, 0),
    (generate_llms, [URL, '--no-config'], 'build', {'site_name': 'Fixture', 'description': '', 'sections': {}, 'pages': 1}, 0),
    (crux, [URL, '--crux-key', 'fixture-key'], 'analyze', {'found': True, 'cwv_pass': False}, 1),
    (crux, [URL, '--lab'], None, None, 1),
    (psi, [URL], 'analyze', {'found': True, 'perf_rating': 'poor'}, 1),
    (gsc, [URL], 'fetch', {'found': False}, 1),
]


def invoke(case, output, content, *, failure=None):
    module, args, function, data, expected = case
    out, err = io.StringIO(), io.StringIO()
    with ExitStack() as stack:
        stack.enter_context(mock.patch.object(env, 'resolve', return_value='fixture-key'))
        stack.enter_context(mock.patch.object(gsc, 'resolve_token', return_value=('fixture-token', '')))
        stack.enter_context(mock.patch.object(psi, 'analyze', return_value={'found': True, 'perf_rating': 'poor'}))
        for target in (module, psi):
            for renderer in ('render_json', 'render_markdown', 'render_llms_txt'):
                if hasattr(target, renderer):
                    stack.enter_context(mock.patch.object(target, renderer, return_value=content))
        if function:
            options = {'side_effect': failure} if failure else {'return_value': data}
            stack.enter_context(mock.patch.object(module, function, **options))
        elif failure:
            stack.enter_context(mock.patch.object(psi, 'analyze', side_effect=failure))
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(err))
        code = module.main(args + ['-o', str(output)])
    return code, out.getvalue(), err.getvalue()


class TestCLIArtifactSaves(unittest.TestCase):
    def test_success_keeps_exact_text_and_original_analysis_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'report.txt'
            for case in CASES:
                with self.subTest(module=case[0].__name__, args=case[1]):
                    output.write_bytes(b'old report' * 1000)
                    code, out, err = invoke(case, output, 'Controlled café report\n')
                    self.assertEqual(case[-1], code)
                    self.assertIn('Wrote ', out)
                    self.assertEqual('Controlled café report\n', output.read_text(encoding='utf-8'))

    def test_missing_destination_is_exit_two_without_success_or_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'missing' / 'report.txt'
            for case in CASES:
                with self.subTest(module=case[0].__name__, args=case[1]):
                    code, out, err = invoke(case, output, 'report')
                    self.assertEqual((2, ''), (code, out))
                    self.assertIn('output', err)
                    self.assertNotIn('Traceback', err)
                    self.assertFalse(output.exists())

    def test_encoding_preflight_preserves_existing_artifact_for_every_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'report.txt'
            for case in CASES:
                with self.subTest(module=case[0].__name__, args=case[1]):
                    output.write_bytes(b'prior report')
                    code, out, err = invoke(case, output, '\ud800')
                    self.assertEqual((2, ''), (code, out))
                    self.assertIn('UTF-8', err)
                    self.assertEqual(b'prior report', output.read_bytes())

    def test_analysis_value_errors_are_not_hidden_by_the_save_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'report.txt'
            for case in CASES:
                with self.subTest(module=case[0].__name__, args=case[1]):
                    with self.assertRaisesRegex(ValueError, 'analysis defect'):
                        invoke(case, output, 'report', failure=ValueError('analysis defect'))
                    self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
