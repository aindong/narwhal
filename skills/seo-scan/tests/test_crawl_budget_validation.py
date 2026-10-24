"""Reject invalid page/worker budgets before crawling or a composite audit starts."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit
import crawl_site as crawl
import mcp_server
from lib.config import Config
from lib.report import Report

URL = 'https://example.test/'
INVALID = (0, -1, True, False, 1.5, float('nan'), float('inf'), '2', None)


class TestCrawlBudgets(unittest.TestCase):
    def test_api_budgets_fail_before_url_resolution_or_any_subscan(self):
        for function in (crawl.crawl, audit.run):
            for field in ('max_pages', 'concurrency'):
                for value in INVALID:
                    with self.subTest(function=function.__name__, field=field, type=type(value).__name__), \
                            mock.patch.object(crawl.http, 'normalize_url') as normalize, \
                            mock.patch.object(crawl.scanner, 'gather_context') as gather, \
                            mock.patch.object(audit.scanner, 'scan') as scan:
                        with self.assertRaisesRegex(ValueError, field + ' must be a positive integer'):
                            function(URL, **{field: value})
                        normalize.assert_not_called()
                        gather.assert_not_called()
                        scan.assert_not_called()

    def test_cli_invalid_flags_preserve_output_without_starting_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'report.json'
            output.write_bytes(b'prior report')
            for module, function in ((crawl, 'crawl'), (audit, 'run')):
                for flag in ('--max-pages', '--concurrency'):
                    for value in ('0', '-1'):
                        out, err = io.StringIO(), io.StringIO()
                        with mock.patch.object(module, function) as run, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                            code = module.main([URL, '--no-config', flag, value, '-o', str(output)])
                        self.assertEqual(2, code)
                        self.assertEqual('', out.getvalue())
                        self.assertIn('positive integer', err.getvalue())
                        self.assertEqual(b'prior report', output.read_bytes())
                        run.assert_not_called()

    def test_invalid_config_defaults_use_the_same_cli_preflight(self):
        for module, function in ((crawl, 'crawl'), (audit, 'run')):
            for field in ('max_pages', 'concurrency'):
                for value in (0, True, 1.5):
                    cfg = Config({'defaults': {field: value}})
                    out, err = io.StringIO(), io.StringIO()
                    with mock.patch.object(module.configlib, 'load_from_args', return_value=cfg), \
                            mock.patch.object(module, function) as run, \
                            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        code = module.main([URL])
                    self.assertEqual(2, code)
                    self.assertEqual('', out.getvalue())
                    self.assertIn(field, err.getvalue())
                    run.assert_not_called()

    def test_valid_core_limits_are_not_silently_clamped_to_mcp_caps(self):
        with mock.patch.object(crawl.http, 'normalize_url', return_value=URL), \
                mock.patch.object(crawl.scanner, 'gather_context', return_value={}), \
                mock.patch.object(crawl, 'discover', return_value=[URL]) as discover, \
                mock.patch.object(crawl.scanner, 'scan', return_value=Report(URL)), \
                mock.patch.object(crawl, 'ThreadPoolExecutor', wraps=crawl.ThreadPoolExecutor) as executor:
            result = crawl.crawl(URL, max_pages=101, concurrency=9)
        self.assertEqual(1, result['pages_scanned'])
        self.assertEqual(303, discover.call_args.kwargs['limit'])
        self.assertEqual(9, executor.call_args.kwargs['max_workers'])
        with mock.patch.object(audit.scanner, 'scan', return_value=Report(URL)), \
                mock.patch.object(audit.crawl_site, 'crawl', return_value={}) as run, \
                mock.patch.object(audit.validate_sitemap, 'analyze', return_value={}):
            audit.run(URL, max_pages=101, concurrency=9)
        self.assertEqual(101, run.call_args.kwargs['max_pages'])
        self.assertEqual(9, run.call_args.kwargs['concurrency'])

    def test_mcp_adapters_keep_documented_positive_clamping(self):
        for tool, module, function in ((mcp_server._crawl, crawl, 'crawl'), (mcp_server._audit, audit, 'run')):
            for pages, workers, expected in ((0, 0, (1, 1)), (1000, 1000, (100, 8)), (4, 2, (4, 2))):
                with mock.patch.object(module, function, return_value={}) as run, \
                        mock.patch.object(module, 'render_json', return_value='{}'):
                    self.assertEqual({}, tool(URL, max_pages=pages, concurrency=workers))
                self.assertEqual(expected, (run.call_args.kwargs['max_pages'], run.call_args.kwargs['concurrency']))


if __name__ == '__main__':
    unittest.main()
