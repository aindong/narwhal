"""Stdlib HTTP errors retain the identity of their guarded terminal request."""

import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import scan
from lib import http, llms_resource

URL = 'https://example.test/start'
HOP = 'https://example.test/middle'
FINAL = 'https://example.test/final?status=404&sample=1'
PUBLIC = [(2, 1, 6, '', ('8.8.8.8', 443))]


def error(url, status, headers=None, body=b'Error'):
    stream = io.BytesIO(body)
    return urllib.error.HTTPError(url, status, 'Fixture', headers or {}, stream), stream


def terminal_response(status=404, body=b'Error', limit=64000):
    first, first_stream = error(URL, 302, {'Location': '/middle'})
    second, second_stream = error(HOP, 307, {'Location': '/final?status=404&sample=1'})
    final, final_stream = error(FINAL, status, {'Content-Type': 'text/html',
                                              'Content-Location': 'https://unfetched.test/forged'}, body)
    opener = mock.Mock()
    opener.open.side_effect = [first, second, final]
    with mock.patch('urllib.request.build_opener', return_value=opener), \
            mock.patch('socket.getaddrinfo', return_value=PUBLIC):
        result = http._fetch_urllib(URL, 2, http.DEFAULT_UA, limit)
    return result, opener, (first_stream, second_stream, final_stream)


class TestErrorDestinations(unittest.TestCase):
    def test_terminal_errors_preserve_requested_final_and_all_observed_hops(self):
        for status in (404, 410, 403, 429, 500, 302):
            with self.subTest(status=status):
                result, opener, streams = terminal_response(status)
                self.assertEqual(URL, result.url)
                self.assertEqual(FINAL, result.final_url)
                self.assertEqual([HOP, FINAL], result.redirects)
                self.assertEqual(status, result.status)
                self.assertEqual('Error', result.text)
                self.assertEqual([URL, HOP, FINAL], [call.args[0].full_url for call in opener.open.call_args_list])
                self.assertTrue(all(stream.closed for stream in streams))

    def test_direct_error_does_not_invent_redirects_or_trust_content_location(self):
        err, stream = error(URL, 404, {'Content-Location': FINAL})
        opener = mock.Mock()
        opener.open.side_effect = err
        with mock.patch('urllib.request.build_opener', return_value=opener):
            result = http._fetch_urllib(URL, 2, http.DEFAULT_UA, 64000)
        self.assertEqual(URL, result.final_url)
        self.assertEqual([], result.redirects)
        self.assertTrue(stream.closed)

    def test_redirect_context_preserves_existing_error_body_budget_and_marker_ownership(self):
        result, _, streams = terminal_response(404, b'123456789', limit=8)
        self.assertEqual(FINAL, result.final_url)
        self.assertEqual([HOP, FINAL], result.redirects)
        self.assertEqual('12345678', result.text)
        self.assertEqual('true', result.headers.get('x-narwhal-truncated'))
        self.assertTrue(all(stream.closed for stream in streams))
        self.assertEqual('unverified', llms_resource.assess(result)['state'])

    def test_llms_receipt_and_failed_page_report_retain_terminal_identity_without_rescoring(self):
        result, _, _ = terminal_response()
        receipt = llms_resource.assess(result)
        self.assertEqual(FINAL, receipt['final_url'])
        self.assertEqual(URL, receipt['requested_url'])
        self.assertEqual('absent', receipt['state'])
        with mock.patch.object(http, 'fetch', return_value=result):
            rep = scan.scan(URL, only=['technical'], check_images=False)
        self.assertTrue(rep.hard_fail)
        self.assertEqual(0, rep.score())
        data = json.loads(rep.to_json())
        self.assertEqual(FINAL, data['final_url'])
        self.assertEqual([HOP, FINAL], data['meta']['redirects'])
        self.assertIn(FINAL, rep.to_markdown())
        self.assertIn('sample=1', rep.to_html())

    def test_denied_redirect_is_not_fetched_or_reported_as_a_terminal_http_destination(self):
        err, stream = error(URL, 302, {'Location': 'http://127.0.0.1/private'})
        opener = mock.Mock()
        opener.open.side_effect = err
        with mock.patch('urllib.request.build_opener', return_value=opener):
            result = http._fetch_urllib(URL, 2, http.DEFAULT_UA, 64000)
        self.assertEqual(1, opener.open.call_count)
        self.assertEqual(0, result.status)
        self.assertEqual(URL, result.final_url)
        self.assertEqual([], result.redirects)
        self.assertTrue(stream.closed)
        self.assertIn('blocked address', result.error.lower())

    def test_over_limit_redirect_is_closed_without_an_extra_request(self):
        err, stream = error(URL, 302, {'Location': '/unvisited'})
        opener = mock.Mock()
        opener.open.side_effect = err
        with mock.patch('urllib.request.build_opener', return_value=opener), \
                mock.patch.object(http, 'MAX_REDIRECTS', 0):
            result = http._fetch_urllib(URL, 2, http.DEFAULT_UA, 64000)
        self.assertEqual(1, opener.open.call_count)
        self.assertEqual(0, result.status)
        self.assertEqual([], result.redirects)
        self.assertTrue(stream.closed)


if __name__ == '__main__':
    unittest.main()
