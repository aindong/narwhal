"""JSON-LD value objects and their JSON payloads are not entity nodes."""

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import scan
from lib import ecommerce, htmlx, http, structured_data
from lib.report import Report

URL = "https://example.test/tutorial"
EXAMPLE = {"@type": "Product", "name": "Example",
           "offers": {"@type": "Offer", "price": "129", "priceCurrency": "USD"}}


def article(value):
    return {"@context": "https://schema.org", "@type": "Article",
            "headline": "Tutorial", "additionalProperty": value}


def doc(raw):
    return htmlx.Doc(URL, scripts_ld=[json.dumps(raw)])


class TestJSONLDLiterals(unittest.TestCase):
    def test_json_example_is_not_product_or_merchant(self):
        raw = article({"@type": "@json", "@value": EXAMPLE})
        records, errors = structured_data.collect(doc(raw))
        self.assertEqual([], errors)
        self.assertEqual(["Article"], [r["node"].get("@type") for r in records])
        meta = ecommerce.audit(doc(raw), Report(URL))
        self.assertFalse(meta["is_product"]); self.assertFalse(meta["is_merchant"])
        self.assertFalse(htmlx.looks_product(doc(raw)))

    def test_context_definition_is_not_product_evidence(self):
        raw = article("Example")
        raw["@context"] = {"example": {"@type": "https://schema.org/Product"}}
        self.assertFalse(htmlx.looks_product(doc(raw)))
        self.assertFalse(ecommerce.audit(doc(raw), Report(URL))["is_product"])

    def test_array_and_nested_graph_literals_do_not_promote_entities(self):
        for value in ([EXAMPLE], {"@graph": [EXAMPLE]},
                      {"example": {"@value": EXAMPLE, "@type": "@json"}}):
            records, _ = structured_data.collect(doc(article({"@value": value, "@type": "@json"})))
            self.assertEqual(["Article"], [r["node"].get("@type") for r in records])

    def test_datatypes_are_not_reported_as_entity_types(self):
        values = [{"@value": "129", "@type": "https://schema.org/Number"},
                  {"@value": "2026-10-12", "@type": "http://www.w3.org/2001/XMLSchema#date"},
                  {"@value": "Product", "@language": "en"}, {"@value": None}]
        parsed = doc(article(values)); records, _ = structured_data.collect(parsed)
        meta = structured_data.provenance(parsed, records)
        self.assertEqual({"jsonld": ["Article"]}, meta["types_by_format"])
        self.assertEqual(1, meta["nodes_count"])
        for value in values:
            self.assertEqual([], structured_data.types(value))
            self.assertEqual([], ecommerce._types(value))

    def test_literal_only_block_has_no_entity_records(self):
        records, errors = structured_data.collect(doc({"@value": EXAMPLE, "@type": "@json"}))
        self.assertEqual([], records); self.assertEqual([], errors)

    def test_independent_page_facts_remain_active_despite_literal_examples(self):
        html = '<meta property="og:type" content="product"><meta property="product:price:amount" content="129"><script type="application/ld+json">' + json.dumps(article({"@value": EXAMPLE, "@type": "@json"})) + '</script>'
        parsed = htmlx.parse(html, URL); report = Report(URL)
        meta = ecommerce.audit(parsed, report)
        self.assertTrue(meta["is_product"]); self.assertTrue(meta["is_merchant"])
        self.assertIn("schema.ecommerce.product.missing", {f.rule_id for f in report.findings})

    def test_real_graph_and_list_entities_remain_visible(self):
        raw = {"@graph": [article({"@value": EXAMPLE, "@type": "@json"}),
                          {"@list": [EXAMPLE]}]}
        records, _ = structured_data.collect(doc(raw))
        found = [t for r in records for t in structured_data.types(r["node"])]
        self.assertEqual(["Article", "Product", "Offer"], found)
        meta = ecommerce.audit(doc(raw), Report(URL))
        self.assertTrue(meta["is_product"]); self.assertTrue(meta["is_merchant"])
        self.assertEqual(1, meta["product_nodes_count"])

    def test_value_payload_and_datatype_are_preserved_without_mutation(self):
        value = {"@value": {"@context": {"price": "example:price"},
                            "@type": ["https://schema.org/Product"],
                            "example": [EXAMPLE]}, "@type": "@json"}
        raw = article(value); before = copy.deepcopy(raw)
        normalized = structured_data._normalize(raw)
        self.assertEqual(before, raw)
        self.assertEqual(value, normalized["additionalProperty"])
        self.assertIsNot(value, normalized["additionalProperty"])

    def test_literal_data_does_not_use_schema_numeric_or_url_equivalence(self):
        payloads = [{"price": "129.00"}, {"price": 129},
                    {"availability": "http://schema.org/InStock"},
                    {"availability": "https://schema.org/InStock"},
                    {"example": [EXAMPLE]}, {"example": EXAMPLE}]
        raw = [article({"@value": value, "@type": "@json"}) for value in payloads]
        records, _ = structured_data.collect(doc(raw))
        self.assertEqual(len(payloads), len(records))

    def test_equal_literal_data_deduplicates_despite_dictionary_key_order(self):
        first = article({"@value": {"one": 1, "two": 2}, "@type": "@json"})
        second = article({"@type": "@json", "@value": {"two": 2, "one": 1}})
        records, _ = structured_data.collect(doc([first, second]))
        self.assertEqual(1, len(records))

    def test_literal_json_decimal_tokens_keep_number_string_distinction(self):
        raw = [article({"@value": {"price": value}, "@type": "@json"})
               for value in ('0.100000000000000005', '0.100000000000000006')]
        blob = json.dumps(raw)
        unquoted = blob.replace('"price": "0.100000000000000005"', '"price": 0.100000000000000005')
        unquoted = unquoted.replace('"price": "0.100000000000000006"', '"price": 0.100000000000000006')
        parsed = htmlx.Doc(URL, scripts_ld=[blob, unquoted])
        records, errors = structured_data.collect(parsed)
        self.assertEqual([], errors)
        self.assertEqual(4, len(records))
        self.assertEqual({"0.100000000000000005", "0.100000000000000006"},
                         {str(r["node"]["additionalProperty"]["@value"]["price"]) for r in records})

    def test_literal_offer_is_not_merchant_evidence(self):
        literal = {"@value": {"@type": "Offer", "price": "129"}, "@type": "@json"}
        for offers in (literal, [literal]):
            raw = dict(EXAMPLE, offers=offers)
            report = Report(URL); meta = ecommerce.audit(doc(raw), report)
            self.assertTrue(meta["is_product"]); self.assertFalse(meta["is_merchant"])
            self.assertEqual([], meta["schema_offer_types"])
            self.assertFalse(any(f.rule_id.startswith("schema.ecommerce.offer.") for f in report.findings))
        raw = dict(EXAMPLE, offers=[literal, EXAMPLE["offers"]])
        meta = ecommerce.audit(doc(raw), Report(URL))
        self.assertTrue(meta["is_merchant"])
        self.assertEqual(["offer"], meta["schema_offer_types"])

    def test_full_scan_and_parser_backends_keep_literal_example_out_of_json(self):
        raw = article({"@value": EXAMPLE, "@type": "@json"})
        html = '<html><head><title>Tutorial</title><script type="application/ld+json">' + json.dumps(raw) + '</script></head><body><h1>Tutorial</h1></body></html>'
        for parsed in (htmlx._parse_stdlib(html, URL), htmlx.parse(html, URL)):
            records, _ = structured_data.collect(parsed)
            self.assertEqual(["Article"], [r["node"].get("@type") for r in records])
        response = http.Response(URL, URL, 200, {"content-type": "text/html"}, html, 1)
        with mock.patch.object(scan.http, "fetch", return_value=response):
            report = scan.scan(URL, only=["schema"], ctx={}, check_images=False)
        payload = json.loads(report.to_json())
        self.assertFalse(payload["meta"]["ecommerce"]["is_merchant"])
        self.assertEqual({"jsonld": ["Article"]}, payload["meta"]["structured_data"]["types_by_format"])
        self.assertFalse(any(f["rule_id"].startswith("schema.ecommerce.") for f in payload["findings"]))


if __name__ == "__main__":
    unittest.main()
