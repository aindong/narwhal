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

from lib import htmlx, http, links  # noqa: E402
from lib.report import Report, below_threshold  # noqa: E402
from lib.robots import RobotsTxt  # noqa: E402
import audit_technical, audit_content, audit_schema, audit_geo  # noqa: E402
import generate_schema  # noqa: E402
import crawl_site  # noqa: E402

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


class TestRobots(unittest.TestCase):
    def test_disallow_prefix(self):
        rt = RobotsTxt.parse("User-agent: *\nDisallow: /private")
        self.assertFalse(rt.allowed("/private/page", "AnyBot"))
        self.assertTrue(rt.allowed("/public", "AnyBot"))

    def test_empty_disallow_allows_all(self):
        rt = RobotsTxt.parse("User-agent: *\nDisallow:")
        self.assertTrue(rt.allowed("/anything", "AnyBot"))

    def test_allow_beats_disallow_longer_match(self):
        rt = RobotsTxt.parse(
            "User-agent: *\nDisallow: /folder\nAllow: /folder/public")
        self.assertFalse(rt.allowed("/folder/secret", "Bot"))
        self.assertTrue(rt.allowed("/folder/public/x", "Bot"))

    def test_allow_wins_equal_length_tie(self):
        rt = RobotsTxt.parse("User-agent: *\nDisallow: /p\nAllow: /p")
        self.assertTrue(rt.allowed("/page", "Bot"))

    def test_wildcard_star(self):
        rt = RobotsTxt.parse("User-agent: *\nDisallow: /*/admin")
        self.assertFalse(rt.allowed("/any/admin", "Bot"))
        self.assertTrue(rt.allowed("/admin", "Bot"))

    def test_end_anchor(self):
        rt = RobotsTxt.parse("User-agent: *\nDisallow: /*.pdf$")
        self.assertFalse(rt.allowed("/files/report.pdf", "Bot"))
        self.assertTrue(rt.allowed("/files/report.pdf?x=1", "Bot"))

    def test_user_agent_specificity(self):
        rt = RobotsTxt.parse(
            "User-agent: *\nDisallow: /\n\nUser-agent: GPTBot\nDisallow:")
        # Specific GPTBot group (allow-all) wins over the restrictive * group
        self.assertTrue(rt.allowed("/anything", "GPTBot"))
        self.assertFalse(rt.allowed("/anything", "RandomBot"))

    def test_multiple_agents_share_block(self):
        rt = RobotsTxt.parse(
            "User-agent: GPTBot\nUser-agent: ClaudeBot\nDisallow: /")
        self.assertTrue(rt.disallowed("/", "GPTBot"))
        self.assertTrue(rt.disallowed("/", "ClaudeBot"))
        self.assertTrue(rt.allowed("/", "PerplexityBot"))

    def test_no_rules_allows(self):
        rt = RobotsTxt.parse("")
        self.assertTrue(rt.allowed("/", "Bot"))

    def test_sitemaps_collected(self):
        rt = RobotsTxt.parse(
            "Sitemap: https://x.com/sitemap.xml\nUser-agent: *\nDisallow:")
        self.assertEqual(rt.sitemaps, ["https://x.com/sitemap.xml"])


class TestLinks(unittest.TestCase):
    HTML = """<html><body>
    <a href="/about">About</a>
    <a href="https://example.com/x">internal abs</a>
    <a href="https://other.com/y">external</a>
    <a href="mailto:a@b.com">mail</a>
    <a href="tel:+15551234">call</a>
    <a href="#section">frag</a>
    <a href="page2">relative</a>
    <a href="/about#top">dup w/ fragment</a>
    </body></html>"""

    def _links(self):
        doc = htmlx.parse(self.HTML, base_url="https://example.com/dir/")
        return links.extract_links(doc, "https://example.com/dir/")

    def test_resolves_and_classifies(self):
        by_url = {l["url"]: l["internal"] for l in self._links()}
        self.assertTrue(by_url.get("https://example.com/about"))
        self.assertTrue(by_url.get("https://example.com/x"))
        self.assertTrue(by_url.get("https://example.com/dir/page2"))
        self.assertFalse(by_url.get("https://other.com/y"))

    def test_skips_non_http_and_fragments(self):
        urls = [l["url"] for l in self._links()]
        self.assertFalse(any(u.startswith(("mailto", "tel")) for u in urls))
        self.assertNotIn("https://example.com/dir/#section", urls)

    def test_dedupes_fragment_variants(self):
        urls = [l["url"] for l in self._links()]
        self.assertEqual(urls.count("https://example.com/about"), 1)

    def test_is_broken(self):
        for code in (0, 400, 404, 410, 500, 503):
            self.assertTrue(links.is_broken(code))
        for code in (200, 204, 301, 302, 399):
            self.assertFalse(links.is_broken(code))

    def test_gated_codes_not_broken(self):
        # rate-limited / bot-blocked / auth-walled are not "dead links"
        for code in (401, 403, 429, 451, 999):
            self.assertFalse(links.is_broken(code))


class TestCrawlPoliteness(unittest.TestCase):
    def test_skips_disallowed_keeps_base(self):
        rt = RobotsTxt.parse("User-agent: seo-scan\nDisallow: /private")
        base = "https://site.com/"
        cands = [base, "https://site.com/public",
                 "https://site.com/private/x", "https://site.com/about"]
        urls, skipped = crawl_site.select_urls(cands, base, rt, True, 100)
        self.assertEqual(skipped, 1)
        self.assertNotIn("https://site.com/private/x", urls)
        self.assertIn(base, urls)
        self.assertIn("https://site.com/about", urls)

    def test_ignore_robots_keeps_all(self):
        rt = RobotsTxt.parse("User-agent: *\nDisallow: /")
        base = "https://site.com/"
        cands = [base, "https://site.com/a", "https://site.com/b"]
        urls, skipped = crawl_site.select_urls(cands, base, rt, False, 100)
        self.assertEqual(skipped, 0)
        self.assertEqual(len(urls), 3)

    def test_caps_at_max_pages(self):
        rt = RobotsTxt.parse("")
        base = "https://site.com/"
        cands = [f"https://site.com/{i}" for i in range(20)]
        urls, skipped = crawl_site.select_urls(cands, base, rt, True, 5)
        self.assertEqual(len(urls), 5)


class TestFailUnderGate(unittest.TestCase):
    def test_no_threshold_never_fails(self):
        self.assertFalse(below_threshold(0, None))
        self.assertFalse(below_threshold(100, None))

    def test_below_threshold_fails(self):
        self.assertTrue(below_threshold(57, 80))

    def test_at_or_above_threshold_passes(self):
        self.assertFalse(below_threshold(80, 80))
        self.assertFalse(below_threshold(95, 80))

    def test_works_with_float_average(self):
        self.assertTrue(below_threshold(79.5, 80))
        self.assertFalse(below_threshold(80.0, 80))


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
