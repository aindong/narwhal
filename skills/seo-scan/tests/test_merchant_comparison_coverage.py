"""Skipping an ambiguous Product/Offer comparison cannot prove a repair."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit
import crawl_site
import diff_scan
import mcp_server
import plan
import scan
from lib import http
from lib.report import recorded_merchant_comparison_problem
from test_offer_comparisons import URL, offers, page
from test_merchant_identity import page as variant_page

REPO = Path(__file__).parent / 'fixtures/planner/plain_html'
PRODUCT = 'schema.ecommerce.comparison.ambiguous'
OFFER = 'schema.ecommerce.offer.comparison.ambiguous'
VERIFY = 'schema.ecommerce.comparison.unverified'
MISMATCH = 'schema.ecommerce.price.mismatch'


def observed(source):
    response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, source, 1)
    with mock.patch.object(http, 'fetch', return_value=response):
        return scan.scan(URL, only=['schema'], ctx={}, check_images=False)


def payload(report):
    return json.loads(report.to_json())


class TestMerchantComparisonCoverage(unittest.TestCase):
    def test_ambiguous_offers_cannot_resolve_a_price_mismatch_or_claim_a_score_gain(self):
        old = payload(observed(page(offers()[:1], price='149.00')))
        new = payload(observed(page(offers(), price='149.00')))
        original = copy.deepcopy((old, new))
        self.assertIn(MISMATCH, {f['rule_id'] for f in old['findings']})
        self.assertNotIn(MISMATCH, {f['rule_id'] for f in new['findings']})
        self.assertEqual('skipped_ambiguous', new['meta']['ecommerce']['offer_comparison_status']['price'])
        result = diff_scan.diff_reports(old, new)
        self.assertEqual('incomparable', result['comparison']['status'])
        self.assertIsNone(result['score_delta'])
        self.assertEqual([], result['resolved'])
        self.assertTrue(any('Product/Offer' in reason for reason in result['comparison']['reasons']))
        self.assertEqual(original, (old, new))

    def test_native_ambiguity_actions_verify_identity_instead_of_generating_schema(self):
        for source, rule in ((page(offers()), OFFER), (variant_page(), PRODUCT)):
            with self.subTest(rule=rule):
                data = payload(observed(source))
                before = copy.deepcopy(data)
                with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
                    built = plan.build_plan(data, str(REPO), report_source='<mcp-object>')
                    with mock.patch.object(Path, 'cwd', return_value=REPO.resolve().parent):
                        self.assertEqual(built, mcp_server._plan(data, REPO.name))
                action = next(a for a in built['actions'] if a['rule_id'] == rule)
                self.assertNotIn(VERIFY, [a['rule_id'] for a in built['actions']])
                self.assertEqual('manual_external', action['safety'])
                self.assertTrue(action['manual_action'])
                self.assertFalse(action['requires_deploy'])
                self.assertEqual([], action['likely_files'])
                self.assertFalse(any(rule in group['rule_ids'] for group in built['groups']))
                self.assertEqual(before, data)

    def test_ignored_notes_do_not_hide_metadata_or_qualify_scores_as_verified(self):
        for source in (page(offers()), variant_page()):
            report = observed(source)
            report.findings = []
            data = payload(report)
            self.assertIn('Product/Offer', report.to_markdown())
            self.assertIn('Product/Offer', report.to_html())
            built = plan.build_plan(data, str(REPO))
            self.assertIn(VERIFY, [a['rule_id'] for a in built['actions']])
            action = next(a for a in built['actions'] if a['rule_id'] == VERIFY)
            self.assertEqual(('schema', 'low'), (action['category'], action['severity']))
            self.assertEqual('manual_external', action['safety'])
            self.assertEqual([], action['likely_files'])
            self.assertFalse(action['requires_deploy'])
            result = diff_scan.diff_reports(data, data)
            self.assertEqual('incomparable', result['comparison']['status'])
            self.assertIsNone(result['score_delta'])

    def test_crawl_retains_leaf_uncertainty_and_qualifies_audit_comparisons(self):
        report = observed(page(offers()))
        report.findings = []
        with mock.patch.object(crawl_site.scanner, 'gather_context', return_value={}), \
                mock.patch.object(crawl_site, 'discover', return_value=[URL + '/leaf']), \
                mock.patch.object(crawl_site.scanner, 'scan', return_value=report):
            result = crawl_site.crawl(URL, max_pages=1)
        self.assertIs(True, result['pages'][0].get('merchant_comparison_unverified'))
        rendered = crawl_site.render_markdown(result)
        self.assertIn('Product/Offer', rendered)
        self.assertIn('# Site SEO & GEO Scan', rendered)
        self.assertIn('**Average score:** ' + str(result['avg_score']) + '/100', rendered)
        home = observed(page(offers()[:1], price='129.00'))
        audit_data = {'site': URL, 'page': home, 'site_result': result,
                      'sitemap': {'start': URL, 'seeds': []}}
        self.assertIn('Product/Offer', audit.render_markdown(audit_data))
        self.assertIn('Product/Offer', audit.render_html(audit_data))
        data = {'site': URL, 'overall_score': 100, 'homepage': payload(home),
                'crawl': json.loads(crawl_site.render_json(result)), 'sitemap': {}}
        compared = diff_scan.diff_reports(data, data)
        self.assertEqual('incomparable', compared['comparison']['status'])
        self.assertIsNone(compared['score_delta'])
        built = plan.build_plan(data, str(REPO))
        action = next(a for a in built['actions'] if a['rule_id'] == VERIFY)
        self.assertEqual(('site', 'manual_external', []), (action['scope'], action['safety'], action['likely_files']))

    def test_explicit_legacy_warning_without_metadata_still_withholds_fix_claims(self):
        data = payload(observed(page(offers())))
        data['meta'].pop('ecommerce')
        result = diff_scan.diff_reports(data, data)
        self.assertEqual('incomparable', result['comparison']['status'])
        self.assertIsNone(result['score_delta'])

    def test_actual_price_correction_and_ready_consensus_remain_comparable(self):
        old = payload(observed(page(offers()[:1], price='149.00')))
        values = offers()
        for offer in values:
            offer['price'] = '149.00'
        new = payload(observed(page(values, price='149.00')))
        result = diff_scan.diff_reports(old, new)
        self.assertEqual('comparable', result['comparison']['status'])
        self.assertGreater(result['score_delta'], 0)
        self.assertIn(MISMATCH, {f['rule_id'] for f in result['resolved']})

    def test_only_known_skips_in_selected_schema_scope_qualify_scores(self):
        for meta in (None, {}, {'ecommerce': None}, {'ecommerce': 'future'},
                     {'merchant_comparison_unverified': 1},
                     {'ecommerce': {'comparison_status': 'ready', 'offer_comparison_status': None}},
                     {'ecommerce': {'offer_comparison_status': {'price': 'future', 'seller': 'skipped_ambiguous'}}}):
            with self.subTest(meta=meta):
                self.assertIsNone(recorded_merchant_comparison_problem(meta, for_score=True))
        for meta in ({'merchant_comparison_unverified': True},
                     {'ecommerce': {'comparison_status': 'skipped_ambiguous'}},
                     *({'ecommerce': {'offer_comparison_status': {key: 'skipped_ambiguous'}}}
                       for key in ('price', 'currency', 'availability'))):
            self.assertIn('Product/Offer', recorded_merchant_comparison_problem(meta, for_score=True))
            meta['scan_scope'] = {'requested': ['content'], 'completed': ['content']}
            self.assertIsNone(recorded_merchant_comparison_problem(meta, for_score=True))
            self.assertIn('Product/Offer', recorded_merchant_comparison_problem(meta))
            meta['scan_scope'] = {'requested': ['content', 'schema'], 'completed': ['content']}
            self.assertIn('Product/Offer', recorded_merchant_comparison_problem(meta, for_score=True))
        report = observed(page(offers()))
        report.meta['scan_scope'] = {'requested': ['content'], 'completed': ['content']}
        data = payload(report)
        self.assertNotIn('Product/Offer', report.to_markdown())
        self.assertEqual('comparable', diff_scan.diff_reports(data, data)['comparison']['status'])

    def test_independent_validity_defects_remain_reviewable(self):
        values = offers()
        values[0]['priceValidUntil'] = '2001-01-01'
        data = payload(observed(page(values)))
        built = plan.build_plan(data, str(REPO))
        independent = next(a for a in built['actions'] if a['rule_id'] == 'schema.ecommerce.offer.price.expired')
        self.assertEqual('review_required', independent['safety'])
        self.assertTrue(independent['likely_files'])
        self.assertFalse(independent['manual_action'])
        data['findings'] = [f for f in data['findings'] if f['rule_id'] != OFFER]
        self.assertIn(VERIFY, [a['rule_id'] for a in plan.build_plan(data, str(REPO))['actions']])
        healthy = payload(observed(page(offers()[:1], price='129.00')))
        saved_audit = {'site': URL, 'overall_score': healthy['score'], 'homepage': healthy,
                       'crawl': {'pages': [{'url': URL, 'merchant_comparison_unverified': True}],
                                 'recurring': [f for f in data['findings'] if f['severity'] != 'good']}, 'sitemap': {}}
        self.assertIn(VERIFY, [a['rule_id'] for a in plan.build_plan(saved_audit, str(REPO))['actions']])

    def test_homepage_warning_does_not_conceal_ignored_crawl_uncertainty(self):
        home = payload(observed(page(offers())))
        data = {'site': URL, 'overall_score': home['score'], 'homepage': home,
                'crawl': {'pages_scanned': 1, 'pages': [{'url': URL + '/leaf',
                          'merchant_comparison_unverified': True}], 'recurring': []}, 'sitemap': {}}
        built = plan.build_plan(data, str(REPO))
        fallback = next(a for a in built['actions'] if a['rule_id'] == VERIFY)
        self.assertEqual('site', fallback['scope'])
        self.assertIn('crawl sample/rollup', fallback['evidence'])
        self.assertNotIn('page report and crawl', fallback['evidence'])

    def test_legacy_crawl_warning_without_new_flag_blocks_fix_claims(self):
        home = payload(observed(page(offers()[:1], price='129.00')))
        warning = next(f for f in payload(observed(page(offers())))['findings'] if f['rule_id'] == OFFER)
        data = {'site': URL, 'overall_score': home['score'], 'homepage': home,
                'crawl': {'pages_scanned': 1, 'pages': [{'url': URL}], 'recurring': [warning]}, 'sitemap': {}}
        compared = diff_scan.diff_reports(data, data)['comparison']
        self.assertEqual('incomparable', compared['status'])
        self.assertTrue(all(isinstance(reason, str) and reason for reason in compared['reasons']))
        warning['severity'] = 'good'
        self.assertEqual('comparable', diff_scan.diff_reports(data, data)['comparison']['status'])

    def test_aggregate_score_note_counts_only_relevant_pages_and_handles_homepage_only(self):
        home = observed(page(offers()))
        data = {'page': home, 'site_result': {}}
        self.assertIn('Product/Offer', audit._schema_score_note(data))
        home.meta['scan_scope'] = {'requested': ['content'], 'completed': ['content']}
        self.assertNotIn('Product/Offer', audit._schema_score_note(data))
        excluded = {'merchant_comparison_unverified': True, 'scan_scope': home.meta['scan_scope']}
        site = {'pages': [{'merchant_comparison_unverified': True}, excluded,
                          {'merchant_comparison_unverified': False}, None,
                          {'merchant_comparison_unverified': True}]}
        self.assertIn('2 scanned page(s)', crawl_site.merchant_comparison_note(site))
        data['site_result'] = {'pages': [row for row in site['pages'] if row is not None]}
        self.assertIn('2 scanned page(s)', audit._schema_score_note(data))
        self.assertEqual('', crawl_site.merchant_comparison_note({}))
        self.assertEqual('', crawl_site.merchant_comparison_note({'pages': [excluded, {}, None]}))

    def test_unselected_crawl_scope_does_not_gain_merchant_uncertainty(self):
        report = observed(page(offers()))
        report.meta['scan_scope'] = {'requested': ['content'], 'completed': ['content']}
        report.findings = []
        with mock.patch.object(crawl_site.scanner, 'gather_context', return_value={}), \
                mock.patch.object(crawl_site, 'discover', return_value=[URL]), \
                mock.patch.object(crawl_site.scanner, 'scan', return_value=report):
            result = crawl_site.crawl(URL, max_pages=1)
        self.assertIs(False, result['pages'][0]['merchant_comparison_unverified'])
        self.assertNotIn('Product/Offer', crawl_site.render_markdown(result))
        row = result['pages'][0]
        row['merchant_comparison_unverified'] = True
        data = {'site': URL, 'overall_score': 100, 'homepage': payload(report),
                'crawl': json.loads(crawl_site.render_json(result)), 'sitemap': {}}
        self.assertEqual('comparable', diff_scan.diff_reports(data, data)['comparison']['status'])
        self.assertNotIn(VERIFY, [a['rule_id'] for a in plan.build_plan(data, str(REPO))['actions']])

    def test_positive_legacy_page_observation_does_not_block_comparison(self):
        data = payload(observed(page(offers())))
        data['meta'].pop('ecommerce')
        for finding in data['findings']:
            if finding['rule_id'] == OFFER:
                finding['severity'] = 'good'
        self.assertEqual('comparable', diff_scan.diff_reports(data, data)['comparison']['status'])

    def test_fallback_scope_distinguishes_page_only_and_joint_uncertainty(self):
        home = observed(page(offers()))
        home.findings = []
        for rows, scope, included in (([], 'page', 'page report'),
                ([{'url': URL, 'merchant_comparison_unverified': True}], 'site',
                 'page report and crawl sample/rollup')):
            data = {'site': URL, 'overall_score': 100, 'homepage': payload(home),
                    'crawl': {'pages': rows, 'recurring': []}, 'sitemap': {}}
            action = next(a for a in plan.build_plan(data, str(REPO))['actions'] if a['rule_id'] == VERIFY)
            self.assertEqual(scope, action['scope'])
            self.assertIn(included, action['evidence'])
            if scope == 'page':
                self.assertNotIn('crawl sample/rollup', action['evidence'])

    def test_crawl_warning_covers_its_own_uncertainty_but_positive_observation_does_not(self):
        home = payload(observed(page(offers()[:1], price='129.00')))
        warning = next(f for f in payload(observed(page(offers())))['findings'] if f['rule_id'] == OFFER)
        data = {'site': URL, 'overall_score': home['score'], 'homepage': home,
                'crawl': {'pages': [{'url': URL, 'merchant_comparison_unverified': True}],
                          'recurring': [warning]}, 'sitemap': {}}
        built = plan.build_plan(data, str(REPO))
        self.assertNotIn(VERIFY, [a['rule_id'] for a in built['actions']])
        action = next(a for a in built['actions'] if a['rule_id'] == OFFER)
        self.assertEqual(('site', 'manual_external', []), (action['scope'], action['safety'], action['likely_files']))
        warning['severity'] = 'good'
        built = plan.build_plan(data, str(REPO))
        self.assertIn(VERIFY, [a['rule_id'] for a in built['actions']])
        self.assertNotIn(OFFER, [a['rule_id'] for a in built['actions']])
        data['crawl'].pop('recurring')
        self.assertIn(VERIFY, [a['rule_id'] for a in plan.build_plan(data, str(REPO))['actions']])

    def test_malformed_crawl_recurring_preserves_unverified_aggregate_contract(self):
        home = payload(observed(page(offers()[:1], price='129.00')))
        for recurring in (None, 7, 'future', {}, [None]):
            with self.subTest(recurring=recurring):
                data = {'site': URL, 'overall_score': home['score'], 'homepage': home,
                        'crawl': {'pages_scanned': 1, 'pages': [{'url': URL}], 'recurring': recurring}, 'sitemap': {}}
                before = copy.deepcopy(data)
                result = diff_scan.diff_reports(data, data)
                aggregate = result['crawl_rule_changes']
                self.assertEqual('unverified', aggregate['status'])
                self.assertIsNone(aggregate['regression'])
                self.assertTrue(aggregate['reason'])
                self.assertEqual([], aggregate['removed'])
                self.assertEqual(result, mcp_server._diff(json.dumps(data), json.dumps(data)))
                self.assertEqual(before, data)


if __name__ == '__main__':
    unittest.main()
