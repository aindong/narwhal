"""Optional request caps reject invalid data before any standalone/composite I/O."""
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
import validate_sitemap as sitemap
from lib import http
from lib.config import Config

URL = 'https://example.test/'
INVALID = (-1, True, False, 1.5, float('nan'), float('inf'), '2', None)


class TestOptionalBudgetPreflight(unittest.TestCase):
    def test_api_invalid_caps_precede_url_resolution_and_subscans(self):
        cases = [(crawl.crawl, 'max_links'), (audit.run, 'max_links'),
                 (audit.run, 'max_sitemaps'), (sitemap.analyze, 'sample'),
                 (sitemap.analyze, 'max_sitemaps')]
        for function, field in cases:
            for value in INVALID:
                with self.subTest(function=function.__module__, field=field, value=type(value).__name__), \
                        mock.patch.object(http, 'normalize_url') as normalize, \
                        mock.patch.object(audit.scanner, 'scan') as scan:
                    with self.assertRaisesRegex(ValueError, field + ' must be a nonnegative integer'):
                        function(URL, **{field: value})
                    normalize.assert_not_called()
                    scan.assert_not_called()
        for value in INVALID:
            with mock.patch.object(audit.scanner, 'scan') as scan:
                with self.assertRaisesRegex(ValueError, 'sample must be a nonnegative integer'):
                    audit.run(URL, config=Config({'defaults': {'sample': value}}))
                scan.assert_not_called()

    def test_invalid_link_cap_never_turns_into_negative_slicing_requests(self):
        targets = {URL: [{'url': URL + str(i), 'internal': True} for i in range(3)]}
        for value in INVALID:
            with mock.patch.object(http, 'head') as head:
                with self.assertRaisesRegex(ValueError, 'max_links'):
                    crawl.check_broken_links(targets, allow_private=False, timeout=1, concurrency=1, max_links=value)
                head.assert_not_called()
        with mock.patch.object(http, 'head') as head:
            result = crawl.check_broken_links(targets, allow_private=False, timeout=1, concurrency=1, max_links=0)
        self.assertEqual((0, 3), (result['checked'], result['skipped_over_cap']))
        self.assertEqual(0, result['coverage']['successful_2xx'])
        head.assert_not_called()

    def test_zero_sitemap_caps_keep_existing_scoped_skip_behavior(self):
        xml = b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.test/page</loc></url></urlset>'
        with mock.patch.object(http, 'normalize_url', side_effect=lambda value: value), \
                mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, 'fetch_bytes', return_value=(xml, None)) as fetch, \
                mock.patch.object(http, 'head') as head:
            skipped = sitemap.analyze(URL + 'sitemap.xml', max_sitemaps=0, sample=0)
            self.assertEqual(0, skipped['sitemaps_attempted'])
            fetch.assert_not_called()
            sampled = sitemap.analyze(URL + 'sitemap.xml', max_sitemaps=1, sample=0)
            self.assertEqual(1, sampled['sitemaps_attempted'])
            self.assertEqual(1, sampled['total_urls'])
            self.assertEqual([], sampled['sample'])
            head.assert_not_called()

    def test_cli_invalid_flags_fail_before_work_and_preserve_output(self):
        cases = [(crawl, 'crawl', '--max-links'), (audit, 'run', '--max-links'),
                 (audit, 'run', '--max-sitemaps'), (sitemap, 'analyze', '--sample'),
                 (sitemap, 'analyze', '--max-sitemaps')]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'report.json'
            output.write_bytes(b'prior report')
            for module, function, flag in cases:
                out, err = io.StringIO(), io.StringIO()
                with mock.patch.object(module, function) as run, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = module.main([URL, '--no-config', flag, '-1', '-o', str(output)])
                self.assertEqual((2, ''), (code, out.getvalue()))
                self.assertIn('nonnegative integer', err.getvalue())
                self.assertEqual(b'prior report', output.read_bytes())
                run.assert_not_called()

    def test_cli_config_defaults_are_validated_where_consumed(self):
        cases = [(crawl, 'crawl', 'max_links'), (audit, 'run', 'sample'),
                 (sitemap, 'analyze', 'sample'), (sitemap, 'analyze', 'max_sitemaps')]
        for module, function, field in cases:
            for value in (-1, True, 1.5):
                out, err = io.StringIO(), io.StringIO()
                with mock.patch.object(module.configlib, 'load_from_args', return_value=Config({'defaults': {field: value}})), \
                        mock.patch.object(module, function) as run, \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = module.main([URL])
                self.assertEqual((2, ''), (code, out.getvalue()))
                self.assertIn(field, err.getvalue())
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
