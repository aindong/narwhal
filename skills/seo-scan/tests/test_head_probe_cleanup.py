"""Reachability probes release HEAD and fallback GET responses."""
import io
from pathlib import Path
import sys
import types
import unittest
from unittest import mock
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from lib import http

URL = 'https://example.test/link'


class ProbeError(OSError):
    pass


class TestHeadProbeCleanup(unittest.TestCase):
    def test_transport_failure_remains_a_controlled_unreachable_result(self):
        for backend in ('requests', 'urllib'):
            client = types.SimpleNamespace(RequestException=ProbeError) if backend == 'requests' else None
            helper = '_requests_safe' if backend == 'requests' else '_urllib_safe_open'
            with self.subTest(backend=backend), mock.patch.dict(sys.modules, {'requests': client}), \
                    mock.patch.object(http, 'assert_public_host'), \
                    mock.patch.object(http, helper, autospec=True, side_effect=ProbeError('origin detail')):
                self.assertEqual((0, 'ProbeError'), http.head(URL))

    def test_requests_head_without_fallback_closes_response(self):
        for status in (200, 301, 404, 503):
            response = mock.Mock(status_code=status)
            with self.subTest(status=status), \
                    mock.patch.dict(sys.modules, {'requests': types.SimpleNamespace(RequestException=ProbeError)}), \
                    mock.patch.object(http, 'assert_public_host'), \
                    mock.patch.object(http, '_requests_safe', return_value=(response, URL, [])) as opened:
                self.assertEqual((status, None), http.head(URL))
            self.assertEqual(['HEAD'], [call.args[1] for call in opened.call_args_list])
            response.close.assert_called_once()
            response.iter_content.assert_not_called()

    def test_requests_closes_head_before_successful_or_failed_get(self):
        for status in (403, 405, 501):
            for failure in (False, True):
                head = mock.Mock(status_code=status)
                get = mock.Mock(status_code=206)
                fake_client = types.SimpleNamespace(RequestException=ProbeError)
                def opened(client, method, url, **kwargs):
                    self.assertIs(fake_client, client)
                    self.assertEqual(URL, url)
                    self.assertEqual(7, kwargs['timeout'])
                    self.assertIs(True, kwargs['allow_private'])
                    self.assertEqual({'user-agent': 'probe-test'},
                                     {k.lower(): v for k, v in kwargs['headers'].items()})
                    if method == 'HEAD':
                        return head, URL, []
                    head.close.assert_called_once()
                    self.assertEqual('GET', method)
                    self.assertIs(True, kwargs['stream'])
                    if failure:
                        raise ProbeError('origin detail')
                    return get, URL, []
                with self.subTest(status=status, failure=failure), \
                        mock.patch.dict(sys.modules, {'requests': fake_client}), \
                        mock.patch.object(http, 'assert_public_host'), \
                        mock.patch.object(http, '_requests_safe', autospec=True, side_effect=opened):
                    self.assertEqual((0, 'ProbeError') if failure else (206, None),
                                     http.head(URL, timeout=7, user_agent='probe-test', allow_private=True))
                head.close.assert_called_once()
                if not failure:
                    get.close.assert_called_once()
                    get.iter_content.assert_not_called()

    def test_urllib_http_error_without_fallback_closes_unread_body(self):
        for status in (404, 503):
            body = mock.Mock(wraps=io.BytesIO(b'error body'))
            error = HTTPError(URL, status, 'origin detail', {}, body)
            with self.subTest(status=status), mock.patch.dict(sys.modules, {'requests': None}), \
                    mock.patch.object(http, 'assert_public_host'), \
                    mock.patch.object(http, '_urllib_safe_open', side_effect=error) as opened:
                self.assertEqual((status, None), http.head(URL))
            self.assertEqual(['HEAD'], [call.kwargs['method'] for call in opened.call_args_list])
            body.close.assert_called_once()
            body.read.assert_not_called()

    def test_urllib_closes_head_and_fallback_http_error_bodies(self):
        for status in (403, 405, 501):
            for failure in (False, True):
                body = mock.Mock(wraps=io.BytesIO(b'head error body'))
                error = HTTPError(URL, status, 'origin detail', {}, body)
                fallback_body = mock.Mock(wraps=io.BytesIO(b'get error body'))
                get = io.BytesIO(b'unread GET body')
                get.status = 206
                def opened(url, **kwargs):
                    self.assertEqual(URL, url)
                    self.assertEqual(7, kwargs['timeout'])
                    self.assertIs(True, kwargs['allow_private'])
                    self.assertEqual({'user-agent': 'probe-test'},
                                     {k.lower(): v for k, v in kwargs['headers'].items()})
                    if kwargs['method'] == 'HEAD':
                        raise error
                    body.close.assert_called_once()
                    self.assertEqual('GET', kwargs['method'])
                    if failure:
                        raise HTTPError(URL, 410, 'origin detail', {}, fallback_body)
                    return get, URL, []
                with self.subTest(status=status, failure=failure), \
                        mock.patch.dict(sys.modules, {'requests': None}), \
                        mock.patch.object(http, 'assert_public_host'), \
                        mock.patch.object(http, '_urllib_safe_open', autospec=True, side_effect=opened):
                    self.assertEqual((410, None) if failure else (206, None),
                                     http.head(URL, timeout=7, user_agent='probe-test', allow_private=True))
                body.close.assert_called_once()
                body.read.assert_not_called()
                if failure:
                    fallback_body.close.assert_called_once()
                    fallback_body.read.assert_not_called()
                    get.close()
                else:
                    self.assertTrue(get.closed)


if __name__ == '__main__':
    unittest.main()
