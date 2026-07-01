"""Offline smoke tests — no network, no third-party deps.

Run from the skill root:
    python -m unittest discover -s tests
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
sys.path.insert(0, SCRIPTS)

from lib import htmlx, http  # noqa: E402
from lib.report import Report  # noqa: E402
import audit_technical, audit_content, audit_schema, audit_geo  # noqa: E402
import generate_schema  # noqa: E402

GOOD_PAGE = """<!doctype html><html lang="en"><head>
<title>What is GEO? A practical guide to AI search optimization</title>
<meta name="description" content="A concise, practical guide to generative engine
optimization: how AI answer engines cite content and how it differs from SEO.">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta property="og:title" content="What is GEO?">
<meta property="og:description" content="Guide">
<meta property="og:image" content="/x.png">
<link rel="canonical" href="https://example.com/geo">
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Article","headline":"What is GEO?",
 "author":{"@type":"Person","name":"Jane"},"datePublished":"2026-01-01","image":"/x.png"}
</script></head><body>
<h1>What is GEO?</h1>
<h2>How does GEO work?</h2>
<p>GEO is the practice of structuring content so AI answer engines cite it.
According to a 2024 study, 40% of searches now show AI overviews. It works by
making each passage a self-contained answer that stands on its own without the
surrounding context, which is exactly what large language models prefer to quote
when they assemble a response for a user asking a direct question.</p>
<img src="a.png" alt="diagram of GEO" loading="lazy">
<a href="/learn-more">read the full GEO methodology</a>
</body></html>"""


class TestParser(unittest.TestCase):
    def test_extracts_core_elements(self):
        doc = htmlx.parse(GOOD_PAGE, base_url="https://example.com/geo")
        self.assertIn("What is GEO", doc.title)
        self.assertEqual(doc.lang, "en")
        self.assertEqual([lvl for lvl, _ in doc.headings], [1, 2])
        self.assertEqual(len(doc.scripts_ld), 1)
        self.assertEqual(doc.canonical(), "https://example.com/geo")
        self.assertTrue(doc.meta_by_name("description"))


class TestSSRF(unittest.TestCase):
    def test_blocks_private_host(self):
        with self.assertRaises(http.SSRFError):
            http.assert_public_host("http://127.0.0.1/admin")

    def test_normalize_adds_scheme(self):
        self.assertTrue(http.normalize_url("example.com").startswith("https://"))

    def test_rejects_bad_scheme(self):
        with self.assertRaises(ValueError):
            http.normalize_url("ftp://example.com")


class TestAuditors(unittest.TestCase):
    def _run(self, html, ctx=None):
        doc = htmlx.parse(html, base_url="https://example.com/geo")
        resp = http.Response(
            url="https://example.com/geo", final_url="https://example.com/geo",
            status=200, headers={"content-type": "text/html"}, text=html,
            elapsed_ms=1)
        report = Report(url=resp.url, final_url=resp.final_url, fetched_status=200)
        ctx = ctx or {"robots_txt": "User-agent: *\nDisallow:\nSitemap: https://example.com/sitemap.xml",
                      "llms_txt": False, "sitemap_found": True}
        for fn in (audit_technical.audit, audit_content.audit,
                   audit_schema.audit, audit_geo.audit):
            fn(doc, resp, report, ctx)
        return report

    def test_good_page_scores_well(self):
        report = self._run(GOOD_PAGE)
        self.assertGreaterEqual(report.score(), 70)
        self.assertEqual(report.counts()["critical"], 0)

    def test_noindex_is_critical(self):
        html = GOOD_PAGE.replace("<head>", '<head><meta name="robots" content="noindex">')
        report = self._run(html)
        titles = [f.title for f in report.findings if f.severity == "critical"]
        self.assertTrue(any("noindex" in t for t in titles))

    def test_blocked_ai_bot_flagged(self):
        ctx = {"robots_txt": "User-agent: GPTBot\nDisallow: /",
               "llms_txt": False, "sitemap_found": False}
        report = self._run(GOOD_PAGE, ctx)
        titles = [f.title for f in report.findings]
        self.assertTrue(any("AI crawlers are blocked" in t for t in titles))

    def test_invalid_jsonld_flagged(self):
        html = GOOD_PAGE.replace('"image":"/x.png"}', '"image": }')  # broken JSON
        report = self._run(html)
        self.assertTrue(any(f.title == "Invalid JSON-LD" for f in report.findings))


class TestSchemaGenerator(unittest.TestCase):
    def test_required_placeholder(self):
        node = generate_schema.build("Product", {})
        self.assertEqual(node["@type"], "Product")
        self.assertIn("TODO", node["name"])

    def test_fields_applied(self):
        node = generate_schema.build("Article", {"headline": "Hi"})
        self.assertEqual(node["headline"], "Hi")

    def test_unknown_type_raises(self):
        with self.assertRaises(SystemExit):
            generate_schema.build("NotAType", {})


if __name__ == "__main__":
    unittest.main()
