"""Product detection, merchant-schema, and visible mismatch contracts."""

import json
import sys
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import audit_schema  # noqa: E402
import crawl_site  # noqa: E402
import mcp_server  # noqa: E402
import scan as scan_mod  # noqa: E402
from lib import ecommerce, htmlx  # noqa: E402
from lib import http  # noqa: E402
from lib.report import Report  # noqa: E402
from unittest import mock

FIXTURES = Path(__file__).parent / "fixtures" / "ecommerce"


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def inspect(html, url="https://shop.test/products/example"):
    doc = htmlx.parse(html, url)
    report = Report(url, final_url=url, fetched_status=200)
    meta = ecommerce.audit(doc, report, today=date(2026, 8, 21))
    return doc, report, meta


def rules(report):
    return {f.rule_id for f in report.findings}


class TestProductDetection(unittest.TestCase):
    def test_product_jsonld_is_authoritative(self):
        doc, _, meta = inspect(fixture("complete-product.html"))
        self.assertTrue(htmlx.looks_product(doc))
        self.assertTrue(meta["is_product"])
        self.assertEqual(1.0, meta["confidence"])

    def test_price_in_article_does_not_trigger_product_checks(self):
        doc, report, meta = inspect(fixture("article-with-price.html"))
        self.assertFalse(htmlx.looks_product(doc))
        self.assertFalse(meta["is_product"])
        self.assertEqual(set(), rules(report))

    def test_article_showing_product_json_example_is_not_a_product(self):
        html = '<article><h1>Product schema tutorial</h1><pre>{"@type":"Product","name":"Example"}</pre></article>'
        doc, report, meta = inspect(html, "https://docs.test/product-schema")
        self.assertFalse(htmlx.looks_product(doc))
        self.assertFalse(meta["is_product"])
        self.assertEqual(set(), rules(report))

    def test_strong_open_graph_product_without_schema_is_flagged(self):
        html = '<meta property="og:type" content="product"><meta property="product:price:amount" content="39.00"><h1>Cap</h1>'
        _, report, meta = inspect(html)
        self.assertTrue(meta["is_product"])
        self.assertTrue(meta["is_merchant"])
        self.assertIn("schema.ecommerce.product.missing", rules(report))

    def test_stdlib_and_optional_parser_views_produce_same_merchant_rules(self):
        html = fixture("mismatch-product.html")
        docs = [htmlx._parse_stdlib(html, "https://shop.test/trail")]
        docs.append(htmlx.parse(html, "https://shop.test/trail"))
        observed = []
        for doc in docs:
            report = Report(doc.base_url, final_url=doc.base_url, fetched_status=200)
            meta = ecommerce.audit(doc, report, today=date(2026, 8, 21))
            observed.append((rules(report), meta["visible_facts"], meta["selected_product"]))
        self.assertEqual(observed[0], observed[1])

    def test_scan_json_contract_exposes_product_evidence(self):
        url = "https://shop.test/products/trail"
        response = http.Response(url, url, 200, {"content-type": "text/html"},
                                 fixture("complete-product.html"), 2)
        with mock.patch.object(scan_mod.http, "fetch", return_value=response):
            report = scan_mod.scan(url, only=["schema"], ctx={}, check_images=False)
        payload = json.loads(report.to_json())
        self.assertTrue(payload["meta"]["ecommerce"]["is_merchant"])
        self.assertEqual("TS-42", payload["meta"]["ecommerce"]["selected_product"])

    def test_existing_mcp_scan_surface_carries_ecommerce_contract(self):
        url = "https://shop.test/products/trail"
        response = http.Response(url, url, 200, {"content-type": "text/html"},
                                 fixture("complete-product.html"), 2)
        with mock.patch.object(scan_mod.http, "fetch", return_value=response):
            payload = mcp_server._scan(url, only="schema")
        self.assertTrue(payload["meta"]["ecommerce"]["is_merchant"])
        self.assertEqual("TS-42", payload["meta"]["ecommerce"]["selected_product"])

    def test_crawl_scope_only_enables_store_specialist_for_merchant_pages(self):
        scope = crawl_site.summarize_ecommerce([
            {"url": "https://review.test/camera", "is_product": True, "is_merchant": False},
            {"url": "https://shop.test/shoe", "is_product": True, "is_merchant": True},
            {"url": "https://shop.test/about", "is_product": False, "is_merchant": False},
        ])
        self.assertTrue(scope["detected"])
        self.assertEqual(["https://shop.test/shoe"], scope["merchant_pages"])
        editorial = crawl_site.summarize_ecommerce([
            {"url": "https://review.test/camera", "is_product": True, "is_merchant": False}])
        self.assertFalse(editorial["detected"])


class TestMerchantSchema(unittest.TestCase):
    def test_complete_product_has_no_ecommerce_problem(self):
        _, report, meta = inspect(fixture("complete-product.html"))
        problems = [f for f in report.findings if f.severity != "good"]
        self.assertEqual([], problems)
        self.assertEqual(["offer"], meta["schema_offer_types"])

    def test_missing_product_and_offer_fields_are_precise(self):
        data = {"@context": "https://schema.org", "@type": "Product",
                "name": "Sparse", "offers": {"@type": "Offer", "price": "10"}}
        _, report, _ = inspect('<h1>Sparse</h1><script type="application/ld+json">' + json.dumps(data) + '</script>')
        got = rules(report)
        for expected in (
            "schema.ecommerce.product.missing.image",
            "schema.ecommerce.product.missing.description",
            "schema.ecommerce.product.missing.brand",
            "schema.ecommerce.product.missing.url",
            "schema.ecommerce.product.missing.sku.gtin.mpn",
            "schema.ecommerce.offer.missing.pricecurrency",
            "schema.ecommerce.offer.missing.availability",
            "schema.ecommerce.offer.missing.url",
            "schema.ecommerce.offer.missing.itemcondition",
            "schema.ecommerce.offer.missing.seller",
        ):
            self.assertIn(expected, got)

    def test_aggregate_offer_reference_and_variant_range(self):
        _, report, meta = inspect(fixture("aggregate-product.html"))
        problems = [f for f in report.findings if f.severity != "good"]
        self.assertEqual([], problems)
        self.assertEqual(["aggregateoffer"], meta["schema_offer_types"])

    def test_editorial_product_with_review_does_not_require_offer(self):
        data = {"@type": "Product", "name": "Reviewed Camera",
                "image": "camera.jpg", "description": "Hands-on review",
                "brand": "Optic", "mpn": "O-1", "url": "https://review.test/camera",
                "review": {"@type": "Review", "reviewRating": {"ratingValue": "4"}}}
        _, report, meta = inspect('<article><h1>Reviewed Camera</h1></article><script type="application/ld+json">' + json.dumps(data) + '</script>', "https://review.test/camera")
        self.assertTrue(meta["is_product"])
        self.assertFalse(meta["is_merchant"])
        self.assertNotIn("schema.ecommerce.product.missing.offers", rules(report))

    def test_offer_price_specification_is_supported(self):
        html = fixture("complete-product.html").replace(
            '"price":"129.00","priceCurrency":"USD",',
            '"priceSpecification":{"@type":"UnitPriceSpecification","price":"129.00","priceCurrency":"USD"},')
        _, report, _ = inspect(html)
        self.assertNotIn("schema.ecommerce.offer.missing.price", rules(report))
        self.assertNotIn("schema.ecommerce.offer.missing.pricecurrency", rules(report))

    def test_visible_sku_selects_the_matching_product_variant(self):
        _, report, meta = inspect(fixture("variant-product.html"))
        self.assertEqual(2, meta["product_nodes_count"])
        self.assertEqual("BLUE-42", meta["selected_product"])
        self.assertNotIn("schema.ecommerce.price.mismatch", rules(report))
        self.assertNotIn("schema.ecommerce.sku.mismatch", rules(report))

    def test_repeated_variant_defect_scores_once(self):
        html = fixture("variant-product.html").replace('"brand":"Northstar",', '')
        _, report, _ = inspect(html)
        findings = [f for f in report.findings
                    if f.rule_id == "schema.ecommerce.product.missing.brand"]
        self.assertEqual(1, len(findings))
        self.assertIn("2 Product node", findings[0].detail)

    def test_invalid_gtin_url_currency_availability_and_condition_are_precise(self):
        html = fixture("complete-product.html") \
            .replace('"url":"https://shop.test/products/trail-shoe"', '"url":"/relative"', 1) \
            .replace('"sku":"TS-42"', '"gtin13":"123"') \
            .replace('"priceCurrency":"USD"', '"priceCurrency":"US"') \
            .replace('"availability":"https://schema.org/InStock"', '"availability":"maybe"') \
            .replace('"itemCondition":"https://schema.org/NewCondition"', '"itemCondition":"oldish"')
        _, report, _ = inspect(html)
        got = rules(report)
        self.assertTrue({"schema.ecommerce.product.invalid.url",
                         "schema.ecommerce.product.invalid.gtin",
                         "schema.ecommerce.offer.invalid.currency",
                         "schema.ecommerce.offer.invalid.availability",
                         "schema.ecommerce.offer.invalid.condition"}.issubset(got))

    def test_localized_decimal_price_matches_schema_decimal(self):
        html = fixture("complete-product.html").replace(
            'product:price:amount" content="129.00"',
            'product:price:amount" content="129,00"')
        _, report, _ = inspect(html)
        self.assertNotIn("schema.ecommerce.price.mismatch", rules(report))

    def test_visible_schema_mismatches_are_field_specific(self):
        _, report, _ = inspect(fixture("mismatch-product.html"))
        got = rules(report)
        for field in ("price", "currency", "availability", "sku", "brand"):
            self.assertIn(f"schema.ecommerce.{field}.mismatch", got)

    def test_visible_fact_missing_from_schema_is_not_called_a_mismatch(self):
        data = {"@type": "Product", "name": "Cap", "image": "cap.jpg",
                "description": "Cap", "brand": "Northstar", "sku": "C1",
                "url": "https://shop.test/cap", "review": {},
                "offers": {"@type": "Offer", "priceCurrency": "USD",
                           "availability": "https://schema.org/InStock",
                           "url": "https://shop.test/cap", "itemCondition": "New",
                           "seller": "Northstar"}}
        html = '<meta property="og:type" content="product"><meta property="product:price:amount" content="20"><h1>Cap</h1><script type="application/ld+json">' + json.dumps(data) + '</script>'
        _, report, _ = inspect(html)
        self.assertIn("schema.ecommerce.visible.price.missing", rules(report))
        self.assertNotIn("schema.ecommerce.price.mismatch", rules(report))

    def test_expired_offer_date_is_stale_data(self):
        html = fixture("complete-product.html").replace(
            '"seller":{"@type":"Organization","name":"Northstar"}',
            '"seller":{"@type":"Organization","name":"Northstar"},"priceValidUntil":"2025-01-01"')
        _, report, _ = inspect(html)
        self.assertIn("schema.ecommerce.offer.price.expired", rules(report))

    def test_malformed_jsonld_still_reports_syntax_and_missing_product_schema(self):
        html = '<meta property="og:type" content="product"><meta property="product:price:amount" content="20"><script type="application/ld+json">{"@type":"Product",}</script><h1>Cap</h1>'
        doc = htmlx.parse(html, "https://shop.test/cap")
        report = Report("https://shop.test/cap", final_url="https://shop.test/cap", fetched_status=200)
        audit_schema.audit(doc, None, report, {})
        self.assertIn("schema.invalid.json.ld", rules(report))
        self.assertIn("schema.ecommerce.product.missing", rules(report))


if __name__ == "__main__":
    unittest.main()
