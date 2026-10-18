"""JS comparisons require two eligible snapshots, not a truncated prefix."""

import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import brief
import compare
import crawl_site
import diff_scan
import scan
from lib import http, report as reportlib

URL = 'https://example.test/owner'
RIVAL = 'https://example.test/rival'
HTML = '<title>A detailed guide</title><h1>Guide</h1><p>' + 'word ' * 350 + '</p>'


def response(body=HTML, status=200, truncated=False, content_type='text/html', rendered=False):
    headers = {'content-type': content_type}
    if truncated:
        headers['x-narwhal-truncated'] = 'true'
    return http.Response(URL, URL, status, headers, body, 1, rendered=rendered)


def scanned(raw, *, partial_dom=False, limit=64_000, context=None, rendered=True, only=None):
    replies = [response(rendered=rendered, truncated=partial_dom), raw]
    with mock.patch.object(http, 'fetch', side_effect=replies) as fetch:
        result = scan.scan(URL, render=rendered, max_bytes=limit,
                           ctx=context if context is not None else {}, check_images=False, only=only)
    return result, fetch


class TestJsBaselineCoverage(unittest.TestCase):
    def test_same_clamped_budget_reaches_the_served_html_fetch(self):
        for requested, expected in ((1, 64_000), (9_000_000, 9_000_000), (99_000_000, 20_000_000)):
            with self.subTest(requested=requested):
                report, fetch = scanned(response(), limit=requested)
                self.assertEqual(expected, fetch.call_args.kwargs['max_bytes'])
                self.assertEqual(expected, report.meta['coverage']['js_comparison']['byte_limit'])

    def test_truncated_served_html_does_not_create_fake_js_only_percentage(self):
        report, _ = scanned(response('<title>Guide</title>', truncated=True))
        self.assertFalse(report.meta['coverage']['response_truncated'])
        self.assertNotIn('js_dependence', report.meta)
        receipt = report.meta['coverage']['js_comparison']
        self.assertEqual('unverified', receipt['status'])
        self.assertEqual('served_html_truncated', receipt['reason'])
        self.assertIn('JS-dependence was not measured', report.to_markdown())
        self.assertIn('served HTML was truncated', report.to_html())

    def test_unavailable_served_html_has_an_explicit_unverified_receipt(self):
        for status in (0, 404, 206):
            with self.subTest(status=status):
                report, _ = scanned(response(status=status))
                self.assertNotIn('js_dependence', report.meta)
                receipt = report.meta['coverage']['js_comparison']
                self.assertEqual('unverified', receipt['status'])
                self.assertEqual('served_html_unavailable', receipt['reason'])

    def test_explicit_non_html_baseline_is_not_js_evidence(self):
        report, _ = scanned(response('{"data": 1}', content_type='application/json'))
        self.assertNotIn('js_dependence', report.meta)
        self.assertEqual('served_non_html', report.meta['coverage']['js_comparison']['reason'])

    def test_complete_pair_keeps_normal_numeric_measurements(self):
        report, _ = scanned(response())
        expected = scan.jsdiff.analyze(HTML, HTML, URL)
        self.assertEqual({key: expected[key] for key in ('words_raw', 'words_rendered', 'js_only_pct', 'text_comparison')},
                         report.meta['js_dependence'])
        self.assertEqual(0, report.meta['js_dependence']['js_only_pct'])
        self.assertEqual({'status': 'measured', 'byte_limit': 64_000},
                         report.meta['coverage']['js_comparison'])

    def test_partial_dom_records_unverified_without_fetching_a_baseline(self):
        report, fetch = scanned(response(), partial_dom=True)
        self.assertEqual(1, fetch.call_count)
        self.assertNotIn('js_dependence', report.meta)
        self.assertEqual('rendered_html_truncated',
                         report.meta['coverage']['js_comparison']['reason'])

    def test_failed_or_partial_baseline_cannot_reuse_cached_js_context(self):
        for raw in (response(status=404), response(truncated=True)):
            with self.subTest(status=raw.status):
                context = {'jsdep': {'js_only_pct': 99}}
                seen = []
                def auditor(doc, resp, report, ctx):
                    seen.append('jsdep' in ctx)
                with mock.patch.dict(scan.AUDITORS, {'technical': auditor}):
                    report, _ = scanned(raw, context=context)
                self.assertEqual([False], seen)
                self.assertEqual({'jsdep': {'js_only_pct': 99}}, context)
                self.assertNotIn('js_dependence', report.meta)

    def test_expected_baseline_transport_failures_are_unverified_not_crashes(self):
        for error in (OSError('connection lost'), http.SSRFError('host policy rejection')):
            with self.subTest(error=type(error).__name__):
                report, _ = scanned(error)
                self.assertNotIn('js_dependence', report.meta)
                self.assertEqual('served_html_unavailable',
                                 report.meta['coverage']['js_comparison']['reason'])

    def test_baseline_programming_errors_are_not_silently_swallowed(self):
        with self.assertRaisesRegex(RuntimeError, 'unexpected bug'):
            scanned(RuntimeError('unexpected bug'))

    def test_raw_scan_does_not_claim_a_js_comparison_was_requested(self):
        report, fetch = scanned(response(), rendered=False)
        self.assertEqual(1, fetch.call_count)
        self.assertNotIn('js_comparison', report.meta['coverage'])

    def test_legacy_missing_or_malformed_receipts_do_not_invent_missing_measurement(self):
        for value in (None, 'unverified', [], {}, {'status': 'measured'}, {'status': True}):
            with self.subTest(value=value):
                meta = {'coverage': {'js_comparison': value}}
                self.assertIsNone(reportlib.recorded_js_comparison_problem(meta))

    def test_unverified_receipt_with_unknown_reason_remains_visible_without_crashing(self):
        for reason in ('future_reason', [], None):
            with self.subTest(reason=reason):
                meta = {'coverage': {'js_comparison': {'status': 'unverified', 'reason': reason}}}
                self.assertIsInstance(reportlib.recorded_js_comparison_problem(meta), str)

    def test_diff_does_not_turn_a_skipped_js_check_into_a_resolution(self):
        complete, _ = scanned(response())
        skipped, _ = scanned(response(truncated=True))
        old, new = json.loads(complete.to_json()), json.loads(skipped.to_json())
        for first, second in ((old, new), (new, old), (new, new)):
            result = diff_scan.diff_reports(first, second)
            self.assertEqual('incomparable', result['comparison']['status'])
            self.assertIsNone(result['score_delta'])
            self.assertIsNone(result['regression'])
            self.assertEqual([], result['resolved'])
        with tempfile.TemporaryDirectory() as folder:
            before, after = Path(folder) / 'before.json', Path(folder) / 'after.json'
            before.write_text(json.dumps(old), encoding='utf-8')
            after.write_text(json.dumps(new), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                status = diff_scan.main([str(before), str(after), '--fail-on-regression'])
            self.assertEqual(2, status)

    def test_unselected_js_auditors_do_not_block_focused_schema_score_diffs(self):
        complete, _ = scanned(response(), only=['schema'])
        skipped, _ = scanned(response(truncated=True), only=['schema'])
        self.assertIsNotNone(reportlib.recorded_js_comparison_problem(skipped.meta))
        self.assertIsNone(reportlib.recorded_js_comparison_problem(skipped.meta, for_score=True))
        result = diff_scan.diff_reports(json.loads(complete.to_json()), json.loads(skipped.to_json()))
        self.assertEqual('comparable', result['comparison']['status'])
        self.assertEqual(0, result['score_delta'])

    def test_compare_and_brief_reject_an_unverified_target_score(self):
        incomplete, _ = scanned(response(truncated=True))
        complete, _ = scanned(response())
        with mock.patch.object(scan, 'scan', side_effect=lambda url, **k: incomplete if url == URL else complete):
            compared = compare.run([URL, RIVAL])
            content = brief.run(URL, [RIVAL], use_gsc=False)
        self.assertIn('error', compared)
        self.assertTrue(compared['failed'][0]['js_comparison_unverified'])
        self.assertIn('JS-dependence', compare.render_markdown(compared))
        self.assertIn('unverified', content['error'])

    def test_crawl_serializes_unverified_js_coverage_and_audit_diff_gates_it(self):
        incomplete, _ = scanned(response(truncated=True))
        complete, _ = scanned(response())
        with mock.patch.object(crawl_site.scanner, 'gather_context', return_value={}), \
                mock.patch.object(crawl_site, 'discover', return_value=[URL, RIVAL]), \
                mock.patch.object(crawl_site.scanner, 'scan', side_effect=[complete, incomplete]):
            result = crawl_site.crawl(URL, max_pages=2, concurrency=1,
                                       obey_robots=False, detect_dupes=False)
        self.assertEqual([False, True], [p['js_comparison_unverified'] for p in result['pages']])
        current = {'site': URL, 'homepage': json.loads(complete.to_json()),
                   'crawl': json.loads(crawl_site.render_json(result)), 'overall_score': 80}
        prior = copy.deepcopy(current)
        for page in prior['crawl']['pages']:
            page['js_comparison_unverified'] = False
        compared = diff_scan.diff_reports(prior, current)
        self.assertEqual('incomparable', compared['comparison']['status'])
        self.assertTrue(any('JS-dependence' in reason for reason in compared['comparison']['reasons']))


if __name__ == '__main__':
    unittest.main()
