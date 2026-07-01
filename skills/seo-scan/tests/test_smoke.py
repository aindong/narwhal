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
from lib import sitemap as sm  # noqa: E402
from lib import text as textlib  # noqa: E402
from lib import config as configlib  # noqa: E402
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


class TestText(unittest.TestCase):
    SIMPLE = "The cat sat on the mat. The dog ran to the park. We had fun."
    COMPLEX = ("Notwithstanding the aforementioned considerations, the "
               "epistemological ramifications necessitate substantial "
               "deliberation regarding methodological presuppositions.")

    def test_syllables(self):
        self.assertEqual(textlib.syllables("cat"), 1)
        self.assertEqual(textlib.syllables("apple"), 2)
        self.assertGreaterEqual(textlib.syllables("beautiful"), 3)

    def test_reading_ease_orders(self):
        simple = textlib.flesch_reading_ease(self.SIMPLE)
        hard = textlib.flesch_reading_ease(self.COMPLEX)
        self.assertGreater(simple, hard)
        self.assertEqual(textlib.reading_ease_label(simple), "easy")

    def test_grade_level(self):
        self.assertLess(textlib.flesch_kincaid_grade(self.SIMPLE),
                        textlib.flesch_kincaid_grade(self.COMPLEX))

    def test_top_keywords_skips_stopwords(self):
        text = "SEO audit tools. SEO audit matters. Audit your SEO regularly."
        kws = dict(textlib.top_keywords(text, 5))
        self.assertIn("seo", kws)
        self.assertIn("audit", kws)
        self.assertNotIn("your", kws)  # stopword

    def test_candidate_entities(self):
        text = "Google Search Console is great. Google Search Console helps SEO."
        ents = dict(textlib.candidate_entities(text))
        self.assertIn("Google Search Console", ents)

    def test_empty_text_safe(self):
        self.assertIsNone(textlib.flesch_reading_ease(""))
        self.assertEqual(textlib.top_keywords(""), [])


class TestSitemap(unittest.TestCase):
    URLSET = """<?xml version="1.0"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/a</loc><lastmod>2026-01-15</lastmod></url>
      <url><loc>https://example.com/b</loc><lastmod>2026-01-15T09:30:00+00:00</lastmod></url>
      <url><loc>/relative</loc></url>
      <url><loc>https://other.com/x</loc><lastmod>15-01-2026</lastmod></url>
    </urlset>"""

    INDEX = """<?xml version="1.0"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://example.com/sitemap-1.xml</loc></sitemap>
      <sitemap><loc>https://example.com/sitemap-2.xml</loc></sitemap>
    </sitemapindex>"""

    def test_parse_urlset(self):
        kind, entries = sm.parse(self.URLSET)
        self.assertEqual(kind, "urlset")
        self.assertEqual(len(entries), 4)
        self.assertEqual(entries[0]["loc"], "https://example.com/a")
        self.assertEqual(entries[0]["lastmod"], "2026-01-15")

    def test_parse_index(self):
        kind, entries = sm.parse(self.INDEX)
        self.assertEqual(kind, "index")
        self.assertEqual(len(entries), 2)
        self.assertTrue(entries[0]["loc"].endswith("sitemap-1.xml"))

    def test_lastmod_validation(self):
        self.assertTrue(sm.valid_lastmod("2026-01-15"))
        self.assertTrue(sm.valid_lastmod("2026-01-15T09:30:00+00:00"))
        self.assertTrue(sm.valid_lastmod("2026-01-15T09:30:00Z"))
        self.assertFalse(sm.valid_lastmod("15-01-2026"))
        self.assertFalse(sm.valid_lastmod("not a date"))
        self.assertFalse(sm.valid_lastmod(None))

    def test_loc_problems(self):
        self.assertEqual(sm.loc_problem("/relative", "example.com"), "not-absolute")
        self.assertEqual(sm.loc_problem("https://other.com/x", "example.com"), "cross-host")
        self.assertIsNone(sm.loc_problem("https://example.com/a", "example.com"))

    def test_gzip_decode(self):
        import gzip
        raw = gzip.compress(self.URLSET.encode("utf-8"))
        self.assertIn("<urlset", sm.decode(raw))
        self.assertIn("<urlset", sm.decode(self.URLSET.encode("utf-8")))  # plain too


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


class TestConfig(unittest.TestCase):
    def test_defaults(self):
        c = configlib.Config()
        self.assertEqual(c.weights["critical"], 12)
        self.assertEqual(c.thresholds["title_max"], 65)
        self.assertEqual(c.default("timeout"), 20)

    def test_overrides_merge(self):
        c = configlib.Config({
            "weights": {"high": 10},
            "thresholds": {"title_max": 70},
            "defaults": {"concurrency": 8},
        })
        self.assertEqual(c.weights["high"], 10)
        self.assertEqual(c.weights["critical"], 12)   # untouched default
        self.assertEqual(c.thresholds["title_max"], 70)
        self.assertEqual(c.thresholds["title_min"], 15)  # untouched
        self.assertEqual(c.default("concurrency"), 8)

    def test_ignore_rules(self):
        c = configlib.Config({"ignore": {
            "categories": ["geo"], "titles": ["Open Graph"]}})
        self.assertTrue(c.is_ignored("geo", "anything"))
        self.assertTrue(c.is_ignored("content", "Incomplete Open Graph tags"))
        self.assertFalse(c.is_ignored("content", "Thin content"))

    def test_report_custom_weights(self):
        r = Report("u", weights={**configlib.DEFAULT_WEIGHTS, "critical": 50})
        r.add("technical", "critical", "boom")
        self.assertEqual(r.score(), 50)

    def test_report_ignore_suppresses(self):
        r = Report("u", ignore=lambda cat, title: cat == "geo")
        r.add("geo", "high", "dropped")
        r.add("technical", "high", "kept")
        self.assertEqual(len(r.findings), 1)
        self.assertEqual(r.findings[0].title, "kept")

    def test_thresholds_flow_to_auditor(self):
        # A 20-char title passes by default (max 65) but fails a strict max of 10.
        doc = htmlx.parse('<title>Twelve chars ok</title>', base_url="https://x.com/")
        strict = Report("u")
        import audit_technical
        audit_technical.audit(doc, http.Response("https://x.com/", "https://x.com/",
                              200, {}, "", 1), strict, {"thresholds": {"title_max": 10}})
        titles = [f.title for f in strict.findings]
        self.assertIn("Title may be truncated in SERPs", titles)


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
