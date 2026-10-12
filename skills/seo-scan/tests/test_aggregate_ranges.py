"""AggregateOffer range compatibility is not an exact seller-price proof."""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import scan
from lib import ecommerce, htmlx, http
from lib.report import Report
try:
    from .test_ecommerce import fixture, inspect, rules
except ImportError:
    from test_ecommerce import fixture, inspect, rules

URL = "https://shop.test/p/socks"
MISMATCH = "schema.ecommerce.price.mismatch"
NOTE = "schema.ecommerce.offer.comparison.ambiguous"


def page(price="21.00", currency="USD", changes=None, missing=()):
    html = fixture("aggregate-product.html")
    blob = htmlx._parse_stdlib(html, URL).scripts_ld[0]
    data = json.loads(blob)
    offer = data["@graph"][1]
    offer.update(changes or {})
    for key in missing:
        offer.pop(key, None)
    html = html.replace(blob, json.dumps(data)).replace('content="18.00"', 'content="' + price + '"')
    if currency is None:
        return html.replace('<meta property="product:price:currency" content="USD">', '')
    return html.replace('content="USD"', 'content="' + currency + '"')


class TestAggregateRanges(unittest.TestCase):
    def test_inclusive_endpoints_and_interior_are_compatible_not_point_mismatches(self):
        for price in ("18.00", "21.00", "24.00"):
            with self.subTest(price=price):
                _, report, meta = inspect(page(price), URL)
                self.assertNotIn(MISMATCH, rules(report))
                self.assertNotIn(NOTE, rules(report))
                self.assertEqual("ready", meta["offer_comparison_status"]["price"])
                scope = meta["aggregate_price_comparison"]
                self.assertTrue(scope["within_range"])
                self.assertEqual("inclusive_range", scope["method"])
                self.assertIn("not selected seller", scope["scope"])

    def test_outside_either_endpoint_remains_a_high_mismatch(self):
        for price in ("17.99", "24.01"):
            _, report, meta = inspect(page(price), URL)
            finding = next(f for f in report.findings if f.rule_id == MISMATCH)
            self.assertEqual("high", finding.severity)
            self.assertIn("18.00–24.00 USD", finding.detail)
            self.assertFalse(meta["aggregate_price_comparison"]["within_range"])
            self.assertIn("outside the schema offer range", report.to_html())

    def test_degenerate_range_checks_only_its_single_amount(self):
        for price, mismatch in (("18.00", False), ("18.01", True)):
            _, report, _ = inspect(page(price, changes={"highPrice": "18.00"}), URL)
            self.assertEqual(mismatch, MISMATCH in rules(report))

    def test_mismatched_currency_is_not_a_numeric_comparison(self):
        _, report, meta = inspect(page("25.00", currency="EUR"), URL)
        self.assertNotIn(MISMATCH, rules(report))
        self.assertIn("schema.ecommerce.currency.mismatch", rules(report))
        self.assertIn(NOTE, rules(report))
        self.assertEqual("skipped_ambiguous", meta["offer_comparison_status"]["price"])

    def test_missing_and_invalid_currency_keep_their_findings(self):
        for changes, missing, expected in (
            ({}, ("priceCurrency",), "schema.ecommerce.aggregateoffer.missing.pricecurrency"),
            ({"priceCurrency": "US"}, (), "schema.ecommerce.offer.invalid.currency"),
        ):
            _, report, meta = inspect(page("25.00", changes=changes, missing=missing), URL)
            self.assertIn(expected, rules(report))
            self.assertNotIn(MISMATCH, rules(report))
            self.assertEqual("skipped_ambiguous", meta["offer_comparison_status"]["price"])

    def test_unknown_observed_currency_does_not_inherit_schema_units(self):
        _, report, meta = inspect(page("25.00", currency=None), URL)
        self.assertIn(NOTE, rules(report))
        self.assertNotIn(MISMATCH, rules(report))
        self.assertNotIn("aggregate_price_comparison", meta)

    def test_non_scalar_declared_currency_cannot_establish_range_units(self):
        for value in (["USD", "EUR"], {"name": "USD"}, True):
            _, report, meta = inspect(page("25", changes={"priceCurrency": value}), URL)
            self.assertIn(NOTE, rules(report))
            self.assertNotIn(MISMATCH, rules(report))
            self.assertEqual("skipped_ambiguous", meta["offer_comparison_status"]["price"])

    def test_missing_bounds_are_not_replaced_by_product_or_point_prices(self):
        for bound in ("lowPrice", "highPrice"):
            _, report, meta = inspect(page("25.00", changes={"price": "18.00"}, missing=(bound,)), URL)
            self.assertIn("schema.ecommerce.aggregateoffer.missing." + bound.lower(), rules(report))
            self.assertIn(NOTE, rules(report))
            self.assertNotIn(MISMATCH, rules(report))
            self.assertNotIn("aggregate_price_comparison", meta)

    def test_known_negative_or_inverted_bounds_are_high_findings(self):
        for changes in ({"highPrice": "17"}, {"lowPrice": "-1"}, {"highPrice": "-1"}):
            _, report, meta = inspect(page(changes=changes), URL)
            finding = next(f for f in report.findings if f.rule_id == "schema.ecommerce.offer.invalid.range")
            self.assertEqual("high", finding.severity)
            self.assertNotIn(MISMATCH, rules(report))
            self.assertEqual("skipped_ambiguous", meta["offer_comparison_status"]["price"])

    def test_unsupported_text_and_shapes_get_manual_comparison_not_digit_stripping(self):
        for value in ("USD 24", "2,400", "twenty four", True, {"value": "24"}, ["24", "25"], "NaN", "Infinity", "9" * 513):
            _, report, meta = inspect(page("25.00", changes={"highPrice": value}), URL)
            self.assertIn(NOTE, rules(report))
            self.assertNotIn(MISMATCH, rules(report))
            self.assertEqual("skipped_ambiguous", meta["offer_comparison_status"]["price"])
            self.assertIn("Verify the source Offer for price", report.to_html())

    def test_normalized_singleton_arrays_keep_their_scalar_semantics(self):
        _, report, meta = inspect(page(changes={"lowPrice": ["18"], "highPrice": ["24"]}), URL)
        self.assertNotIn(NOTE, rules(report))
        self.assertTrue(meta["aggregate_price_comparison"]["within_range"])

    def test_numeric_and_exponent_bounds_are_read_without_rounding(self):
        _, report, meta = inspect(page(changes={"lowPrice": 18, "highPrice": "2.4e1"}), URL)
        self.assertNotIn(NOTE, rules(report))
        self.assertTrue(meta["aggregate_price_comparison"]["within_range"])
        high = "123456789012345678901234567890.01"
        _, report, meta = inspect(page("123456789012345678901234567890.02", changes={"lowPrice": "18", "highPrice": high}), URL)
        self.assertIn(MISMATCH, rules(report))
        self.assertEqual(high, meta["aggregate_price_comparison"]["highPrice"])

    def test_explicit_localized_observed_price_is_supported(self):
        _, report, meta = inspect(page("$21,00"), URL)
        self.assertNotIn(MISMATCH, rules(report))
        self.assertTrue(meta["aggregate_price_comparison"]["within_range"])

    def test_unparseable_observed_amount_is_not_guessed(self):
        for price in ("from 25", "21–30", "1e3", "NaN", "2,,5", "1,2,5", "EUR 25", "€25"):
            _, report, meta = inspect(page(price), URL)
            self.assertIn(NOTE, rules(report))
            self.assertNotIn(MISMATCH, rules(report))
            self.assertEqual("skipped_ambiguous", meta["offer_comparison_status"]["price"])

    def test_other_offer_and_identity_checks_still_run(self):
        html = page(changes={"availability": "https://schema.org/OutOfStock", "url": "http://[bad"})
        html = html.replace('<h1>Wool Socks</h1>', '<h1>Completely different item</h1>')
        _, report, _ = inspect(html, URL)
        self.assertIn("schema.ecommerce.offer.invalid.url", rules(report))
        self.assertIn("schema.ecommerce.name.mismatch", rules(report))
        self.assertNotIn(MISMATCH, rules(report))

    def test_all_three_formats_and_parser_backends_share_range_scope(self):
        pages = [page()]
        for name, attr in (("microdata-product.html", "itemprop"), ("rdfa-product.html", "property")):
            html = fixture(name).replace('https://schema.org/Offer"', 'https://schema.org/AggregateOffer"').replace('typeof="Offer"', 'typeof="AggregateOffer"')
            html = html.replace('<meta ' + attr + '="price" content="129.00">', '<meta ' + attr + '="lowPrice" content="120"><meta ' + attr + '="highPrice" content="140"><meta ' + attr + '="offerCount" content="3">')
            pages.append(html)
        for html in pages:
            outcomes = []
            for doc in (htmlx._parse_stdlib(html, URL), htmlx.parse(html, URL)):
                report = Report(URL)
                meta = ecommerce.audit(doc, report)
                self.assertNotIn(MISMATCH, rules(report))
                self.assertTrue(meta["aggregate_price_comparison"]["within_range"])
                outcomes.append((meta, rules(report)))
            self.assertEqual(outcomes[0], outcomes[1])

    def test_scan_json_preserves_serializable_range_evidence(self):
        response = http.Response(URL, URL, 200, {"content-type": "text/html"}, page(), 1)
        with mock.patch.object(scan.http, "fetch", return_value=response):
            payload = json.loads(scan.scan(URL, only=["schema"], ctx={}, check_images=False).to_json())
        self.assertEqual("18.00", payload["meta"]["ecommerce"]["aggregate_price_comparison"]["lowPrice"])
        self.assertNotIn(MISMATCH, {f["rule_id"] for f in payload["findings"]})


if __name__ == "__main__":
    unittest.main()
