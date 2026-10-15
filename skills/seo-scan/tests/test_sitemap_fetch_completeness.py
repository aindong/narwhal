"""Only complete successful raw responses may feed sitemap extraction."""

import io
import sys
import types
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import validate_sitemap as validator
from lib import http

URL = 'https://example.test/sitemap.xml'
XML = b'<urlset><url><loc>https://example.test/valid</loc></url></urlset>'


class TransportError(OSError):
    pass


REQUESTS = types.SimpleNamespace(RequestException=TransportError)


class Stream(io.BytesIO):
    def __init__(self, body, status=200, declared=None):
        super().__init__(body)
        self.status = status
        self.headers = Message()
        if declared is not None:
            self.headers['Content-Length'] = str(declared)


def requests_response(chunks, status=200, length=None):
    response = mock.Mock()
    response.status_code = status
    response.headers = {} if length is None else {'content-length': str(length)}
    response.iter_content.return_value = chunks
    return response


def fetch(provider, response=None, failure=None, budget=1024):
    module = REQUESTS if provider == 'requests' else None
    name = '_requests_safe' if provider == 'requests' else '_urllib_safe_open'
    with mock.patch.dict(sys.modules, {'requests': module}), \
            mock.patch.object(http, 'assert_public_host'), \
            mock.patch.object(http, name, side_effect=failure, return_value=(response, URL, [])):
        return http.fetch_bytes(URL, max_bytes=budget)


class TestSitemapFetchCompleteness(unittest.TestCase):
    def test_success_and_exact_limit_preserve_bytes_in_both_transports(self):
        for provider in ('requests', 'urllib'):
            for declared in (None, len(XML)):
                response = (requests_response([XML], length=declared) if provider == 'requests'
                            else Stream(XML, declared=declared))
                with self.subTest(provider=provider, declared=declared):
                    self.assertEqual((XML, None), fetch(provider, response, budget=len(XML)))
                    if provider == 'requests':
                        response.close.assert_called_once()
                    else:
                        self.assertTrue(response.closed)

    def test_overflow_discards_a_complete_looking_xml_prefix(self):
        for provider in ('requests', 'urllib'):
            for declared in (None, len(XML) + 1):
                response = (requests_response([XML, b'x'], length=declared) if provider == 'requests'
                            else Stream(XML + b'x', declared=declared))
                with self.subTest(provider=provider, declared=declared):
                    body, error = fetch(provider, response, budget=len(XML))
                    self.assertIsNone(body)
                    self.assertIn('raw byte limit', error)
                    self.assertIn(str(len(XML)), error)
                    if provider == 'requests':
                        response.close.assert_called_once()
                    else:
                        self.assertTrue(response.closed)

    def test_non_success_status_never_exposes_an_xml_error_body(self):
        for provider in ('requests', 'urllib'):
            for status in (301, 403, 404, 429, 503):
                response = requests_response([XML], status) if provider == 'requests' else Stream(XML, status)
                with self.subTest(provider=provider, status=status):
                    self.assertEqual((None, 'HTTP ' + str(status)), fetch(provider, response))
                    if provider == 'requests':
                        response.iter_content.assert_not_called()
                        response.close.assert_called_once()
                    else:
                        self.assertTrue(response.closed)

    def test_declared_incomplete_urllib_body_is_unverified(self):
        response = Stream(XML, declared=len(XML) + 20)
        body, error = fetch('urllib', response)
        self.assertIsNone(body)
        self.assertIn('Incomplete response', error)
        self.assertTrue(response.closed)

    def test_large_declared_lengths_do_not_crash_integer_conversion(self):
        for declared in ('9' * 10_000, '000' + str(len(XML) + 20)):
            with self.subTest(declared=declared[:20]):
                body, error = fetch('urllib', Stream(XML, declared=declared))
                self.assertIsNone(body)
                self.assertIn('Incomplete response', error)
                response = requests_response([XML], length=declared)
                body, error = fetch('requests', response, budget=len(XML))
                self.assertIsNone(body)
                self.assertIn('raw byte limit', error)
        response = requests_response([XML], length='000' + str(len(XML)))
        self.assertEqual((XML, None), fetch('requests', response, budget=len(XML)))

    def test_http_error_handles_are_closed_without_reading_their_body(self):
        source = io.BytesIO(XML)
        error = urllib.error.HTTPError(URL, 404, 'not found', {}, source)
        self.assertEqual((None, 'HTTP 404'), fetch('urllib', failure=error))
        self.assertTrue(source.closed)

    def test_expected_transport_errors_are_bounded_and_prefixes_withheld(self):
        def chunks():
            yield XML
            raise TransportError('secret-password\n' + 'x' * 1000)

        response = requests_response(chunks())
        self.assertEqual((None, 'TransportError'), fetch('requests', response))
        response.close.assert_called_once()
        for provider, failure in (('requests', TransportError('secret-password')),
                                  ('urllib', OSError('secret-password'))):
            body, error = fetch(provider, failure=failure)
            self.assertIsNone(body)
            self.assertNotIn('secret-password', error)

    def test_unexpected_read_errors_propagate_after_closing(self):
        for provider in ('requests', 'urllib'):
            for failure in (RuntimeError('bug'), ValueError('bug')):
                response = requests_response([]) if provider == 'requests' else Stream(XML)
                if provider == 'requests':
                    response.iter_content.side_effect = failure
                else:
                    response.read = mock.Mock(side_effect=failure)
                with self.subTest(provider=provider, failure=type(failure).__name__):
                    with self.assertRaises(type(failure)):
                        fetch(provider, response)
                    if provider == 'requests':
                        response.close.assert_called_once()
                    else:
                        self.assertTrue(response.closed)

    def test_invalid_budget_fails_before_dns_or_transport(self):
        for budget in (0, -1, True, '128', 1.5):
            with self.subTest(budget=budget), mock.patch.object(http, 'assert_public_host') as dns:
                with self.assertRaises(ValueError):
                    http.fetch_bytes(URL, max_bytes=budget)
                dns.assert_not_called()

    def test_validator_rejects_error_paired_with_bytes_defensively(self):
        with mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, 'fetch_bytes', return_value=(XML, 'HTTP 404')), \
                mock.patch.object(http, 'head') as head:
            result = validator.analyze(URL)
        self.assertEqual(0, result['total_urls'])
        self.assertEqual(0, result['sitemaps_fetched'])
        self.assertEqual(1, result['fetch_failures'])
        self.assertTrue(result['errors'])
        self.assertNotIn('Sitemap looks healthy', validator.render_markdown(result))
        head.assert_not_called()

    def test_failed_siblings_label_incomplete_totals_without_guessing_legacy_counts(self):
        index = ('<sitemapindex><sitemap><loc>https://example.test/good.xml</loc></sitemap>'
                 '<sitemap><loc>https://example.test/bad.xml</loc></sitemap></sitemapindex>').encode()
        bodies = {URL: (index, None), 'https://example.test/good.xml': (XML, None),
                  'https://example.test/bad.xml': (None, 'HTTP 404')}
        with mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, 'fetch_bytes', side_effect=lambda url, **kw: bodies[url]), \
                mock.patch.object(http, 'head', return_value=(200, None)) as head:
            result = validator.analyze(URL)
        self.assertEqual(1, result['fetch_failures'])
        self.assertEqual(1, result['total_urls'])
        self.assertEqual(2, result['sitemaps_fetched'])
        self.assertIn('fetch failures leave total incomplete', validator.render_markdown(result))
        self.assertNotIn('Sitemap looks healthy', validator.render_markdown(result))
        head.assert_called_once()
        result['errors'] = []
        self.assertNotIn('Sitemap looks healthy', validator.render_markdown(result))
        result.pop('fetch_failures')
        self.assertNotIn('**Fetch failures:**', validator.render_markdown(result))

    def test_failed_attempts_consume_file_budget_and_duplicate_queue_entries_do_not_inflate_remainder(self):
        bad, good = 'https://example.test/bad.xml', 'https://example.test/good.xml'
        index = ('<sitemapindex>' + ''.join('<sitemap><loc>' + url + '</loc></sitemap>'
                 for url in (bad, bad, good)) + '</sitemapindex>').encode()
        bodies = {URL: (index, None), bad: (None, 'HTTP 404'), good: (XML, None)}
        for cap in (2, 3):
            with self.subTest(cap=cap), mock.patch.object(http, 'assert_public_host'), \
                    mock.patch.object(http, 'fetch_bytes', side_effect=lambda url, **kw: bodies[url]) as fetcher, \
                    mock.patch.object(http, 'head', return_value=(200, None)):
                result = validator.analyze(URL, max_sitemaps=cap)
            self.assertEqual(cap, fetcher.call_count)
            self.assertEqual(cap, result['sitemaps_attempted'])
            self.assertEqual(1, result['fetch_failures'])
            if cap == 2:
                self.assertEqual(1, result['truncated'])
                self.assertEqual(0, result['total_urls'])
            else:
                self.assertNotIn('truncated', result)
                self.assertEqual(1, result['total_urls'])

    def test_initial_private_host_guard_is_still_enforced(self):
        with mock.patch.object(http, '_requests_safe') as requests, \
                mock.patch.object(http, '_urllib_safe_open') as urllib:
            body, error = http.fetch_bytes('http://127.0.0.1/private')
        self.assertIsNone(body)
        self.assertIn('blocked', error)
        requests.assert_not_called()
        urllib.assert_not_called()

    def test_urllib_redirect_response_closes_before_next_request(self):
        source = io.BytesIO(b'redirect body')
        headers = Message()
        headers['Location'] = '/final.xml'
        redirect = urllib.error.HTTPError(URL, 302, 'moved', headers, source)
        final = Stream(XML)
        opener = mock.Mock()

        def open_response(*args, **kwargs):
            if opener.open.call_count == 1:
                raise redirect
            self.assertTrue(source.closed)
            return final

        opener.open.side_effect = open_response
        with mock.patch('urllib.request.build_opener', return_value=opener), \
                mock.patch.object(http, 'assert_public_host') as guard:
            response, target, redirects = http._urllib_safe_open(URL, timeout=1, headers={}, allow_private=False)
        self.assertIs(final, response)
        self.assertEqual('https://example.test/final.xml', target)
        self.assertEqual([target], redirects)
        guard.assert_called_once_with(target, allow_private=False)
        self.assertFalse(final.closed)
        final.close()

    def test_denied_and_over_limit_redirects_close_without_a_second_request(self):
        for over_limit in (False, True):
            source = io.BytesIO(b'redirect body')
            headers = Message()
            headers['Location'] = 'http://127.0.0.1/private'
            redirect = urllib.error.HTTPError(URL, 302, 'moved', headers, source)
            opener = mock.Mock()
            opener.open.side_effect = redirect
            with self.subTest(over_limit=over_limit), \
                    mock.patch('urllib.request.build_opener', return_value=opener), \
                    mock.patch.object(http, 'MAX_REDIRECTS', 0 if over_limit else 10), \
                    mock.patch.object(http, 'assert_public_host', side_effect=http.SSRFError('blocked')):
                with self.assertRaises(http.SSRFError):
                    http._urllib_safe_open(URL, timeout=1, headers={}, allow_private=False)
            self.assertTrue(source.closed)
            opener.open.assert_called_once()


if __name__ == '__main__':
    unittest.main()
