"""A focused or uncompleted scan is not an overall page-health verdict."""

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import scan
from lib import config, http
from lib.report import Report, score_gauge

URL = 'https://example.test/recipe'
HTML = '<h1>Soup</h1><script type="application/ld+json">{"@type":"Recipe","name":"Soup","image":"/soup.jpg"}</script>'


def response(status=200, headers=None):
    return http.Response(URL, URL, status, headers or {'content-type': 'text/html'}, HTML, 1)


def scanned(only=None, resp=None, cfg=None):
    with mock.patch.object(scan.http, 'fetch', return_value=resp or response()):
        return scan.scan(URL, only=only, ctx={}, check_images=False, config=cfg)


class TestScanScope(unittest.TestCase):
    def test_subset_records_selected_completed_and_not_selected_groups(self):
        report = scanned(['schema'])
        self.assertEqual({'requested': ['schema'], 'completed': ['schema'],
                          'not_selected': ['technical', 'content', 'geo']}, report.meta['scan_scope'])
        self.assertEqual(report.meta['scan_scope'], json.loads(report.to_json())['meta']['scan_scope'])
        self.assertEqual('Selected-check score', report.score_label())

    def test_markdown_and_html_label_subset_score_without_overall_page_claim(self):
        report = scanned(['schema'])
        for rendered in (report.to_markdown(), report.to_html()):
            for phrase in ('Focused page scan', 'Selected-check score', 'Checked auditor groups: Structured data.',
                           'Not selected: Technical SEO', 'not overall page health'):
                self.assertIn(phrase, rendered)
            self.assertNotIn('This page scores', rendered)
            self.assertNotIn('This page is in', rendered)
        self.assertIn('aria-label="Selected-check score', report.to_html())

    def test_all_four_groups_are_recorded_and_keep_the_full_title(self):
        report = scanned()
        self.assertEqual(list(scan.AUDITORS), report.meta['scan_scope']['requested'])
        self.assertEqual(list(scan.AUDITORS), report.meta['scan_scope']['completed'])
        self.assertEqual([], report.meta['scan_scope']['not_selected'])
        self.assertEqual('Health score', report.score_label())
        for rendered in (report.to_markdown(), report.to_html()):
            self.assertIn('SEO &amp; GEO Audit' if rendered.startswith('<!DOCTYPE') else 'SEO & GEO Audit', rendered)
            self.assertIn('All four groups ran for this page, not a site-wide or exhaustive validation.', rendered)
            self.assertNotIn('Not selected:', rendered)

    def test_explicit_all_groups_match_default_and_respect_request_order(self):
        selected = ['geo', 'schema', 'content', 'technical']
        report = scanned(selected)
        self.assertEqual(selected, report.meta['scan_scope']['requested'])
        self.assertEqual(selected, report.meta['scan_scope']['completed'])
        self.assertEqual(scanned().score(), report.score())
        self.assertEqual('Health score', report.score_label())

    def test_duplicates_do_not_run_or_penalize_a_group_twice(self):
        with mock.patch.dict(scan.AUDITORS, {'schema': mock.Mock(wraps=scan.AUDITORS['schema'])}):
            report = scanned(['schema', 'schema'])
            self.assertEqual(1, scan.AUDITORS['schema'].call_count)
        self.assertEqual(scanned(['schema']).score(), report.score())
        self.assertEqual(['schema'], report.meta['scan_scope']['requested'])

    def test_failed_fetch_runs_no_auditors_and_does_not_claim_measured_health(self):
        with mock.patch.dict(scan.AUDITORS, {name: mock.Mock() for name in scan.AUDITORS}):
            report = scanned(['schema'], response(status=503))
            self.assertFalse(any(fn.called for fn in scan.AUDITORS.values()))
        self.assertEqual([], report.meta['scan_scope']['completed'])
        self.assertEqual(0, report.score())
        self.assertEqual('Score unavailable', report.score_label())
        for rendered in (report.to_markdown(), report.to_html()):
            self.assertIn('Page scan not completed', rendered)
            self.assertIn('No auditor groups completed', rendered)
            self.assertIn('fail-safe, not measured page health', rendered)
            self.assertNotIn('Selected checks score', rendered)
            self.assertNotIn('Breakdown by area', rendered)
            self.assertIn('not measured' if rendered.startswith('#') else 'Not Measured', rendered)

    def test_recorded_zero_execution_is_zero_not_a_perfect_score(self):
        report = Report(URL, meta={'scan_scope': {'requested': ['schema'], 'completed': []}})
        self.assertEqual(0, report.score())
        self.assertEqual('Score unavailable', report.score_label())
        self.assertIn('not measured', report.to_markdown())
        self.assertNotIn('100/100', report.to_html())

    def test_nonhtml_response_does_not_mark_requested_auditors_completed(self):
        report = scanned(['technical', 'geo'], response(headers={'content-type': 'application/pdf'}))
        self.assertEqual([], report.meta['scan_scope']['completed'])
        self.assertEqual(0, report.score())
        self.assertEqual('Score unavailable', report.score_label())

    def test_truncated_responses_keep_partial_html_warning_even_with_all_groups(self):
        report = scanned(resp=response(headers={'content-type': 'text/html', 'x-narwhal-truncated': 'true'}))
        self.assertEqual(list(scan.AUDITORS), report.meta['scan_scope']['completed'])
        for rendered in (report.to_markdown(), report.to_html()):
            self.assertIn('Response was truncated; findings use partial HTML coverage.', rendered)

    def test_subset_score_includes_response_findings_without_claiming_technical_audit_ran(self):
        report = scanned(['schema'], response(headers={'content-type': 'text/html', 'x-narwhal-truncated': 'true'}))
        self.assertEqual(['schema'], report.meta['scan_scope']['completed'])
        self.assertIn('technical.response.truncated', {f.rule_id for f in report.findings})
        self.assertIn('response-level findings, not overall page health', report.to_markdown())

    def test_no_findings_does_not_mean_unselected_groups_passed(self):
        cfg = config.Config({'ignore': {'categories': ['technical', 'content', 'schema', 'geo']}})
        report = scanned(['schema'], cfg=cfg)
        self.assertEqual([], report.findings)
        self.assertEqual(100, report.score())
        self.assertEqual(['schema'], report.meta['scan_scope']['completed'])
        self.assertIn('not overall page health', report.to_markdown())
        self.assertNotIn('This page is in', report.to_html())

    def test_unknown_auditors_are_rejected_before_any_network_request(self):
        with mock.patch.object(scan.http, 'fetch') as fetch:
            with self.assertRaises(ValueError):
                scan.scan(URL, only=['schema', 'unknown'])
        fetch.assert_not_called()

    def test_legacy_or_malformed_metadata_never_infers_scope_from_findings(self):
        for scope in (None, [], {}, {'requested': ['schema'], 'completed': ['technical']},
                      {'requested': ['schema', 'schema'], 'completed': ['schema']},
                      {'requested': ['<script>'], 'completed': ['<script>']}):
            report = Report(URL)
            if scope is not None:
                report.meta['scan_scope'] = scope
            report.ok('schema', 'Valid test')
            self.assertEqual('Reported-findings score', report.score_label())
            for rendered in (report.to_markdown(), report.to_html()):
                self.assertIn('Auditor selection was not recorded', rendered)
                self.assertIn('Page findings report', rendered)
                self.assertNotIn('This page scores', rendered)
                self.assertNotIn('<script>', rendered)

    def test_partial_execution_identifies_unfinished_selected_groups(self):
        report = Report(URL, meta={'scan_scope': {'requested': ['schema', 'geo'], 'completed': ['schema']}})
        self.assertEqual('Selected-check score', report.score_label())
        self.assertIn('Not completed: GEO / LLMO.', report.to_markdown())
        self.assertIn('Not selected: Technical SEO; Content &amp; E-E-A-T.', report.to_html())

    def test_custom_title_preserved_while_scope_stays_visible(self):
        report = scanned(['schema'])
        self.assertIn('# My report', report.to_markdown('My report'))
        self.assertIn('<h1>My report</h1>', report.to_html('My report'))
        self.assertIn('not overall page health', report.to_html('My report'))

    def test_cli_threshold_failure_uses_the_selected_score_label(self):
        stderr, stdout = io.StringIO(), io.StringIO()
        with mock.patch.object(scan, 'scan', return_value=scanned(['schema'])), \
                contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
            rc = scan.main([URL, '--only', 'schema', '--no-config', '--fail-under', '100'])
        self.assertEqual(1, rc)
        self.assertIn('FAIL: selected-check score', stderr.getvalue())

    def test_mcp_subset_returns_the_same_execution_scope(self):
        with mock.patch.object(scan.http, 'fetch', return_value=response()), \
                mock.patch.object(scan, 'gather_context', return_value={}):
            payload = mcp_server._scan(URL, only='schema')
        self.assertEqual(['schema'], payload['meta']['scan_scope']['completed'])
        self.assertEqual(['technical', 'content', 'geo'], payload['meta']['scan_scope']['not_selected'])

    def test_shared_score_gauge_keeps_default_and_escapes_custom_label(self):
        self.assertIn('aria-label="Health score 99 of 100"', score_gauge(99))
        self.assertIn('Selected &amp; &lt;checks&gt;', score_gauge(99, label='Selected & <checks>'))


if __name__ == '__main__':
    unittest.main()
