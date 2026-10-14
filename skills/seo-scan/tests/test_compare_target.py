"""A failed requested target must not turn a rival into the user's page."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import compare
from lib import http

TARGET = 'https://example.test/owner'
RIVALS = ['https://example.test/rival-one', 'https://example.test/rival-two']
HTML = '<html><title>A detailed guide</title><h1>Guide</h1><p>A brief guide.</p></html>'


def response(url, status=200, content_type='text/html', final_url=None):
    return http.Response(url, final_url or url, status, {'content-type': content_type}, HTML, 1)


class TestCompareTarget(unittest.TestCase):
    def run_compare(self, fetch, urls=None):
        with mock.patch.object(compare.scanner, 'gather_context', return_value={}), \
                mock.patch.object(http, 'fetch', side_effect=fetch):
            return compare.run(urls or [TARGET] + RIVALS)

    def assert_no_target_verdict(self, data):
        self.assertIn('error', data)
        self.assertIn('first URL', data['error'])
        for key in ('you', 'gaps', 'leads', 'competitors'):
            self.assertNotIn(key, data)
        self.assertEqual(TARGET, data['failed'][0]['url'])

    def test_failed_target_is_not_replaced_by_two_successful_rivals(self):
        calls = []
        def fetch(url, **kwargs):
            calls.append(url)
            return response(url, status=404 if url == TARGET else 200)
        data = self.run_compare(fetch)
        self.assert_no_target_verdict(data)
        self.assertEqual(404, data['failed'][0]['status'])
        self.assertEqual([TARGET] + RIVALS, calls)

    def test_rejected_target_retains_error_without_promoting_a_rival(self):
        def fetch(url, **kwargs):
            if url == TARGET:
                raise http.SSRFError('Target rejected by host policy')
            return response(url)
        data = self.run_compare(fetch)
        self.assert_no_target_verdict(data)
        self.assertEqual(0, data['failed'][0]['status'])
        self.assertIn('host policy', data['failed'][0]['error'])

    def test_non_html_target_cannot_be_replaced_by_html_rivals(self):
        def fetch(url, **kwargs):
            return response(url, content_type='application/pdf' if url == TARGET else 'text/html')
        self.assert_no_target_verdict(self.run_compare(fetch))

    def test_successful_target_redirect_keeps_its_requested_role(self):
        final = 'https://example.test/owner-renamed'
        def fetch(url, **kwargs):
            return response(url, final_url=final if url == TARGET else None)
        data = self.run_compare(fetch)
        self.assertNotIn('error', data)
        self.assertEqual(final, data['you']['url'])
        self.assertEqual(RIVALS, [item['url'] for item in data['competitors']])

    def test_dead_rival_does_not_sink_a_valid_target_and_remaining_rival(self):
        def fetch(url, **kwargs):
            return response(url, status=404 if url == RIVALS[0] else 200)
        data = self.run_compare(fetch)
        self.assertNotIn('error', data)
        self.assertEqual(TARGET, data['you']['url'])
        self.assertEqual([RIVALS[1]], [item['url'] for item in data['competitors']])

    def test_repeated_url_is_not_an_implicit_target_retry(self):
        calls = []
        def fetch(url, **kwargs):
            calls.append(url)
            return response(url, status=404 if len(calls) == 1 else 200)
        self.assert_no_target_verdict(self.run_compare(fetch, urls=[TARGET, TARGET, RIVALS[0]]))

    def test_target_failure_markdown_has_diagnostics_not_a_scoreboard(self):
        data = self.run_compare(lambda url, **k: response(url, status=404 if url == TARGET else 200))
        output = compare.render_markdown(data)
        self.assertIn('first URL', output)
        self.assertIn(TARGET + ' (status 404)', output)
        self.assertNotIn('Scoreboard', output)
        self.assertNotIn('No feature gaps detected', output)

    def test_target_failure_cli_json_exits_two_and_has_no_rival_as_you(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'comparison.json'
            with mock.patch.object(compare.scanner, 'gather_context', return_value={}), \
                    mock.patch.object(http, 'fetch', side_effect=lambda url, **k: response(
                        url, status=404 if url == TARGET else 200)), \
                    contextlib.redirect_stdout(io.StringIO()):
                status = compare.main([TARGET] + RIVALS + ['--format', 'json', '-o', str(path)])
            self.assertEqual(2, status)
            self.assert_no_target_verdict(json.loads(path.read_text()))


if __name__ == '__main__':
    unittest.main()
