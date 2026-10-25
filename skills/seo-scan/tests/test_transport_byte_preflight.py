"""Invalid byte budgets are programmer errors before DNS or transport work."""
from contextlib import ExitStack
import io
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from lib import http

URL = 'https://example.test/document'
INVALID = (-1, -2, True, False, 0.5, '8', None)
IO = ('assert_public_host', '_fetch_requests', '_fetch_urllib', '_try_render',
      '_requests_safe', '_urllib_safe_open')


class TestTransportBytePreflight(unittest.TestCase):
    def test_primary_budget_rejected_before_dns_or_browser_even_with_private_opt_in(self):
        for value in INVALID:
            for render in (False, True):
                with self.subTest(value=value, render=render), ExitStack() as stack:
                    calls = [stack.enter_context(mock.patch.object(http, name)) for name in IO]
                    with self.assertRaisesRegex(ValueError, 'nonnegative integer') as error:
                        http.fetch(URL, max_bytes=value, render=render, allow_private=True)
                    self.assertNotIn(repr(value), str(error.exception))
                    for call in calls:
                        call.assert_not_called()

    def test_range_and_raw_byte_budgets_are_positive_and_fail_before_io(self):
        for value in (0,) + INVALID:
            for kind in ('range', 'raw'):
                with self.subTest(value=value, kind=kind), ExitStack() as stack:
                    calls = [stack.enter_context(mock.patch.object(http, name)) for name in IO]
                    with self.assertRaisesRegex(ValueError, 'positive integer'):
                        if kind == 'range':
                            http.fetch_range(URL, value)
                        else:
                            http.fetch_bytes(URL, max_bytes=value)
                    for call in calls:
                        call.assert_not_called()

    def test_valid_primary_budgets_are_forwarded_and_zero_retains_existing_semantics(self):
        for value in (0, 1, 8):
            response = http.Response(URL, URL, 200, {}, '', 0)
            with self.subTest(value=value), mock.patch.object(http, 'assert_public_host'), \
                    mock.patch.object(http, '_fetch_requests', return_value=response) as requests:
                self.assertIs(response, http.fetch(URL, max_bytes=value))
                self.assertEqual(value, requests.call_args[0][3])
        with mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, '_try_render', return_value=http.Response(URL, URL, 200, {}, 'abc', 0, rendered=True)):
            response = http.fetch(URL, render=True, max_bytes=0)
        self.assertEqual('', response.text)
        self.assertEqual('true', response.headers['x-narwhal-truncated'])

    def test_raw_budget_error_keeps_the_existing_message(self):
        with self.assertRaises(ValueError) as error:
            http.fetch_bytes(URL, max_bytes=0)
        self.assertEqual('Raw response byte budget must be a positive integer.', str(error.exception))

    def test_valid_range_counts_preserve_prefixes_in_both_backends(self):
        fake = types.SimpleNamespace(RequestException=OSError)
        for count in (1, 3, 8):
            response = mock.Mock(status_code=200)
            response.iter_content.return_value = [b'abcd']
            with self.subTest(count=count, backend='requests'), \
                    mock.patch.dict(sys.modules, {'requests': fake}), \
                    mock.patch.object(http, 'assert_public_host'), \
                    mock.patch.object(http, '_requests_safe', return_value=(response, URL, [])) as opened:
                self.assertEqual((b'abcd'[:count], None), http.fetch_range(URL, count))
                self.assertEqual('bytes=0-' + str(count - 1), opened.call_args[1]['headers']['Range'])
                response.close.assert_called_once()
            stream = io.BytesIO(b'abcd')
            with self.subTest(count=count, backend='urllib'), \
                    mock.patch.dict(sys.modules, {'requests': None}), \
                    mock.patch.object(http, 'assert_public_host'), \
                    mock.patch.object(http, '_urllib_safe_open', return_value=(stream, URL, [])):
                self.assertEqual((b'abcd'[:count], None), http.fetch_range(URL, count))
                self.assertTrue(stream.closed)


if __name__ == '__main__':
    unittest.main()
