"""Starter generation must respect bounded MCP work and valid explicit budgets."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import generate_llms as llms
import mcp_server
from lib import http

URL = 'https://example.test/'
DATA = {'site_name': 'Example', 'description': '', 'sections': [], 'pages': 0}


class TestLlmsBudgets(unittest.TestCase):
    def test_mcp_bounds_pages_before_invoking_generator(self):
        for requested, effective in ((-1, 1), (0, 1), (1, 1), (40, 40), (100, 100),
                                     (101, 100), (1000000, 100)):
            with self.subTest(requested=requested), mock.patch.object(llms, 'build', return_value=DATA) as build:
                result = mcp_server._llms(URL, max_pages=requested)
                build.assert_called_once_with(URL, max_pages=effective)
                self.assertIn('# Example', result)
        with mock.patch.object(llms, 'build', return_value=DATA) as build:
            mcp_server._llms(URL)
            build.assert_called_once_with(URL, max_pages=40)

    def test_invalid_core_budgets_fail_before_any_fetch_or_discovery(self):
        for field in ('max_pages', 'concurrency'):
            for value in (0, -1, True, 1.5, '2', None):
                with self.subTest(field=field, value=value), \
                        mock.patch.object(http, 'fetch') as fetch, \
                        mock.patch.object(http, 'fetch_text') as robots, \
                        mock.patch.object(llms.crawl_site, 'discover') as discover:
                    with self.assertRaisesRegex(llms.GenerationError, field):
                        llms.build(URL, **{field: value})
                    fetch.assert_not_called(); robots.assert_not_called(); discover.assert_not_called()

    def test_explicit_core_page_budget_above_mcp_cap_is_preserved(self):
        urls = [URL + str(index) for index in range(105)]
        def fetch(url, **kwargs):
            return http.Response(url, url, 200, {}, '<title>Example</title>', 1)
        with mock.patch.object(http, 'fetch', side_effect=fetch) as fetched, \
                mock.patch.object(http, 'fetch_text', return_value=''), \
                mock.patch.object(llms.crawl_site, 'discover', return_value=urls) as discover:
            result = llms.build(URL, max_pages=101, concurrency=1)
        self.assertEqual(101, result['pages'])
        self.assertEqual(101, result['coverage']['attempted_pages'])
        self.assertEqual(202, discover.call_args.kwargs['limit'])
        self.assertEqual(102, fetched.call_count)  # primary response plus selected metadata fetches
        self.assertEqual(urls[:101], [page['url'] for _, pages in result['sections'] for page in pages])

    def test_cli_invalid_budgets_preserve_output_without_starting_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'llms.txt'
            for option in ('--max-pages', '--concurrency'):
                for existing in (False, True):
                    if existing:
                        output.write_bytes(b'curated original')
                    elif output.exists():
                        output.unlink()
                    out, err = io.StringIO(), io.StringIO()
                    with mock.patch.object(http, 'fetch') as fetch, \
                            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        code = llms.main([URL, option, '0', '-o', str(output)])
                    self.assertEqual(2, code)
                    self.assertEqual('', out.getvalue())
                    self.assertIn('positive integer', err.getvalue())
                    self.assertNotIn('Traceback', err.getvalue())
                    fetch.assert_not_called()
                    self.assertEqual(b'curated original' if existing else None,
                                     output.read_bytes() if output.exists() else None)


if __name__ == '__main__':
    unittest.main()
