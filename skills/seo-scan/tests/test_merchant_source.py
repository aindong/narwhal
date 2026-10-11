"""Source-only commerce evidence must not read inert or hidden examples."""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lib import ecommerce, htmlx, merchant_source
from lib.report import Report
try:
    from .test_ecommerce import fixture, inspect, rules
except ImportError:
    from test_ecommerce import fixture, inspect, rules

URL = "https://shop.test/products/trail-shoe"


def product_with_observation(markup):
    html = fixture("complete-product.html").replace('<meta property="product:price:amount" content="129.00">', '')
    return html.replace('<body>', '<body>' + markup)


class TestMerchantSource(unittest.TestCase):
    def test_inert_markup_never_supplies_price_observations(self):
        bad = '<meta itemprop="price" content="999.00">'
        for markup in ('<!--' + bad + '-->', '<template>' + bad + '</template>',
                       '<script>"' + bad + '"</script>', '<svg>' + bad + '</svg>',
                       '<pre>' + bad.replace('<', '&lt;').replace('>', '&gt;') + '</pre>'):
            with self.subTest(markup=markup):
                _, report, meta = inspect(product_with_observation(markup), URL)
                self.assertNotIn('price', meta['visible_facts'])
                self.assertNotIn('schema.ecommerce.price.mismatch', rules(report))

    def test_active_price_after_inert_example_is_still_compared(self):
        bad = '<template><meta itemprop="price" content="999.00"></template>'
        for value, mismatch in (("129.00", False), ("130.00", True)):
            _, report, meta = inspect(product_with_observation(bad + '<span itemprop="price">' + value + '</span>'), URL)
            self.assertEqual(value, meta['visible_facts']['price']['value'])
            self.assertEqual(mismatch, 'schema.ecommerce.price.mismatch' in rules(report))

    def test_inert_open_graph_cannot_classify_an_article_as_product(self):
        bad = '<meta property="og:type" content="product"><meta property="product:price:amount" content="999">'
        for wrapper in (lambda s: '<template>' + s + '</template>', lambda s: '<!--' + s + '-->',
                        lambda s: '<div hidden>' + s + '</div>'):
            doc, report, meta = inspect(wrapper(bad) + '<article><h1>Schema tutorial</h1></article>')
            self.assertFalse(htmlx.looks_product(doc))
            self.assertFalse(meta['is_product'])
            self.assertFalse(meta['is_merchant'])
            self.assertEqual(set(), rules(report))

    def test_first_active_open_graph_type_keeps_preference_order(self):
        html = '<template><meta property="og:type" content="product"></template><meta property="og:type" content="article"><meta property="og:type" content="product"><meta property="product:price:amount" content="99"><h1>Review</h1>'
        doc, _, meta = inspect(html)
        self.assertFalse(htmlx.looks_product(doc))
        self.assertFalse(meta['is_product'])
        self.assertNotIn('og:type=product', meta['evidence'])

    def test_hidden_metadata_and_labels_cannot_override_active_values(self):
        html = '''<div hidden><h1>Wrong</h1><meta property="product:price:amount" content="999">
        <p>SKU: WRONG Brand: Wrong Availability: out of stock</p></div>
        <h1>Shoe</h1><meta property="product:price:amount" content="129.00"><p>SKU: TS-42</p>'''
        facts = ecommerce.visible_facts(htmlx.parse(html, URL))
        self.assertEqual('Shoe', facts['name']['value'])
        self.assertEqual('129.00', facts['price']['value'])
        self.assertEqual('TS-42', facts['sku']['value'])
        self.assertNotIn('brand', facts)
        self.assertNotIn('availability', facts)

    def test_nested_hidden_text_does_not_contaminate_an_itemprop_value(self):
        result = merchant_source.extract('<span itemprop="brand">Northstar<span hidden>Wrong</span></span>', URL)
        self.assertEqual('Northstar', result['itemprops']['brand'])

    def test_value_precedence_tokens_and_schema_namespace(self):
        html = '''<meta itemprop="price other" content="129.00"><data itemprop="priceCurrency" value="USD">Wrong</data>
        <span itemprop="https://schema.org/sku">TS-42</span><span itemprop="https://schema.org.evil.test/brand">Wrong</span>
        <span itemprop="brand" content="Wrong">Northstar</span><link itemprop="availability" href="https://schema.org/InStock">'''
        values = merchant_source.extract(html, URL)['itemprops']
        self.assertEqual({'price':'129.00', 'priceCurrency':'USD', 'sku':'TS-42', 'brand':'Northstar',
                          'availability':'https://schema.org/InStock'}, values)

    def test_nested_attribute_is_not_the_parent_property_value(self):
        html = '<span itemprop="sku"><span data-note="keep" content="WRONG">TS-42</span></span>'
        self.assertEqual('TS-42', merchant_source.extract(html, URL)['itemprops']['sku'])

    def test_linked_brand_name_is_visible_label_not_resource_url(self):
        html = '<a itemprop="brand" href="/brands/northstar">Northstar</a>'
        self.assertEqual('Northstar', merchant_source.extract(html, URL)['itemprops']['brand'])

    def test_html_head_labels_do_not_supply_body_facts(self):
        html = '<html><head><title>SKU: WRONG</title><meta property="product:price:amount" content="129"></head><body><p>SKU: TS-42</p></body></html>'
        facts = ecommerce.visible_facts(htmlx.parse(html, URL))
        self.assertEqual('TS-42', facts['sku']['value'])
        self.assertEqual('129', facts['price']['value'])

    def test_shared_extraction_is_cached_across_consumers(self):
        doc = htmlx.parse(fixture('complete-product.html'), URL)
        with mock.patch.object(merchant_source, 'extract', wraps=merchant_source.extract) as extract:
            ecommerce.visible_facts(doc)
            htmlx.looks_product(doc)
            ecommerce.detect(doc)
            ecommerce._purchase_action(doc)
            self.assertEqual(1, extract.call_count)

    def test_limits_are_reported_in_scan_evidence_and_finding(self):
        doc = htmlx.parse(fixture('complete-product.html'), URL)
        with mock.patch.object(merchant_source, 'MAX_ELEMENTS', 2):
            report = Report(URL)
            meta = ecommerce.audit(doc, report)
        self.assertTrue(any('partial' in w for w in meta['source_warnings']))
        self.assertIn('schema.ecommerce.source.extraction', rules(report))
        json.loads(report.to_json())

    def test_excessive_nesting_does_not_crash(self):
        result = merchant_source.extract('<div>' * 300 + '<meta itemprop="price" content="1">', URL)
        self.assertTrue(result['warnings'])

    def test_invalid_url_warning_fanout_is_bounded(self):
        html = ''.join('<a itemprop="availability" href="http://[bad%d">Stock</a>' % i for i in range(50))
        with mock.patch.object(merchant_source, 'MAX_WARNINGS', 2):
            result = merchant_source.extract(html, URL)
        self.assertEqual(3, len(result['warnings']))
        self.assertIn('warning limit', result['warnings'][-1])
        self.assertEqual({}, result['itemprops'])

    def test_programmatic_doc_metadata_contract_is_preserved(self):
        doc = htmlx.Doc(URL, meta=[htmlx.Tag('meta', {'property':'product:price:amount', 'content':'129'})],
                        headings=[(1,'Shoe')])
        self.assertEqual('129', ecommerce.visible_facts(doc)['price']['value'])
        self.assertEqual('Shoe', ecommerce.visible_facts(doc)['name']['value'])

    def test_parser_backends_share_source_values_and_inert_exclusions(self):
        html = product_with_observation('<template><meta itemprop="price" content="999"></template><data itemprop="price" value="129.00">129</data>')
        docs = [htmlx._parse_stdlib(html, URL), htmlx.parse(html, URL)]
        self.assertEqual(docs[0].merchant_markup, docs[1].merchant_markup)
        self.assertEqual(ecommerce.visible_facts(docs[0]), ecommerce.visible_facts(docs[1]))


if __name__ == '__main__':
    unittest.main()
