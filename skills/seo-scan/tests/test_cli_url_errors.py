"""Expected URL rejections are concise at the CLI, strict in core APIs."""

import contextlib
import io
import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit
import cli
import crawl_site
import generate_llms
import scan
import validate_sitemap
from lib import http
from lib.cli_errors import MAX_DETAIL, url_errors

MAINS = (scan.main, audit.main, crawl_site.main, generate_llms.main, validate_sitemap.main)
LOOPBACK = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('127.0.0.1', 0))]


def invoke(main, args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(args)
    return rc, out.getvalue(), err.getvalue()


class TestCLIURLRejections(unittest.TestCase):
    def test_expected_errors_keep_valueerror_and_ssrf_exception_contracts(self):
        self.assertTrue(issubclass(http.URLInputError, ValueError))
        self.assertTrue(issubclass(http.SSRFError, http.URLInputError))
        with self.assertRaises(http.SSRFError):
            http.fetch('http://127.0.0.1/private')

    def test_unsupported_schemes_are_typed_before_any_transport(self):
        for url in ('ftp://example.test', 'file:///etc/passwd', 'gopher://example.test'):
            with self.subTest(url=url), mock.patch.object(http, '_fetch_requests') as requests, \
                    mock.patch.object(http, '_fetch_urllib') as urllib:
                with self.assertRaisesRegex(http.URLInputError, 'Unsupported URL scheme'):
                    http.fetch(url)
                requests.assert_not_called(); urllib.assert_not_called()

    def test_malformed_ipv6_port_and_missing_host_are_typed(self):
        for url in ('http://[broken', 'https://example.test:bad/', 'https://example.test:65536/', 'https:///path'):
            with self.subTest(url=url), mock.patch.object(http.socket, 'getaddrinfo') as dns:
                with self.assertRaises(http.URLInputError):
                    http.normalize_url(url)
                dns.assert_not_called()

    def test_valid_hostnames_ipv6_ports_paths_and_fragment_normalization_remain(self):
        for given, expected in (('example.test', 'https://example.test/'),
                                ('http://example.test:8080/a?q=1#part', 'http://example.test:8080/a?q=1'),
                                ('http://[::1]:8080/', 'http://[::1]:8080/')):
            self.assertEqual(expected, http.normalize_url(given))

    def test_parser_diagnostics_do_not_echo_credentials_or_query_values(self):
        urls = ('http://owner:FAKE_SECRET@example.test\uff0fother/?token=FAKE_TOKEN',
                'http://owner:FAKE_SECRET@example.test:FAKE_PORT/?token=FAKE_TOKEN')
        for url in urls:
            with self.subTest(url=url), mock.patch.object(http.socket, 'getaddrinfo') as dns, \
                    mock.patch.object(http, '_fetch_requests') as requests, \
                    mock.patch.object(http, '_fetch_urllib') as urllib:
                with self.assertRaises(http.URLInputError) as failure:
                    http.normalize_url(url)
                self.assertIsInstance(failure.exception.__cause__, ValueError)
                for main in MAINS:
                    rc, out, err = invoke(main, [url, '--no-config'])
                    self.assertEqual(2, rc); self.assertEqual('', out)
                    self.assertEqual(1, len(err.splitlines()))
                    for secret in ('owner', 'FAKE_SECRET', 'FAKE_TOKEN', 'FAKE_PORT'):
                        self.assertNotIn(secret, err)
                dns.assert_not_called(); requests.assert_not_called(); urllib.assert_not_called()

    def test_dns_failures_and_host_encoding_errors_remain_expected_input_errors(self):
        for error in (socket.gaierror('unresolved'), UnicodeError('IDNA label too long')):
            with mock.patch.object(http.socket, 'getaddrinfo', side_effect=error):
                with self.assertRaises(http.URLInputError):
                    http.assert_public_host('https://example.test')
        with mock.patch.object(http.socket, 'getaddrinfo', side_effect=socket.gaierror('unresolved')):
            rc, out, err = invoke(scan.main, ['https://example.test', '--no-config'])
        self.assertEqual(2, rc); self.assertEqual('', out)
        self.assertIn('Cannot resolve host', err)
        self.assertNotIn('Traceback', err)

    def test_head_host_encoding_failures_keep_the_result_contract(self):
        with mock.patch.object(http.socket, 'getaddrinfo', side_effect=UnicodeError('IDNA label too long')), \
                mock.patch.object(http, '_requests_safe') as requests, \
                mock.patch.object(http, '_urllib_safe_open') as urllib:
            status, error = http.head('https://example.test')
        self.assertEqual(0, status)
        self.assertIn('Invalid host encoding', error)
        requests.assert_not_called(); urllib.assert_not_called()

    def test_all_five_main_boundaries_reject_private_targets_without_transport_or_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            for main in MAINS:
                path = Path(tmp) / (main.__module__ + '.json')
                with self.subTest(main=main.__module__), \
                        mock.patch.object(http.socket, 'getaddrinfo', return_value=LOOPBACK), \
                        mock.patch.object(http, '_fetch_requests') as requests, \
                        mock.patch.object(http, '_fetch_urllib') as urllib:
                    rc, out, err = invoke(main, ['http://127.0.0.1/private', '--no-config', '-o', str(path)])
                    self.assertEqual(2, rc); self.assertEqual('', out)
                    self.assertIn('ERROR: URL rejected:', err)
                    self.assertIn('blocked address', err)
                    self.assertNotIn('Traceback', err)
                    self.assertFalse(path.exists())
                    requests.assert_not_called(); urllib.assert_not_called()

    def test_all_main_boundaries_report_bad_syntax_without_broad_valueerror_catching(self):
        for main in MAINS:
            for url in ('http://[broken', 'https://example.test:bad/', 'ftp://example.test'):
                with self.subTest(main=main.__module__, url=url):
                    rc, out, err = invoke(main, [url, '--no-config'])
                    self.assertEqual(2, rc); self.assertEqual('', out)
                    self.assertTrue(err.startswith('ERROR: URL rejected:'))
                    self.assertEqual(1, len(err.splitlines()))

    def test_rejection_does_not_overwrite_existing_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'existing.json'; path.write_text('user-owned sentinel')
            rc, _, _ = invoke(scan.main, ['http://127.0.0.1', '--no-config', '-o', str(path)])
            self.assertEqual(2, rc)
            self.assertEqual('user-owned sentinel', path.read_text())

    def test_unified_cli_routes_retain_narrow_handlers(self):
        for command in ('scan', 'audit', 'crawl', 'crawl_site', 'llms', 'sitemap'):
            with self.subTest(command=command):
                rc, out, err = invoke(cli.main, [command, 'http://127.0.0.1', '--no-config'])
                self.assertEqual(2, rc); self.assertEqual('', out)
                self.assertNotIn('Traceback', err)
                self.assertIn('URL rejected', err)

    def test_help_is_still_argparse_help_not_a_policy_rejection(self):
        for main in MAINS:
            with self.subTest(main=main.__module__), contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as exit:
                    main(['--help'])
                self.assertEqual(0, exit.exception.code)

    def test_helper_preserves_function_metadata_and_success_value(self):
        @url_errors
        def sample(argv=None):
            """Original CLI docstring."""
            return 7
        self.assertEqual('sample', sample.__name__)
        self.assertEqual('Original CLI docstring.', sample.__doc__)
        self.assertEqual(7, sample([]))

    def test_programming_errors_and_interrupts_are_not_hidden(self):
        for error in (ValueError('internal defect'), RuntimeError('bug'), KeyboardInterrupt(), SystemExit(9)):
            @url_errors
            def bad(argv=None):
                raise error
            with self.subTest(error=type(error).__name__), self.assertRaises(type(error)):
                bad([])
        with mock.patch.object(scan, 'scan', side_effect=ValueError('internal defect')):
            with self.assertRaisesRegex(ValueError, 'internal defect'):
                scan.main(['https://example.test', '--no-config'])

    def test_diagnostic_is_bounded_and_cannot_inject_control_lines(self):
        @url_errors
        def bad(argv=None):
            raise http.URLInputError('line\nnext\r\t\x1b[31m' + 'X' * 2000)
        rc, out, err = invoke(bad, [])
        self.assertEqual(2, rc); self.assertEqual('', out)
        self.assertEqual(1, len(err.splitlines()))
        self.assertNotIn('\x1b', err)
        self.assertIn('\\u000a', err)
        self.assertLessEqual(len(err), len('ERROR: URL rejected: ') + MAX_DETAIL + 2)
        self.assertTrue(err.rstrip().endswith('…'))

    def test_explicit_private_scan_still_runs_with_the_flag(self):
        response = http.Response('http://127.0.0.1/', 'http://127.0.0.1/', 200,
                                 {'content-type': 'text/html'}, '<h1>Local preview</h1>', 1)
        with mock.patch.object(http, '_fetch_requests', return_value=response), \
                mock.patch.object(http, '_fetch_urllib', return_value=response), \
                mock.patch.object(scan, 'gather_context', return_value={}):
            rc, out, err = invoke(scan.main, ['http://127.0.0.1', '--allow-private', '--no-config',
                                             '--only', 'schema', '--no-image-checks', '--format', 'json'])
        self.assertEqual(0, rc); self.assertEqual('', err)
        self.assertEqual(['schema'], json.loads(out)['meta']['scan_scope']['completed'])

    def test_initial_sitemap_rejection_fails_before_discovery_or_direct_fetch(self):
        for url in ('http://127.0.0.1', 'http://127.0.0.1/sitemap.xml'):
            with self.subTest(url=url), mock.patch.object(http, 'fetch_text') as text, \
                    mock.patch.object(http, 'fetch_bytes') as binary:
                with self.assertRaises(http.SSRFError):
                    validate_sitemap.analyze(url)
                text.assert_not_called(); binary.assert_not_called()

    def test_explicit_local_sitemap_and_bare_host_normalization_are_supported(self):
        with mock.patch.object(http, 'fetch_text', return_value=None):
            result = validate_sitemap.analyze('127.0.0.1', allow_private=True)
        self.assertEqual('https://127.0.0.1/', result['start'])
        self.assertIn('No sitemap found', result['errors'][0])  # attempted discovery, not blocked input


if __name__ == '__main__':
    unittest.main()
