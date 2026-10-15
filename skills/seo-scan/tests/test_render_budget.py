"""Rendered snapshots obey the primary HTML budget and report partial input."""

import sys
import io
import types
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import scan
from lib import http

URL = 'https://example.test/guide'


def rendered(text, **kwargs):
    return http.Response(URL, URL, 200, {'content-type': 'text/html'}, text, 7,
                         rendered=True, **kwargs)


class TestRenderBudget(unittest.TestCase):
    def fetch(self, response, limit):
        with mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, '_try_render', return_value=response):
            return http.fetch(URL, render=True, max_bytes=limit)

    def test_rendered_ascii_is_bounded_and_marked_truncated(self):
        response = self.fetch(rendered('abcdefghijk'), 8)
        self.assertEqual('abcdefgh', response.text)
        self.assertEqual('true', response.headers['x-narwhal-truncated'])
        self.assertTrue(response.rendered)
        self.assertEqual(200, response.status)

    def test_budget_is_utf8_bytes_not_python_character_count(self):
        response = self.fetch(rendered('abc' + '😀' * 3), 8)
        self.assertEqual('abc😀', response.text)
        self.assertLessEqual(len(response.text.encode('utf-8')), 8)
        self.assertNotIn('\ufffd', response.text)
        self.assertEqual('true', response.headers['x-narwhal-truncated'])

    def test_exact_utf8_boundary_does_not_claim_truncation(self):
        original = rendered('é' * 5)
        response = self.fetch(original, 10)
        self.assertIs(original, response)
        self.assertNotIn('x-narwhal-truncated', response.headers)

    def test_smaller_snapshots_keep_text_and_metadata_unchanged(self):
        original = rendered('<h1>Guide</h1>')
        original.headers['x-example'] = 'kept'
        response = self.fetch(original, 100)
        self.assertIs(original, response)
        self.assertEqual('<h1>Guide</h1>', response.text)
        self.assertEqual({'content-type': 'text/html', 'x-example': 'kept'}, response.headers)
        self.assertEqual(7, response.elapsed_ms)

    def test_truncation_does_not_mutate_provider_response_or_headers(self):
        original = rendered('abcdefghijk')
        original.redirects.append('https://example.test/redirected')
        response = self.fetch(original, 8)
        self.assertIsNot(original, response)
        self.assertIsNot(original.headers, response.headers)
        self.assertEqual('abcdefghijk', original.text)
        self.assertNotIn('x-narwhal-truncated', original.headers)
        self.assertEqual(original.redirects, response.redirects)
        self.assertEqual(original.final_url, response.final_url)

    def test_zero_transport_budget_keeps_no_rendered_html(self):
        response = self.fetch(rendered('abc'), 0)
        self.assertEqual('', response.text)
        self.assertEqual('true', response.headers['x-narwhal-truncated'])

    def test_render_errors_remain_errors_without_raw_fallback(self):
        original = http.Response(URL, URL, 0, {}, '', 7, rendered=True, error='browser missing')
        with mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, '_try_render', return_value=original), \
                mock.patch.object(http, '_fetch_requests') as raw:
            response = http.fetch(URL, render=True, max_bytes=8)
        self.assertIs(original, response)
        self.assertEqual('browser missing', response.error)
        raw.assert_not_called()

    def test_missing_playwright_keeps_raw_budget_forwarding(self):
        original = http.Response(URL, URL, 200, {}, 'raw', 0)
        with mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, '_try_render', return_value=None), \
                mock.patch.object(http, '_fetch_requests', return_value=original) as raw:
            response = http.fetch(URL, render=True, max_bytes=8)
        self.assertIs(original, response)
        self.assertEqual(8, raw.call_args.args[3])
        self.assertFalse(response.rendered)

    def test_private_host_rejection_still_precedes_browser_launch(self):
        with mock.patch.object(http, '_try_render') as browser:
            with self.assertRaises(http.SSRFError):
                http.fetch('http://127.0.0.1/private', render=True, max_bytes=8)
        browser.assert_not_called()

    def test_scan_records_partial_dom_and_does_not_measure_js_dependence(self):
        original = rendered('<title>Guide</title><p>' + 'x' * 70_000 + '</p>')
        with mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, '_try_render', return_value=original), \
                mock.patch.object(http, '_fetch_requests') as raw:
            report = scan.scan(URL, render=True, max_bytes=64_000, ctx={},
                                only=['technical'], check_images=False)
        self.assertTrue(report.meta['coverage']['response_truncated'])
        self.assertEqual(64_000, report.meta['coverage']['response_byte_limit'])
        self.assertTrue(report.rendered)
        self.assertNotIn('js_dependence', report.meta)
        self.assertIn('technical.response.truncated', [finding.rule_id for finding in report.findings])
        raw.assert_not_called()

    def test_complete_rendered_snapshot_still_measures_js_dependence(self):
        original = rendered('<title>Guide</title><h1>Guide</h1><p>Rendered answer.</p>')
        raw_response = http.Response(URL, URL, 200, {'content-type': 'text/html'},
                                     '<title>Guide</title><p>Loading</p>', 0)
        with mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, '_try_render', return_value=original), \
                mock.patch.object(http, '_fetch_requests', return_value=raw_response):
            report = scan.scan(URL, render=True, max_bytes=64_000, ctx={},
                                only=['technical'], check_images=False)
        self.assertFalse(report.meta['coverage']['response_truncated'])
        self.assertIn('js_dependence', report.meta)

    def test_partial_snapshot_cannot_reuse_cached_js_dependence_context(self):
        original = rendered('<title>Guide</title><p>' + 'x' * 70_000 + '</p>')
        context = {'jsdep': {'js_only_pct': 99}}
        observed = []
        def auditor(doc, response, report, ctx):
            observed.append('jsdep' in ctx)
        with mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, '_try_render', return_value=original), \
                mock.patch.dict(scan.AUDITORS, {'technical': auditor}):
            report = scan.scan(URL, render=True, max_bytes=64_000, ctx=context,
                                only=['technical'], check_images=False)
        self.assertEqual([False], observed)
        self.assertEqual({'jsdep': {'js_only_pct': 99}}, context)
        self.assertNotIn('js_dependence', report.meta)


class TestOriginCoverageMarker(unittest.TestCase):
    def headers(self):
        headers = Message()
        headers['Content-Type'] = 'text/html; charset=utf-8'
        headers['X-Narwhal-Truncated'] = 'true'
        return headers

    def test_origin_header_filter_is_case_insensitive_and_non_mutating(self):
        original = {'X-Narwhal-Truncated': 'true', 'Content-Type': 'text/html'}
        self.assertEqual({'content-type': 'text/html'}, http._origin_headers(original))
        self.assertEqual('true', original['X-Narwhal-Truncated'])

    def test_requests_coverage_comes_from_byte_count_not_origin_marker(self):
        fake_module = types.SimpleNamespace(TooManyRedirects=RuntimeError)
        for body, expected in ((b'abc', False), (b'abcdefghi', True)):
            with self.subTest(body=body):
                response = mock.Mock(headers={'X-Narwhal-Truncated': 'true'},
                                     encoding='utf-8', status_code=200)
                response.iter_content.return_value = [body]
                with mock.patch.dict(sys.modules, {'requests': fake_module}), \
                        mock.patch.object(http, '_requests_safe', return_value=(response, URL, [])):
                    result = http._fetch_requests(URL, 20, http.DEFAULT_UA, 8)
                self.assertEqual(expected, result.headers.get('x-narwhal-truncated') == 'true')
                self.assertLessEqual(len(result.text), 8)
                response.close.assert_called_once()

    def test_urllib_coverage_comes_from_byte_count_not_origin_marker(self):
        for body, expected in ((b'abc', False), (b'abcdefghi', True)):
            with self.subTest(body=body):
                stream = mock.MagicMock(headers=self.headers(), status=200)
                stream.__enter__.return_value = stream
                stream.read.return_value = body
                with mock.patch.object(http, '_urllib_safe_open', return_value=(stream, URL, [])):
                    result = http._fetch_urllib(URL, 20, http.DEFAULT_UA, 8)
                self.assertEqual(expected, result.headers.get('x-narwhal-truncated') == 'true')
                self.assertLessEqual(len(result.text), 8)

    def test_urllib_error_response_cannot_forge_coverage(self):
        error = urllib.error.HTTPError(URL, 403, 'Forbidden', self.headers(), io.BytesIO(b'denied'))
        with mock.patch.object(http, '_urllib_safe_open', side_effect=error):
            result = http._fetch_urllib(URL, 20, http.DEFAULT_UA, 8)
        self.assertEqual(403, result.status)
        self.assertNotIn('x-narwhal-truncated', result.headers)


if __name__ == '__main__':
    unittest.main()
