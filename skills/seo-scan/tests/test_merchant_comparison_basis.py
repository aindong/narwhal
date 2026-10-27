"""Changing observed fields or exact-vs-range checks is not repair evidence."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import crawl_site
import diff_scan
import mcp_server
from lib.report import recorded_merchant_comparison_basis
from test_diff_scope import invoke
from test_diff_crawl_sample import audit as saved_audit
from test_merchant_comparison_coverage import observed, payload, page, offers, URL, MISMATCH


def range_page(high='159'):
    offer = dict(offers()[0], **{'@type': 'AggregateOffer', 'lowPrice': '129',
                               'highPrice': high, 'offerCount': 2})
    return page([offer], price='149.00')


class TestMerchantComparisonBasis(unittest.TestCase):
    def assert_withheld(self, old, new):
        original = copy.deepcopy((old, new))
        result = diff_scan.diff_reports(old, new)
        self.assertEqual('incomparable', result['comparison']['status'])
        self.assertIsNone(result['score_delta'])
        self.assertIsNone(result['regression'])
        self.assertEqual([], result['resolved'])
        self.assertTrue(any('merchant' in reason.lower() for reason in result['comparison']['reasons']))
        self.assertEqual(result, mcp_server._diff(json.dumps(old), json.dumps(new)))
        self.assertEqual(2, invoke(old, new, '--require-comparable', '--fail-on-regression')[0])
        self.assertEqual(original, (old, new))

    def test_removing_observed_price_cannot_resolve_a_mismatch(self):
        source = page(offers()[:1], price='149.00')
        old = payload(observed(source))
        new = payload(observed(source.replace('<meta property="product:price:amount" content="149.00">', '')))
        self.assertIn(MISMATCH, {f['rule_id'] for f in old['findings']})
        self.assertNotIn(MISMATCH, {f['rule_id'] for f in new['findings']})
        self.assertGreater(new['score'], old['score'])
        self.assertNotIn('price', new['meta']['ecommerce']['visible_facts'])
        for before, after in ((old, new), (new, old)):
            self.assert_withheld(before, after)

    def test_range_compatibility_cannot_become_an_exact_price_repair(self):
        old = payload(observed(page(offers()[:1], price='149.00')))
        new = payload(observed(range_page()))
        self.assertEqual('exact_decimal', old['meta']['ecommerce']['point_price_comparison']['method'])
        self.assertTrue(new['meta']['ecommerce']['aggregate_price_comparison']['within_range'])
        self.assertNotIn(MISMATCH, {f['rule_id'] for f in new['findings']})
        for before, after in ((old, new), (new, old)):
            self.assert_withheld(before, after)

    def test_real_exact_and_range_corrections_remain_comparable(self):
        pairs = ((page(offers()[:1], price='149.00'),
                  page([dict(offers()[0], price='149.00')], price='149.00')),
                 (range_page('139'), range_page('159')))
        for old_source, new_source in pairs:
            old, new = payload(observed(old_source)), payload(observed(new_source))
            result = diff_scan.diff_reports(old, new)
            self.assertEqual('comparable', result['comparison']['status'])
            self.assertGreater(result['score_delta'], 0)
            self.assertIn(MISMATCH, {f['rule_id'] for f in result['resolved']})
            self.assertTrue(diff_scan.diff_reports(new, old)['regression'])

    def test_adding_a_missing_schema_price_remains_a_valid_repair(self):
        offer = dict(offers()[0])
        offer.pop('price')
        old = payload(observed(page([offer], price='149.00')))
        new = payload(observed(page([dict(offers()[0], price='149.00')], price='149.00')))
        self.assertNotIn('point_price_comparison', old['meta']['ecommerce'])
        result = diff_scan.diff_reports(old, new)
        self.assertEqual('comparable', result['comparison']['status'])
        self.assertGreater(result['score_delta'], 0)
        self.assertIn('schema.ecommerce.offer.missing.price', {f['rule_id'] for f in result['resolved']})

    def test_native_crawl_preserves_basis_and_leaf_loss_blocks_audit_claims(self):
        source = page(offers()[:1], price='149.00')
        reports = [observed(source), observed(source.replace('<meta property="product:price:amount" content="149.00">', ''))]
        crawls = []
        for report in reports:
            with mock.patch.object(crawl_site.scanner, 'gather_context', return_value={}), \
                    mock.patch.object(crawl_site, 'discover', return_value=[URL + '/leaf']), \
                    mock.patch.object(crawl_site.scanner, 'scan', return_value=report):
                crawls.append(crawl_site.crawl(URL, max_pages=1))
        old_basis = crawls[0]['pages'][0].get('merchant_comparison_basis')
        new_basis = crawls[1]['pages'][0].get('merchant_comparison_basis')
        self.assertIsInstance(old_basis, dict)
        self.assertIn('price', old_basis['visible_fields'])
        self.assertNotIn('price', new_basis['visible_fields'])
        home = payload(observed(page(offers()[:1], price='129.00')))
        audits = [{'site': URL, 'overall_score': crawl['avg_score'], 'homepage': home,
                   'crawl': json.loads(crawl_site.render_json(crawl)), 'sitemap': {}} for crawl in crawls]
        self.assert_withheld(*audits)
        audits[1]['crawl']['pages'][0]['merchant_comparison_basis'] = dict(old_basis, price_method='inclusive_range')
        self.assert_withheld(*audits)

    def test_known_crawl_basis_cannot_certify_an_unrecorded_counterpart(self):
        old, new = saved_audit([URL]), saved_audit([URL], 99)
        new['crawl']['pages'][0]['merchant_comparison_basis'] = {'visible_fields': ['price'], 'price_method': 'exact_decimal'}
        self.assert_withheld(old, new)
        old['crawl']['pages'][0]['merchant_comparison_basis'] = copy.deepcopy(new['crawl']['pages'][0]['merchant_comparison_basis'])
        self.assertEqual('comparable', diff_scan.diff_reports(old, new)['comparison']['status'])
        old['crawl']['pages'][0].pop('merchant_comparison_basis')
        new['crawl']['pages'][0].pop('merchant_comparison_basis')
        self.assertEqual('comparable', diff_scan.diff_reports(old, new)['comparison']['status'])

    def test_unselected_schema_observations_do_not_invalidate_content_diffs(self):
        old = payload(observed(page(offers()[:1], price='149.00')))
        new = payload(observed(range_page()))
        for report in (old, new):
            report['meta']['scan_scope'] = {'requested': ['content'], 'completed': ['content']}
        self.assertEqual('comparable', diff_scan.diff_reports(old, new)['comparison']['status'])

    def test_explicit_malformed_crawl_receipts_withhold_claims(self):
        for basis in (None, {}, {'visible_fields': ['price'], 'price_method': 'future'},
                      {'visible_fields': [1], 'price_method': None},
                      {'visible_fields': ['future'], 'price_method': None},
                      {'visible_fields': {'price': {}}, 'price_method': None},
                      {'visible_fields': [[]], 'price_method': None},
                      {'visible_fields': [], 'price_method': 'exact_decimal'},
                      {'visible_fields': ['price', 'price'], 'price_method': None}):
            old = saved_audit([URL])
            old['crawl']['pages'][0]['merchant_comparison_basis'] = basis
            self.assert_withheld(old, old)
            old['crawl']['pages'][0]['scan_scope'] = {'requested': ['schema'], 'completed': ['schema']}
            self.assert_withheld(old, old)

    def test_receipt_order_and_missing_price_repairs_do_not_change_crawl_scope(self):
        old, new = saved_audit([URL]), saved_audit([URL], 99)
        old['crawl']['pages'][0]['merchant_comparison_basis'] = {'visible_fields': ['price', 'currency'], 'price_method': None}
        new['crawl']['pages'][0]['merchant_comparison_basis'] = {'visible_fields': ['currency', 'price'], 'price_method': 'exact_decimal'}
        self.assertEqual('comparable', diff_scan.diff_reports(old, new)['comparison']['status'])
        old['crawl']['pages'][0]['merchant_comparison_basis']['price_method'] = 'exact_decimal'
        self.assertEqual('comparable', diff_scan.diff_reports(old, new)['comparison']['status'])
        for data in (old, new):
            data['crawl']['pages'][0]['merchant_comparison_basis']['price_method'] = 'inclusive_range'
        self.assertEqual('comparable', diff_scan.diff_reports(old, new)['comparison']['status'])

    def test_explicit_page_receipts_validate_and_respect_selected_scope(self):
        data = payload(observed(page(offers()[:1])))
        data['meta']['merchant_comparison_basis'] = recorded_merchant_comparison_basis(data['meta'])
        self.assertEqual('comparable', diff_scan.diff_reports(data, data)['comparison']['status'])
        for bad in (None, {}, {'visible_fields': ['price'], 'price_method': 'future'}):
            data['meta']['merchant_comparison_basis'] = bad
            self.assert_withheld(data, data)
        data['meta']['scan_scope'] = {'requested': ['content'], 'completed': ['content']}
        self.assertEqual('comparable', diff_scan.diff_reports(data, data)['comparison']['status'])

    def test_unselected_crawl_scope_ignores_unrelated_receipts(self):
        old, new = saved_audit([URL]), saved_audit([URL], 99)
        for data in (old, new):
            scope = {'requested': ['content'], 'completed': ['content']}
            data['homepage']['meta']['scan_scope'] = scope
            data['crawl']['pages'][0]['scan_scope'] = scope
        old['crawl']['pages'][0]['merchant_comparison_basis'] = None
        new['crawl']['pages'][0]['merchant_comparison_basis'] = {'visible_fields': ['price'], 'price_method': 'exact_decimal'}
        self.assertEqual('comparable', diff_scan.diff_reports(old, new)['comparison']['status'])

    def test_basis_retains_only_active_known_observation_fields(self):
        data = payload(observed(page(offers()[:1])))['meta']
        before = copy.deepcopy(data)
        basis = recorded_merchant_comparison_basis(data)
        self.assertEqual(['availability', 'brand', 'currency', 'name', 'price', 'sku'], basis['visible_fields'])
        self.assertEqual('exact_decimal', basis['price_method'])
        self.assertEqual(before, data)
        data['ecommerce']['is_product'] = False
        self.assertEqual({'visible_fields': [], 'price_method': None}, recorded_merchant_comparison_basis(data))
        for unsupported in (None, {}, {'ecommerce': None}, {'ecommerce': {'is_product': True}},
                            {'ecommerce': {'is_product': 1, 'visible_facts': {}}}):
            self.assertIsNone(recorded_merchant_comparison_basis(unsupported))

    def test_duplicate_crawl_observations_cannot_conceal_conflicting_coverage(self):
        old, new = saved_audit([URL, URL]), saved_audit([URL, URL], 99)
        complete = {'visible_fields': ['price'], 'price_method': 'exact_decimal'}
        for data in (old, new):
            for row in data['crawl']['pages']:
                row['merchant_comparison_basis'] = copy.deepcopy(complete)
        new['crawl']['pages'][1]['merchant_comparison_basis']['visible_fields'] = []
        self.assert_withheld(old, new)
        new['crawl']['pages'].reverse()
        self.assert_withheld(old, new)

    def test_known_price_method_cannot_disappear_behind_missing_schema_data(self):
        old = payload(observed(page(offers()[:1], price='149.00')))
        offer = dict(offers()[0])
        offer.pop('price')
        new = payload(observed(page([offer], price='149.00')))
        self.assertEqual(old['meta']['ecommerce']['visible_facts'], new['meta']['ecommerce']['visible_facts'])
        self.assertNotIn('point_price_comparison', new['meta']['ecommerce'])
        self.assert_withheld(old, new)
        earlier, later = saved_audit([URL]), saved_audit([URL], 99)
        for data, method in ((earlier, 'exact_decimal'), (later, None)):
            data['crawl']['pages'][0]['merchant_comparison_basis'] = {'visible_fields': ['price'], 'price_method': method}
        self.assert_withheld(earlier, later)
        self.assertEqual('comparable', diff_scan.diff_reports(later, earlier)['comparison']['status'])

    def test_duplicate_rows_preserve_missing_basis_and_missing_method(self):
        for remove in ('receipt', 'method'):
            old, new = saved_audit([URL, URL]), saved_audit([URL, URL], 99)
            for data in (old, new):
                for row in data['crawl']['pages']:
                    row['merchant_comparison_basis'] = {'visible_fields': ['price'], 'price_method': 'exact_decimal'}
            if remove == 'receipt':
                new['crawl']['pages'][1].pop('merchant_comparison_basis')
            else:
                new['crawl']['pages'][1]['merchant_comparison_basis']['price_method'] = None
            self.assert_withheld(old, new)
            self.assert_withheld(new, new)
