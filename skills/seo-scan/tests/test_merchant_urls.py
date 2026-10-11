"""Untrusted Product/Offer URLs are findings, never parser crashes."""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import scan
from lib import ecommerce, htmlx, http
try:
    from .test_ecommerce import fixture, inspect, rules
except ImportError:
    from test_ecommerce import fixture, inspect, rules

URL = "https://shop.test/products/trail-shoe"


def with_url(value, owner):
    html = fixture("complete-product.html")
    blob = htmlx._parse_stdlib(html, URL).scripts_ld[0]
    product = json.loads(blob)
    (product if owner == "product" else product["offers"])["url"] = value
    return html.replace(blob, json.dumps(product))


class TestMerchantUrls(unittest.TestCase):
    def test_malformed_product_and_offer_urls_are_field_specific_findings(self):
        for owner in ("product", "offer"):
            with self.subTest(owner=owner):
                _, report, meta = inspect(with_url("http://[bad", owner), URL)
                self.assertIn("schema.ecommerce." + owner + ".invalid.url", rules(report))
                self.assertNotIn("schema.ecommerce." + ("offer" if owner == "product" else "product") + ".invalid.url", rules(report))
                self.assertTrue(meta["is_merchant"])
                self.assertIn("Product page merchant signals inspected", report.to_markdown())
                self.assertEqual(200, json.loads(report.to_json())["status"])

    def test_invalid_authorities_ports_and_embedded_whitespace_are_rejected(self):
        for value in ("http://[bad", "https://[not-ipv6]/", "https://", "https://:443/path",
                      "https://user@/path", "https://shop.test:bad/path", "https://shop.test:99999/path",
                      "https://shop.test:-1/path", "https://shop.test/a b", "https://shop.test/a\tb",
                      "https://shop.test/a\x00b", "https://shop.test\\evil/path", "/relative", "javascript:alert(1)",
                      "https://shop.test\uff0fevil/path", "https://[127.0.0.1]/", "https://[v-not-future]/",
                      "https://prefix[2001:db8::1]/", "https://[2001:db8::1]suffix/", "https://[v1.{}]/"):
            with self.subTest(value=value):
                self.assertFalse(ecommerce._valid_url(value))
                for owner in ("product", "offer"):
                    _, report, _ = inspect(with_url(value, owner), URL)
                    self.assertIn("schema.ecommerce." + owner + ".invalid.url", rules(report))

    def test_valid_absolute_urls_remain_valid_without_network_checks(self):
        for value in ("http://shop.test/p", "https://shop.test:443/p", "https://shop.test:8443/p",
                      "https://[2001:db8::1]:443/p", "https://[fe80::1%25eth0]/p", "https://[v1.example]/p",
                      "https://127.0.0.1/p", "https://example.test/a%20b",
                      "https://shop.test/p?sku=TS-42#details", "https://m\u00fcnich.example/p"):
            with self.subTest(value=value):
                self.assertTrue(ecommerce._valid_url(value))
                for owner in ("product", "offer"):
                    _, report, _ = inspect(with_url(value, owner), URL)
                    self.assertNotIn("schema.ecommerce." + owner + ".invalid.url", rules(report))

    def test_programmatic_value_shapes_keep_existing_contract(self):
        self.assertTrue(ecommerce._valid_url({"@id": URL}))
        self.assertTrue(ecommerce._valid_url([URL]))
        self.assertFalse(ecommerce._valid_url({"@id": "http://[bad"}))
        self.assertFalse(ecommerce._valid_url(["http://[bad"]))

    def test_scan_returns_serializable_report_with_both_bad_urls(self):
        html = with_url("http://[bad", "product").replace('"url": "' + URL + '"', '"url": "https://shop.test:bad/p"')
        response = http.Response(URL, URL, 200, {"content-type": "text/html"}, html, 1)
        with mock.patch.object(scan.http, "fetch", return_value=response):
            report = scan.scan(URL, only=["schema"], ctx={}, check_images=False)
        self.assertTrue({"schema.ecommerce.product.invalid.url", "schema.ecommerce.offer.invalid.url"}.issubset(rules(report)))
        self.assertTrue(report.meta["ecommerce"]["is_merchant"])
        self.assertEqual(200, json.loads(report.to_json())["status"])


if __name__ == "__main__":
    unittest.main()
