"""Crawl/audit handoffs retain and compare explicit per-page auditor execution."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import crawl_site
import diff_scan
import mcp_server
import plan
import scan
from lib import canonical, htmlx, http, hreflang, llms_resource, sitemap_discovery
from lib.report import Report, CATEGORY_LABELS
from test_crawl_rule_handoff import crawl_reports
from test_diff_crawl_rules import report
from test_diff_severe_escalation import cli

SCOPE = {'requested': ['technical', 'schema'], 'completed': ['technical', 'schema']}


class TestCrawlExecutionScope(unittest.TestCase):
    def test_crawl_serializes_recorded_scope_without_inference_or_report_mutation(self):
        pages = [Report('https://example.test/' + str(i), fetched_status=200) for i in range(3)]
        pages[0].meta['scan_scope'] = copy.deepcopy(SCOPE)
        pages[1].meta['scan_scope'] = dict(SCOPE, completed=[])
        original = copy.deepcopy([p.meta for p in pages])
        with mock.patch.object(crawl_site.time, 'sleep', side_effect=AssertionError('Default zero-delay crawl must not sleep')) as sleep:
            result = json.loads(crawl_site.render_json(crawl_reports(pages)))
        sleep.assert_not_called()
        self.assertEqual(SCOPE, result['pages'][0]['scan_scope'])
        self.assertEqual([], result['pages'][1]['scan_scope']['completed'])
        self.assertNotIn('scan_scope', result['pages'][2])
        self.assertEqual(original, [p.meta for p in pages])

    def test_crawl_handoff_preserves_coverage_flags_and_merchant_classification(self):
        base = 'https://example.test/'
        scope = {'requested': list(CATEGORY_LABELS), 'completed': list(CATEGORY_LABELS)}
        doc = htmlx.parse('<link rel="canonical" href="https://[">'
                         '<link rel="alternate" hreflang="fr" href="/fr/">', base)
        alternate_receipt = {}
        hreflang.extract(doc, base, diagnostics=alternate_receipt)
        meta = {'scan_scope': scope, 'scan_settings': {'schema_extraction_reviewed': False},
                'coverage': {'js_comparison': {'status': 'unverified', 'reason': 'served_html_unavailable'}},
                'sitemap_discovery': sitemap_discovery.Discovery('context_candidates').receipt(),
                'llms_txt': llms_resource.assess(http.Response(base + 'llms.txt', base + 'llms.txt',
                    403, {'content-type': 'text/plain'}, '', 0)),
                'canonical_comparison': canonical.observe(doc, base),
                'hreflang_extraction': alternate_receipt,
                'ecommerce': {'is_product': True, 'is_merchant': True, 'confidence': 0.9}}
        uncertain = Report(base + 'merchant', fetched_status=200, meta=meta)
        plain = Report(base + 'plain', fetched_status=200, meta={'scan_scope': copy.deepcopy(scope),
                       'scan_settings': {'schema_extraction_reviewed': True}})
        focused = Report(base + 'editorial', fetched_status=200, meta=copy.deepcopy(meta))
        focused.meta['scan_scope'] = {'requested': ['content'], 'completed': ['content']}
        focused.meta.pop('canonical_comparison')  # Technical canonical checks are absent in this report.
        focused.meta['ecommerce'] = {'is_product': True, 'is_merchant': False, 'confidence': 0.6}
        pages = [uncertain, plain, focused]
        original = copy.deepcopy([page.meta for page in pages])
        result = json.loads(crawl_site.render_json(crawl_reports(pages)))
        for flag in ('js_comparison_unverified', 'sitemap_discovery_unverified', 'llms_txt_unverified',
                     'schema_extraction_unverified', 'canonical_comparison_unverified',
                     'hreflang_comparison_unverified'):
            with self.subTest(flag=flag):
                self.assertEqual([True, False, False], [page.get(flag) for page in result['pages']])
        self.assertEqual([True, False, True], [page['is_product'] for page in result['pages']])
        self.assertEqual([True, False, False], [page['is_merchant'] for page in result['pages']])
        self.assertEqual([0.9, 0.0, 0.6], [page['product_confidence'] for page in result['pages']])
        self.assertEqual([uncertain.url], result['ecommerce']['merchant_pages'])
        self.assertEqual([uncertain.url, focused.url], result['ecommerce']['product_pages'])
        self.assertEqual(100, result['avg_score'])
        self.assertEqual(original, [page.meta for page in pages])

    def test_crawl_retains_native_indexing_receipts_only_for_successful_pages(self):
        base = 'https://example.test/'
        root = llms_resource.assess(http.Response(base + 'llms.txt', base + 'llms.txt',
                                   403, {'content-type': 'text/plain'}, '', 0))
        native = []
        for url, directive in ((base, 'noindex'), (base + 'other', 'nofollow')):
            body = ('<html><head><meta name="googlebot" content="' + directive + '">'
                    '</head><body>Guide</body></html>')
            response = http.Response(url, url, 200, {'content-type': 'text/html',
                                     'x-robots-tag': 'googlebot: ' + directive}, body, 1)
            with mock.patch.object(http, 'fetch', return_value=response), \
                    mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
                native.append(scan.scan(url, ctx={'llms_txt_receipt': root}, check_images=False))
        keys = ('crawler_meta_robots', 'http_robots', 'llms_txt')
        expected = [{key: copy.deepcopy(page.meta[key]) for key in keys} for page in native]
        failed = Report(base + 'failed', fetched_status=503, hard_fail=True,
                        meta=copy.deepcopy(native[0].meta))
        legacy = Report(base + 'legacy', fetched_status=200)
        pages = native + [failed, legacy]
        before = copy.deepcopy([page.meta for page in pages])
        result = json.loads(crawl_site.render_json(crawl_reports(pages)))
        self.assertEqual(expected, [{key: page[key] for key in keys} for page in result['pages'][:2]])
        for page in result['pages'][2:]:
            for key in keys:
                self.assertNotIn(key, page)
        self.assertEqual([False, False, True, False], [page['hard_fail'] for page in result['pages']])
        self.assertEqual(before, [page.meta for page in pages])

    def test_crawl_json_retains_page_counts_scores_and_fractional_average(self):
        pages = [Report('https://example.test/' + str(i), fetched_status=200) for i in range(3)]
        severities = ('critical', 'high', 'medium', 'low', 'good')
        for page, findings in zip(pages, (severities, ('low',), ('good',))):
            for severity in findings:
                page.add('technical', severity, 'Controlled ' + severity,
                         rule_id='technical.controlled.' + severity)
        before = [json.loads(page.to_json()) for page in pages]
        result = json.loads(crawl_site.render_json(crawl_reports(pages)))
        self.assertEqual([page.url for page in pages], [page['url'] for page in result['pages']])
        self.assertEqual([78, 99, 100], [page['score'] for page in result['pages']])
        self.assertEqual([dict.fromkeys(severities, 1),
                          {'critical': 0, 'high': 0, 'medium': 0, 'low': 1, 'good': 0},
                          {'critical': 0, 'high': 0, 'medium': 0, 'low': 0, 'good': 1}],
                         [page['counts'] for page in result['pages']])
        self.assertEqual(92.3, result['avg_score'])
        self.assertEqual(before, [json.loads(page.to_json()) for page in pages])

    def test_crawl_preserves_primary_status_and_actual_rendering(self):
        pages = [Report('https://example.test/' + str(i), fetched_status=status, rendered=rendered,
                        hard_fail=failed) for i, (status, rendered, failed) in enumerate(
                        ((200, False, False), (201, True, False), (503, False, True), (0, False, True)))]
        for page in pages:
            page.meta['scan_scope'] = copy.deepcopy(SCOPE)
            page.meta['scan_settings'] = {'render_requested': True, 'rendered': page.rendered}
        original = copy.deepcopy([json.loads(page.to_json()) for page in pages])
        result = json.loads(crawl_site.render_json(crawl_reports(pages)))
        self.assertEqual([200, 201, 503, 0], [page.get('status') for page in result['pages']])
        self.assertEqual([False, True, False, False], [page.get('rendered') for page in result['pages']])
        self.assertEqual([False, False, True, True], [page['hard_fail'] for page in result['pages']])
        self.assertEqual(original, [json.loads(page.to_json()) for page in pages])

    def test_crawl_handoff_preserves_rendering_conflict_for_diff_and_planner(self):
        homepage = Report('https://example.test/', fetched_status=200)
        inner = Report('https://example.test/pricing/', fetched_status=200, rendered=True)
        for page in (homepage, inner):
            page.meta['scan_scope'] = copy.deepcopy(SCOPE)
            page.meta['scan_settings'] = {'render_requested': True, 'rendered': False}
        inner.add('technical', 'high', 'No responsive viewport tag',
                  rule_id='technical.no.responsive.viewport.tag')
        data = {'site': homepage.url, 'overall_score': 90, 'homepage': json.loads(homepage.to_json()),
                'crawl': json.loads(crawl_site.render_json(crawl_reports([homepage, inner])))}
        result = diff_scan.diff_reports(data, data)
        self.assertEqual('incomparable', result['comparison']['status'])
        self.assertIsNone(result['score_delta'])
        self.assertEqual(2, cli(data, data, '--fail-on-regression')[0])
        self.assertEqual(result, mcp_server._diff(json.dumps(data), json.dumps(data)))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'pricing').mkdir()
            (root / 'pricing/index.html').write_text('<html></html>', encoding='utf-8')
            action = plan.build_plan(data, tmp)['actions'][0]
            self.assertFalse(action['automation_eligibility']['eligible'])
            self.assertIn('known_incomplete_source_evidence', action['automation_eligibility']['blockers'])
            inner.rendered = False
            data['crawl'] = json.loads(crawl_site.render_json(crawl_reports([homepage, inner])))
            self.assertEqual('comparable', diff_scan.diff_reports(data, data)['comparison']['status'])
            clean_action = plan.build_plan(data, tmp)['actions'][0]
            self.assertTrue(clean_action['automation_eligibility']['eligible'], clean_action)

    def test_partial_invalid_changed_and_one_sided_inner_scope_withhold_verdicts(self):
        for change in ('partial', 'invalid', 'matching_partial', 'matching_invalid',
                       'changed', 'missing', 'contradictory_duplicate'):
            old, new = report([]), report([])
            for data in (old, new):
                data['crawl']['pages'][1]['scan_scope'] = copy.deepcopy(SCOPE)
            if change in ('partial', 'matching_partial'):
                new['crawl']['pages'][1]['scan_scope']['completed'] = []
            elif change in ('invalid', 'matching_invalid'):
                new['crawl']['pages'][1]['scan_scope'] = {'requested': 'technical', 'completed': []}
            elif change == 'changed':
                new['crawl']['pages'][1]['scan_scope'] = {'requested': ['technical'], 'completed': ['technical']}
            elif change == 'missing':
                old['crawl']['pages'][1].pop('scan_scope')
            else:
                for data in (old, new):
                    data['crawl']['pages'].append(copy.deepcopy(data['crawl']['pages'][1]))
                new['crawl']['pages'][2]['scan_scope'] = {'requested': ['technical'], 'completed': ['technical']}
            if change.startswith('matching_'):
                old = copy.deepcopy(new)
            for before, after in ((old, new), (new, old)):
                with self.subTest(change=change):
                    original = copy.deepcopy((before, after))
                    result = diff_scan.diff_reports(before, after)
                    self.assertEqual('incomparable', result['comparison']['status'])
                    self.assertIsNone(result['score_delta'])
                    self.assertIsNone(result['regression'])
                    self.assertEqual('unverified', result['crawl_rule_changes']['status'])
                    self.assertEqual(2, cli(before, after, '--fail-on-regression', '--require-comparable')[0])
                    self.assertEqual(result, mcp_server._diff(json.dumps(before), json.dumps(after)))
                    self.assertEqual(original, (before, after))

    def test_matching_reordered_scopes_and_absent_legacy_scopes_are_distinct(self):
        old, new = report([]), report([])
        for data in (old, new):
            data['crawl']['pages'][1]['scan_scope'] = copy.deepcopy(SCOPE)
        new['crawl']['pages'][1]['scan_scope']['completed'].reverse()
        new['crawl']['pages'][1]['scan_scope']['requested'].reverse()
        self.assertEqual('comparable', diff_scan.diff_reports(old, new)['comparison']['status'])
        legacy = diff_scan.diff_reports(report([]), report([]))
        self.assertEqual('comparable', legacy['comparison']['status'])
        self.assertIn('missing legacy page scopes remain unverified', legacy['comparison']['basis'])

    def test_recorded_unfinished_technical_check_blocks_existing_planner_automation(self):
        data = report([{'category': 'technical', 'severity': 'high',
                       'rule_id': 'technical.no.responsive.viewport.tag', 'title': 'No responsive viewport tag',
                       'count': 1, 'url_sample': {'basis': 'recorded_crawl_rule_url_labels_v1',
                       'urls': ['https://example.test/pricing/'], 'truncated': False, 'omitted': 0}}])
        data['crawl']['pages'][1]['scan_scope'] = dict(SCOPE, completed=[])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'pricing').mkdir()
            (root / 'pricing/index.html').write_text('<html></html>', encoding='utf-8')
            action = plan.build_plan(data, tmp)['actions'][0]
        self.assertEqual(['pricing/index.html'], [owner['path'] for owner in action['likely_files']])
        self.assertFalse(action['automation_eligibility']['eligible'])
        self.assertIn('known_incomplete_source_evidence', action['automation_eligibility']['blockers'])


if __name__ == '__main__':
    unittest.main()
