"""Image header probes close their responses without consuming bodies."""
import io
from pathlib import Path
import sys
import types
import unittest
from unittest import mock
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from lib import http

URL = 'https://example.test/image'
HEADERS = {'Content-Type': 'image/png', 'Content-Length': '1234'}
EXPECTED = {'content-type': 'image/png', 'content-length': '1234'}


class ProbeError(OSError):
    pass


class TestHeadInfoCleanup(unittest.TestCase):
    def test_transport_errors_have_no_header_evidence(self):
        for backend in ('requests', 'urllib'):
            for error in (ProbeError, http.SSRFError, ValueError):
                client = types.SimpleNamespace(RequestException=ProbeError) if backend == 'requests' else None
                helper = '_requests_safe' if backend == 'requests' else '_urllib_safe_open'
                with self.subTest(backend=backend, error=error.__name__), \
                        mock.patch.dict(sys.modules, {'requests': client}), \
                        mock.patch.object(http, 'assert_public_host'), \
                        mock.patch.object(http, helper, autospec=True, side_effect=error('origin detail')):
                    self.assertEqual((0, {}, error.__name__), http.head_info(URL))

    def test_urllib_success_closes_without_reading_and_keeps_headers(self):
        for status in (200, 206):
            body = io.BytesIO(b'unread image bytes')
            body.status, body.headers = status, HEADERS
            with self.subTest(status=status), mock.patch.dict(sys.modules, {'requests': None}), \
                    mock.patch.object(http, 'assert_public_host'), \
                    mock.patch.object(body, 'read', side_effect=AssertionError('Unexpected body read')) as read, \
                    mock.patch.object(http, '_urllib_safe_open', autospec=True, return_value=(body, URL, [])):
                self.assertEqual((status, EXPECTED, None), http.head_info(URL))
                self.assertTrue(body.closed)
                read.assert_not_called()

    def test_requests_preserves_status_and_headers_and_closes_without_reading(self):
        for status in (200, 301, 403, 404, 503):
            response = mock.Mock(status_code=status, headers=HEADERS)
            client = types.SimpleNamespace(RequestException=ProbeError)
            with self.subTest(status=status), mock.patch.dict(sys.modules, {'requests': client}), \
                    mock.patch.object(http, 'assert_public_host') as guard, \
                    mock.patch.object(http, '_requests_safe', autospec=True, return_value=(response, URL, [])) as opened:
                self.assertEqual((status, EXPECTED, None),
                                 http.head_info(URL, timeout=7, user_agent='image-probe', allow_private=True))
                guard.assert_called_once_with(URL, allow_private=True)
                opened.assert_called_once()
                args, kwargs = opened.call_args
                self.assertEqual((client, 'HEAD', URL), (args[0], args[1].upper(), args[2]))
                self.assertEqual(7, kwargs['timeout'])
                self.assertIs(True, kwargs['allow_private'])
                self.assertEqual({'user-agent': 'image-probe'},
                                 {k.lower(): v for k, v in kwargs['headers'].items()})
                response.close.assert_called_once()
                response.iter_content.assert_not_called()

    def test_requests_header_failure_closes_response_and_returns_controlled_error(self):
        headers = mock.Mock()
        headers.items.side_effect = ValueError('origin detail')
        response = mock.Mock(status_code=200, headers=headers)
        with mock.patch.dict(sys.modules, {'requests': types.SimpleNamespace(RequestException=ProbeError)}), \
                mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, '_requests_safe', autospec=True, return_value=(response, URL, [])):
            self.assertEqual((0, {}, 'ValueError'), http.head_info(URL))
        response.close.assert_called_once()

    def test_urllib_http_error_preserves_headers_and_closes_unread_body(self):
        for status in (403, 404, 503):
            for headers in (HEADERS, None):
                body = mock.Mock(wraps=io.BytesIO(b'unread origin error body'))
                error = HTTPError(URL, status, 'origin detail', headers, body)
                with self.subTest(status=status, headers=headers is not None), \
                        mock.patch.dict(sys.modules, {'requests': None}), \
                        mock.patch.object(http, 'assert_public_host') as guard, \
                        mock.patch.object(http, '_urllib_safe_open', autospec=True, side_effect=error) as opened:
                    self.assertEqual((status, EXPECTED if headers else {}, None),
                                     http.head_info(URL, timeout=7, user_agent='image-probe', allow_private=True))
                    guard.assert_called_once_with(URL, allow_private=True)
                    opened.assert_called_once()
                    args, kwargs = opened.call_args
                    self.assertEqual((URL,), args)
                    self.assertEqual(7, kwargs['timeout'])
                    self.assertIs(True, kwargs['allow_private'])
                    self.assertEqual('HEAD', kwargs['method'])
                    self.assertEqual({'user-agent': 'image-probe'},
                                     {k.lower(): v for k, v in kwargs['headers'].items()})
                    body.close.assert_called_once()
                    body.read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
