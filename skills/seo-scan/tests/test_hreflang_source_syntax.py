"""Malformed source alternates must not crash scans or fabricate fully-qualified annotations."""
from pathlib import Path
import copy
import json
import socket
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import scan
import audit_technical
import brief
import compare
import crawl_site
import diff_scan
import plan
from lib import htmlx, http, hreflang
from lib.report import Report

BASE = 'https://example.test/en/'
VALID = 'https://example.test/fr/'


def source(*hrefs):
    return '<html><head><title>Alternate fixture</title>' + ''.join(
        '<link rel="alternate" hreflang="fr" href="' + href + '">' for href in hrefs) + '</head><body><h1>Alternate fixture</h1></body></html>'


def receipt(*hrefs):
    result = {}
    hreflang.extract(htmlx.parse(source(*hrefs), BASE), BASE, diagnostics=result)
    return result


def alts(*urls):
    return [{'lang': 'fr', 'href': url} for url in urls]


def page_report(*hrefs, only=None):
    response = http.Response(BASE, BASE, 200, {'content-type': 'text/html'}, source(*hrefs), 1)
    with mock.patch.object(http, 'fetch', return_value=response):
        return scan.scan(BASE, ctx={}, only=only, check_images=False)


class TestHreflangSourceSyntax(unittest.TestCase):
    def test_malformed_brackets_do_not_abort_later_supported_alternates(self):
        page = htmlx.parse(source('http://[', VALID), BASE)
        self.assertEqual([{'lang': 'fr', 'href': VALID}], hreflang.extract(page, BASE))

    def test_bad_ports_are_source_omissions_not_probe_targets(self):
        for href in ('https://example.test:nope/fr/', 'https://example.test:65536/fr/'):
            self.assertEqual([], hreflang.extract(htmlx.parse(source(href), BASE), BASE))

    def test_relative_and_scheme_relative_are_not_fabricated_absolute_annotations(self):
        for href in ('/fr/', '../fr/', '//example.test/fr/', 'https:fr/'):
            self.assertEqual([], hreflang.extract(htmlx.parse(source(href), BASE), BASE))

    def test_non_http_hrefs_are_not_language_page_targets(self):
        for href in ('javascript:alert(1)', 'data:text/plain,hello', 'mailto:a@example.test'):
            self.assertEqual([], hreflang.extract(htmlx.parse(source(href), BASE), BASE))

    def test_scan_finishes_all_groups_after_malformed_source_hreflang(self):
        body = source('http://secret:password@[broken', VALID)
        response = http.Response(BASE, BASE, 200, {'content-type': 'text/html'}, body, 1)
        with mock.patch.object(http, 'fetch', return_value=response):
            report = scan.scan(BASE, ctx={}, check_images=False)
        self.assertEqual(['technical', 'content', 'schema', 'geo'], report.meta['scan_scope']['completed'])
        self.assertEqual([{'lang': 'fr', 'href': VALID}], report.meta['hreflang'])
        self.assertNotIn('password', report.to_json())

    def test_imported_bad_probe_target_cannot_crash_or_consume_valid_cap(self):
        pages = {BASE: [{'lang': 'fr', 'href': 'http://['}, {'lang': 'fr', 'href': VALID}]}
        called = []
        def fetch(url): called.append(url); return '<html></html>'
        result = hreflang.probe(pages, cap=1, fetch_text=fetch)
        self.assertEqual([VALID], called)
        self.assertEqual([VALID], list(result))

    def test_supported_literal_url_variants_are_not_collapsed_by_extraction(self):
        urls = [VALID, VALID + '/', VALID + '?x=A', VALID + '?x=a']
        self.assertEqual([{'lang': 'fr', 'href': url} for url in urls], hreflang.extract(htmlx.parse(source(*urls), BASE), BASE))

    def test_source_extraction_is_offline_and_does_not_authorize_private_fetch(self):
        url = 'http://127.0.0.1/fr/'
        with mock.patch.object(socket, 'getaddrinfo', side_effect=AssertionError('No DNS')):
            self.assertEqual([{'lang': 'fr', 'href': url}], hreflang.extract(htmlx.parse(source(url), BASE), BASE))

    def test_declared_accepted_and_reason_counts_are_explicit_not_network_results(self):
        value = receipt(VALID, '/fr/', 'javascript:alert(1)', 'http://[', '', 'https://user:password@example.test/')
        self.assertEqual(6, value['declared'])
        self.assertEqual(1, value['accepted'])
        self.assertEqual({'not_fully_qualified': 1, 'non_http': 1, 'syntax': 1, 'missing_href': 1, 'unsupported_reference': 1}, value['omitted'])
        self.assertNotIn('password', json.dumps(value))
        self.assertIn('not HTTP failures', hreflang.note({'hreflang_extraction': value}))

    def test_no_annotations_and_missing_href_have_distinct_receipts(self):
        self.assertEqual({'basis': hreflang.EXTRACTION_BASIS, 'declared': 0, 'accepted': 0, 'omitted': {}}, receipt())
        page = htmlx.Doc(BASE, link_rels=[htmlx.Tag('link', {'rel': 'alternate', 'hreflang': 'fr'})])
        value = {}; self.assertEqual([], hreflang.extract(page, BASE, diagnostics=value))
        self.assertEqual({'missing_href': 1}, value['omitted'])

    def test_receipts_validate_types_basis_and_arithmetic_without_inference(self):
        good = receipt(VALID, '/fr/')
        for field, value in (('basis', 'future'), ('declared', True), ('accepted', -1),
                             ('declared', 9), ('omitted', {'syntax': True}), ('omitted', {'future': 1})):
            broken = copy.deepcopy(good); broken[field] = value
            self.assertIsNone(hreflang.recorded({'hreflang_extraction': broken}), (field, value))
        for value in ({}, {'hreflang_extraction': None}, {'hreflang_extraction': []}):
            self.assertIsNone(hreflang.recorded(value)); self.assertFalse(hreflang.unverified(value))

    def test_rejected_urls_do_not_get_a_good_cluster_finding(self):
        report = Report(BASE)
        audit_technical._hreflang(htmlx.parse(source('/fr/'), BASE), report)
        self.assertIn('technical.hreflang.urls.review', {f.rule_id for f in report.findings})
        self.assertNotIn('technical.hreflang.cluster.present', {f.rule_id for f in report.findings})
        self.assertEqual('low', next(f.severity for f in report.findings if f.rule_id == 'technical.hreflang.urls.review'))

    def test_supported_declaration_keeps_stable_presence_rule_not_acceptance_verdict(self):
        report = Report(BASE)
        audit_technical._hreflang(htmlx.parse(source(VALID), BASE), report)
        finding = next(f for f in report.findings if f.rule_id == 'technical.hreflang.cluster.present')
        self.assertIn('not search acceptance', finding.detail)
        self.assertNotIn('technical.hreflang.urls.review', {f.rule_id for f in report.findings})

    def test_parser_backends_share_rejected_url_counts_and_order(self):
        body = source('http://[', '/fr/', VALID)
        standard, optional = {}, {}
        left = hreflang.extract(htmlx._parse_stdlib(body, BASE), BASE, diagnostics=standard)
        right = hreflang.extract(htmlx.parse(body, BASE), BASE, diagnostics=optional)
        self.assertEqual(left, right); self.assertEqual(standard, optional)

    def test_probe_zero_budget_never_fetches(self):
        with mock.patch.object(http, 'fetch', side_effect=AssertionError('No request')):
            self.assertEqual({}, hreflang.probe({BASE: alts(VALID)}, cap=0))

    def test_production_probe_rejects_partial_non_html_redirected_and_failed_snapshots(self):
        responses = [http.Response(VALID, VALID, 403, {}, '', 1),
                     http.Response(VALID, VALID, 200, {'content-type': 'text/html', 'x-narwhal-truncated': 'true'}, source(BASE), 1),
                     http.Response(VALID, VALID, 200, {'content-type': 'text/plain'}, source(BASE), 1),
                     http.Response(VALID, BASE, 200, {'content-type': 'text/html'}, source(BASE), 1),
                     http.Response(VALID, '', 200, {'content-type': 'text/html'}, source(BASE), 1),
                     http.Response(VALID, VALID, 200, {'content-type': 'text/html-unrecognized'}, source(BASE), 1),
                     http.Response(VALID, VALID, 200, {}, source(BASE), 1)]
        for response in responses:
            observations = []
            with mock.patch.object(http, 'fetch', return_value=response) as fetch:
                self.assertEqual({}, hreflang.probe({BASE: alts(VALID)}, cap=1, observations=observations))
            fetch.assert_called_once_with(VALID, allow_private=False, timeout=8)
            self.assertEqual(1, len(observations))
            self.assertIn(observations[0]['status'], ('unavailable', 'partial', 'non_html', 'identity_changed'))
            self.assertEqual('guarded_http', observations[0]['acquisition'])

    def test_production_probe_records_supported_html_and_source_gaps_within_cap(self):
        response = http.Response(VALID, VALID, 200, {'content-type': 'text/html'}, source('http://[', BASE), 1)
        coverage = {}
        with mock.patch.object(http, 'fetch', return_value=response) as fetch:
            result = hreflang.probe({BASE: alts(VALID, BASE + 'other')}, cap=1, diagnostics=coverage)
        self.assertEqual({VALID: alts(BASE)}, result)
        self.assertEqual({'syntax': 1}, coverage[VALID]['omitted'])
        self.assertEqual(1, fetch.call_count)

    def test_source_omissions_do_not_fabricate_missing_self_or_return(self):
        result = hreflang.analyze({BASE: alts(BASE, VALID), VALID: []},
                                  coverage={BASE: receipt(BASE, VALID), VALID: receipt('/en/')})
        self.assertEqual([], result['missing_return'])
        self.assertEqual([], result['missing_self'])
        self.assertEqual(1, result['unassessed_pairs'])
        self.assertEqual([VALID], result['unassessed_self'])
        self.assertEqual(1, result['source_coverage']['omitted_declarations'])
        rendered = '\n'.join(hreflang.render_markdown(result))
        self.assertIn('Unassessed due to source gaps', rendered)
        self.assertNotIn('🟢', rendered)

    def test_complete_empty_target_and_unavailable_target_remain_distinct(self):
        complete = hreflang.analyze({BASE: alts(BASE, VALID), VALID: []}, coverage={BASE: receipt(BASE, VALID), VALID: receipt()})
        self.assertEqual([{'page': BASE, 'target': VALID, 'lang': 'fr'}], complete['missing_return'])
        partial = hreflang.analyze({BASE: alts(BASE, VALID), VALID: []}, partial_sources=[VALID])
        self.assertEqual([], partial['missing_return']); self.assertEqual(1, partial['unassessed_pairs'])
        absent = hreflang.analyze({BASE: alts(BASE, VALID)})
        self.assertEqual(1, absent['unverified_targets']); self.assertEqual([], absent['missing_return'])

    def test_imported_unsupported_targets_are_bounded_uncertainty_not_crashes_or_leaks(self):
        result = hreflang.analyze({BASE: alts('http://secret:password@[broken')})
        self.assertTrue(result['used'])
        self.assertEqual(1, result['source_coverage']['unsupported_supplied_targets'])
        self.assertEqual([BASE], result['unassessed_self'])
        self.assertNotIn('password', json.dumps(result))

    def test_unsupported_source_address_is_not_silently_reported_as_no_annotations(self):
        result = hreflang.analyze({'http://secret:password@[broken': alts(VALID)})
        self.assertTrue(result['used'])
        self.assertEqual(1, result['pages_with_hreflang'])
        self.assertEqual(1, result['source_coverage']['unsupported_source_pages'])
        self.assertEqual([], result['missing_return'])
        self.assertNotIn('password', json.dumps(result))

    def test_default_probe_accepts_exact_html_mime_with_parameters_and_matching_identity(self):
        response = http.Response(VALID, VALID, 200, {'content-type': 'Text/HTML; charset=utf-8'}, source(BASE), 1)
        with mock.patch.object(http, 'fetch', return_value=response):
            self.assertEqual({VALID: alts(BASE)}, hreflang.probe({BASE: alts(VALID)}))

    def test_probe_observations_disclose_supplied_body_hook_not_http_verification(self):
        observations = []
        result = hreflang.probe({BASE: alts(VALID)}, fetch_text=lambda url: source(BASE), observations=observations)
        self.assertEqual({VALID: alts(BASE)}, result)
        self.assertEqual([{'target': VALID, 'acquisition': 'supplied_body', 'status': 'source_observed'}], observations)

    def test_probe_validation_rejection_is_unavailable_and_later_targets_continue(self):
        later = VALID + 'later/'
        response = http.Response(later, later, 200, {'content-type': 'text/html'}, source(BASE), 1)
        for error in (http.URLInputError('secret:password@bad'), http.SSRFError('secret:password@private')):
            observations = []
            with mock.patch.object(http, 'fetch', side_effect=[error, response]) as fetch:
                result = hreflang.probe({BASE: alts(VALID, later)}, cap=2, observations=observations)
            self.assertEqual({later: alts(BASE)}, result)
            self.assertEqual(2, fetch.call_count)
            self.assertEqual({'target': VALID, 'acquisition': 'guarded_http', 'status': 'unavailable'}, observations[0])
            self.assertNotIn('password', json.dumps(observations))

    def test_probe_does_not_hide_unexpected_programming_exceptions(self):
        with mock.patch.object(http, 'fetch', side_effect=RuntimeError('Unexpected bug')):
            with self.assertRaisesRegex(RuntimeError, 'Unexpected bug'):
                hreflang.probe({BASE: alts(VALID)})

    def test_probe_real_host_validation_failure_stays_unavailable_without_transport(self):
        observations = []
        with mock.patch.object(socket, 'getaddrinfo', side_effect=socket.gaierror('secret:password@dns')), \
                mock.patch.object(http, '_fetch_requests', side_effect=AssertionError('No request')), \
                mock.patch.object(http, '_fetch_urllib', side_effect=AssertionError('No request')):
            self.assertEqual({}, hreflang.probe({BASE: alts(VALID)}, observations=observations))
        self.assertEqual([{'target': VALID, 'acquisition': 'guarded_http', 'status': 'unavailable'}], observations)
        self.assertNotIn('password', json.dumps(observations))

    def test_empty_and_legacy_rendering_do_not_certify_reciprocity(self):
        result = hreflang.analyze({})
        self.assertFalse(result['used'])
        legacy = {'pages_with_hreflang': 1, 'missing_return': [], 'missing_self': [], 'invalid_codes': [],
                  'has_x_default': True, 'unverified_targets': 0}
        text = '\n'.join(hreflang.render_markdown(legacy))
        self.assertIn('coverage was not recorded', text); self.assertNotIn('🟢', text)

    def test_report_lists_keep_existing_item_caps_and_explicit_omissions_without_mutation(self):
        targets = [BASE + str(i) for i in range(8)]
        result = hreflang.analyze({BASE: alts(BASE, *targets), **{url: alts(url) for url in targets}})
        before = copy.deepcopy(result); text = '\n'.join(hreflang.render_markdown(result))
        self.assertIn('… +2 more (see JSON)', text)
        self.assertEqual(before, result)
        self.assertEqual(8, len(result['missing_return']))

    def test_page_site_notes_and_diff_gates_retain_known_uncertainty(self):
        report = page_report('/fr/')
        self.assertIn(hreflang.ERROR, report.to_markdown())
        self.assertIn('HTML hreflang source coverage', report.to_html())
        current = json.loads(report.to_json()); legacy = copy.deepcopy(current)
        legacy['meta'].pop('hreflang_policy_basis'); legacy['meta'].pop('hreflang_extraction')
        for left, right in ((legacy, current), (current, current)):
            self.assertEqual('incomparable', diff_scan.diff_reports(left, right)['comparison']['status'])

    def test_policy_mismatch_isolated_from_extraction_failure(self):
        for groups in (['technical'], ['content']):
            page = json.loads(page_report(VALID, only=groups).to_json())
            self.assertFalse(hreflang.unverified(page['meta'], for_score=True))
            for location in ('page', 'crawl'):
                current = copy.deepcopy(page)
                if location == 'crawl':
                    current = {'site': BASE, 'overall_score': page['score'], 'homepage': current,
                               'crawl': {'pages': [], 'hreflang_policy_basis': hreflang.EXTRACTION_BASIS}}
                self.assertEqual('comparable', diff_scan.diff_reports(current, current)['comparison']['status'])
                for basis in (None, 'future'):
                    other = copy.deepcopy(current)
                    meta = other['meta'] if location == 'page' else other['crawl']
                    if basis is None:
                        meta.pop('hreflang_policy_basis')
                    else:
                        meta['hreflang_policy_basis'] = basis
                    self.assertEqual('comparable', diff_scan.diff_reports(other, other)['comparison']['status'])
                    for old, new in ((other, current), (current, other)):
                        with self.subTest(groups=groups, location=location, basis=basis, reverse=old is current):
                            original = copy.deepcopy((old, new))
                            result = diff_scan.diff_reports(old, new)
                            expected = 'incomparable' if groups == ['technical'] else 'comparable'
                            self.assertEqual(expected, result['comparison']['status'])
                            if expected == 'incomparable':
                                self.assertIsNone(result['score_delta'])
                                self.assertIsNone(result['regression'])
                                self.assertEqual([], result['resolved'])
                            self.assertEqual(original, (old, new))

    def test_supported_current_pairs_compare_without_a_false_gap(self):
        payload = json.loads(page_report(VALID).to_json())
        self.assertEqual('comparable', diff_scan.diff_reports(payload, copy.deepcopy(payload))['comparison']['status'])

    def test_content_only_scores_are_not_invalidated_by_unselected_technical_checks(self):
        report = page_report('/fr/', only=['content'])
        self.assertTrue(hreflang.unverified(report.meta))
        self.assertFalse(hreflang.unverified(report.meta, for_score=True))
        self.assertNotIn(hreflang.ERROR, report.to_markdown())
        current = json.loads(report.to_json()); legacy = copy.deepcopy(current)
        legacy['meta'].pop('hreflang_policy_basis'); legacy['meta'].pop('hreflang_extraction')
        self.assertEqual('comparable', diff_scan.diff_reports(legacy, current)['comparison']['status'])

    def test_real_compare_and_brief_withhold_unsupported_hreflang_scores(self):
        def response(url, **kwargs):
            return http.Response(url, url, 200, {'content-type': 'text/html'}, source('/fr/') if url == BASE else source(), 1)
        with mock.patch.object(scan, 'gather_context', return_value={}), mock.patch.object(http, 'fetch', side_effect=response):
            result = compare.run([BASE, 'https://other.test/'])
            self.assertTrue(result['failed'][0]['hreflang_comparison_unverified'])
            with self.assertRaisesRegex(RuntimeError, 'HTML hreflang URL'):
                brief._page(BASE)

    def test_crawl_all_rejected_annotations_stay_visible_and_not_clean_or_failed(self):
        response = http.Response(BASE, BASE, 200, {'content-type': 'text/html'}, source('/fr/'), 1)
        with mock.patch.object(scan, 'gather_context', return_value={}), \
                mock.patch.object(http, 'fetch_text', return_value=''), mock.patch.object(http, 'fetch', return_value=response):
            result = crawl_site.crawl(BASE, max_pages=1, concurrency=1, detect_dupes=False)
        self.assertTrue(result['hreflang']['used'])
        self.assertEqual(1, result['hreflang']['pages_with_hreflang'])
        self.assertEqual([], result['hreflang']['missing_self'])
        self.assertTrue(result['pages'][0]['hreflang_comparison_unverified'])
        text = crawl_site.render_markdown(result)
        self.assertIn('source URL coverage has omissions on 1', text)
        self.assertNotIn('🟢', text)

    def test_planner_keeps_intended_alternate_urls_manual_without_source_owners(self):
        report = Report(BASE)
        audit_technical._hreflang(htmlx.parse(source('/fr/'), BASE), report)
        report.findings = [finding for finding in report.findings if finding.rule_id == 'technical.hreflang.urls.review']
        with tempfile.TemporaryDirectory() as root:
            result = plan.build_plan(json.loads(report.to_json()), root)
        action = result['actions'][0]
        self.assertEqual('manual_external', action['safety'])
        self.assertEqual([], action['likely_files'])
        self.assertEqual('hreflang', action['artifact'])

    def test_crawled_empty_target_is_not_refetched_to_consume_probe_budget(self):
        def response(url, **kwargs):
            return http.Response(url, url, 200, {'content-type': 'text/html'}, source(BASE, VALID) if url == BASE else source(), 1)
        with mock.patch.object(scan, 'gather_context', return_value={}), \
                mock.patch.object(crawl_site, 'discover', return_value=[BASE, VALID]), \
                mock.patch.object(http, 'fetch', side_effect=response) as fetch:
            result = crawl_site.crawl(BASE, max_pages=2, concurrency=1, detect_dupes=False)
        self.assertEqual([BASE, VALID], [call.args[0] for call in fetch.call_args_list])
        self.assertEqual(0, result['hreflang']['probed'])
        self.assertEqual(1, len(result['hreflang']['missing_return']))

    def test_content_only_audit_does_not_gain_a_false_hreflang_score_gap(self):
        report = json.loads(page_report('/fr/', only=['content']).to_json())
        value = {'site': BASE, 'overall_score': report['score'], 'homepage': report, 'crawl': {
            'hreflang_policy_basis': hreflang.EXTRACTION_BASIS,
            'pages': [{'url': BASE, 'hreflang_comparison_unverified': False, 'hreflang_extraction': receipt('/fr/')}]}}
        self.assertEqual('comparable', diff_scan.diff_reports(value, copy.deepcopy(value))['comparison']['status'])


if __name__ == '__main__': unittest.main()
