"""Source templates cannot supply facts to any normalized page consumer."""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import scan
from lib import ecommerce, htmlx, http, structured_data, template_source
from lib.report import Report
try:
    from .test_ecommerce import fixture, inspect, rules
except ImportError:
    from test_ecommerce import fixture, inspect, rules

URL = "https://docs.test/tutorial"
SCRIPT = '<script type="application/ld+json">{"@type":"Product","name":"Demo","offers":{"@type":"Offer","price":"99","priceCurrency":"USD"}}</script>'


def tutorial(example=SCRIPT):
    return '<!doctype html><html lang="en"><head><title>Real tutorial</title></head><body><article><h1>Product schema tutorial</h1><template>' + example + '</template><p>This is documentation, not a store.</p></article></body></html>'


class TestTemplateSource(unittest.TestCase):
    def test_inert_product_example_cannot_classify_docs_as_a_merchant(self):
        for parser in (htmlx._parse_stdlib, htmlx.parse):
            doc = parser(tutorial(), URL)
            report = Report(URL)
            meta = ecommerce.audit(doc, report)
            self.assertFalse(htmlx.looks_product(doc))
            self.assertFalse(meta["is_product"])
            self.assertFalse(meta["is_merchant"])
            self.assertEqual([], doc.scripts_ld)
            self.assertEqual(set(), rules(report))

    def test_inert_invalid_json_is_not_a_page_schema_syntax_failure(self):
        doc = htmlx.parse(tutorial('<script type="application/ld+json">{broken</script>'), URL)
        self.assertEqual(([], []), structured_data.collect(doc))

    def test_fake_metadata_canonical_and_title_cannot_mask_active_values(self):
        example = '<title>Fake</title><meta name="description" content="Fake"><meta property="og:type" content="product"><link rel="canonical" href="https://fake.test/p">'
        html = '<template>' + example + '</template><title>Actual</title><meta name="description" content="Actual"><link rel="canonical" href="/tutorial">'
        for parser in (htmlx._parse_stdlib, htmlx.parse):
            doc = parser(html, URL)
            self.assertEqual("Actual", doc.title)
            self.assertEqual("Actual", doc.meta_by_name("description"))
            self.assertIsNone(doc.meta_by_property("og:type"))
            self.assertEqual(URL, doc.canonical())
            self.assertEqual(1, len(doc.meta))

    def test_inert_headings_links_images_and_language_cannot_pollute_doc(self):
        example = '<html lang="fr"><h1>Fake</h1><a href="/fake">Fake</a><img src="fake.jpg"></html>'
        for parser in (htmlx._parse_stdlib, htmlx.parse):
            doc = parser(tutorial(example), URL)
            self.assertEqual([(1, "Product schema tutorial")], doc.headings)
            self.assertEqual([], doc.links)
            self.assertEqual([], doc.images)
            self.assertEqual("en", doc.lang)
            self.assertNotIn("Fake", doc.text)

    def test_inert_article_does_not_change_page_type_heuristic(self):
        doc = htmlx.parse('<template><article>Example</article></template><h1>Home</h1>', URL)
        self.assertFalse(htmlx.looks_article(doc))
        doc = htmlx.parse('<template><article>Example</article></template><article>Actual</article>', URL)
        self.assertTrue(htmlx.looks_article(doc))

    def test_nested_templates_and_deep_content_are_iterative(self):
        html = '<template>' * 1000 + SCRIPT + '</template>' * 1000 + '<h1>Active</h1>'
        projected = template_source.document_source(html)
        self.assertEqual('<h1>Active</h1>', projected)

    def test_unclosed_template_remains_inert_to_the_end_of_source(self):
        html = '<h1>Active</h1><template>' + SCRIPT + '<h1>Inert</h1>'
        for parser in (htmlx._parse_stdlib, htmlx.parse):
            doc = parser(html, URL)
            self.assertEqual([(1, "Active")], doc.headings)
            self.assertEqual([], doc.scripts_ld)

    def test_template_slash_is_not_an_html_end_tag(self):
        html = '<template/>' + SCRIPT + '<h1>Inert</h1></template><h1>Active</h1>'
        for parser in (htmlx._parse_stdlib, htmlx.parse):
            doc = parser(html, URL)
            self.assertEqual([(1, "Active")], doc.headings)
            self.assertEqual([], doc.scripts_ld)

    def test_raw_script_text_cannot_open_or_close_a_template(self):
        html = '<script>const example="<template>";</script><h1>Actual</h1><template><script>const example="</template>";</script>' + SCRIPT + '</template>'
        doc = htmlx.parse(html, URL)
        self.assertEqual([(1, "Actual")], doc.headings)
        self.assertEqual([], doc.scripts_ld)

    def test_comments_escaped_examples_and_textareas_do_not_open_templates(self):
        for example in ('<!-- <template> -->', '&lt;template&gt;', '<textarea>&lt;template&gt;</textarea>', '<textarea><template></textarea>', '<title>A <template> example &amp; text</title>'):
            for parser in (htmlx._parse_stdlib, htmlx.parse):
                doc = parser(example + SCRIPT, URL)
                self.assertEqual(1, len(doc.scripts_ld))
                self.assertTrue(htmlx.looks_product(doc))

    def test_textarea_cannot_close_an_inert_template_early(self):
        html = '<template><textarea></template></textarea>' + SCRIPT + '</template><h1>Active</h1>'
        doc = htmlx.parse(html, URL)
        self.assertEqual([], doc.scripts_ld)
        self.assertEqual([(1, 'Active')], doc.headings)

    def test_script_in_pre_is_active_html_not_automatically_an_example(self):
        doc = htmlx.parse('<pre>' + SCRIPT + '</pre><template>Ignored</template>', URL)
        self.assertTrue(htmlx.looks_product(doc))

    def test_hidden_and_head_data_blocks_remain_eligible(self):
        for attrs in ('hidden', 'aria-hidden="true"', 'style="display:none"'):
            html = '<head>' + SCRIPT + '</head><div ' + attrs + '>' + SCRIPT + '</div><template>Ignored</template>'
            doc = htmlx.parse(html, URL)
            self.assertEqual(2, len(doc.scripts_ld))
            self.assertTrue(htmlx.looks_product(doc))

    def test_active_invalid_json_still_has_syntax_evidence(self):
        html = '<template>' + SCRIPT + '</template><script type="application/ld+json">{broken</script>'
        doc = htmlx.parse(html, URL)
        nodes, errors = structured_data.collect(doc)
        self.assertEqual([], nodes)
        self.assertEqual(1, len(errors))

    def test_original_source_is_preserved_but_main_extractor_gets_projected_source(self):
        html = tutorial('<h1>Inert</h1>')
        with mock.patch.object(htmlx, "_main_content", return_value="") as extract:
            doc = htmlx.parse(html, URL)
        self.assertEqual(html, doc.html)
        self.assertNotIn("<template>", extract.call_args[0][0])
        self.assertNotIn("Inert", extract.call_args[0][0])

    def test_projection_is_cached_across_normalized_and_lazy_consumers(self):
        with mock.patch.object(htmlx, 'document_source', wraps=template_source.document_source) as project:
            doc = htmlx.parse(tutorial(), URL)
            doc.microdata
            doc.rdfa
            doc.merchant_markup
            self.assertEqual(1, project.call_count)

    def test_shared_view_excludes_template_slash_markup_in_all_schema_formats(self):
        example = '<meta property="og:type" content="product"><meta property="product:price:amount" content="99"><div itemscope itemtype="https://schema.org/Product"><span itemprop="name">Demo</span></div><div vocab="https://schema.org/" typeof="Product"><span property="name">Demo</span></div>'
        doc = htmlx.parse('<template/>' + example + SCRIPT + '</template><h1>Docs</h1>', URL)
        self.assertEqual([], doc.microdata)
        self.assertEqual([], doc.rdfa)
        self.assertEqual([], doc.scripts_ld)
        self.assertEqual([], doc.merchant_markup['meta'])
        self.assertFalse(htmlx.looks_product(doc))

    def test_unchanged_source_fast_path_and_active_entities_are_preserved(self):
        active = '<!doctype html><h1>A &amp; B &#38; C</h1><!-- ordinary comment -->' + SCRIPT
        self.assertIs(active, template_source.document_source(active))
        for html in (active, active + '<template>Excluded</template>'):
            doc = htmlx.parse(html, URL)
            self.assertEqual([(1, "A & B & C")], doc.headings)
            self.assertEqual(1, len(doc.scripts_ld))

    def test_unknown_marked_declaration_does_not_crash_template_projection(self):
        doc = htmlx.parse('<![unknown]><template>' + SCRIPT + '</template><h1>Actual</h1>', URL)
        self.assertEqual([(1, "Actual")], doc.headings)
        self.assertEqual([], doc.scripts_ld)

    def test_real_product_with_inert_extra_variant_still_uses_its_active_offer(self):
        html = fixture('complete-product.html').replace('</body>', '<template>' + SCRIPT + '</template></body>')
        _, report, meta = inspect(html)
        self.assertEqual(1, meta['product_nodes_count'])
        self.assertEqual('TS-42', meta['selected_product'])
        self.assertEqual('ready', meta['comparison_status'])
        self.assertFalse(any(f.severity != 'good' for f in report.findings))

    def test_scan_json_excludes_inert_schema_provenance(self):
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, tutorial(), 1)
        with mock.patch.object(scan.http, 'fetch', return_value=response):
            payload = json.loads(scan.scan(URL, only=['schema'], ctx={}, check_images=False).to_json())
        self.assertFalse(payload['meta']['ecommerce']['is_product'])
        self.assertFalse(payload['meta']['ecommerce']['is_merchant'])
        self.assertEqual([], payload['meta']['structured_data']['formats'])


if __name__ == '__main__':
    unittest.main()
