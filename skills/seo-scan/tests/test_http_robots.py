"""Response-header indexing declarations retain field and crawler scope."""

import json
import sys
import tempfile
import types
import unittest
from email.message import Message
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_technical
import plan
import scan
from lib import http, indexing
from lib.report import Report, _http_robots_notes

URL = 'https://example.test/guide'
NOINDEX, NOFOLLOW = 'technical.http.robots.noindex', 'technical.http.robots.nofollow'


def response(fields=None, headers=None):
    return http.Response(URL, URL, 200, headers or {'content-type': 'text/html'},
                         '<html><head><title>Example page title</title></head><body><h1>Example</h1></body></html>',
                         0, robots_header_fields=fields,
                         robots_header_basis='response_header_fields' if fields is not None else 'merged_or_unknown')


def audited(fields=None, headers=None):
    rep = Report(URL, final_url=URL, fetched_status=200)
    audit_technical._http_robots(response(fields, headers), rep)
    return rep


class TestHTTPRobots(unittest.TestCase):
    def test_generic_none_is_two_distinct_header_findings(self):
        rep = audited(['NONE'])
        self.assertEqual([(NOINDEX, 'critical'), (NOFOLLOW, 'medium')], [(f.rule_id, f.severity) for f in rep.findings])
        self.assertTrue(all('field #1: none' in f.evidence for f in rep.findings))
        self.assertTrue(all('hosting' in f.recommendation for f in rep.findings))

    def test_new_field_resets_named_scope_to_generic(self):
        rep = audited(['googlebot: nofollow', 'noindex'])
        self.assertEqual([NOINDEX], [f.rule_id for f in rep.findings])
        receipt = rep.meta['http_robots']
        self.assertEqual(['noindex'], receipt['generic'])
        self.assertEqual([{'agent': 'googlebot', 'directives': ['nofollow']}], receipt['scoped'])
        self.assertIn('field #2', rep.findings[0].evidence)

    def test_named_scope_continues_across_commas_until_next_prefix(self):
        rep = audited(['GoogleBot: noindex, nofollow, otherbot: none'])
        self.assertEqual([], rep.findings)
        self.assertEqual([], rep.meta['http_robots']['generic'])
        self.assertEqual(['googlebot', 'otherbot'], [item['agent'] for item in rep.meta['http_robots']['scoped']])
        self.assertEqual(100, rep.score())

    def test_generic_and_named_rules_do_not_overwrite_each_other(self):
        rep = audited(['noindex, googlebot: nofollow', 'all'])
        self.assertEqual([NOINDEX], [f.rule_id for f in rep.findings])
        self.assertEqual(['noindex'], rep.meta['http_robots']['generic'])

    def test_parameters_dates_and_substrings_are_not_restriction_names(self):
        for value in ('max-image-preview: none', 'max-snippet:0', 'x-noindex, x-nofollow',
                      'unavailable_after: Wed, 21 Oct 2099 12:00:00 GMT'):
            with self.subTest(value=value):
                rep = audited([value])
                self.assertEqual([], rep.findings)
                self.assertEqual([], rep.meta['http_robots']['scoped'])
        rep = audited(['noindex max-image-preview:none'])
        self.assertEqual([NOINDEX], [f.rule_id for f in rep.findings])

    def test_parameter_keeps_preceding_named_scope(self):
        rep = audited(['googlebot: noindex, max-image-preview: none, nofollow'])
        self.assertEqual([], rep.findings)
        self.assertEqual([{'agent': 'googlebot', 'directives': ['nofollow', 'noindex']}], rep.meta['http_robots']['scoped'])

    def test_repeated_generic_rules_are_deduplicated(self):
        rep = audited(['noindex', 'noindex, none', 'nofollow'])
        self.assertEqual([NOINDEX, NOFOLLOW], [f.rule_id for f in rep.findings])
        self.assertEqual(3, rep.meta['http_robots']['field_count'])

    def test_merged_legacy_headers_are_explicitly_unverified(self):
        rep = audited(headers={'X-Robots-Tag': 'googlebot: noindex, nofollow'})
        self.assertEqual([], rep.findings)
        self.assertEqual('merged_or_unknown', rep.meta['http_robots']['basis'])
        self.assertTrue(any('boundaries' in note for note in rep.meta['http_robots']['notes']))

    def test_browser_basis_is_not_original_wire_field_proof(self):
        receipt, _ = indexing.http_robots(['googlebot: noindex'], 'browser_reported_fields')
        self.assertTrue(any('confirm original fields' in note for note in receipt['notes']))

    def test_browser_newlines_keep_observed_named_prefix_without_wire_claim(self):
        receipt, _ = indexing.http_robots(['none\ngooglebot: nofollow'], 'browser_reported_fields')
        self.assertEqual(['nofollow', 'noindex'], receipt['generic'])
        self.assertEqual([{'agent': 'googlebot', 'directives': ['nofollow']}], receipt['scoped'])
        self.assertEqual(1, receipt['field_count'])

    def test_merged_newline_does_not_reset_named_scope_to_generic(self):
        receipt, _ = indexing.http_robots(['googlebot: nofollow\nnoindex'], 'browser_reported_fields')
        self.assertEqual([], receipt['generic'])
        self.assertEqual([{'agent': 'googlebot', 'directives': ['nofollow', 'noindex']}], receipt['scoped'])
        self.assertTrue(any('confirm original fields' in note for note in receipt['notes']))

    def test_folded_parameter_values_are_not_standalone_rules(self):
        rep = audited(['max-image-preview:\r\n none'])
        self.assertEqual([], rep.findings)
        scoped = audited(['googlebot: noindex\r\n nofollow'])
        self.assertEqual([], scoped.findings)
        self.assertEqual([{'agent': 'googlebot', 'directives': ['nofollow', 'noindex']}], scoped.meta['http_robots']['scoped'])

    def test_no_header_adds_no_finding_receipt_or_passing_claim(self):
        rep = audited([])
        self.assertEqual([], rep.findings)
        self.assertNotIn('http_robots', rep.meta)

    def test_non_scoring_notes_reach_json_markdown_and_escaped_html(self):
        rep = audited(['googlebot: noindex'])
        self.assertIn('http_robots', json.loads(rep.to_json())['meta'])
        self.assertIn('HTTP robots observations (not scored)', rep.to_markdown())
        self.assertIn('googlebot', rep.to_html())
        rep.meta['http_robots']['notes'].append('<script>bad</script>')
        html = rep.to_html()
        self.assertNotIn('<script>bad</script>', html)
        self.assertIn('&lt;script&gt;bad&lt;/script&gt;', html)
        self.assertEqual(100, rep.score())

    def test_unknown_receipts_ignored_and_display_notes_are_bounded(self):
        self.assertEqual([], _http_robots_notes({'http_robots': {'version': 99, 'basis': 'response_header_fields', 'notes': ['bad']}}))
        notes = _http_robots_notes({'http_robots': {'version': 1, 'basis': 'response_header_fields', 'notes': ['x' * 1000] * 30}})
        self.assertEqual(22, len(notes))
        self.assertTrue(all(len(note) <= 600 for note in notes))
        self.assertIn('10 more', notes[-1])

    def test_technical_scan_integrates_header_receipt_and_ids(self):
        with mock.patch.object(http, 'fetch', return_value=response(['noindex'])):
            rep = scan.scan(URL, only=['technical'], ctx={}, check_images=False)
        self.assertIn(NOINDEX, {f.rule_id for f in rep.findings})
        self.assertEqual(['noindex'], rep.meta['http_robots']['generic'])
        with mock.patch.object(http, 'fetch', return_value=response(['noindex'])):
            content = scan.scan(URL, only=['content'], ctx={}, check_images=False)
        self.assertNotIn('http_robots', content.meta)

    def test_header_plan_is_manual_hosting_not_html_metadata(self):
        rep = audited(['noindex'])
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'index.html').write_text('<html><title>Owner fixture</title></html>', encoding='utf-8')
            result = plan.build_plan(json.loads(rep.to_json()), directory, report_source='before.json')
        action = result['actions'][0]
        self.assertEqual('server_config', action['artifact'])
        self.assertEqual('manual_external', action['safety'])
        self.assertTrue(action['requires_deploy'])
        self.assertEqual([], action['likely_files'])
        self.assertIn('response-header', action['proposed_change'])
        self.assertFalse(any('local-preview-url' in step for step in action['verification']))


class TestHTTPRobotsCapture(unittest.TestCase):
    def test_stdlib_duplicate_fields_survive_even_when_mapping_would_drop_one(self):
        headers = Message()
        headers['X-Robots-Tag'] = 'googlebot: nofollow'
        headers['x-robots-tag'] = 'noindex'
        self.assertEqual(['googlebot: nofollow', 'noindex'], http._robots_header_fields(headers))
        self.assertEqual('noindex', http._origin_headers(headers)['x-robots-tag'])

    def test_raw_requests_getlist_and_no_header_capture(self):
        headers = types.SimpleNamespace(getlist=lambda name: ['googlebot: nofollow', 'noindex'])
        self.assertEqual(['googlebot: nofollow', 'noindex'], http._robots_header_fields(headers))
        self.assertEqual([], http._robots_header_fields(Message()))
        self.assertIsNone(http._robots_header_fields({'x-robots-tag': 'noindex'}))

    def test_both_fetch_transports_keep_fields_and_scrub_internal_marker(self):
        headers = Message()
        headers['Content-Type'] = 'text/html; charset=utf-8'
        headers['X-Robots-Tag'] = 'googlebot: nofollow'
        headers['X-Robots-Tag'] = 'noindex'
        headers['X-Narwhal-Truncated'] = 'true'
        raw = mock.Mock()
        raw.headers = headers
        raw.raw = types.SimpleNamespace(headers=headers)
        raw.encoding, raw.status_code, raw.status = 'utf-8', 200, 200
        raw.iter_content.return_value = [b'<h1>Complete</h1>']
        raw.read.return_value = b'<h1>Complete</h1>'
        raw.__enter__ = mock.Mock(return_value=raw)
        raw.__exit__ = mock.Mock(return_value=False)
        requests = types.SimpleNamespace(RequestException=type('RequestError', (OSError,), {}))
        with mock.patch.dict(sys.modules, {'requests': requests}), \
                mock.patch.object(http, '_requests_safe', return_value=(raw, URL, [])):
            req = http._fetch_requests(URL, 2, http.DEFAULT_UA, 64000)
        with mock.patch.object(http, '_urllib_safe_open', return_value=(raw, URL, [])):
            std = http._fetch_urllib(URL, 2, http.DEFAULT_UA, 64000)
        for result in (req, std):
            self.assertTrue(result.ok)
            self.assertEqual(['googlebot: nofollow', 'noindex'], result.robots_header_fields)
            self.assertEqual('response_header_fields', result.robots_header_basis)
            self.assertNotIn('x-narwhal-truncated', result.headers)
            self.assertEqual([NOINDEX], [f.rule_id for f in audited(result.robots_header_fields).findings])


if __name__ == '__main__':
    unittest.main()
