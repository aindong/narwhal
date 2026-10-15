"""Remote charset names are input, not permission to crash or guess a decoder."""

import sys
import types
import unittest
from email.message import Message
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import scan
from lib import http

URL = 'https://example.test/guide'
FINAL = 'https://example.test/final'
REQUESTS = types.SimpleNamespace(RequestException=type('RequestError', (OSError,), {}))


def response(body, encoding):
    result = mock.Mock()
    result.encoding = encoding
    result.status_code = result.status = 200
    result.headers = Message()
    result.headers['Content-Type'] = 'text/html; charset=' + encoding
    result.iter_content.return_value = [body]
    result.read.return_value = body
    result.__enter__ = mock.Mock(return_value=result)
    result.__exit__ = mock.Mock(return_value=False)
    return result


def fetch(provider, body, encoding):
    raw = response(body, encoding)
    if provider == 'requests':
        with mock.patch.dict(sys.modules, {'requests': REQUESTS}), \
                mock.patch.object(http, '_requests_safe', return_value=(raw, FINAL, [FINAL])):
            result = http._fetch_requests(URL, 2, http.DEFAULT_UA, 64_000)
        raw.close.assert_called_once_with()
    else:
        with mock.patch.object(http, '_urllib_safe_open', return_value=(raw, FINAL, [FINAL])):
            result = http._fetch_urllib(URL, 2, http.DEFAULT_UA, 64_000)
        raw.__exit__.assert_called_once()
    return result


class TestResponseCharset(unittest.TestCase):
    def test_unknown_charset_is_a_failed_response_in_both_providers(self):
        for provider in ('requests', 'urllib'):
            with self.subTest(provider=provider):
                result = fetch(provider, b'<h1>Unverified</h1>', 'nonexistent-character-set')
                self.assertFalse(result.ok)
                self.assertEqual(0, result.status)
                self.assertEqual('', result.text)
                self.assertIn('Unsupported HTTP charset', result.error)
                self.assertIn('Content-Type', result.error)

    def test_non_text_codecs_do_not_transform_http_html(self):
        for encoding in ('base64_codec', 'hex_codec', 'rot_13'):
            for provider in ('requests', 'urllib'):
                with self.subTest(encoding=encoding, provider=provider):
                    result = fetch(provider, b'PGgxPkE8L2gxPg==', encoding)
                    self.assertFalse(result.ok)
                    self.assertEqual('', result.text)
                    self.assertIn('Unsupported HTTP charset', result.error)

    def test_supported_utf8_and_legacy_encodings_are_unchanged(self):
        text = '<h1>Caf\u00e9</h1>'
        for encoding in ('utf-8', 'iso-8859-1', 'latin1'):
            for provider in ('requests', 'urllib'):
                with self.subTest(encoding=encoding, provider=provider):
                    result = fetch(provider, text.encode(encoding), encoding)
                    self.assertTrue(result.ok)
                    self.assertEqual(text, result.text)
                    self.assertEqual(FINAL, result.final_url)
                    self.assertEqual([FINAL], result.redirects)

    def test_bad_bytes_under_a_supported_charset_keep_replacement_behavior(self):
        for provider in ('requests', 'urllib'):
            with self.subTest(provider=provider):
                result = fetch(provider, b'<h1>\xff</h1>', 'utf-8')
                self.assertTrue(result.ok)
                self.assertEqual('<h1>\ufffd</h1>', result.text)

    def test_unknown_charset_diagnostics_are_bounded_and_single_line(self):
        for provider in ('requests', 'urllib'):
            with self.subTest(provider=provider):
                result = fetch(provider, b'content', 'unknown-' + 'x' * 10_000)
                self.assertLess(len(result.error), 200)
                self.assertNotIn('\n', result.error)
                self.assertIn('…', result.error)
        for encoding in ('unknown-\n\t' + '\x00' * 1000, 'unknown-' + '\u2603' * 1000):
            with self.assertRaises(ValueError) as raised:
                http._decode_html(b'content', encoding)
            self.assertLess(len(str(raised.exception)), 200)
            self.assertNotIn('\n', str(raised.exception))

    def test_unrelated_lookup_errors_are_not_reclassified_as_bad_charset(self):
        raw = response(b'content', 'utf-8')
        raw.headers = mock.Mock()
        raw.headers.items.side_effect = KeyError('unexpected metadata bug')
        with mock.patch.dict(sys.modules, {'requests': REQUESTS}), \
                mock.patch.object(http, '_requests_safe', return_value=(raw, FINAL, [])):
            with self.assertRaisesRegex(KeyError, 'unexpected metadata bug'):
                http._fetch_requests(URL, 2, http.DEFAULT_UA, 64_000)
        raw.close.assert_called_once_with()

    def test_unexpected_decoder_failures_still_propagate_and_close(self):
        raw = response(b'content', 'utf-8')
        with mock.patch.dict(sys.modules, {'requests': REQUESTS}), \
                mock.patch.object(http, '_requests_safe', return_value=(raw, FINAL, [])), \
                mock.patch.object(http, '_limited_content', return_value=(mock.Mock(), False)) as read:
            read.return_value[0].decode.side_effect = RuntimeError('unexpected decoder bug')
            with self.assertRaisesRegex(RuntimeError, 'unexpected decoder bug'):
                http._fetch_requests(URL, 2, http.DEFAULT_UA, 64_000)
        raw.close.assert_called_once_with()

    def test_scan_does_not_measure_page_health_from_an_unknown_charset(self):
        raw = response(b'<h1>Unverified</h1>', 'nonexistent-character-set')
        with mock.patch.dict(sys.modules, {'requests': REQUESTS}), \
                mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, '_requests_safe', return_value=(raw, FINAL, [])):
            report = scan.scan(URL, ctx={}, check_images=False)
        self.assertTrue(report.hard_fail)
        self.assertEqual([], report.meta['scan_scope']['completed'])
        self.assertEqual(0, report.score())
        self.assertIn('Unsupported HTTP charset', report.to_markdown())
        self.assertNotIn('Unverified</h1>', report.to_markdown())


if __name__ == '__main__':
    unittest.main()
