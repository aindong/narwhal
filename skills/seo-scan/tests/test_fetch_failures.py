"""Optional requests failures produce reports, not dependency-specific crashes."""

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import scan
from lib import http

URL = 'https://example.test/guide'
FINAL = 'https://example.test/final'


class TransportError(OSError):
    pass


class ConnectionFailure(TransportError):
    pass


class ReadTimeout(TransportError):
    pass


class RedirectLimit(TransportError):
    pass


REQUESTS = types.SimpleNamespace(RequestException=TransportError,
                                 TooManyRedirects=RedirectLimit)


def response(*, error=None):
    result = mock.Mock()
    result.encoding = 'utf-8'
    result.status_code = 200
    result.headers = {'content-type': 'text/html'}
    def chunks(**kwargs):
        yield b'<title>Only a prefix</title>'
        if error:
            raise error
    result.iter_content.side_effect = chunks
    return result


class TestFetchFailures(unittest.TestCase):
    def fetch(self, *, acquisition_error=None, raw=None):
        with mock.patch.dict(sys.modules, {'requests': REQUESTS}), \
                mock.patch.object(http, '_requests_safe',
                                  side_effect=acquisition_error,
                                  return_value=(raw, FINAL, [FINAL])):
            return http._fetch_requests(URL, 2, http.DEFAULT_UA, 64_000)

    def assert_failed(self, result, message):
        self.assertFalse(result.ok)
        self.assertEqual(0, result.status)
        self.assertEqual('', result.text)
        self.assertEqual({}, result.headers)
        self.assertIn(message, result.error)

    def test_expected_acquisition_failures_are_failed_responses(self):
        for error in (ConnectionFailure('connection lost'), ReadTimeout('timed out'),
                      TransportError('TLS verification failed')):
            with self.subTest(error=type(error).__name__):
                self.assert_failed(self.fetch(acquisition_error=error), str(error))

    def test_midstream_failures_discard_unverified_prefix_and_close_response(self):
        for error in (ConnectionFailure('stream lost'), ReadTimeout('read timed out'),
                      TransportError('invalid compressed body')):
            with self.subTest(error=type(error).__name__):
                raw = response(error=error)
                result = self.fetch(raw=raw)
                self.assert_failed(result, str(error))
                self.assertEqual(FINAL, result.final_url)
                self.assertEqual([FINAL], result.redirects)
                raw.close.assert_called_once_with()

    def test_success_preserves_body_status_and_redirects_and_closes(self):
        raw = response()
        result = self.fetch(raw=raw)
        self.assertTrue(result.ok)
        self.assertEqual('<title>Only a prefix</title>', result.text)
        self.assertEqual(FINAL, result.final_url)
        self.assertEqual([FINAL], result.redirects)
        raw.close.assert_called_once_with()

    def test_http_error_status_is_not_rewritten_as_transport_failure(self):
        raw = response()
        raw.status_code = 503
        result = self.fetch(raw=raw)
        self.assertFalse(result.ok)
        self.assertEqual(503, result.status)
        self.assertIsNone(result.error)
        self.assertIn('Only a prefix', result.text)
        raw.close.assert_called_once_with()

    def test_programming_errors_still_propagate_and_acquired_response_closes(self):
        for error in (RuntimeError('unexpected bug'), ValueError('unexpected value')):
            with self.subTest(error=type(error).__name__):
                raw = response(error=error)
                with self.assertRaises(type(error)):
                    self.fetch(raw=raw)
                raw.close.assert_called_once_with()
        with self.assertRaisesRegex(RuntimeError, 'unexpected bug'):
            self.fetch(acquisition_error=RuntimeError('unexpected bug'))

    def test_decode_errors_propagate_but_still_close_response(self):
        raw = response()
        raw.encoding = 'nonexistent-character-set'
        with self.assertRaises(LookupError):
            self.fetch(raw=raw)
        raw.close.assert_called_once_with()

    def test_scan_returns_unmeasured_failure_instead_of_a_dependency_crash(self):
        with mock.patch.dict(sys.modules, {'requests': REQUESTS}), \
                mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, '_requests_safe', side_effect=ConnectionFailure('connection lost')):
            result = scan.scan(URL, ctx={}, check_images=False)
        self.assertTrue(result.hard_fail)
        self.assertEqual(0, result.fetched_status)
        self.assertEqual([], result.meta['scan_scope']['completed'])
        self.assertEqual(0, result.score())
        self.assertIn('Page could not be fetched', result.to_markdown())


if __name__ == '__main__':
    unittest.main()
