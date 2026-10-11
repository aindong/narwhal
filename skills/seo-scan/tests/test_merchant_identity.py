"""Variant comparisons require unique identity, not schema source order."""

import json
import sys
import unittest
from html import escape
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

URL = "https://shop.test/trail"
AMBIGUOUS = "schema.ecommerce.comparison.ambiguous"


def variants():
    blob = htmlx._parse_stdlib(fixture("variant-product.html"), URL).scripts_ld[0]
    return json.loads(blob)["hasVariant"]


def page(products=None, sku=None, h1="Trail Shoe"):
    html = fixture("variant-product.html")
    blob = htmlx._parse_stdlib(html, URL).scripts_ld[0]
    group = json.loads(blob)
    if products is not None:
        group["hasVariant"] = products
    html = html.replace(blob, json.dumps(group))
    tag = '<meta property="product:retailer_item_id" content="BLUE-42">'
    html = html.replace(tag, tag.replace("BLUE-42", escape(sku, quote=True)) if sku is not None else "")
    return html.replace("<h1>Trail Shoe Blue</h1>", "<h1>" + escape(h1) + "</h1>")


class TestMerchantIdentity(unittest.TestCase):
    def assert_ambiguous(self, html, method):
        _, report, meta = inspect(html, URL)
        self.assertEqual("skipped_ambiguous", meta["comparison_status"])
        self.assertEqual(method, meta["selection_method"])
        self.assertIsNone(meta["selected_product"])
        self.assertIn(AMBIGUOUS, rules(report))
        self.assertFalse(any(".mismatch" in r or r.startswith("schema.ecommerce.visible.") for r in rules(report)))
        finding = next(f for f in report.findings if f.rule_id == AMBIGUOUS)
        self.assertEqual("low", finding.severity)
        self.assertIn("comparisons are skipped", finding.detail)
        json.loads(report.to_json())
        return report, meta

    def test_generic_group_name_does_not_select_the_first_variant(self):
        _, meta = self.assert_ambiguous(page(), "ambiguous_name")
        self.assertTrue(meta["is_merchant"])
        self.assertEqual(2, meta["product_nodes_count"])

    def test_ambiguous_output_is_independent_of_variant_order(self):
        products = variants()
        reports = [self.assert_ambiguous(page(products=order), "ambiguous_name")[0]
                   for order in (products, list(reversed(products)))]
        self.assertEqual(rules(reports[0]), rules(reports[1]))
        self.assertEqual(reports[0].score(), reports[1].score())

    def test_missing_or_unmatched_identity_never_falls_back_to_first(self):
        for h1 in ("", "Our collection"):
            with self.subTest(h1=h1):
                self.assert_ambiguous(page(h1=h1), "unmatched_identity")

    def test_unique_identifier_selects_variant_and_preserves_real_mismatch(self):
        for value, mismatch in (("139.00", False), ("140.00", True)):
            products = variants()
            products[1]["offers"]["price"] = value
            _, report, meta = inspect(page(products, sku="BLUE-42"), URL)
            self.assertEqual("BLUE-42", meta["selected_product"])
            self.assertEqual("visible_identifier", meta["selection_method"])
            self.assertEqual("ready", meta["comparison_status"])
            self.assertNotIn(AMBIGUOUS, rules(report))
            self.assertEqual(mismatch, "schema.ecommerce.price.mismatch" in rules(report))

    def test_unique_exact_name_beats_broad_containment(self):
        products = variants()
        products[0]["name"] = "Trail Shoe"
        _, report, meta = inspect(page(products, h1="Trail Shoe Blue"), URL)
        self.assertEqual("BLUE-42", meta["selected_product"])
        self.assertEqual("visible_name_exact", meta["selection_method"])
        self.assertNotIn("schema.ecommerce.price.mismatch", rules(report))

    def test_unique_containment_name_still_supports_comparison(self):
        _, report, meta = inspect(page(h1="Buy Trail Shoe Blue today"), URL)
        self.assertEqual("BLUE-42", meta["selected_product"])
        self.assertEqual("visible_name_unique", meta["selection_method"])
        self.assertNotIn(AMBIGUOUS, rules(report))

    def test_conflicting_copies_with_same_identifier_are_not_silently_chosen(self):
        products = variants()
        products[0]["sku"] = "BLUE-42"
        self.assert_ambiguous(page(products, sku="BLUE-42", h1="Trail Shoe Blue"), "ambiguous_identifier")

    def test_duplicate_exact_names_are_ambiguous(self):
        products = variants()
        products[0]["name"] = products[1]["name"]
        self.assert_ambiguous(page(products, h1="Trail Shoe Blue"), "ambiguous_name")

    def test_identifier_punctuation_and_unicode_are_preserved(self):
        for first, second in (("BLUE42", "BLUE-42"), ("\u9774-\u8d64", "\u9774-\u9752")):
            products = variants()
            products[0]["sku"], products[1]["sku"] = first, second
            _, report, meta = inspect(page(products, sku=second), URL)
            self.assertEqual(second, meta["selected_product"])
            self.assertNotIn("schema.ecommerce.sku.mismatch", rules(report))
            self.assertNotIn("schema.ecommerce.price.mismatch", rules(report))

    def test_single_product_sku_mismatch_remains_detectable(self):
        html = fixture("complete-product.html").replace('content="TS-42"', 'content="TS42"')
        _, report, meta = inspect(html, URL)
        self.assertEqual("single_product", meta["selection_method"])
        self.assertIn("schema.ecommerce.sku.mismatch", rules(report))

    def test_ambiguous_identity_does_not_suppress_schema_defects(self):
        products = variants()
        del products[0]["brand"]
        products[1]["offers"]["price"] = "-1"
        report, _ = self.assert_ambiguous(page(products), "ambiguous_name")
        self.assertIn("schema.ecommerce.product.missing.brand", rules(report))
        self.assertIn("schema.ecommerce.offer.invalid.price", rules(report))

    def test_parser_backends_and_scan_json_expose_same_comparison_scope(self):
        html = page()
        observed = []
        for doc in (htmlx._parse_stdlib(html, URL), htmlx.parse(html, URL)):
            report = Report(URL)
            observed.append((ecommerce.audit(doc, report), rules(report)))
        self.assertEqual(observed[0], observed[1])
        response = http.Response(URL, URL, 200, {"content-type": "text/html"}, html, 1)
        with mock.patch.object(scan.http, "fetch", return_value=response):
            report = scan.scan(URL, only=["schema"], ctx={}, check_images=False)
        payload = json.loads(report.to_json())
        self.assertIsNone(payload["meta"]["ecommerce"]["selected_product"])
        self.assertEqual("skipped_ambiguous", payload["meta"]["ecommerce"]["comparison_status"])
        self.assertIn(AMBIGUOUS, rules(report))


if __name__ == "__main__":
    unittest.main()
