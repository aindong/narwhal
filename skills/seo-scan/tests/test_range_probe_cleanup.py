"""Range probes release responses even when no usable prefix is returned."""
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


class ProbeError(OSError):
    pass


class TestRangeProbeCleanup(unittest.TestCase):
    def test_invalid_count_identifies_the_range_budget(self):
        with self.assertRaises(ValueError) as error:
            http.fetch_range(URL, 0)
        self.assertEqual('Range byte budget must be a positive integer.', str(error.exception))

    def test_requests_redirect_preserves_private_host_choice(self):
        for private in (False, True):
            redirect = mock.Mock(is_redirect=True, headers={'location': '/next'})
            response = mock.Mock(status_code=200, is_redirect=False, is_permanent_redirect=False)
            response.iter_content.return_value = [b'abc']
            client = types.SimpleNamespace(RequestException=ProbeError,
                                           request=mock.Mock(side_effect=[redirect, response]))
            with self.subTest(private=private), mock.patch.dict(sys.modules, {'requests': client}), \
                    mock.patch.object(http, 'assert_public_host') as guard:
                self.assertEqual((b'abc', None), http.fetch_range(URL, 3, allow_private=private))
            self.assertEqual([mock.call(URL, allow_private=private),
                              mock.call('https://example.test/next', allow_private=private)], guard.call_args_list)
            self.assertEqual(['https://example.test/image', 'https://example.test/next'],
                             [call.args[1] for call in client.request.call_args_list])
            redirect.close.assert_called_once()
            response.close.assert_called_once()

    def test_requests_keeps_bounded_stream_and_caller_transport_options(self):
        for status in (399, 400):
            for private in (False, True):
                def chunks(chunk_size):
                    self.assertIsInstance(chunk_size, int)
                    self.assertGreater(chunk_size, 0)
                    yield b'a'
                    yield b'bc'
                    raise AssertionError('probe consumed beyond its prefix')
                response = mock.Mock(status_code=status, is_redirect=False, is_permanent_redirect=False)
                response.iter_content.side_effect = chunks
                client = types.SimpleNamespace(RequestException=ProbeError, request=mock.Mock(return_value=response))
                options = {'allow_private': True} if private else {}
                with self.subTest(status=status, private=private), \
                        mock.patch.dict(sys.modules, {'requests': client}), \
                        mock.patch.object(http, 'assert_public_host') as guard:
                    self.assertEqual((b'abc', None if status == 399 else 'HTTP 400'),
                                     http.fetch_range('example.test/image', 3, timeout=7, user_agent='probe-test', **options))
                guard.assert_called_once_with(URL, allow_private=private)
                args, kwargs = client.request.call_args
                self.assertEqual(('GET', URL), (args[0].upper(), args[1]))
                self.assertEqual({'user-agent': 'probe-test', 'range': 'bytes=0-2'},
                                 {k.lower(): v for k, v in kwargs['headers'].items()})
                self.assertEqual(7, kwargs['timeout'])
                self.assertIs(True, kwargs['stream'])
                self.assertIs(False, kwargs['allow_redirects'])
                response.close.assert_called_once()

    def test_urllib_keeps_caller_transport_options(self):
        for private in (False, True):
            stream = io.BytesIO(b'abcdef')
            options = {'allow_private': True} if private else {}
            with self.subTest(private=private), mock.patch.dict(sys.modules, {'requests': None}), \
                    mock.patch.object(http, 'assert_public_host') as guard, \
                    mock.patch.object(http, '_urllib_safe_open', return_value=(stream, URL, [])) as opened:
                self.assertEqual((b'abc', None),
                                 http.fetch_range('example.test/image', 3, timeout=7, user_agent='probe-test', **options))
            guard.assert_called_once_with(URL, allow_private=private)
            args, kwargs = opened.call_args
            self.assertEqual((URL,), args)
            self.assertEqual({'user-agent': 'probe-test', 'range': 'bytes=0-2'},
                             {k.lower(): v for k, v in kwargs['headers'].items()})
            self.assertEqual(7, kwargs['timeout'])
            self.assertIs(private, kwargs['allow_private'])
            self.assertTrue(stream.closed)

    def test_guard_and_urllib_transport_failures_remain_controlled(self):
        with mock.patch.object(http, 'assert_public_host', side_effect=http.SSRFError('blocked fixture')), \
                mock.patch.object(http, '_requests_safe') as requests, \
                mock.patch.object(http, '_urllib_safe_open') as urllib:
            self.assertEqual((None, 'blocked fixture'), http.fetch_range(URL, 3))
            requests.assert_not_called()
            urllib.assert_not_called()
        with mock.patch.dict(sys.modules, {'requests': None}), \
                mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, '_urllib_safe_open', side_effect=OSError('origin detail')):
            self.assertEqual((None, 'OSError'), http.fetch_range(URL, 3))

    def test_requests_stream_failure_discards_prefix_and_closes_response(self):
        for prefix in ((), (b'partial',)):
            def chunks(chunk_size):
                yield from prefix
                raise ProbeError('untrusted origin detail')
            response = mock.Mock(status_code=200)
            response.iter_content.side_effect = chunks
            with self.subTest(prefix=prefix), \
                    mock.patch.dict(sys.modules, {'requests': types.SimpleNamespace(RequestException=ProbeError)}), \
                    mock.patch.object(http, 'assert_public_host'), \
                    mock.patch.object(http, '_requests_safe', return_value=(response, URL, [])):
                self.assertEqual((None, 'ProbeError'), http.fetch_range(URL, 16))
                response.close.assert_called_once()

    def test_requests_http_failure_keeps_existing_result_and_closes_response(self):
        response = mock.Mock(status_code=404)
        response.iter_content.return_value = [b'not found']
        with mock.patch.dict(sys.modules, {'requests': types.SimpleNamespace(RequestException=ProbeError)}), \
                mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, '_requests_safe', return_value=(response, URL, [])):
            self.assertEqual((b'not', 'HTTP 404'), http.fetch_range(URL, 3))
        response.close.assert_called_once()

    def test_urllib_http_error_closes_body_without_reading_it(self):
        for status in (404, 503):
            body = mock.Mock(wraps=io.BytesIO(b'unneeded error body'))
            error = HTTPError(URL, status, 'untrusted origin detail', {}, body)
            with self.subTest(status=status), mock.patch.dict(sys.modules, {'requests': None}), \
                    mock.patch.object(http, 'assert_public_host'), \
                    mock.patch.object(http, '_urllib_safe_open', side_effect=error):
                self.assertEqual((None, 'HTTP ' + str(status)), http.fetch_range(URL, 3))
            body.read.assert_not_called()
            body.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
