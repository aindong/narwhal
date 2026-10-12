"""Multiple Offers require per-field consensus, never source-order guesses."""

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

URL = "https://shop.test/products/trail-shoe"
NOTE = "schema.ecommerce.offer.comparison.ambiguous"


def product():
    return json.loads(htmlx._parse_stdlib(fixture("complete-product.html"), URL).scripts_ld[0])


def offers():
    base = product()["offers"]
    other = dict(base, price="139.00", seller={"@type": "Organization", "name": "Second seller"})
    return [base, other]


def page(values, price="139.00", sku="TS-42"):
    html = fixture("complete-product.html")
    blob = htmlx._parse_stdlib(html, URL).scripts_ld[0]
    p = json.loads(blob)
    p["offers"] = values
    return html.replace(blob, json.dumps(p)).replace('content="129.00"', 'content="' + price + '"').replace('content="TS-42"', 'content="' + sku + '"')


class TestOfferComparisons(unittest.TestCase):
    def test_different_valid_offer_prices_are_not_a_guessed_mismatch(self):
        _, report, meta = inspect(page(offers()), URL)
        self.assertIn(NOTE, rules(report))
        self.assertNotIn("schema.ecommerce.price.mismatch", rules(report))
        self.assertEqual("ready", meta["comparison_status"])
        self.assertEqual("skipped_ambiguous", meta["offer_comparison_status"]["price"])
        self.assertEqual("ready", meta["offer_comparison_status"]["currency"])
        self.assertEqual("TS-42", meta["selected_product"])
        self.assertIn("Verify the source Offer for price", report.to_html())

    def test_reversing_offer_order_preserves_score_findings_and_scope(self):
        values = offers()
        results = [inspect(page(order), URL)[1:] for order in (values, list(reversed(values)))]
        self.assertEqual(rules(results[0][0]), rules(results[1][0]))
        self.assertEqual(results[0][0].score(), results[1][0].score())
        self.assertEqual(results[0][1]["offer_comparison_status"], results[1][1]["offer_comparison_status"])

    def test_price_consensus_preserves_real_mismatch(self):
        values = offers()
        values[1]["price"] = "129.0"
        for price, mismatch in (("129.00", False), ("130.00", True)):
            _, report, meta = inspect(page(values, price), URL)
            self.assertNotIn(NOTE, rules(report))
            self.assertEqual("ready", meta["offer_comparison_status"]["price"])
            self.assertEqual(mismatch, "schema.ecommerce.price.mismatch" in rules(report))
            if mismatch:
                f = next(f for f in report.findings if f.rule_id == "schema.ecommerce.price.mismatch")
                self.assertIn("consensus (2 Offer objects)", f.detail)

    def test_consensus_price_specification_fallback_still_works(self):
        values = offers()
        for offer in values:
            del offer["price"]
            offer["priceSpecification"] = {"price": "129.00"}
        _, report, meta = inspect(page(values, "129.00"), URL)
        self.assertNotIn(NOTE, rules(report))
        self.assertNotIn("schema.ecommerce.price.mismatch", rules(report))
        self.assertEqual("ready", meta["offer_comparison_status"]["price"])

    def test_different_currencies_block_monetary_comparison_even_for_equal_numbers(self):
        values = offers()
        values[1]["price"] = "129.00"
        values[1]["priceCurrency"] = "EUR"
        _, report, meta = inspect(page(values, "130.00"), URL)
        self.assertIn(NOTE, rules(report))
        self.assertNotIn("schema.ecommerce.price.mismatch", rules(report))
        self.assertNotIn("schema.ecommerce.currency.mismatch", rules(report))
        self.assertEqual("skipped_ambiguous", meta["offer_comparison_status"]["price"])
        self.assertEqual("skipped_ambiguous", meta["offer_comparison_status"]["currency"])

    def test_missing_offer_currency_does_not_create_monetary_consensus(self):
        values = offers()
        values[1]["price"] = "129.00"
        del values[1]["priceCurrency"]
        _, report, meta = inspect(page(values, "130.00"), URL)
        self.assertIn("schema.ecommerce.offer.missing.pricecurrency", rules(report))
        self.assertNotIn("schema.ecommerce.price.mismatch", rules(report))
        self.assertEqual("skipped_ambiguous", meta["offer_comparison_status"]["price"])

    def test_different_stock_skips_only_stock_comparison(self):
        values = offers()
        values[1]["price"] = "129.00"
        values[1]["availability"] = "https://schema.org/OutOfStock"
        _, report, meta = inspect(page(values, "130.00", sku="WRONG"), URL)
        self.assertIn(NOTE, rules(report))
        self.assertEqual("skipped_ambiguous", meta["offer_comparison_status"]["availability"])
        self.assertNotIn("schema.ecommerce.availability.mismatch", rules(report))
        self.assertIn("schema.ecommerce.price.mismatch", rules(report))
        self.assertIn("schema.ecommerce.sku.mismatch", rules(report))

    def test_common_stock_and_currency_mismatches_remain_detectable(self):
        values = offers()
        values[1]["price"] = "129.00"
        for offer in values:
            offer["priceCurrency"] = "EUR"
            offer["availability"] = "https://schema.org/OutOfStock"
        _, report, _ = inspect(page(values, "129.00"), URL)
        self.assertIn("schema.ecommerce.currency.mismatch", rules(report))
        self.assertIn("schema.ecommerce.availability.mismatch", rules(report))

    def test_visible_currency_mismatch_does_not_also_invent_numeric_price_mismatch(self):
        values = offers()
        for offer in values:
            offer["price"] = "129.00"
            offer["priceCurrency"] = "EUR"
        _, report, meta = inspect(page(values, "130.00"), URL)
        self.assertIn("schema.ecommerce.currency.mismatch", rules(report))
        self.assertNotIn("schema.ecommerce.price.mismatch", rules(report))
        self.assertEqual("skipped_ambiguous", meta["offer_comparison_status"]["price"])

    def test_unknown_visible_currency_is_not_assumed_from_schema(self):
        values = offers()
        values[1]["price"] = "129.00"
        html = page(values, "130.00").replace('<meta property="product:price:currency" content="USD">', '')
        _, report, meta = inspect(html, URL)
        self.assertNotIn("schema.ecommerce.price.mismatch", rules(report))
        self.assertEqual("skipped_ambiguous", meta["offer_comparison_status"]["price"])
        self.assertIn(NOTE, rules(report))

    def test_incomplete_price_evidence_keeps_completeness_findings(self):
        values = offers()
        del values[1]["price"]
        _, report, meta = inspect(page(values, "130.00"), URL)
        self.assertIn(NOTE, rules(report))
        self.assertIn("schema.ecommerce.offer.missing.price", rules(report))
        self.assertNotIn("schema.ecommerce.price.mismatch", rules(report))
        self.assertEqual("skipped_ambiguous", meta["offer_comparison_status"]["price"])

    def test_single_offer_behavior_and_true_price_mismatch_are_preserved(self):
        for price, mismatch in (("129.00", False), ("130.00", True)):
            _, report, meta = inspect(page(product()["offers"], price), URL)
            self.assertNotIn(NOTE, rules(report))
            self.assertEqual("ready", meta["offer_comparison_status"]["price"])
            self.assertEqual(mismatch, "schema.ecommerce.price.mismatch" in rules(report))

    def test_multiple_aggregate_ranges_are_not_selected_lower_bound_prices(self):
        values = offers()
        values[1].update({"@type": "AggregateOffer", "lowPrice": "129.00", "highPrice": "149.00", "offerCount": "2"})
        _, report, meta = inspect(page(values), URL)
        self.assertIn(NOTE, rules(report))
        self.assertNotIn("schema.ecommerce.price.mismatch", rules(report))
        self.assertEqual("skipped_ambiguous", meta["offer_comparison_status"]["price"])

    def test_all_missing_prices_remain_missing_not_silently_suppressed(self):
        values = offers()
        for offer in values:
            del offer["price"]
        _, report, _ = inspect(page(values), URL)
        self.assertIn("schema.ecommerce.offer.missing.price", rules(report))
        self.assertIn("schema.ecommerce.visible.price.missing", rules(report))

    def test_parser_backends_and_scan_json_share_field_scope(self):
        html = page(offers())
        results = []
        for doc in (htmlx._parse_stdlib(html, URL), htmlx.parse(html, URL)):
            report = Report(URL)
            results.append((ecommerce.audit(doc, report), rules(report)))
        self.assertEqual(results[0], results[1])
        response = http.Response(URL, URL, 200, {"content-type": "text/html"}, html, 1)
        with mock.patch.object(scan.http, "fetch", return_value=response):
            payload = json.loads(scan.scan(URL, only=["schema"], ctx={}, check_images=False).to_json())
        self.assertEqual("skipped_ambiguous", payload["meta"]["ecommerce"]["offer_comparison_status"]["price"])


if __name__ == "__main__":
    unittest.main()
