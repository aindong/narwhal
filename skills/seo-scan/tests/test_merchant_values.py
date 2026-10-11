"""Malformed Offer container shapes remain observable without crashing."""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import scan
from lib import htmlx, http
try:
    from .test_ecommerce import fixture, inspect, rules
except ImportError:
    from test_ecommerce import fixture, inspect, rules

URL = "https://shop.test/products/trail-shoe"
SPEC_NOTE = "schema.ecommerce.offer.price_specification.extraction"
REF_ERROR = "schema.ecommerce.offer.invalid.reference"


def product():
    return json.loads(htmlx._parse_stdlib(fixture("complete-product.html"), URL).scripts_ld[0])


def page(data):
    html = fixture("complete-product.html")
    blob = htmlx._parse_stdlib(html, URL).scripts_ld[0]
    return html.replace(blob, json.dumps(data))


class TestMerchantValues(unittest.TestCase):
    def test_nonstring_offer_references_do_not_crash_hash_lookup(self):
        for value in ({"value": "#offer"}, ["#one", "#two"], 42, True):
            with self.subTest(value=value):
                p = product()
                p["offers"] = {"@id": value}
                _, report, meta = inspect(page(p), URL)
                self.assertIn(REF_ERROR, rules(report))
                self.assertIn("schema.ecommerce.offer.missing.price", rules(report))
                self.assertTrue(meta["is_merchant"])
                json.loads(report.to_json())

    def test_supported_local_offer_reference_still_resolves(self):
        p = product()
        offer = p["offers"]
        offer["@id"] = "#offer"
        p["offers"] = {"@id": "#offer"}
        _, report, meta = inspect(page({"@context": "https://schema.org", "@graph": [p, offer]}), URL)
        self.assertNotIn(REF_ERROR, rules(report))
        self.assertNotIn("schema.ecommerce.offer.missing.price", rules(report))
        self.assertNotIn("schema.ecommerce.price.mismatch", rules(report))
        self.assertEqual(["offer"], meta["schema_offer_types"])

    def test_malformed_specification_members_become_coverage_notes(self):
        for value in ([1, "bad", None], [True, ["nested", "list"]], 42, "#price"):
            with self.subTest(value=value):
                p = product()
                del p["offers"]["price"]
                p["offers"]["priceSpecification"] = value
                _, report, _ = inspect(page(p), URL)
                self.assertIn(SPEC_NOTE, rules(report))
                self.assertIn("schema.ecommerce.offer.missing.price", rules(report))
                note = next(f for f in report.findings if f.rule_id == SPEC_NOTE)
                self.assertEqual("low", note.severity)
                self.assertIn("bounded parser", note.detail)
                json.loads(report.to_json())

    def test_supported_members_survive_mixed_specification_array(self):
        for values in ([1, {"price": "129.00", "priceCurrency": "USD"}],
                       [{"price": "129.00", "priceCurrency": "USD"}, "bad"]):
            p = product()
            del p["offers"]["price"]
            del p["offers"]["priceCurrency"]
            p["offers"]["priceSpecification"] = values
            _, report, _ = inspect(page(p), URL)
            self.assertIn(SPEC_NOTE, rules(report))
            self.assertNotIn("schema.ecommerce.offer.missing.price", rules(report))
            self.assertNotIn("schema.ecommerce.offer.missing.pricecurrency", rules(report))
            self.assertNotIn("schema.ecommerce.price.mismatch", rules(report))

    def test_supported_specification_forms_and_null_members_remain_clean(self):
        spec = {"@type": "UnitPriceSpecification", "price": "129.00", "priceCurrency": "USD"}
        for value in (spec, [spec], [None, spec]):
            p = product()
            del p["offers"]["price"]
            del p["offers"]["priceCurrency"]
            p["offers"]["priceSpecification"] = value
            _, report, _ = inspect(page(p), URL)
            self.assertNotIn(SPEC_NOTE, rules(report))
            self.assertNotIn("schema.ecommerce.offer.missing.price", rules(report))
            self.assertNotIn("schema.ecommerce.offer.missing.pricecurrency", rules(report))
            self.assertNotIn("schema.ecommerce.price.mismatch", rules(report))

    def test_direct_offer_price_does_not_hide_partial_specification_coverage(self):
        p = product()
        p["offers"]["priceSpecification"] = [1, "bad"]
        _, report, _ = inspect(page(p), URL)
        self.assertIn(SPEC_NOTE, rules(report))
        self.assertNotIn("schema.ecommerce.offer.missing.price", rules(report))
        self.assertNotIn("schema.ecommerce.price.mismatch", rules(report))

    def test_mixed_specification_still_reports_real_supported_price_mismatch(self):
        p = product()
        del p["offers"]["price"]
        p["offers"]["priceSpecification"] = [1, {"price": "130.00"}]
        _, report, _ = inspect(page(p), URL)
        self.assertIn(SPEC_NOTE, rules(report))
        self.assertIn("schema.ecommerce.price.mismatch", rules(report))

    def test_scan_emits_json_instead_of_traceback_for_both_crash_shapes(self):
        for offer in ({"@id": {"value": "#offer"}},
                      dict(product()["offers"], price=None, priceSpecification=[1, "bad", None])):
            p = product()
            p["offers"] = offer
            html = page(p)
            response = http.Response(URL, URL, 200, {"content-type": "text/html"}, html, 1)
            with mock.patch.object(scan.http, "fetch", return_value=response):
                report = scan.scan(URL, only=["schema"], ctx={}, check_images=False)
            payload = json.loads(report.to_json())
            self.assertEqual(200, payload["status"])
            self.assertTrue(payload["meta"]["ecommerce"]["is_merchant"])
            self.assertTrue({SPEC_NOTE, REF_ERROR} & rules(report))


if __name__ == "__main__":
    unittest.main()
