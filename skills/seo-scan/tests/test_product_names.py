"""Product H1 comparisons cannot borrow names from sale/seller Offers."""

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
MISMATCH = "schema.ecommerce.name.mismatch"


def page(name="Trail Shoe", offer_name="Online exclusive offer", price="129.00"):
    html = fixture("complete-product.html")
    blob = htmlx._parse_stdlib(html, URL).scripts_ld[0]
    data = json.loads(blob)
    if name is None:
        data.pop("name")
    else:
        data["name"] = name
    data["offers"]["name"] = offer_name
    return html.replace(blob, json.dumps(data)).replace('content="129.00"', 'content="' + price + '"')


class TestProductNames(unittest.TestCase):
    def test_offer_label_does_not_override_matching_product_name(self):
        _, report, meta = inspect(page(), URL)
        self.assertNotIn(MISMATCH, rules(report))
        self.assertEqual("TS-42", meta["selected_product"])
        self.assertEqual(("Trail Shoe", "Product.name"), ecommerce._schema_fact({"@type": "Product", "name": "Trail Shoe"}, [{"name": "Sale"}], "name"))

    def test_matching_offer_label_cannot_mask_true_product_name_mismatch(self):
        _, report, _ = inspect(page("Completely different item", "Trail Shoe"), URL)
        finding = next(f for f in report.findings if f.rule_id == MISMATCH)
        self.assertEqual("medium", finding.severity)
        self.assertIn("Product.name", finding.detail)
        self.assertIn("Completely different item", finding.detail)
        self.assertIn("Visible and schema name do not match", report.to_html())

    def test_offer_label_cannot_fill_a_missing_product_name(self):
        _, report, _ = inspect(page(None, "Trail Shoe"), URL)
        self.assertIn("schema.ecommerce.product.missing.name", rules(report))
        self.assertIn("schema.ecommerce.visible.name.missing", rules(report))
        self.assertNotIn(MISMATCH, rules(report))

    def test_offer_order_does_not_affect_product_name_comparison(self):
        html = page()
        blob = htmlx._parse_stdlib(html, URL).scripts_ld[0]
        data = json.loads(blob)
        offers = [data['offers'], dict(data['offers'], name='Trail Shoe')]
        results = []
        for values in (offers, list(reversed(offers))):
            data['offers'] = values
            _, report, meta = inspect(html.replace(blob, json.dumps(data)), URL)
            self.assertNotIn(MISMATCH, rules(report))
            results.append((rules(report), report.score(), meta))
        self.assertEqual(results[0], results[1])

    def test_true_price_mismatch_is_not_suppressed_by_name_ownership(self):
        _, report, _ = inspect(page(price="130.00"), URL)
        self.assertNotIn(MISMATCH, rules(report))
        self.assertIn("schema.ecommerce.price.mismatch", rules(report))

    def test_non_name_fact_precedence_is_not_silently_changed(self):
        product = {'@type': 'Product', 'sku': 'Manufacturer-ID', 'brand': 'Product brand'}
        offer = {'@type': 'Offer', 'sku': 'Retailer-ID', 'brand': 'Offer brand'}
        self.assertEqual(('Retailer-ID', 'Offer.sku'), ecommerce._schema_fact(product, [offer], 'sku'))
        self.assertEqual(('Offer brand', 'Offer.brand'), ecommerce._schema_fact(product, [offer], 'brand'))

    def test_uniquely_selected_variant_uses_its_product_name(self):
        html = page()
        blob = htmlx._parse_stdlib(html, URL).scripts_ld[0]
        product = json.loads(blob)
        other = dict(product, name='Other variant', sku='OTHER-42')
        _, report, meta = inspect(html.replace(blob, json.dumps([other, product])), URL)
        self.assertEqual('visible_identifier', meta['selection_method'])
        self.assertEqual('TS-42', meta['selected_product'])
        self.assertNotIn(MISMATCH, rules(report))

    def test_named_local_aggregate_offer_does_not_supply_product_name(self):
        html = fixture("aggregate-product.html")
        blob = htmlx._parse_stdlib(html, URL).scripts_ld[0]
        data = json.loads(blob)
        data['@graph'][1]['name'] = 'Three store offers'
        _, report, meta = inspect(html.replace(blob, json.dumps(data)), URL)
        self.assertNotIn(MISMATCH, rules(report))
        self.assertTrue(meta['aggregate_price_comparison']['within_range'])

    def test_all_three_formats_and_backends_keep_product_name_ownership(self):
        pages = [page()]
        for name, attr, type_attr in (("microdata-product.html", "itemprop", 'itemscope itemtype="https://schema.org/Offer"'), ("rdfa-product.html", "property", 'typeof="Offer"')):
            html = fixture(name).replace(type_attr + '>', type_attr + '><meta ' + attr + '="name" content="Online exclusive offer">')
            pages.append(html)
        for html in pages:
            results = []
            for doc in (htmlx._parse_stdlib(html, URL), htmlx.parse(html, URL)):
                report = Report(URL)
                meta = ecommerce.audit(doc, report)
                self.assertNotIn(MISMATCH, rules(report))
                self.assertTrue(any(n.get('name') == 'Online exclusive offer' for n in ecommerce.schema_nodes(doc)))
                results.append((rules(report), meta))
            self.assertEqual(results[0], results[1])

    def test_scan_json_finding_evidence_names_the_product_not_the_offer(self):
        response = http.Response(URL, URL, 200, {"content-type": "text/html"}, page("Different item", "Trail Shoe"), 1)
        with mock.patch.object(scan.http, 'fetch', return_value=response):
            payload = json.loads(scan.scan(URL, only=['schema'], ctx={}, check_images=False).to_json())
        finding = next(f for f in payload['findings'] if f['rule_id'] == MISMATCH)
        self.assertIn('Product.name', finding['detail'])
        self.assertIn('Different item', finding['evidence'])


if __name__ == '__main__':
    unittest.main()
