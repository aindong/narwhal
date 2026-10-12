"""A measured numeric zero is present evidence, not a missing price."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from lib import ecommerce
try:
    from .test_offer_comparisons import product, page, URL
    from .test_ecommerce import inspect, rules
except ImportError:
    from test_offer_comparisons import product, page, URL
    from test_ecommerce import inspect, rules


class TestZeroPriceEvidence(unittest.TestCase):
    def test_clean_preserves_numeric_zero_without_treating_false_as_a_number(self):
        for value, expected in ((0, '0'), (0.0, '0.0'), (-0.0, '-0.0'),
                                ([0], '0'), ({'value': 0}, '0')):
            self.assertEqual(expected, ecommerce._clean(value))
        self.assertEqual('', ecommerce._clean(False))
        self.assertEqual('', ecommerce._clean(None))

    def test_zero_merchant_price_is_present_but_invalid_not_missing(self):
        for value in (0, 0.0, '0', '0.00'):
            _, report, meta = inspect(page(dict(product()['offers'], price=value), '0'), URL)
            self.assertIn('schema.ecommerce.offer.invalid.price', rules(report))
            self.assertNotIn('schema.ecommerce.offer.missing.price', rules(report))
            self.assertNotIn('schema.ecommerce.visible.price.missing', rules(report))
            self.assertNotIn('schema.ecommerce.price.mismatch', rules(report))
            self.assertEqual('exact_decimal', meta['point_price_comparison']['method'])
            finding = next(f for f in report.findings if f.rule_id == 'schema.ecommerce.offer.invalid.price')
            self.assertEqual('high', finding.severity)

    def test_zero_can_be_compared_to_a_different_explicit_amount(self):
        _, report, meta = inspect(page(dict(product()['offers'], price=0), '1'), URL)
        self.assertIn('schema.ecommerce.price.mismatch', rules(report))
        self.assertEqual('0', meta['point_price_comparison']['schema_price'])

    def test_price_specification_zero_remains_present(self):
        offer = product()['offers']; del offer['price']
        offer['priceSpecification'] = {'price': 0, 'priceCurrency': 'USD'}
        _, report, _ = inspect(page(offer, '0'), URL)
        self.assertIn('schema.ecommerce.offer.invalid.price', rules(report))
        self.assertNotIn('schema.ecommerce.offer.missing.price', rules(report))

    def test_zero_is_not_replaced_by_a_positive_fallback(self):
        offer = dict(product()['offers'], price=0)
        offer['priceSpecification'] = {'price': '129', 'priceCurrency': 'USD'}
        _, report, meta = inspect(page(offer, '0'), URL)
        self.assertEqual('0', meta['point_price_comparison']['schema_price'])
        self.assertNotIn('schema.ecommerce.price.mismatch', rules(report))

    def test_absent_and_positive_prices_keep_existing_findings(self):
        _, missing, _ = inspect(page(dict(product()['offers'], price=None)), URL)
        self.assertIn('schema.ecommerce.offer.missing.price', rules(missing))
        self.assertNotIn('schema.ecommerce.offer.invalid.price', rules(missing))
        _, complete, _ = inspect(page(product()['offers']), URL)
        self.assertNotIn('schema.ecommerce.offer.missing.price', rules(complete))
        self.assertNotIn('schema.ecommerce.offer.invalid.price', rules(complete))


if __name__ == '__main__':
    unittest.main()
