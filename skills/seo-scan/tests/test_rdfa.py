"""Bounded schema.org RDFa extraction and shared mixed-format auditing."""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import compare
import scan
from lib import ecommerce, htmlx, http, rdfa, structured_data
from test_microdata import URL, audit, fixture, problems, with_jsonld


class TestRdfaExtraction(unittest.TestCase):
    def test_nested_entities_and_values(self):
        doc = htmlx.parse(fixture("rdfa-product.html"), URL)
        product = next(n for n in doc.rdfa if n.get("@type") == "Product")
        self.assertEqual("Trail Shoe", product["name"])
        self.assertEqual("Northstar", product["brand"]["name"])
        self.assertEqual("Northstar", product["offers"]["seller"]["name"])
        self.assertEqual("129.00", product["offers"]["price"])
        self.assertNotIn("price", product)
        self.assertEqual([], doc.rdfa_warnings)

    def test_prefix_and_scoped_rebinding(self):
        html = '''<div prefix="s: https://schema.org/" typeof="s:Product">
        <h1 property="s:name">Shoe</h1><div prefix="s: https://evil.test/">
        <span property="s:name">Not the shoe</span><div typeof="s:Product"></div></div>
        <span property="s:sku">P1</span></div>'''
        nodes, warnings = rdfa.extract(html, URL)
        self.assertEqual({"@type": "Product", "name": "Shoe", "sku": "P1"}, nodes[0])
        self.assertEqual([], warnings)

    def test_vocabulary_reset_and_foreign_scope(self):
        html = '''<div vocab="https://schema.org/" typeof="Product"><span property="name">Shoe</span>
        <div vocab=""><span property="name">Wrong</span></div>
        <div vocab="https://foreign.test/" typeof="Product"><span property="name">Wrong</span></div>
        <span property="sku">P1</span></div>'''
        self.assertEqual({"@type": "Product", "name": "Shoe", "sku": "P1"}, rdfa.extract(html, URL)[0][0])

    def test_predefined_prefix_full_uris_and_multiple_types(self):
        html = '''<div typeof="schema:Product https://schema.org/IndividualProduct">
        <span property="schema:name https://schema.org/description">Shoe</span></div>'''
        self.assertEqual({"@type": ["Product", "IndividualProduct"], "name": "Shoe", "description": "Shoe"},
                         rdfa.extract(html, URL)[0][0])

    def test_about_merges_local_subject_statements_and_forward_refs(self):
        html = '''<div vocab="https://schema.org/">
        <div about="#shoe" typeof="Product"><span property="name">Shoe</span>
        <link property="offers" resource="#offer"></div>
        <div about="#shoe"><span property="sku">P1</span></div>
        <div about="#offer" typeof="Offer"><meta property="price" content="10">
        <meta property="priceCurrency" content="USD"></div></div>'''
        nodes, warnings = rdfa.extract(html, URL)
        product = next(n for n in nodes if n.get("@type") == "Product")
        self.assertEqual("P1", product["sku"])
        self.assertEqual({"@id": URL + "#offer", "@type": "Offer", "price": "10", "priceCurrency": "USD"}, product["offers"])
        self.assertEqual([], warnings)

    def test_about_property_type_is_subject_not_a_nested_object(self):
        html = '<div vocab="https://schema.org/" typeof="Product"><span about="#brand" typeof="Brand" property="name">Northstar</span></div>'
        nodes, _ = rdfa.extract(html, URL)
        product = next(n for n in nodes if n.get("@type") == "Product")
        self.assertNotIn("name", product)
        self.assertIn({"@id": URL + "#brand", "@type": "Brand", "name": "Northstar"}, nodes)

    def test_base_resource_curie_and_url_values(self):
        html = '''<base href="https://cdn.test/store/"><div prefix="id: https://shop.test/id/" vocab="https://schema.org/" resource="[id:shoe]" typeof="Product">
        <a property="url" href="../shoe">View</a><img property="image" src="shoe.jpg">
        <link property="availability" resource="schema:InStock"></div>'''
        node = rdfa.extract(html, URL)[0][0]
        self.assertEqual("https://shop.test/id/shoe", node["@id"])
        self.assertEqual("https://cdn.test/shoe", node["url"])
        self.assertEqual("https://cdn.test/store/shoe.jpg", node["image"])
        self.assertEqual("http://schema.org/InStock", node["availability"])

    def test_scalar_iris_do_not_expand_into_self_references(self):
        html = '<div vocab="https://schema.org/" about="" typeof="Product"><a property="url" href="">Shoe</a></div>'
        self.assertEqual(URL, rdfa.extract(html, URL)[0][0]["url"])

    def test_image_objects_are_not_lost_when_normalizing_url_properties(self):
        for resource in ('', ' resource="#photo"'):
            html = '<div typeof="schema:Product"><div property="schema:image" typeof="schema:ImageObject"' + resource + '><link property="schema:url" href="/shoe.jpg"></div></div>'
            nodes, warnings = rdfa.extract(html, URL)
            self.assertEqual([], warnings)
            self.assertEqual("ImageObject", nodes[0]["image"]["@type"])
            self.assertEqual("https://shop.test/shoe.jpg", nodes[0]["image"]["url"])

    def test_literal_precedence_dates_repetition_and_datatype(self):
        html = '''<article vocab="http://schema.org/" typeof="Article">
        <span property="headline name" content="Real headline">Ignored</span>
        <time property="datePublished" datetime="2026-10-11">Today</time>
        <meta property="ratingValue" datatype="xsd:decimal" content="4.5">
        <a property="description" datatype="" href="/ignored">Plain text</a>
        <span property="keywords">SEO</span><span property="keywords">SEO</span><span property="keywords">GEO</span>
        </article>'''
        nodes, warnings = rdfa.extract(html, URL)
        self.assertEqual([], warnings)
        self.assertEqual("Real headline", nodes[0]["headline"])
        self.assertEqual("2026-10-11", nodes[0]["datePublished"])
        self.assertEqual("4.5", nodes[0]["ratingValue"])
        self.assertEqual(["SEO", "GEO"], nodes[0]["keywords"])
        self.assertIn({"@id": "https://shop.test/ignored", "description": "Plain text"}, nodes)

    def test_inert_and_escaped_examples_are_not_products(self):
        markup = '<div typeof="schema:Product"><span property="schema:name">Shoe</span></div>'
        for html in ('<!--' + markup + '-->', '<script>' + markup + '</script>',
                     '<template>' + markup + '</template>', '<svg>' + markup + '</svg>',
                     '<pre>' + markup.replace('<', '&lt;').replace('>', '&gt;') + '</pre>'):
            with self.subTest(html=html):
                doc = htmlx.parse(html, URL)
                self.assertFalse(htmlx.looks_product(doc))
                self.assertEqual([], doc.rdfa)

    def test_lookalike_unqualified_and_foreign_names_are_not_products(self):
        for typ in ('Product', 'evil:Product', 'https://schema.org.evil.test/Product', '[unknown:Product]'):
            html = '<div typeof="' + typ + '"><span property="schema:name">Not a product</span></div>'
            self.assertFalse(htmlx.looks_product(htmlx.parse(html, URL)))

    def test_unsupported_constructs_report_partial_coverage_without_leaking(self):
        for attrs in ('rel="offers"', 'property="offers" inlist',
                      'prefix="f: https://foreign.test/" rel="f:knows"',
                      'property="rdfa:copy" resource="#pattern"',
                      'property="description" datatype="rdf:XMLLiteral"',
                      'property="description" datatype="https://foreign.test/custom"'):
            html = '<div vocab="https://schema.org/" typeof="Product"><div ' + attrs + '><span property="name">Wrong entity</span></div></div>'
            nodes, warnings = rdfa.extract(html, URL)
            self.assertEqual({"@type": "Product"}, nodes[0])
            self.assertTrue(any("partial" in w for w in warnings))

    def test_invalid_urls_prefixes_and_safe_curies_warn(self):
        for markup in ('<a property="schema:url" href="http://[bad">Bad</a>',
                       '<span property="schema:name" prefix="schema: relative/">Bad</span>',
                       '<span property="schema:name" prefix="schema:">Bad</span>',
                       '<div about="[unknown:entity]" typeof="schema:Product"></div>'):
            _, warnings = rdfa.extract(markup, URL)
            self.assertTrue(warnings)

    def test_normal_html_rel_does_not_hide_schema_properties(self):
        html = '<div typeof="schema:Product"><a property="schema:url" href="/shoe" rel="nofollow noopener">View</a></div>'
        nodes, warnings = rdfa.extract(html, URL)
        self.assertEqual("https://shop.test/shoe", nodes[0]["url"])
        self.assertEqual([], warnings)

    def test_root_subject_and_unclosed_or_omitted_end_tags(self):
        nodes, _ = rdfa.extract('<html vocab="https://schema.org/" typeof="Product"><body><h1 property="name">Shoe</h1></body></html>', URL)
        self.assertEqual({"@id": URL, "@type": "Product", "name": "Shoe"}, nodes[0])
        html = '<ul vocab="https://schema.org/"><li typeof="Product"><p property="name">Red Shoe<li typeof="Product"><p property="name">Blue Shoe'
        nodes, _ = rdfa.extract(html, URL)
        self.assertEqual(["Red Shoe", "Blue Shoe"], [n["name"] for n in nodes])

    def test_cycles_and_depth_are_bounded_and_serializable(self):
        html = '''<div vocab="https://schema.org/"><div about="#p" typeof="Product"><link property="offers" resource="#o"></div>
        <div about="#o" typeof="Offer"><link property="itemOffered" resource="#p"></div></div>'''
        nodes, warnings = rdfa.extract(html, URL)
        json.dumps(nodes)
        self.assertTrue(any("cyclic" in w for w in warnings))
        with mock.patch.object(rdfa, "MAX_DEPTH", 1):
            _, warnings = rdfa.extract(fixture("rdfa-product.html"), URL)
        self.assertTrue(any("nested" in w for w in warnings))

    def test_node_property_and_html_limits_are_explicit(self):
        for name, cap in (("MAX_NODES", 2), ("MAX_PROPERTIES", 2), ("MAX_ELEMENTS", 2)):
            with self.subTest(limit=name), mock.patch.object(rdfa, name, cap):
                _, warnings = rdfa.extract(fixture("rdfa-product.html"), URL)
            self.assertTrue(any("limit" in w for w in warnings))
        _, warnings = rdfa.extract('<div typeof="schema:Product">' + '<div>' * 300, URL)
        self.assertTrue(any("HTML nesting" in w for w in warnings))


class TestRdfaAuditing(unittest.TestCase):
    def test_equivalent_formats_have_equivalent_findings(self):
        _, baseline = audit(fixture("complete-product.html"))
        doc, report = audit(fixture("rdfa-product.html"))
        self.assertEqual(problems(baseline), problems(report))
        self.assertTrue(htmlx.looks_product(doc))
        self.assertEqual(1, report.meta["ecommerce"]["product_nodes_count"])
        self.assertIn("Product RDFa", report.meta["ecommerce"]["evidence"])
        self.assertEqual(["rdfa"], report.meta["structured_data"]["formats"])
        self.assertTrue(report.meta["structured_data"]["rdfa_supported"])
        self.assertIn("not a full", report.meta["structured_data"]["rdfa_scope"])

    def test_all_three_formats_deduplicate_without_losing_provenance(self):
        html = fixture("rdfa-product.html")
        micro_body = fixture("microdata-product.html").split('<body>')[1].split('</body>')[0]
        html = with_jsonld(html.replace('</body>', micro_body + '</body>'))
        doc, report = audit(html)
        self.assertEqual(1, report.meta["ecommerce"]["product_nodes_count"])
        self.assertEqual(["jsonld", "microdata", "rdfa"], report.meta["structured_data"]["formats"])
        records, _ = structured_data.collect(doc)
        product = next(r for r in records if r["node"].get("@type") == "Product")
        self.assertEqual(["jsonld", "microdata", "rdfa"], product["formats"])

    def test_conflicting_prices_preserved(self):
        doc, report = audit(with_jsonld(fixture("rdfa-product.html").replace('content="129.00"', 'content="130.00"')))
        prices = {n["offers"]["price"] for n in ecommerce.schema_nodes(doc) if n.get("@type") == "Product"}
        self.assertEqual({"129.00", "130.00"}, prices)
        self.assertEqual(2, report.meta["ecommerce"]["product_nodes_count"])

    def test_missing_currency_and_visible_mismatch_use_existing_rules(self):
        _, report = audit(fixture("rdfa-product.html").replace('<meta property="priceCurrency" content="USD">', ''))
        self.assertIn(("schema.ecommerce.offer.missing.pricecurrency", "high"), problems(report))
        _, report = audit(fixture("rdfa-product.html").replace('property="price" content="129.00"', 'property="price" content="130.00"'))
        self.assertIn(("schema.ecommerce.price.mismatch", "high"), problems(report))

    def test_article_with_price_is_not_a_merchant(self):
        html = '''<article vocab="https://schema.org/" typeof="Article"><h1 property="headline">Shoe guide</h1>
        <span property="author">Jane</span><time property="datePublished" datetime="2026-10-11">Today</time>
        <img property="image" src="/a.jpg"><p>A shoe costs $99.</p></article>'''
        doc, report = audit(html)
        self.assertFalse(htmlx.looks_product(doc))
        self.assertFalse(report.meta["ecommerce"]["is_product"])
        self.assertNotIn("schema.no.structured.data", {f.rule_id for f in report.findings})

    def test_partial_extraction_warning_has_stable_rule(self):
        _, report = audit('<div vocab="https://schema.org/" typeof="Product"><div rel="offers"></div></div>')
        self.assertIn(("schema.rdfa.extraction", "low"), problems(report))

    def test_stale_offer_variant_group_and_nested_price_specification(self):
        html = fixture("rdfa-product.html").replace('<meta property="priceCurrency"', '<time property="priceValidUntil" datetime="2000-01-01">Expired</time><meta property="priceCurrency"')
        _, report = audit(html)
        self.assertIn(("schema.ecommerce.offer.price.expired", "high"), problems(report))
        html = fixture("rdfa-product.html").replace('<main vocab="https://schema.org/" typeof="Product">', '<main vocab="https://schema.org/" typeof="ProductGroup"><div property="hasVariant" typeof="Product">').replace('</main>', '</div></main>')
        html = html.replace('<meta property="price" content="129.00"><meta property="priceCurrency" content="USD">', '<div property="priceSpecification" typeof="UnitPriceSpecification"><meta property="price" content="129.00"><meta property="priceCurrency" content="USD"></div>')
        _, report = audit(html)
        self.assertEqual(1, report.meta["ecommerce"]["product_nodes_count"])
        self.assertNotIn(("schema.ecommerce.offer.missing.price", "high"), problems(report))
        self.assertNotIn(("schema.ecommerce.offer.missing.pricecurrency", "high"), problems(report))

    def test_scan_json_exposes_rdfa_provenance_and_coverage(self):
        response = http.Response(URL, URL, 200, {"content-type": "text/html"}, fixture("rdfa-product.html"), 1)
        with mock.patch.object(scan.http, "fetch", return_value=response):
            report = scan.scan(URL, only=["schema"], ctx={}, check_images=False)
        payload = json.loads(report.to_json())
        self.assertEqual(["rdfa"], payload["meta"]["structured_data"]["formats"])
        self.assertEqual([], payload["meta"]["structured_data"]["rdfa_warnings"])
        self.assertTrue(payload["meta"]["ecommerce"]["is_merchant"])

    def test_shared_resource_dag_does_not_expand_exponentially(self):
        html = '<div vocab="https://schema.org/">' + ''.join(
            '<div about="#n{0}" typeof="Thing"><link property="related1 related2" resource="#n{1}"></div>'.format(i, i + 1)
            for i in range(26))
        html += '<div about="#n26" typeof="Product"><span property="name">Shoe</span></div></div>'
        doc = htmlx.parse(html, URL)
        records, errors = structured_data.collect(doc)
        self.assertEqual([], errors)
        self.assertEqual(27, len(records))
        self.assertTrue(htmlx.looks_product(doc))

    def test_parser_backends_and_comparison_use_same_view(self):
        html = fixture("rdfa-product.html")
        stdlib = htmlx._parse_stdlib(html, URL)
        self.assertEqual(["AggregateRating", "Brand", "Offer", "Organization", "Product"], compare._schema_types(stdlib))
        try:
            optional = htmlx._parse_bs4(html, URL)
        except ImportError:
            self.skipTest("BeautifulSoup not installed")
        self.assertEqual(stdlib.rdfa, optional.rdfa)
        self.assertEqual(stdlib.rdfa_warnings, optional.rdfa_warnings)


if __name__ == "__main__":
    unittest.main()
