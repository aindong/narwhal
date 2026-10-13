"""Disabling subchecks or changing page representations does not prove a fix."""

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import crawl_site
import diff_scan
import mcp_server
import scan
from lib import http
from lib.report import Report
try:
    from .test_diff_scope import ALL, FINDING, report, invoke
except ImportError:
    from test_diff_scope import ALL, FINDING, report, invoke

URL = 'https://example.test/page'
HTML = '<title>A detailed image guide</title><h1>Image guide</h1><img src="/photo.png" width="1200" height="800">'
SETTINGS = {'render_requested': False, 'rendered': False, 'image_checks': True}


def configured(**changes):
    data = report(ALL)
    data['meta']['scan_settings'] = dict(SETTINGS, **changes)
    return data


class TestDiffSettings(unittest.TestCase):
    def assert_not_comparable(self, old, new):
        result = diff_scan.diff_reports(old, new)
        self.assertEqual('incomparable', result['comparison']['status'])
        self.assertIsNone(result['score_delta']); self.assertIsNone(result['regression'])
        for key in ('added', 'resolved', 'improved', 'worsened', 'new_critical_high'):
            self.assertEqual([], result[key])
        return result

    def test_changed_known_settings_block_in_both_directions(self):
        for key in SETTINGS:
            before = configured(); after = configured(**{key: not SETTINGS[key]})
            self.assert_not_comparable(before, after)
            self.assert_not_comparable(after, before)

    def test_matching_settings_keep_real_fix_and_regression_gates(self):
        before, after = configured(), configured()
        before['score'] = 94; before['findings'] = [FINDING]
        result = diff_scan.diff_reports(before, after)
        self.assertEqual('comparable', result['comparison']['status'])
        self.assertEqual(6, result['score_delta']); self.assertEqual([FINDING], result['resolved'])
        self.assertEqual(0, invoke(before, after, '--fail-on-regression')[0])
        self.assertEqual(1, invoke(after, before, '--fail-on-regression')[0])

    def test_partial_metadata_compares_only_explicit_known_booleans(self):
        old, new = report(ALL), report(ALL)
        old['meta']['scan_settings'] = {'image_checks': True}
        new['meta']['scan_settings'] = {'image_checks': False}
        self.assert_not_comparable(old, new)
        new['meta']['scan_settings'] = {'rendered': True}
        self.assertEqual('comparable', diff_scan.diff_reports(old, new)['comparison']['status'])

    def test_legacy_and_malformed_settings_are_not_inferred_from_findings(self):
        for raw in (None, [], {}, {'image_checks': 'false'}, {'rendered': 1},
                    {'render_requested': 0}, {'unknown': True}):
            legacy = report(ALL); legacy['meta']['scan_settings'] = raw
            result = diff_scan.diff_reports(legacy, configured())
            self.assertEqual('comparable', result['comparison']['status'])
            self.assertEqual({}, result['comparison']['old_settings'])
            self.assertIn('Missing settings are not inferred', result['comparison']['basis'])

    def test_unknown_scope_does_not_hide_a_known_setting_mismatch(self):
        before, after = configured(), configured(image_checks=False)
        del before['meta']['scan_scope']; del after['meta']['scan_scope']
        self.assert_not_comparable(before, after)

    def test_existing_boolean_rendered_field_is_known_without_new_settings(self):
        before, after = report(ALL), report(ALL)
        before['rendered'] = True; after['rendered'] = False
        self.assert_not_comparable(before, after)
        before['rendered'] = 'true'
        result = diff_scan.diff_reports(before, after)
        self.assertEqual({}, result['comparison']['old_settings'])
        self.assertEqual('comparable', result['comparison']['status'])

    def test_cli_gate_exits_two_and_diagnostic_has_no_resolved_claims(self):
        old, new = configured(), configured(image_checks=False)
        old['score'] = 94; old['findings'] = [FINDING]
        rc, text, _ = invoke(old, new, '--fail-on-regression')
        self.assertEqual(2, rc); self.assertIn('Image-check setting differs', text)
        self.assertIn('image resource checks: enabled', text); self.assertIn('image resource checks: disabled', text)
        self.assertNotIn('## ✅ Resolved', text)
        self.assertIn('rendering/image settings', text)
        self.assertEqual(0, invoke(old, new)[0])

    def test_mcp_uses_the_same_offline_guard_without_mutation(self):
        old, new = configured(), configured(rendered=True)
        saved = copy.deepcopy((old, new))
        result = mcp_server._diff(json.dumps(old), json.dumps(new))
        self.assertIsNone(result['score_delta']); self.assertEqual([], result['resolved'])
        self.assertEqual(saved, (old, new))

    def test_scan_records_effective_image_setting_not_unused_flag(self):
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, HTML, 1)
        with mock.patch.object(http, 'fetch', return_value=response):
            for groups, check in ((['schema'], True), (['technical'], False)):
                rep = scan.scan(URL, only=groups, ctx={}, check_images=check)
                self.assertEqual(dict(SETTINGS, image_checks=False),
                                 {key: rep.meta['scan_settings'][key] for key in SETTINGS})
                self.assertEqual(64, len(rep.meta['scan_settings']['rule_config']))
                self.assertEqual(rep.meta['scan_settings'], json.loads(rep.to_json())['meta']['scan_settings'])

    def test_requested_rendering_and_actual_fallback_are_distinct(self):
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, HTML, 1, rendered=False)
        with mock.patch.object(http, 'fetch', return_value=response):
            rep = scan.scan(URL, only=['schema'], ctx={}, check_images=False, render=True)
        self.assertEqual({'render_requested': True, 'rendered': False, 'image_checks': False},
                         {key: rep.meta['scan_settings'][key] for key in SETTINGS})
        for text in (rep.to_markdown(), rep.to_html()):
            self.assertIn('Rendering was requested but no rendered DOM was measured', text)

    def test_actual_rendered_response_is_recorded(self):
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, HTML, 1, rendered=True)
        with mock.patch.object(http, 'fetch', return_value=response):
            rep = scan.scan(URL, only=['schema'], ctx={}, check_images=False, render=True)
        self.assertTrue(rep.meta['scan_settings']['rendered'])
        self.assertIn('Findings use rendered HTML.', rep.to_html())

    def test_visible_scope_notes_show_disabled_images_without_guessing_legacy(self):
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, HTML, 1)
        with mock.patch.object(http, 'fetch', return_value=response):
            rep = scan.scan(URL, only=['technical'], ctx={}, check_images=False)
        for text in (rep.to_html(), rep.to_markdown()):
            self.assertIn('Image resource checks were disabled.', text)
            self.assertIn('Findings use served HTML.', text)
        del rep.meta['scan_settings']
        self.assertNotIn('Image resource checks were disabled.', rep.to_html())

    def test_disabling_resource_checks_does_not_disable_alt_text_findings(self):
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, HTML, 1)
        with mock.patch.object(http, 'fetch', return_value=response):
            rep = scan.scan(URL, only=['technical'], ctx={}, check_images=False)
        self.assertTrue(any('alt' in finding.title.lower() for finding in rep.findings))
        self.assertIn('Image resource checks were disabled.', rep.to_html())

    def test_skipping_image_checks_on_unchanged_page_is_not_a_fix(self):
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, HTML, 1)
        head = (200, {'content-type': 'image/png', 'content-length': '768000'}, '')
        with mock.patch.object(http, 'fetch', return_value=response), mock.patch.object(http, 'head_info', return_value=head):
            before = scan.scan(URL, only=['technical'], ctx={}, check_images=True)
            after = scan.scan(URL, only=['technical'], ctx={}, check_images=False)
        self.assertGreater(after.score(), before.score())
        self.assert_not_comparable(json.loads(before.to_json()), json.loads(after.to_json()))

    def test_crawl_serializes_page_settings_without_changing_scores(self):
        rep = Report(URL, meta={'scan_settings': dict(SETTINGS, image_checks=False)})
        with mock.patch.object(crawl_site.scanner, 'gather_context', return_value={}), \
                mock.patch.object(crawl_site, 'discover', return_value=[URL]), \
                mock.patch.object(crawl_site.scanner, 'scan', return_value=rep):
            data = crawl_site.crawl(URL, concurrency=1, detect_dupes=False)
        saved = json.loads(crawl_site.render_json(data))
        self.assertEqual(rep.meta['scan_settings'], saved['pages'][0]['scan_settings'])
        self.assertEqual(100, saved['avg_score'])

    def test_audit_compares_common_crawl_page_settings_not_just_homepage(self):
        good = {'site': URL, 'overall_score': 90, 'homepage': configured(),
                'crawl': {'pages': [{'url': URL, 'scan_settings': dict(SETTINGS, image_checks=False)}]}}
        changed = copy.deepcopy(good)
        changed['crawl']['pages'][0]['scan_settings']['rendered'] = True
        result = self.assert_not_comparable(good, changed)
        self.assertTrue(any('Crawl setting rendered' in reason for reason in result['comparison']['reasons']))
        self.assert_not_comparable(changed, good)
        self.assertEqual(2, invoke(good, changed, '--fail-on-regression')[0])

    def test_crawl_settings_do_not_infer_missing_or_outside_sample_modes(self):
        before = {'site': URL, 'homepage': configured(), 'crawl': {'pages': [None, {'url': URL}]}}
        after = copy.deepcopy(before)
        after['crawl']['pages'] = [{'url': URL + '/other', 'scan_settings': SETTINGS}]
        self.assertEqual('comparable', diff_scan.diff_reports(before, after)['comparison']['status'])

    def test_contradictory_duplicate_crawl_modes_are_not_last_wins(self):
        data = {'site': URL, 'homepage': configured(), 'crawl': {'pages': [
            {'url': URL, 'scan_settings': SETTINGS},
            {'url': URL, 'scan_settings': dict(SETTINGS, rendered=True)}]}}
        self.assert_not_comparable(data, data)

    def test_known_crawl_contradictions_block_with_unknown_or_outside_sample_other(self):
        data = {'site': URL, 'homepage': configured(), 'crawl': {'pages': [
            {'url': URL, 'scan_settings': SETTINGS},
            {'url': URL, 'scan_settings': dict(SETTINGS, rendered=True)}]}}
        for crawl in (None, {'pages': [{'url': URL}]},
                      {'pages': [{'url': URL + '/other', 'scan_settings': SETTINGS}]}):
            unknown = {'site': URL, 'homepage': configured(), 'crawl': crawl}
            self.assert_not_comparable(data, unknown)
            self.assert_not_comparable(unknown, data)
            self.assertEqual(2, invoke(data, unknown, '--fail-on-regression')[0])


if __name__ == '__main__':
    unittest.main()
