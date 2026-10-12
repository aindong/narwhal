"""Exact amount comparisons require numeric evidence in matching units."""

import json
import sys
import unittest
from decimal import Decimal, Inexact, Rounded, localcontext
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import scan
from lib import ecommerce, htmlx, http
from lib.report import Report
try:
    from .test_offer_comparisons import product, page, URL
    from .test_ecommerce import fixture, inspect, rules
except ImportError:
    from test_offer_comparisons import product, page, URL
    from test_ecommerce import fixture, inspect, rules

MISMATCH = 'schema.ecommerce.price.mismatch'
NOTE = 'schema.ecommerce.offer.comparison.ambiguous'
EXTRACTION = 'schema.ecommerce.offer.price.extraction'


def point(declared, observed='129.00'):
    return page(dict(product()['offers'], price=declared), observed)


class TestExactPointPrices(unittest.TestCase):
    def test_declared_exponents_are_numbers_not_concatenated_digits(self):
        for value in ('1e3', '1E+3', '10e2', '1000.00'):
            _, report, meta = inspect(point(value, '1000'), URL)
            self.assertNotIn(MISMATCH, rules(report)); self.assertNotIn(NOTE, rules(report))
            self.assertEqual('exact_decimal', meta['point_price_comparison']['method'])
        _, report, _ = inspect(point('1e3', '13'), URL)
        self.assertIn(MISMATCH, rules(report))

    def test_long_decimal_differences_are_not_rounded_equal(self):
        left = '123456789012345678901234567890.01'
        right = '123456789012345678901234567890.02'
        _, report, meta = inspect(point(left, right), URL)
        self.assertIn(MISMATCH, rules(report))
        self.assertEqual(left, meta['point_price_comparison']['schema_price'])
        self.assertEqual(right, meta['point_price_comparison']['observed_price'])

    def test_exact_comparison_does_not_depend_on_decimal_context(self):
        with localcontext() as ctx:
            ctx.prec = 2; ctx.traps[Inexact] = True; ctx.traps[Rounded] = True
            _, report, _ = inspect(point('129.00', '129.01'), URL)
            self.assertIn(MISMATCH, rules(report))
            self.assertEqual(Decimal('129.00'), ecommerce._norm_price('129.00'))
            self.assertFalse(ctx.flags[Inexact]); self.assertFalse(ctx.flags[Rounded])

    def test_multiple_long_prices_cannot_create_false_consensus(self):
        left = '123456789012345678901234567890.01'
        right = '123456789012345678901234567890.02'
        offers = [dict(product()['offers'], price=left), dict(product()['offers'], price=right)]
        for values in (offers, list(reversed(offers))):
            _, report, meta = inspect(page(values, right), URL)
            self.assertIn(NOTE, rules(report)); self.assertNotIn(MISMATCH, rules(report))
            self.assertEqual('skipped_ambiguous', meta['offer_comparison_status']['price'])

    def test_numeric_equivalence_keeps_consensus_without_rounding(self):
        offers = [dict(product()['offers'], price='1e3'), dict(product()['offers'], price='1000.00')]
        for observed, mismatch in (('1000', False), ('1001', True)):
            _, report, meta = inspect(page(offers, observed), URL)
            self.assertEqual('ready', meta['offer_comparison_status']['price'])
            self.assertEqual(mismatch, MISMATCH in rules(report))

    def test_unsupported_schema_text_is_not_coerced_or_called_invalid_schema(self):
        for value in ('from 129', '$129', 'USD 129', '129,00', '1,000', '1_29', 'NaN', 'Infinity', '9' * 513):
            _, report, meta = inspect(point(value), URL)
            self.assertIn(EXTRACTION, rules(report)); self.assertIn(NOTE, rules(report))
            self.assertNotIn(MISMATCH, rules(report))
            self.assertNotIn('schema.ecommerce.offer.invalid.price', rules(report))
            self.assertEqual('skipped_ambiguous', meta['offer_comparison_status']['price'])
            self.assertNotIn('point_price_comparison', meta)
            self.assertIn('Unsupported Text', report.to_html())

    def test_observed_prose_exponents_ranges_and_bad_separators_are_not_guessed(self):
        for observed in ('from 129', '1e3', '129–139', '1,2,9', '129 USD extra', 'NaN', '€129', 'EUR 129'):
            _, report, meta = inspect(point('129', observed), URL)
            self.assertNotIn(MISMATCH, rules(report)); self.assertIn(NOTE, rules(report))
            self.assertEqual('skipped_ambiguous', meta['offer_comparison_status']['price'])

    def test_supported_localized_display_and_explicit_units_remain(self):
        for observed in ('129', '129,00', '$129.00', 'USD 129.00', '129.00 USD'):
            _, report, meta = inspect(point('129', observed), URL)
            self.assertNotIn(MISMATCH, rules(report)); self.assertNotIn(NOTE, rules(report))
            self.assertEqual('ready', meta['offer_comparison_status']['price'])
        _, report, _ = inspect(point('1000', '1,000.00'), URL)
        self.assertNotIn(MISMATCH, rules(report))

    def test_single_offer_different_or_unknown_units_skip_amount_only(self):
        for currency in ('EUR', '', 'US'):
            html = point('129', '130').replace('content="USD"', 'content="' + currency + '"')
            _, report, meta = inspect(html, URL)
            self.assertNotIn(MISMATCH, rules(report)); self.assertIn(NOTE, rules(report))
            self.assertEqual('skipped_ambiguous', meta['offer_comparison_status']['price'])
            if currency:
                self.assertIn('schema.ecommerce.currency.mismatch', rules(report))

    def test_known_nonpositive_merchant_prices_keep_high_finding(self):
        for value in ('-1', '-0.01', '0', '0.00'):
            _, report, _ = inspect(point(value, value), URL)
            finding = next(f for f in report.findings if f.rule_id == 'schema.ecommerce.offer.invalid.price')
            self.assertEqual('high', finding.severity)

    def test_price_specification_fallback_uses_the_same_exact_parser(self):
        offer = product()['offers']; del offer['price']
        offer['priceSpecification'] = {'price': '1e3', 'priceCurrency': 'USD'}
        _, report, meta = inspect(page(offer, '1000'), URL)
        self.assertNotIn(MISMATCH, rules(report))
        self.assertEqual('ready', meta['offer_comparison_status']['price'])

    def test_jsonld_microdata_rdfa_and_parser_backends_agree(self):
        pages = [point('1e3', '1000')]
        for name in ('microdata-product.html', 'rdfa-product.html'):
            html = fixture(name).replace('content="129.00"', 'content="1e3"')
            html = '<meta property="product:price:amount" content="1000">' + html
            pages.append(html)
        for html in pages:
            for doc in (htmlx._parse_stdlib(html, URL), htmlx.parse(html, URL)):
                report = Report(URL); meta = ecommerce.audit(doc, report)
                self.assertNotIn(MISMATCH, rules(report))
                self.assertEqual('ready', meta['offer_comparison_status']['price'])
                json.loads(report.to_json())

    def test_full_scan_json_records_exact_comparison_without_decimal_objects(self):
        html = point('1e3', '1000')
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, html, 1)
        with mock.patch.object(scan.http, 'fetch', return_value=response):
            report = scan.scan(URL, only=['schema'], ctx={}, check_images=False)
        meta = json.loads(report.to_json())['meta']['ecommerce']['point_price_comparison']
        self.assertEqual('exact_decimal', meta['method'])
        self.assertEqual('1000', meta['observed_price'])


if __name__ == '__main__':
    unittest.main()
