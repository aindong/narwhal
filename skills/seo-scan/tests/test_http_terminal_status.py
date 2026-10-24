"""Unresolved 3xx responses are not successful page/resource representations."""
from pathlib import Path
import copy
import json
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import scan
import compare
import brief
import crawl_site
import diff_scan
from lib import http

URL = 'https://example.test/page/'
FINAL = 'https://example.test/final/'
BODY = '<html lang="en"><head><title>Controlled terminal response fixture</title></head><body><h1>Controlled fixture</h1><p>Not proof of a completed redirect.</p></body></html>'


def response(status, *, final=URL, body=BODY, redirects=None):
    return http.Response(URL, final, status, {'content-type': 'text/html'}, body, 1, redirects=redirects or [])


def scanned(status, **kwargs):
    with mock.patch.object(http, 'fetch', return_value=response(status, **kwargs)):
        return scan.scan(URL, ctx={}, check_images=False)


class TestTerminalHttpStatus(unittest.TestCase):
    def test_terminal_redirect_and_not_modified_statuses_are_not_success(self):
        for status in (300, 301, 302, 303, 304, 305, 307, 308, 399):
            self.assertFalse(response(status).ok, status)

    def test_success_remains_transport_success_not_complete_body_certification(self):
        for status in (200, 201, 202, 203, 204, 205, 206, 299):
            self.assertTrue(response(status).ok, status)
        self.assertTrue(response(200, body='').ok)
        failed = response(200); failed.error = 'Transport error'
        self.assertFalse(failed.ok)

    def test_existing_unavailable_statuses_remain_unsuccessful(self):
        for status in (0, 400, 403, 404, 429, 500, 503):
            self.assertFalse(response(status).ok)

    def test_terminal_html_body_does_not_run_page_auditors_or_receive_health_score(self):
        for status in (301, 302, 303, 307, 308):
            report = scanned(status)
            self.assertTrue(report.hard_fail, status)
            self.assertEqual(0, report.score())
            self.assertEqual([], report.meta['scan_scope']['completed'])
            self.assertEqual('Score unavailable', report.score_label())
            self.assertEqual(1, len(report.findings))
            self.assertNotIn('hreflang_extraction', report.meta)
            self.assertIsNone(getattr(report, '_doc', None))

    def test_not_modified_without_cached_representation_has_no_measured_health(self):
        report = scanned(304, body='')
        self.assertTrue(report.hard_fail)
        self.assertEqual([], report.meta['scan_scope']['completed'])
        self.assertIn('no page health was measured', report.to_html())

    def test_followed_redirect_with_successful_final_page_still_runs_all_groups(self):
        report = scanned(200, final=FINAL, redirects=[FINAL])
        self.assertFalse(report.hard_fail)
        self.assertEqual(FINAL, report.final_url)
        self.assertEqual([FINAL], report.meta['redirects'])
        self.assertEqual(['technical','content','schema','geo'], report.meta['scan_scope']['completed'])

    def test_text_resource_wrapper_does_not_return_terminal_redirect_body(self):
        for status in (301, 302, 304, 307, 308):
            with mock.patch.object(http, 'fetch', return_value=response(status)):
                self.assertIsNone(http.fetch_text(URL))

    def test_text_resource_wrapper_retains_successful_resource_body(self):
        with mock.patch.object(http, 'fetch', return_value=response(200)):
            self.assertEqual(BODY, http.fetch_text(URL))

    def test_real_compare_and_brief_reject_terminal_response(self):
        with mock.patch.object(scan, 'gather_context', return_value={}), \
                mock.patch.object(http, 'fetch', return_value=response(302)):
            result = compare.run([URL, FINAL])
            self.assertNotIn('you', result)
            self.assertNotIn('competitors', result)
            self.assertEqual(2, len(result['failed']))
            with self.assertRaises(RuntimeError): brief._page(URL)

    def test_crawl_retains_terminal_http_status_as_unavailable_sample_not_page_health(self):
        with mock.patch.object(scan, 'gather_context', return_value={}), \
                mock.patch.object(crawl_site, 'discover', return_value=[URL]), \
                mock.patch.object(http, 'fetch', return_value=response(301)):
            result = crawl_site.crawl(URL, max_pages=1, concurrency=1, detect_dupes=False)
        self.assertTrue(result['pages'][0]['hard_fail'])
        self.assertEqual(0, result['avg_score'])
        self.assertEqual('unavailable', result['pages'][0]['hreflang_source_observation']['status'])

    def test_unmeasured_terminal_status_diffs_do_not_claim_measured_regression_or_fix(self):
        valid = json.loads(scanned(200).to_json())
        terminal = json.loads(scanned(302).to_json())
        for earlier, later in [(valid, terminal), (terminal, valid), (terminal, copy.deepcopy(terminal))]:
            self.assertEqual('incomparable', diff_scan.diff_reports(earlier, later)['comparison']['status'])


if __name__ == '__main__': unittest.main()
