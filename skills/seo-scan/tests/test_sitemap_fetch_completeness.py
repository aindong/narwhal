"""Only complete successful raw responses may feed sitemap extraction."""

import io
import gzip
import zlib
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


REQUESTS = types.SimpleNamespace(
    RequestException=TransportError,
    packages=types.SimpleNamespace(urllib3=types.SimpleNamespace(
        exceptions=types.SimpleNamespace(HTTPError=TransportError))))


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

    def test_short_requests_body_below_limit_is_unverified_on_older_streams(self):
        for encoding in (None, 'identity', ' Identity '):
            response = requests_response([XML], length=len(XML) + 20)
            if encoding is not None:
                response.headers['content-encoding'] = encoding
            with self.subTest(encoding=encoding):
                body, error = fetch('requests', response, budget=len(XML) + 100)
                self.assertIsNone(body)
                self.assertIn('Incomplete response', error)
                response.close.assert_called_once()

    def test_transfer_decoded_lengths_are_not_compared_to_wire_length(self):
        response = requests_response([XML], length=len(XML) + 20)
        response.headers['transfer-encoding'] = 'chunked'
        self.assertEqual((XML, None), fetch('requests', response))
        response.close.assert_called_once()

    def encoded_fetch(self, provider, wire, encoding='gzip', declared=None, budget=1024):
        if provider == 'requests':
            response = requests_response([], length=declared)
            response.raw.read.return_value = wire
            response.headers['content-encoding'] = encoding
        else:
            response = Stream(wire, declared=declared)
            response.headers['Content-Encoding'] = encoding
        result = fetch(provider, response, budget=budget)
        if provider == 'requests':
            response.raw.read.assert_called_once_with(budget + 1, decode_content=False)
            response.iter_content.assert_not_called()
            response.close.assert_called_once()
        else:
            self.assertTrue(response.closed)
        return result

    def test_http_encoded_bodies_are_checked_as_wire_then_decoded(self):
        for provider in ('requests', 'urllib'):
            for encoding, wire in (('gzip', gzip.compress(XML)), ('x-gzip', gzip.compress(XML)),
                                   ('deflate', zlib.compress(XML)),
                                   ('deflate', zlib.compress(XML)[2:-4])):
                for length in (None, len(wire)):
                    with self.subTest(provider=provider, encoding=encoding, length=length):
                        self.assertEqual((XML, None), self.encoded_fetch(provider, wire, encoding, length))

    def test_short_encoded_wire_does_not_expose_complete_xml(self):
        wire = gzip.compress(XML)
        for provider in ('requests', 'urllib'):
            with self.subTest(provider=provider):
                body, error = self.encoded_fetch(provider, wire, declared=len(wire) + 20)
                self.assertIsNone(body)
                self.assertIn('Content-Length not satisfied', error)

    def test_missing_footer_and_invalid_encoded_streams_with_exact_length_are_unverified(self):
        gzip_body = gzip.compress(XML)
        cases = [('gzip', gzip_body[:-8]), ('gzip', gzip_body[:-1]),
                 ('gzip', gzip_body[:-8] + b'\x00' * 8), ('gzip', XML), ('gzip', b''),
                 ('deflate', zlib.compress(XML)[:-4]), ('deflate', zlib.compress(XML) + b'junk')]
        for provider in ('requests', 'urllib'):
            for encoding, wire in cases:
                with self.subTest(provider=provider, encoding=encoding, wire=wire[-8:]):
                    body, error = self.encoded_fetch(provider, wire, encoding, len(wire))
                    self.assertIsNone(body)
                    self.assertEqual('Incomplete or invalid HTTP encoded body; body unverified.', error)

    def test_http_wire_and_decoded_bodies_both_obey_budget(self):
        for provider in ('requests', 'urllib'):
            for encoding, wire in (('gzip', gzip.compress(b'x' * 10_000)),
                                   ('deflate', zlib.compress(b'x' * 10_000))):
                with self.subTest(provider=provider, encoding=encoding):
                    body, error = self.encoded_fetch(provider, wire, encoding, len(wire), budget=100)
                    self.assertIsNone(body)
                    self.assertIn('decoded byte limit', error)
            body, error = self.encoded_fetch(provider, gzip.compress(XML), budget=10)
            self.assertIsNone(body)
            self.assertIn('raw byte limit', error)
            wire = gzip.compress(b'x' * 100)
            self.assertEqual((b'x' * 100, None),
                             self.encoded_fetch(provider, wire, declared=len(wire), budget=100))

    def test_raw_gzip_files_remain_raw_without_http_encoding(self):
        wire = gzip.compress(XML)
        for provider in ('requests', 'urllib'):
            response = requests_response([wire], length=len(wire)) if provider == 'requests' else Stream(wire, declared=len(wire))
            self.assertEqual((wire, None), fetch(provider, response))

    def test_http_gzip_members_share_budget_and_require_final_integrity(self):
        wire = gzip.compress(XML[:20]) + gzip.compress(XML[20:])
        for provider in ('requests', 'urllib'):
            self.assertEqual((XML, None), self.encoded_fetch(provider, wire, declared=len(wire)))
            body, error = self.encoded_fetch(provider, wire[:-1], declared=len(wire)-1)
            self.assertIsNone(body)
            self.assertIn('invalid HTTP encoded', error)
            self.assertEqual((b'', None), self.encoded_fetch(provider, gzip.compress(b'')))

    def test_unsupported_http_encoding_is_explicitly_unverified(self):
        for provider in ('requests', 'urllib'):
            for encoding in ('br', 'gzip, deflate'):
                body, error = self.encoded_fetch(provider, XML, encoding, len(XML))
                self.assertIsNone(body)
                self.assertEqual('Unsupported HTTP content encoding; body unverified.', error)

    def test_encoded_requests_wire_errors_withhold_body_and_close_response(self):
        response = requests_response([])
        response.headers['content-encoding'] = 'gzip'
        response.raw.read.side_effect = TransportError('secret-token')
        self.assertEqual((None, 'TransportError'), fetch('requests', response))
        response.close.assert_called_once()
        for failure in (RuntimeError('bug'), ValueError('bug')):
            response = requests_response([])
            response.headers['content-encoding'] = 'gzip'
            response.raw.read.side_effect = failure
            with self.subTest(failure=type(failure).__name__), self.assertRaises(type(failure)):
                fetch('requests', response)
            response.close.assert_called_once()

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

    def test_malformed_or_missing_declared_lengths_do_not_establish_excess(self):
        for value in (None, '', ' \t', '-100', '+100', '1e9', '1.0', '100,100',
                      '9:', 'A', '/', '\uff11\uff12\uff13', '\u0661\u0662\u0663'):
            with self.subTest(value=value):
                self.assertIs(False, http._declared_length_exceeds(value, 1))

    def test_declared_length_comparison_matches_small_integer_boundaries(self):
        for number in (0, 1, 9, 10, 99, 100, 199, 200, 201):
            for budget in (0, 1, 8, 9, 10, 99, 100, 199, 200, 201):
                for value in (str(number), '000' + str(number), ' \t00' + str(number) + ' '):
                    with self.subTest(value=value, budget=budget):
                        self.assertIs(number > budget, http._declared_length_exceeds(value, budget))
        self.assertIs(True, http._declared_length_exceeds('9' * 10_000, 1_000_000))
        self.assertIs(False, http._declared_length_exceeds('0' * 10_000, 0))

    def test_limit_probe_uses_only_valid_declared_lengths_and_discards_overflow(self):
        for declared, expected_chunks in (('4', 1), ('3A', 2), ('\uff14', 2), (None, 2)):
            with self.subTest(declared=declared):
                yielded = []
                def chunks():
                    for chunk in (b'abc', b'X'):
                        yielded.append(chunk)
                        yield chunk
                response = requests_response([], length=declared)
                response.iter_content.return_value = chunks()
                body, error = fetch('requests', response, budget=3)
                self.assertIsNone(body)
                self.assertIn('raw byte limit', error)
                self.assertEqual(expected_chunks, len(yielded))
                response.close.assert_called_once()

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
