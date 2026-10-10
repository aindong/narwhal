"""Microdata extraction, shared schema checks and mixed-format contracts."""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audit_schema
import compare
import scan
from lib import ecommerce, htmlx, http, microdata, structured_data
from lib.report import Report

URL = "https://shop.test/products/trail-shoe"
FIXTURES = Path(__file__).parent / "fixtures" / "ecommerce"


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def audit(html):
    doc = htmlx.parse(html, URL)
    report = Report(URL, final_url=URL, fetched_status=200)
    audit_schema.audit(doc, http.Response(URL, URL, 200, {}, html, 1), report)
    return doc, report


def problems(report):
    return {(f.rule_id, f.severity) for f in report.findings if f.severity != "good"}


def with_jsonld(html, blobs=None):
    blobs = (htmlx._parse_stdlib(fixture("complete-product.html"), URL).scripts_ld
             if blobs is None else blobs)
    scripts = "".join('<script type="application/ld+json">' + blob + '</script>' for blob in blobs)
    return html.replace("</head>", scripts + "</head>")


class TestMicrodataExtraction(unittest.TestCase):
    def test_nested_scopes_do_not_leak_properties(self):
        doc = htmlx.parse(fixture("microdata-product.html"), URL)
        product = doc.microdata[0]
        self.assertEqual("Trail Shoe", product["name"])
        self.assertEqual("Northstar", product["brand"]["name"])
        self.assertEqual("Northstar", product["offers"]["seller"]["name"])
        self.assertNotIn("price", product)
        self.assertEqual([], doc.microdata_warnings)

    def test_values_repetition_and_multiple_names(self):
        html = '''<div itemscope itemtype="http://schema.org/Article" itemid="/a">
        <span itemprop="name headline">A <b>useful</b> article</span>
        <meta itemprop="keywords" content="SEO"><span itemprop="keywords">GEO</span>
        <time itemprop="datePublished" datetime="2026-10-11">Today</time>
        <data itemprop="identifier" value="001">one</data><meter itemprop="ratingValue" value="4.5">great</meter>
        <img itemprop="image" src="/image.jpg"><a itemprop="url" href="/a">Read</a></div>'''
        nodes, warnings = microdata.extract(html, URL)
        self.assertEqual([], warnings)
        self.assertEqual({"@type": "Article", "@id": "https://shop.test/a", "name": "A useful article",
                          "headline": "A useful article", "keywords": ["SEO", "GEO"],
                          "datePublished": "2026-10-11", "identifier": "001", "ratingValue": "4.5",
                          "image": "https://shop.test/image.jpg", "url": "https://shop.test/a"}, nodes[0])

    def test_base_url_and_url_value_elements(self):
        html = '''<base href="https://cdn.test/store/"><div itemscope itemtype="https://schema.org/Thing">
        <object itemprop="image" data="x.jpg"></object><video itemprop="video" src="v.mp4"></video>
        <a itemprop="url">no href</a><meta itemprop="name">no content</meta></div>'''
        node = microdata.extract(html, URL)[0][0]
        self.assertEqual("https://cdn.test/store/x.jpg", node["image"])
        self.assertEqual("https://cdn.test/store/v.mp4", node["video"])
        self.assertEqual("", node["url"])
        self.assertEqual("", node["name"])

    def test_itemref_is_local_and_ordered_without_duplicate_values(self):
        html = '''<span id="earlier" itemprop="name">First</span>
        <div itemscope itemtype="https://schema.org/Product" itemref="earlier later">
        <span itemprop="name">Second</span></div><span id="later" itemprop="sku">P1</span>'''
        nodes, warnings = microdata.extract(html, URL)
        self.assertEqual(["First", "Second"], nodes[0]["name"])
        self.assertEqual("P1", nodes[0]["sku"])
        self.assertEqual([], warnings)

    def test_cyclic_itemref_is_bounded_and_serializable(self):
        html = '''<div id="a" itemprop="itemOffered" itemscope itemtype="https://schema.org/Product" itemref="b"></div>
        <div id="b" itemprop="offers" itemscope itemtype="https://schema.org/Offer" itemref="a"></div>'''
        nodes, warnings = microdata.extract(html, URL)
        json.dumps(nodes)
        self.assertTrue(warnings)

    def test_missing_itemref_is_explicit_not_fetched(self):
        nodes, warnings = microdata.extract('<div itemscope itemtype="https://schema.org/Product" itemref="missing"></div>', URL)
        self.assertEqual([{"@type": "Product"}], nodes)
        self.assertIn("Microdata itemref target not found: missing", warnings)

    def test_inert_templates_comments_and_escaped_examples_are_not_products(self):
        for html in ('<!-- <div itemscope itemtype="https://schema.org/Product"> -->',
                     '<template><div itemscope itemtype="https://schema.org/Product"></div></template>',
                     '<script>"<div itemscope itemtype=\'https://schema.org/Product\'>"</script>',
                     '<pre>&lt;div itemscope itemtype="https://schema.org/Product"&gt;</pre>',
                     '<svg itemscope itemtype="https://schema.org/Product"></svg>'):
            with self.subTest(html=html):
                doc = htmlx.parse(html, URL)
                self.assertFalse(htmlx.looks_product(doc))
                self.assertEqual([], doc.microdata)

    def test_orphan_type_and_lookalike_namespace_are_not_products(self):
        for html in ('<div itemtype="https://schema.org/Product">Not a scope</div>',
                     '<div itemscope itemtype="https://schema.org.evil.test/Product"></div>',
                     '<div itemscope itemtype="Product"></div>'):
            self.assertFalse(htmlx.looks_product(htmlx.parse(html, URL)))

    def test_unclosed_markup_is_recovered_without_a_crash(self):
        nodes, _ = microdata.extract('<div itemscope itemtype="https://schema.org/Product"><span itemprop="name">Shoe', URL)
        self.assertEqual("Shoe", nodes[0]["name"])

    def test_valid_omitted_end_tags_do_not_bleed_into_sibling_items(self):
        html = '''<ul><li itemscope itemtype="https://schema.org/Product"><p itemprop="name">Red Shoe
        <p itemprop="description">Red description
        <li itemscope itemtype="https://schema.org/Product"><p itemprop="name">Blue Shoe
        <p itemprop="description">Blue description</ul>'''
        nodes, _ = microdata.extract(html, URL)
        self.assertEqual(["Red Shoe", "Blue Shoe"], [n["name"] for n in nodes])
        self.assertEqual(["Red description", "Blue description"], [n["description"] for n in nodes])
        html = '<dl itemscope itemtype="https://schema.org/Product"><dt>Name<dd itemprop="name">Shoe<dt>SKU<dd itemprop="sku">P1</dl>'
        nodes, _ = microdata.extract(html, URL)
        self.assertEqual("Shoe", nodes[0]["name"])
        self.assertEqual("P1", nodes[0]["sku"])

    def test_invalid_urls_warn_instead_of_crashing(self):
        html = '<div itemscope itemtype="https://schema.org/Product"><a itemprop="url" href="http://[bad">Product</a></div>'
        nodes, warnings = microdata.extract(html, URL)
        self.assertEqual("", nodes[0]["url"])
        self.assertTrue(any("could not be resolved" in w for w in warnings))

    def test_itemref_overlap_does_not_duplicate_a_property(self):
        html = '<div itemscope itemtype="https://schema.org/Product" itemref="name"><span id="name" itemprop="name">Shoe</span></div>'
        nodes, warnings = microdata.extract(html, URL)
        self.assertEqual("Shoe", nodes[0]["name"])
        self.assertTrue(warnings)

    def test_multitype_and_url_property_names_are_normalized(self):
        html = '<div itemscope itemtype="http://schema.org/Product https://schema.org/IndividualProduct"><span itemprop="https://schema.org/name">Shoe</span></div>'
        node = microdata.extract(html, URL)[0][0]
        self.assertEqual(["Product", "IndividualProduct"], node["@type"])
        self.assertEqual("Shoe", node["name"])

    def test_resource_limits_are_reported_as_partial_coverage(self):
        html = '<div itemscope itemtype="https://schema.org/Product"><span itemprop="name">Shoe</span></div>' * 3
        with mock.patch.object(microdata, "MAX_ITEMS", 2):
            nodes, warnings = microdata.extract(html, URL)
        self.assertEqual(2, len(nodes))
        self.assertTrue(any("partial" in w for w in warnings))
        with mock.patch.object(microdata, "MAX_ELEMENTS", 2):
            _, warnings = microdata.extract(html, URL)
        self.assertTrue(any("partial" in w for w in warnings))

    def test_nesting_limits_do_not_raise_recursion_errors(self):
        html = '<div itemscope itemtype="https://schema.org/Product">' + '<div>' * 300 + '</div>' * 301
        _, warnings = microdata.extract(html, URL)
        self.assertTrue(any("HTML nesting limit" in w for w in warnings))
        html = '<div itemscope itemtype="https://schema.org/Product"><div itemprop="offers" itemscope itemtype="https://schema.org/Offer"></div></div>'
        with mock.patch.object(microdata, "MAX_DEPTH", 1):
            _, warnings = microdata.extract(html, URL)
        self.assertTrue(any("nested item" in w for w in warnings))


class TestMicrodataAuditing(unittest.TestCase):
    def test_product_jsonld_and_microdata_have_equivalent_findings(self):
        _, json_report = audit(fixture("complete-product.html"))
        _, micro_report = audit(fixture("microdata-product.html"))
        self.assertEqual(problems(json_report), problems(micro_report))
        self.assertNotIn(("schema.ecommerce.product.missing", "high"), problems(micro_report))
        self.assertEqual(1, micro_report.meta["ecommerce"]["product_nodes_count"])
        self.assertEqual(["microdata"], micro_report.meta["structured_data"]["formats"])
        self.assertEqual(["Product microdata", "og:type=product", "explicit merchant facts: availability, currency, price, sku"],
                         micro_report.meta["ecommerce"]["evidence"])

    def test_mixed_equivalent_product_is_not_counted_twice(self):
        html = with_jsonld(fixture("microdata-product.html"))
        doc, report = audit(html)
        self.assertEqual(1, report.meta["ecommerce"]["product_nodes_count"])
        self.assertEqual(["jsonld", "microdata"], report.meta["structured_data"]["formats"])
        records, _ = structured_data.collect(doc)
        product = next(r for r in records if r["node"].get("@type") == "Product")
        self.assertEqual(["jsonld", "microdata"], product["formats"])

    def test_mixed_numeric_prices_and_schema_enum_urls_are_equivalent(self):
        blob = htmlx._parse_stdlib(fixture("complete-product.html"), URL).scripts_ld[0]
        blob = blob.replace('"price":"129.00"', '"price":129').replace('https://schema.org/InStock', 'http://schema.org/InStock')
        _, report = audit(with_jsonld(fixture("microdata-product.html"), [blob]))
        self.assertEqual(1, report.meta["ecommerce"]["product_nodes_count"])

    def test_normalization_preserves_different_multitype_nodes(self):
        raw = [{"@type": ["Thing", "Product"], "name": "Shoe"},
               {"@type": ["CreativeWork", "Article"], "headline": "Guide"}]
        doc = htmlx.Doc(URL, scripts_ld=[json.dumps(raw)])
        records, _ = structured_data.collect(doc)
        self.assertEqual([["Product", "Thing"], ["Article", "CreativeWork"]],
                         [r["node"]["@type"] for r in records])

    def test_conflicting_mixed_nodes_are_preserved_not_overwritten(self):
        html = with_jsonld(fixture("microdata-product.html").replace('content="129.00"', 'content="130.00"'))
        doc, _ = audit(html)
        prices = {n["offers"]["price"] for n in ecommerce.schema_nodes(doc) if n.get("@type") == "Product"}
        self.assertEqual({"129.00", "130.00"}, prices)
        raw = [{"@type": "Offer", "price": "123456789012345678901234567890.01"},
               {"@type": "Offer", "price": "123456789012345678901234567890.02"}]
        records, _ = structured_data.collect(htmlx.Doc(URL, scripts_ld=[json.dumps(raw)]))
        self.assertEqual(2, len(records))

    def test_nested_offer_missing_currency_uses_existing_rule(self):
        html = fixture("microdata-product.html").replace('<meta itemprop="priceCurrency" content="USD">', '')
        _, report = audit(html)
        self.assertIn(("schema.ecommerce.offer.missing.pricecurrency", "high"), problems(report))

    def test_article_microdata_is_not_penalized_for_no_jsonld(self):
        html = '''<article itemscope itemtype="https://schema.org/Article">
        <h1 itemprop="headline">An article</h1><span itemprop="author">Jane</span>
        <time itemprop="datePublished" datetime="2026-10-11">Today</time>
        <img itemprop="image" src="/a.jpg" alt="Article"><p>A shoe costs $99.</p></article>'''
        doc, report = audit(html)
        self.assertFalse(htmlx.looks_product(doc))
        self.assertFalse(report.meta["ecommerce"]["is_product"])
        self.assertNotIn("schema.no.structured.data", {f.rule_id for f in report.findings})
        self.assertNotIn("schema.article.like.page.without.article.schema", {f.rule_id for f in report.findings})

    def test_invalid_jsonld_still_reported_alongside_valid_microdata(self):
        _, report = audit(with_jsonld(fixture("microdata-product.html"), ["{bad}"]))
        self.assertIn(("schema.invalid.json.ld", "high"), problems(report))
        self.assertNotIn(("schema.no.structured.data", "medium"), problems(report))

    def test_article_required_field_validation_applies_to_microdata(self):
        _, report = audit('<article itemscope itemtype="https://schema.org/Article"><h1>Example</h1></article>')
        self.assertIn(("schema.article.missing.required.headline", "high"), problems(report))

    def test_duplicate_defect_scores_once_across_formats(self):
        html = '''<div itemscope itemtype="https://schema.org/Article"></div>
        <script type="application/ld+json">{"@type":"Article"}</script>'''
        _, report = audit(html)
        self.assertEqual(1, sum(f.rule_id == "schema.article.missing.required.headline" for f in report.findings))
        # Coalescing a rule must not hide different missing-property evidence.
        html = '<script type="application/ld+json">' + json.dumps([
            {"@type": "Article", "headline": "First", "author": "Jane", "image": "/a.jpg"},
            {"@type": "Article", "headline": "Second", "datePublished": "2026-10-11"}]) + '</script>'
        _, report = audit(html)
        findings = [f for f in report.findings if f.rule_id == "schema.article.missing.recommended.properties"]
        self.assertEqual(1, len(findings))
        self.assertIn("datePublished", findings[0].detail)
        self.assertIn("author, image", findings[0].detail)

    def test_productgroup_variants_and_nested_prices_remain_separate(self):
        html = '''<div itemscope itemtype="https://schema.org/ProductGroup">
        <div itemprop="hasVariant" itemscope itemtype="https://schema.org/Product">
        <span itemprop="sku">RED-1</span><span itemprop="name">Red Shoe</span>
        <div itemprop="offers" itemscope itemtype="https://schema.org/Offer">
        <div itemprop="priceSpecification" itemscope itemtype="https://schema.org/UnitPriceSpecification">
        <meta itemprop="price" content="90"><meta itemprop="priceCurrency" content="USD"></div></div></div>
        <div itemprop="hasVariant" itemscope itemtype="https://schema.org/Product">
        <span itemprop="sku">BLUE-1</span><span itemprop="name">Blue Shoe</span>
        <div itemprop="offers" itemscope itemtype="https://schema.org/AggregateOffer">
        <meta itemprop="lowPrice" content="100"><meta itemprop="highPrice" content="110">
        <meta itemprop="priceCurrency" content="USD"><meta itemprop="offerCount" content="2"></div></div></div>'''
        _, report = audit(html)
        self.assertEqual(2, report.meta["ecommerce"]["product_nodes_count"])
        self.assertEqual(["aggregateoffer", "offer"], report.meta["ecommerce"]["schema_offer_types"])
        self.assertNotIn(("schema.ecommerce.offer.missing.price", "high"), problems(report))
        self.assertNotIn(("schema.ecommerce.offer.missing.pricecurrency", "high"), problems(report))

    def test_microdata_stale_offer_and_visible_price_mismatch_are_audited(self):
        html = fixture("microdata-product.html").replace('itemprop="price" content="129.00"', 'itemprop="price" content="130.00"')
        html = html.replace('<meta itemprop="priceCurrency"', '<time itemprop="priceValidUntil" datetime="2000-01-01">Expired</time><meta itemprop="priceCurrency"')
        _, report = audit(html)
        self.assertIn(("schema.ecommerce.offer.price.expired", "high"), problems(report))
        self.assertIn(("schema.ecommerce.price.mismatch", "high"), problems(report))

    def test_extraction_warning_is_scored_once_and_keeps_coverage_evidence(self):
        _, report = audit('<div itemscope itemtype="Product" itemref="missing other"></div>')
        warnings = report.meta["structured_data"]["microdata_warnings"]
        self.assertEqual(3, len(warnings))
        self.assertEqual(1, sum(f.rule_id == "schema.microdata.extraction" for f in report.findings))

    def test_comparison_sees_microdata_schema_types(self):
        doc = htmlx.parse(fixture("microdata-product.html"), URL)
        self.assertEqual(["AggregateRating", "Brand", "Offer", "Organization", "Product"], compare._schema_types(doc))

    def test_stdlib_and_optional_backends_share_extraction_and_findings(self):
        html = fixture("microdata-product.html")
        docs = [htmlx._parse_stdlib(html, URL), htmlx.parse(html, URL)]
        reports = []
        for doc in docs:
            report = Report(URL)
            audit_schema.audit(doc, http.Response(URL, URL, 200, {}, html, 1), report)
            reports.append(report)
        self.assertEqual(docs[0].microdata, docs[1].microdata)
        self.assertEqual(problems(reports[0]), problems(reports[1]))
        self.assertEqual(reports[0].meta, reports[1].meta)

    def test_scan_json_exposes_format_provenance_and_merchant_scope(self):
        response = http.Response(URL, URL, 200, {"content-type": "text/html"}, fixture("microdata-product.html"), 1)
        with mock.patch.object(scan.http, "fetch", return_value=response):
            report = scan.scan(URL, only=["schema"], ctx={}, check_images=False)
        payload = json.loads(report.to_json())
        self.assertTrue(payload["meta"]["ecommerce"]["is_merchant"])
        self.assertEqual(["microdata"], payload["meta"]["structured_data"]["formats"])

    def test_shared_itemref_dag_does_not_expand_exponentially(self):
        # Each item names two properties referencing the same next item. A naive
        # recursive normalization or json.dumps doubles work at every level.
        html = ''.join('<div id="n{0}" itemprop="related1 related2" itemscope '
                       'itemtype="https://schema.org/Thing" itemref="n{1}"></div>'.format(i, i + 1)
                       for i in range(26))
        html += '<div id="n26" itemprop="related1 related2" itemscope itemtype="https://schema.org/Product"><span itemprop="name">Shoe</span></div>'
        doc = htmlx.parse(html, URL)
        records, errors = structured_data.collect(doc)
        self.assertEqual([], errors)
        self.assertEqual(27, len(records))
        self.assertTrue(htmlx.looks_product(doc))


if __name__ == "__main__":
    unittest.main()
