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
from lib import simhash  # noqa: E402
from lib import content_quality as cq  # noqa: E402
from lib.report import Report, below_threshold  # noqa: E402
from lib import report as report_lib  # noqa: E402
from lib.robots import RobotsTxt  # noqa: E402
import audit_technical, audit_content, audit_schema, audit_geo  # noqa: E402
import generate_schema  # noqa: E402
import crawl_site  # noqa: E402
import generate_llms  # noqa: E402
import audit as audit_mod  # noqa: E402

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


class TestContentQuality(unittest.TestCase):
    AI = ("In today's fast-paced world, it is worth noting that we must delve into "
          "the ever-evolving realm of marketing. When it comes to unlocking the "
          "potential of your brand, our cutting-edge seamless solutions play a "
          "crucial role. Needless to say, this is a testament to our game-changing "
          "approach that will elevate your presence. ") * 2
    CLEAN = ("We measured load times on 40 store pages with WebPageTest. Median LCP "
             "was 3.2 seconds, driven by a 1.4 MB hero PNG. Converting it to WebP and "
             "setting width and height cut the median to 1.9 seconds. Checkout pages "
             "improved less because a third-party script blocks the main thread. ") * 2

    def test_flags_filler_and_ai(self):
        r = cq.analyze(self.AI)
        self.assertGreater(r["filler_per_100w"], 1.0)
        self.assertGreaterEqual(r["ai_distinct"], 4)
        self.assertTrue(r["filler_examples"])

    def test_clean_text_is_clean(self):
        r = cq.analyze(self.CLEAN)
        self.assertEqual(r["filler_count"], 0)
        self.assertEqual(r["ai_distinct"], 0)

    def test_short_text_safe(self):
        r = cq.analyze("Too short.")
        self.assertEqual(r["filler_per_100w"], 0.0)  # under 100 words -> not scored

    def test_auditor_flags_ai_content(self):
        import audit_content
        from lib.report import Report
        rep = Report("u")
        audit_content._quality(self.AI, rep)
        titles = [f.title for f in rep.findings]
        self.assertTrue(any("AI-generated" in t or "Filler" in t for t in titles))


class TestSimhash(unittest.TestCase):
    # Realistic page-length, VARIED text (many unique shingles). SimHash is built
    # for substantial documents, where a small edit moves few of the 64 bits.
    A = " ".join(
        f"paragraph {i} explains the alpha methodology concept {i} using worked "
        f"example {i} and a practical note {i} for readers." for i in range(60))
    # Near-identical: a couple of words changed in a long document.
    A2 = A.replace("worked example 10", "worked sample 10").replace(
        "practical note 20", "practical tip 20")
    B = " ".join(
        f"row {i} tabulates metric {i} with observed value {i} and current "
        f"status {i} pending review by team {i} today." for i in range(60))

    def test_deterministic(self):
        self.assertEqual(simhash.simhash(self.A), simhash.simhash(self.A))

    def test_near_dup_high_similarity(self):
        sim = simhash.similarity(simhash.simhash(self.A), simhash.simhash(self.A2))
        self.assertGreaterEqual(sim, 90)

    def test_different_low_similarity(self):
        sim = simhash.similarity(simhash.simhash(self.A), simhash.simhash(self.B))
        self.assertLess(sim, 80)

    def test_cluster_groups_near_dupes(self):
        items = [("a", simhash.simhash(self.A)),
                 ("a2", simhash.simhash(self.A2)),
                 ("b", simhash.simhash(self.B))]
        clusters = simhash.cluster(items, 90.0)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(set(clusters[0]), {"a", "a2"})

    def test_find_duplicates_flags_canonical(self):
        fp_a = simhash.simhash(self.A)
        fp_a2 = simhash.simhash(self.A2)
        # near-dupes with no canonical -> flagged
        bad = crawl_site.find_duplicates([
            {"url": "u1", "fingerprint": fp_a, "canonical": None},
            {"url": "u2", "fingerprint": fp_a2, "canonical": None}], 90.0)
        self.assertEqual(len(bad), 1)
        self.assertFalse(bad[0]["canonical_ok"])
        # near-dupes pointing at one canonical -> ok
        good = crawl_site.find_duplicates([
            {"url": "u1", "fingerprint": fp_a, "canonical": "https://x.com/canon"},
            {"url": "u2", "fingerprint": fp_a2, "canonical": "https://x.com/canon"}], 90.0)
        self.assertTrue(good[0]["canonical_ok"])


class TestAuditCompose(unittest.TestCase):
    def test_demote_drops_h1_and_pushes_headings(self):
        md = "# Title\n\nintro\n\n## Section\n\ntext\n\n### Sub\n"
        out = audit_mod._demote(md)
        self.assertNotIn("# Title", out)
        self.assertIn("### Section", out)   # ## -> ###
        self.assertIn("#### Sub", out)      # ### -> ####
        self.assertIn("intro", out)

    def test_overall_score_is_lower_of_two(self):
        data = {"page": Report("u"), "site_result": {"avg_score": 42.0}}
        # empty page report scores 100; overall should be the site average
        self.assertEqual(audit_mod.overall_score(data), 42.0)


class TestLlmsTxt(unittest.TestCase):
    def test_section_for(self):
        self.assertEqual(generate_llms.section_for("https://x.com/"), "Main")
        self.assertEqual(generate_llms.section_for("https://x.com/about"), "Main")
        self.assertEqual(generate_llms.section_for("https://x.com/blog/post-1"), "Blog")
        self.assertEqual(generate_llms.section_for("https://x.com/case-studies/a"),
                         "Case Studies")

    def test_grouping_main_first(self):
        pages = [
            {"url": "https://x.com/blog/a", "title": "A", "description": ""},
            {"url": "https://x.com/", "title": "Home", "description": ""},
            {"url": "https://x.com/docs/b", "title": "B", "description": ""},
        ]
        sections = generate_llms.group_sections(pages)
        self.assertEqual(sections[0][0], "Main")           # Main always first
        self.assertEqual([s[0] for s in sections[1:]], ["Blog", "Docs"])  # sorted

    def test_render_format_and_todos(self):
        sections = [("Main", [
            {"url": "https://x.com/", "title": "Home", "description": "Welcome."},
            {"url": "https://x.com/about", "title": "", "description": ""},
        ])]
        out = generate_llms.render_llms_txt("Acme", "A great site", sections)
        self.assertIn("# Acme", out)
        self.assertIn("> A great site", out)
        self.assertIn("## Main", out)
        self.assertIn("- [Home](https://x.com/): Welcome.", out)
        self.assertIn("- [About](https://x.com/about)", out)  # slug title fallback

    def test_render_marks_missing_name(self):
        out = generate_llms.render_llms_txt("", "", [])
        self.assertIn("TODO", out)


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


class TestHtmlRenderer(unittest.TestCase):
    def _report(self):
        r = Report("https://x.com/p", final_url="https://x.com/p",
                   fetched_status=200)
        r.add("technical", "critical", "Missing <title>", "No title element.",
              "Add a unique title.", evidence="<head></head>")
        r.add("content", "medium", "Thin content", "Only 120 words.",
              "Expand the copy.")
        r.add("geo", "low", "No llms.txt", "", "Add /llms.txt.")
        r.ok("schema", "JSON-LD present", "Article detected")
        return r

    def test_to_html_is_self_contained_document(self):
        html = self._report().to_html()
        self.assertTrue(html.lstrip().startswith("<!DOCTYPE html>"))
        self.assertIn("</html>", html)
        self.assertIn("<style>", html)          # inline CSS, not linked
        self.assertNotIn("<link", html)          # no external stylesheet
        self.assertNotIn("<script", html)        # no scripts
        self.assertIn("<svg", html)              # score gauge present

    def test_to_html_has_inline_brand_logo(self):
        html = self._report().to_html()
        self.assertIn('<header class="brand">', html)   # branded header
        self.assertIn("data:image/png;base64,", html)   # logo embedded inline...
        self.assertNotIn('src="assets/', html)          # ...not an external file
        self.assertIn("Generated by", html)             # footer credit

    def test_to_html_escapes_untrusted_text(self):
        r = Report("https://x.com/")
        r.add("technical", "high", "Bad <tag> & \"quote\"",
              "Detail with <b>markup</b>", "Fix <it>")
        html = r.to_html()
        self.assertIn("&lt;tag&gt;", html)
        self.assertNotIn("<b>markup</b>", html)  # would be an injection

    def test_to_html_shows_score_and_findings(self):
        html = self._report().to_html()
        self.assertIn("Missing &lt;title&gt;", html)
        self.assertIn("Thin content", html)
        self.assertIn("Priority fixes", html)
        self.assertIn("Passing checks", html)

    def test_md_to_html_covers_our_subset(self):
        md = ("# Title\n\n## Section\n\n| A | B |\n|:--|:--|\n| 1 | `x` |\n\n"
              "- one\n- two\n\n> a note with **bold**\n\n---\n")
        out = report_lib.md_to_html(md)
        for tag in ("<h1>", "<h2>", "<table>", "<th>", "<td>", "<ul>",
                    "<li>", "<blockquote>", "<strong>", "<code>", "<hr>"):
            self.assertIn(tag, out)

    def test_pdf_deliver_falls_back_to_html(self):
        import tempfile
        import contextlib
        import io
        # WeasyPrint isn't a test dependency, so deliver() must gracefully
        # write HTML instead of crashing.
        d = tempfile.mkdtemp()
        pdf = os.path.join(d, "r.pdf")
        with contextlib.redirect_stderr(io.StringIO()), \
                contextlib.redirect_stdout(io.StringIO()):
            rc = report_lib.deliver("pdf", pdf, "<html><body>hi</body></html>",
                                    score=88)
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(pdf) or
                        os.path.exists(os.path.join(d, "r.html")))

    def test_pdf_without_output_is_usage_error(self):
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()):
            rc = report_lib.deliver("pdf", None, "<html></html>")
        self.assertEqual(rc, 2)

    def test_audit_render_html(self):
        from collections import Counter
        page = self._report()
        data = {
            "site": "https://x.com",
            "page": page,
            "site_result": {
                "base": "https://x.com", "avg_score": 70, "pages_scanned": 2,
                "pages": [{"score": 56, "url": "https://x.com/"},
                          {"score": 84, "url": "https://x.com/a"}],
                "recurring": Counter({("technical", "high", "No meta description"): 2}),
                "links": {"broken": [], "checked": 8, "skipped_over_cap": 0},
                "duplicates": [],
            },
            "sitemap": {"start": "https://x.com", "seeds": []},
        }
        html = audit_mod.render_html(data)
        self.assertTrue(html.lstrip().startswith("<!DOCTYPE html>"))
        self.assertIn("Homepage audit", html)
        self.assertIn("Site-wide", html)
        self.assertIn("Sitemap", html)
        self.assertIn("<svg", html)


class TestScanDiff(unittest.TestCase):
    def setUp(self):
        import diff_scan
        self.diff = diff_scan

    def _report(self, findings, score_url="https://x.com/p"):
        r = Report(score_url, final_url=score_url, fetched_status=200)
        for cat, sev, title in findings:
            r.add(cat, sev, title)
        import json
        return json.loads(r.to_json())

    def test_added_resolved_and_score_delta(self):
        old = self._report([("technical", "critical", "Canonical points elsewhere"),
                            ("technical", "high", "Meta description missing")])
        new = self._report([("technical", "high", "Meta description missing"),
                            ("schema", "critical", "Broken JSON-LD")])
        d = self.diff.diff_reports(old, new)
        self.assertEqual([f["title"] for f in d["added"]], ["Broken JSON-LD"])
        self.assertEqual([f["title"] for f in d["resolved"]], ["Canonical points elsewhere"])
        self.assertEqual(d["unchanged"], 1)
        self.assertTrue(d["regression"])          # new critical finding
        self.assertEqual([f["title"] for f in d["new_critical_high"]], ["Broken JSON-LD"])

    def test_dynamic_title_suffix_matches_across_runs(self):
        # "Thin content (210 words)" and "(95 words)" are the same finding.
        old = self._report([("content", "medium", "Thin content (210 words)")])
        new = self._report([("content", "high", "Thin content (95 words)")])
        d = self.diff.diff_reports(old, new)
        self.assertEqual(d["added"], [])
        self.assertEqual(d["resolved"], [])
        self.assertEqual(len(d["worsened"]), 1)
        self.assertEqual(d["worsened"][0]["from"], "medium")
        self.assertEqual(d["worsened"][0]["to"], "high")

    def test_improvement_is_not_a_regression(self):
        old = self._report([("technical", "high", "Meta description missing")])
        new = self._report([])
        d = self.diff.diff_reports(old, new)
        self.assertFalse(d["regression"])
        self.assertEqual(len(d["resolved"]), 1)
        self.assertIn("Improved", self.diff._verdict(d))

    def test_regression_on_score_drop_without_new_high(self):
        old = self._report([("geo", "low", "No llms.txt")])
        new = self._report([("geo", "low", "No llms.txt"),
                            ("content", "medium", "Thin content")])
        d = self.diff.diff_reports(old, new)
        self.assertTrue(d["regression"])          # score dropped (added medium)
        self.assertEqual(d["new_critical_high"], [])

    def test_accepts_audit_shape_json(self):
        old = {"site": "https://x.com", "overall_score": 60,
               "homepage": {"url": "https://x.com", "score": 60,
                            "findings": [{"category": "technical",
                                          "severity": "high",
                                          "title": "Meta description missing"}]}}
        new = {"site": "https://x.com", "overall_score": 72,
               "homepage": {"url": "https://x.com", "score": 72, "findings": []}}
        d = self.diff.diff_reports(old, new)
        self.assertEqual(d["score_delta"], 12)
        self.assertEqual(len(d["resolved"]), 1)

    def test_unrecognized_json_raises(self):
        with self.assertRaises(ValueError):
            self.diff._normalize({"nope": 1})

    def test_render_markdown_smoke(self):
        old = self._report([("technical", "high", "Meta description missing")])
        new = self._report([("schema", "critical", "Broken JSON-LD")])
        md = self.diff.render_markdown(self.diff.diff_reports(old, new))
        self.assertIn("Narwhal Scan Diff", md)
        self.assertIn("New findings", md)
        self.assertIn("Resolved", md)


class TestCruxVitals(unittest.TestCase):
    def setUp(self):
        import crux
        self.crux = crux

    def _record(self, lcp=2100, inp=180, cls="0.05", ttfb=900):
        return {"metrics": {
            "largest_contentful_paint": {"percentiles": {"p75": lcp}},
            "interaction_to_next_paint": {"percentiles": {"p75": inp}},
            "cumulative_layout_shift": {"percentiles": {"p75": cls}},
            "experimental_time_to_first_byte": {"percentiles": {"p75": ttfb}},
        }, "collectionPeriod": {"lastDate": {"year": 2026, "month": 6, "day": 28}}}

    def test_thresholds(self):
        self.assertEqual(self.crux.rate(2500, 4000, 2100), "good")
        self.assertEqual(self.crux.rate(2500, 4000, 3000), "needs-improvement")
        self.assertEqual(self.crux.rate(2500, 4000, 5000), "poor")

    def test_all_good_passes_cwv(self):
        p = self.crux.parse_record(self._record())
        self.assertTrue(p["cwv_pass"])
        self.assertEqual(p["period"], "2026-06-28")
        core = {r["metric"]: r["rating"] for r in p["rows"] if r["core"]}
        self.assertEqual(core, {"LCP": "good", "INP": "good", "CLS": "good"})

    def test_one_poor_core_fails_cwv(self):
        p = self.crux.parse_record(self._record(lcp=5000))
        self.assertFalse(p["cwv_pass"])

    def test_missing_core_metric_is_incomplete(self):
        rec = self._record()
        del rec["metrics"]["interaction_to_next_paint"]
        p = self.crux.parse_record(rec)
        self.assertIsNone(p["cwv_pass"])   # can't confirm without INP

    def test_cls_string_p75_is_coerced(self):
        p = self.crux.parse_record(self._record(cls="0.24"))
        cls = [r for r in p["rows"] if r["metric"] == "CLS"][0]
        self.assertEqual(cls["rating"], "needs-improvement")
        self.assertAlmostEqual(cls["p75"], 0.24)

    def test_render_markdown_not_found(self):
        md = self.crux.render_markdown(
            {"found": False, "target": "https://x.com/", "error": "no data"})
        self.assertIn("Core Web Vitals", md)
        self.assertIn("no data", md)

    def test_main_requires_key(self):
        import contextlib
        import io
        import unittest.mock
        from lib import env as envlib
        # Hermetic: no ambient key AND no .env discovered anywhere up the tree.
        with unittest.mock.patch.dict(os.environ, {}, clear=False), \
                unittest.mock.patch.object(envlib, "find_dotenv", return_value=None):
            os.environ.pop("CRUX_API_KEY", None)
            with contextlib.redirect_stderr(io.StringIO()):
                rc = self.crux.main(["https://example.com"])
        self.assertEqual(rc, 2)


class TestEnvLoader(unittest.TestCase):
    def setUp(self):
        from lib import env
        self.env = env

    def _write_env(self, text):
        import tempfile
        d = tempfile.mkdtemp()
        with open(os.path.join(d, ".env"), "w", encoding="utf-8") as fh:
            fh.write(text)
        return os.path.join(d, ".env")

    def test_resolve_prefers_cli_then_env_then_dotenv(self):
        import unittest.mock
        path = self._write_env("CRUX_API_KEY=from_dotenv\n")
        with unittest.mock.patch.object(self.env, "find_dotenv", return_value=path):
            with unittest.mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("CRUX_API_KEY", None)
                # CLI value wins outright
                self.assertEqual(self.env.resolve("CRUX_API_KEY", "cli"), "cli")
                # env var beats .env
                os.environ["CRUX_API_KEY"] = "from_env"
                self.assertEqual(self.env.resolve("CRUX_API_KEY", None), "from_env")
                # .env used only when neither present
                os.environ.pop("CRUX_API_KEY", None)
                self.assertEqual(self.env.resolve("CRUX_API_KEY", None), "from_dotenv")

    def test_load_dotenv_parsing(self):
        import unittest.mock
        path = self._write_env(
            "# a comment\n\nexport CRUX_API_KEY = 'quoted value'\n"
            "PLAIN=bare\nNOEQ line\n")
        with unittest.mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CRUX_API_KEY", None)
            os.environ.pop("PLAIN", None)
            loaded = self.env.load_dotenv(path)
        self.assertEqual(loaded.get("CRUX_API_KEY"), "quoted value")  # export+quotes stripped
        self.assertEqual(loaded.get("PLAIN"), "bare")
        self.assertNotIn("NOEQ", loaded)                              # malformed line ignored

    def test_existing_env_not_overridden_by_default(self):
        import unittest.mock
        path = self._write_env("CRUX_API_KEY=from_dotenv\n")
        with unittest.mock.patch.dict(os.environ, {}, clear=False):
            os.environ["CRUX_API_KEY"] = "already_set"
            self.env.load_dotenv(path)
            self.assertEqual(os.environ["CRUX_API_KEY"], "already_set")
            self.env.load_dotenv(path, override=True)
            self.assertEqual(os.environ["CRUX_API_KEY"], "from_dotenv")


class TestParserNestedCaptures(unittest.TestCase):
    """Regression tests for the stdlib parser bugs found tuning on real sites
    (#19): nested captures lost headings, and anchor text vanished from the
    visible text — making link-heavy pages look falsely thin."""

    def test_heading_wrapping_a_link_is_recorded(self):
        # jvns.ca pattern: <h1><a href="/">Julia Evans</a></h1> lost the H1.
        d = htmlx.parse('<h1><a href="/">Julia Evans</a></h1><p>hi</p>', base_url="x")
        self.assertIn((1, "Julia Evans"), d.headings)
        self.assertEqual([l.text for l in d.links], ["Julia Evans"])

    def test_anchor_text_counts_as_visible_text(self):
        # HN pattern: story titles are links; they are page content.
        d = htmlx.parse('<p><a href="/s/1">A very newsworthy story</a> 264 points</p>',
                        base_url="x")
        self.assertIn("A very newsworthy story", d.text)
        self.assertIn("264 points", d.text)

    def test_title_text_stays_out_of_body_text(self):
        d = htmlx.parse("<title>Head Title</title><p>body copy</p>", base_url="x")
        self.assertEqual(d.title, "Head Title")
        self.assertNotIn("Head Title", d.text)


class TestPageTypeHelpers(unittest.TestCase):
    def test_hub_page_detection(self):
        links = "".join(f'<a href="/{i}">story number {i} headline</a> ' for i in range(20))
        hub = htmlx.parse(f"<body>{links}</body>", base_url="https://x.com/")
        self.assertTrue(htmlx.is_hub_page(hub))
        prose = htmlx.parse("<p>" + "word " * 300 + '</p><a href="/">home</a>',
                            base_url="https://x.com/a")
        self.assertFalse(htmlx.is_hub_page(prose))

    def test_looks_article(self):
        art = htmlx.parse('<meta property="og:type" content="article"><p>x</p>',
                          base_url="x")
        self.assertTrue(htmlx.looks_article(art))
        single = htmlx.parse("<article><p>x</p></article>", base_url="x")
        self.assertTrue(htmlx.looks_article(single))
        listing = htmlx.parse("<article>a</article><article>b</article>", base_url="x")
        self.assertFalse(htmlx.looks_article(listing))
        plain = htmlx.parse("<p>x</p>", base_url="x")
        self.assertFalse(htmlx.looks_article(plain))

    def test_is_homepage(self):
        self.assertTrue(htmlx.is_homepage(htmlx.parse("", base_url="https://x.com/")))
        self.assertFalse(htmlx.is_homepage(htmlx.parse("", base_url="https://x.com/blog/a")))


class TestPageTypeAwareChecks(unittest.TestCase):
    """The false-positive fixes from the 8-site real-world tuning sweep (#19)."""

    def _scan_page(self, html, url="https://x.com/page"):
        doc = htmlx.parse(html, base_url=url)
        rep = Report(url)
        resp = http.Response(url, url, 200, {}, html, 1)
        return doc, resp, rep

    def test_brand_homepage_title_is_low_not_high(self):
        doc, resp, rep = self._scan_page("<title>The Verge</title>",
                                         url="https://x.com/")
        audit_technical.audit(doc, resp, rep, {})
        sev = {f.title: f.severity for f in rep.findings}
        self.assertEqual(sev.get("Homepage title is just the brand"), "low")
        self.assertNotIn("Title is very short", sev)

    def test_short_title_on_inner_page_still_high(self):
        doc, resp, rep = self._scan_page("<title>Hi</title>",
                                         url="https://x.com/blog/post")
        audit_technical.audit(doc, resp, rep, {})
        sev = {f.title: f.severity for f in rep.findings}
        self.assertEqual(sev.get("Title is very short"), "high")

    def test_hub_page_thin_content_is_low(self):
        links = "".join(f'<a href="/{i}">interesting story {i}</a> ' for i in range(30))
        doc, resp, rep = self._scan_page(f"<body>{links}</body>")
        audit_content.audit(doc, resp, rep, {})
        sev = {f.title: f.severity for f in rep.findings}
        self.assertEqual(sev.get("Link-hub page with little prose"), "low")
        self.assertNotIn("Thin content", sev)

    def test_prose_page_thin_content_still_high(self):
        doc, resp, rep = self._scan_page("<p>just a few words here</p>")
        audit_content.audit(doc, resp, rep, {})
        sev = {f.title: f.severity for f in rep.findings}
        self.assertEqual(sev.get("Thin content"), "high")

    def test_byline_only_flagged_on_articles(self):
        # non-article: no byline finding at all
        doc, resp, rep = self._scan_page("<p>" + "word " * 400 + "</p>")
        audit_content.audit(doc, resp, rep, {})
        self.assertNotIn("No visible author/byline", {f.title for f in rep.findings})
        # article: still flagged medium
        html = '<meta property="og:type" content="article"><p>' + "word " * 400 + "</p>"
        doc, resp, rep = self._scan_page(html)
        audit_content.audit(doc, resp, rep, {})
        sev = {f.title: f.severity for f in rep.findings}
        self.assertEqual(sev.get("No visible author/byline"), "medium")

    def test_geo_question_headings_low_on_non_article(self):
        html = "<h2>Pricing</h2><h2>Features</h2><h2>Customers</h2><h2>Docs</h2><h2>Blog</h2>"
        doc, resp, rep = self._scan_page(html)
        audit_geo.audit(doc, resp, rep, {})
        sev = {f.title: f.severity for f in rep.findings}
        self.assertEqual(sev.get("Few question-based headings"), "low")

    def test_month_tokens_are_not_dominant_topics(self):
        # Archive pages full of dates reported "dec (78), jan (74)" as topics.
        kws = textlib.top_keywords(
            "dec jan nov dec jan nov debugging debugging networking "
            "networking networking linux linux", 5)
        names = [k for k, _ in kws]
        self.assertNotIn("dec", names)
        self.assertNotIn("jan", names)
        self.assertIn("networking", names)

    def test_geo_question_headings_medium_on_article(self):
        html = ('<meta property="og:type" content="article">'
                "<h2>Overview</h2><h2>Details</h2><h2>Setup</h2><h2>Usage</h2><h2>Notes</h2>")
        doc, resp, rep = self._scan_page(html)
        audit_geo.audit(doc, resp, rep, {})
        sev = {f.title: f.severity for f in rep.findings}
        self.assertEqual(sev.get("Few question-based headings"), "medium")


class TestHreflang(unittest.TestCase):
    """Offline tests for cross-page hreflang validation (#25)."""

    def _alts(self, *pairs):
        return [{"lang": l, "href": h} for l, h in pairs]

    def test_valid_codes(self):
        from lib import hreflang
        for good in ("en", "en-GB", "zh-Hans", "zh-Hans-CN", "es-419", "x-default"):
            self.assertTrue(hreflang.valid_code(good), good)
        for bad in ("english", "en_US", "e", "en-GBR-x"):
            self.assertFalse(hreflang.valid_code(bad), bad)

    def test_extract_resolves_relative(self):
        from lib import hreflang
        doc = htmlx.parse('<link rel="alternate" hreflang="fr" href="/fr/">',
                          base_url="https://x.com/en/")
        self.assertEqual(hreflang.extract(doc, "https://x.com/en/"),
                         [{"lang": "fr", "href": "https://x.com/fr/"}])

    def test_reciprocal_cluster_is_clean(self):
        from lib import hreflang
        en = self._alts(("en", "https://x.com/en/"), ("fr", "https://x.com/fr/"),
                        ("x-default", "https://x.com/en/"))
        fr = self._alts(("fr", "https://x.com/fr/"), ("en", "https://x.com/en/"))
        r = hreflang.analyze({"https://x.com/en/": en, "https://x.com/fr/": fr})
        self.assertEqual(r["missing_return"], [])
        self.assertEqual(r["missing_self"], [])
        self.assertTrue(r["has_x_default"])
        self.assertEqual(r["unverified_targets"], 0)

    def test_missing_return_named_precisely(self):
        from lib import hreflang
        en = self._alts(("en", "https://x.com/en/"), ("fr", "https://x.com/fr/"))
        fr = self._alts(("fr", "https://x.com/fr/"))   # no link back to /en/
        r = hreflang.analyze({"https://x.com/en/": en, "https://x.com/fr/": fr})
        self.assertEqual(len(r["missing_return"]), 1)
        m = r["missing_return"][0]
        self.assertEqual((m["page"], m["target"]),
                         ("https://x.com/en/", "https://x.com/fr/"))
        self.assertEqual(r["missing_self"], [])   # both pages list themselves

    def test_unverified_outside_sample(self):
        from lib import hreflang
        en = self._alts(("en", "https://x.com/en/"), ("de", "https://x.com/de/"))
        r = hreflang.analyze({"https://x.com/en/": en})
        self.assertEqual(r["unverified_targets"], 1)   # /de/ was never seen
        self.assertEqual(r["missing_return"], [])       # never reported broken

    def test_probe_fetches_same_host_alternates(self):
        from lib import hreflang
        pages = {"https://x.com/en/": self._alts(
            ("fr", "https://x.com/fr/"), ("ja", "https://other.com/ja/"))}
        fetched = []

        def fake_fetch(u):
            fetched.append(u)
            return '<link rel="alternate" hreflang="en" href="https://x.com/en/">'

        probed = hreflang.probe(pages, fetch_text=fake_fetch)
        self.assertEqual(fetched, ["https://x.com/fr/"])    # same-host only
        self.assertIn("https://x.com/fr/", probed)

    def test_render_reports_pairs_and_honesty(self):
        from lib import hreflang
        en = self._alts(("en", "https://x.com/en/"), ("fr", "https://x.com/fr/"),
                        ("it", "https://x.com/it/"))
        fr = self._alts(("fr", "https://x.com/fr/"))
        r = hreflang.analyze({"https://x.com/en/": en, "https://x.com/fr/": fr})
        md = "\n".join(hreflang.render_markdown(r))
        self.assertIn("Missing return tags", md)
        self.assertIn("https://x.com/en/ → https://x.com/fr/", md)
        self.assertIn("unverified**, not", md)              # /it/ outside sample


class TestImageChecks(unittest.TestCase):
    """Offline tests for image weight/format + og:image validation (#24)."""

    @staticmethod
    def _png(w, h):
        import struct
        return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
                + struct.pack(">II", w, h) + b"\x08\x02\x00\x00\x00")

    def test_probe_dimensions_formats(self):
        import struct
        from lib import images
        self.assertEqual(images.probe_dimensions(self._png(1200, 630)), (1200, 630))
        gif = b"GIF89a" + struct.pack("<HH", 320, 240) + b"\x00" * 20
        self.assertEqual(images.probe_dimensions(gif), (320, 240))
        jpeg = (b"\xff\xd8" + b"\xff\xe0\x00\x10" + b"JFIF\x00" + b"\x00" * 10
                + b"\xff\xc0\x00\x11\x08" + struct.pack(">HH", 630, 1200)
                + b"\x03" + b"\x00" * 10)
        self.assertEqual(images.probe_dimensions(jpeg), (1200, 630))
        webpx = (b"RIFF\x00\x00\x00\x00WEBPVP8X" + b"\x00" * 8
                 + (799).to_bytes(3, "little") + (419).to_bytes(3, "little"))
        self.assertEqual(images.probe_dimensions(webpx), (800, 420))
        self.assertIsNone(images.probe_dimensions(b"not an image at all......"))

    def _facts(self, html, head_map, og_bytes=b""):
        """Run audit_images with injected (offline) network functions."""
        from lib import images
        doc = htmlx.parse(html, base_url="https://x.com/")

        def fake_head(url, **kw):
            return head_map.get(url, (404, {}, None))

        def fake_range(url, n, **kw):
            return og_bytes[:n], None

        return images.audit_images(doc, "https://x.com/",
                                   head_info=fake_head, fetch_range=fake_range)

    def test_heavy_and_legacy_images_flagged(self):
        html = ('<img src="/hero.jpg"><img src="/big.png" width="1" height="1">'
                '<img src="/ok.webp" width="1" height="1">')
        head = {
            "https://x.com/hero.jpg": (200, {"content-length": str(600 * 1024),
                                             "content-type": "image/jpeg"}, None),
            "https://x.com/big.png": (200, {"content-length": str(250 * 1024),
                                            "content-type": "image/png"}, None),
            "https://x.com/ok.webp": (200, {"content-length": str(40 * 1024),
                                            "content-type": "image/webp"}, None),
        }
        facts = self._facts(html, head)
        rep = Report("u")
        from lib import images
        images.findings(facts, rep)
        sev = {f.title: f.severity for f in rep.findings}
        heavy_titles = [t for t in sev if t.startswith("Heavy images")]
        self.assertTrue(heavy_titles and sev[heavy_titles[0]] == "medium")  # 600KB
        legacy = [t for t in sev if t.startswith("Legacy image formats")]
        self.assertTrue(legacy and sev[legacy[0]] == "low")

    def test_missing_dimensions_flagged(self):
        html = '<img src="/a.png"><img src="/b.png"><img src="/c.png">'
        facts = self._facts(html, {})
        rep = Report("u")
        from lib import images
        images.findings(facts, rep)
        self.assertIn("Images without width/height attributes",
                      {f.title for f in rep.findings})

    def test_og_image_broken_and_too_small(self):
        from lib import images
        html = '<meta property="og:image" content="/og.png">'
        # broken (404)
        facts = self._facts(html, {"https://x.com/og.png": (404, {}, None)})
        rep = Report("u")
        images.findings(facts, rep)
        self.assertEqual({f.title: f.severity for f in rep.findings}
                         .get("og:image is broken"), "high")
        # reachable but tiny (100x100 png)
        facts = self._facts(html, {"https://x.com/og.png":
                                   (200, {"content-type": "image/png"}, None)},
                            og_bytes=self._png(100, 100))
        rep = Report("u")
        images.findings(facts, rep)
        self.assertEqual({f.title: f.severity for f in rep.findings}
                         .get("og:image is too small"), "medium")
        # healthy 1200x630
        facts = self._facts(html, {"https://x.com/og.png":
                                   (200, {"content-type": "image/png"}, None)},
                            og_bytes=self._png(1200, 630))
        rep = Report("u")
        images.findings(facts, rep)
        self.assertIn("og:image looks healthy", {f.title for f in rep.findings})


class TestJsDependence(unittest.TestCase):
    """Offline tests for the raw-vs-rendered JS-dependence diff (#23)."""

    RAW = "<title>T</title><h1>Shell</h1><p>server text here</p>"
    RENDERED = ("<title>T</title><meta name=\"description\" content=\"injected\">"
                "<link rel=\"canonical\" href=\"https://x.com/p\">"
                "<script type=\"application/ld+json\">{}</script>"
                "<h1>Shell</h1><h2>Loaded by JS</h2><p>server text here "
                + "client rendered word " * 30 + "</p>")

    def test_analyze_measures_delta(self):
        from lib import jsdiff
        dep = jsdiff.analyze(self.RAW, self.RENDERED, "https://x.com/p")
        self.assertGreaterEqual(dep["js_only_pct"], 90)
        self.assertIn("Loaded by JS", dep["js_only_headings"])
        m = dep["meta_js_only"]
        self.assertTrue(m["description"] and m["canonical"] and m["jsonld"])
        self.assertFalse(m["title"])          # title exists in both

    def test_identical_documents_are_zero(self):
        from lib import jsdiff
        dep = jsdiff.analyze(self.RAW, self.RAW, "https://x.com/p")
        self.assertEqual(dep["js_only_pct"], 0)
        self.assertEqual(dep["js_only_headings"], [])
        self.assertFalse(any(dep["meta_js_only"].values()))

    def test_technical_findings_tiered(self):
        from lib import jsdiff
        rep = Report("u")
        jsdiff.technical_findings(
            jsdiff.analyze(self.RAW, self.RENDERED, "u"), rep)
        sev = {f.title: f.severity for f in rep.findings}
        self.assertEqual(sev.get("Most content requires JavaScript"), "high")
        self.assertEqual(sev.get("Head metadata injected by JavaScript"), "high")
        self.assertEqual(sev.get("JSON-LD injected by JavaScript"), "medium")
        # low-JS page -> passing note instead
        rep2 = Report("u")
        jsdiff.technical_findings(jsdiff.analyze(self.RAW, self.RAW, "u"), rep2)
        self.assertIn("Content is server-rendered",
                      {f.title for f in rep2.findings})

    def test_geo_finding_only_when_heavy(self):
        from lib import jsdiff
        rep = Report("u")
        jsdiff.geo_finding(jsdiff.analyze(self.RAW, self.RENDERED, "u"), rep)
        self.assertIn("AI answer engines may not see this content",
                      {f.title for f in rep.findings})
        rep2 = Report("u")
        jsdiff.geo_finding(jsdiff.analyze(self.RAW, self.RAW, "u"), rep2)
        self.assertEqual(rep2.findings, [])

    def test_auditors_silent_without_jsdep(self):
        # No --render measurement -> ctx has no jsdep -> no JS findings at all.
        doc = htmlx.parse(self.RAW, base_url="https://x.com/p")
        rep = Report("u")
        resp = http.Response("u", "u", 200, {}, self.RAW, 1)
        audit_technical.audit(doc, resp, rep, {})
        audit_geo.audit(doc, resp, rep, {})
        titles = {f.title for f in rep.findings}
        self.assertFalse(any("JavaScript" in t for t in titles))


class TestSiteGraph(unittest.TestCase):
    """Offline tests for the site-structure analysis (#22)."""

    def _links(self, *urls):
        return [{"url": u, "internal": True} for u in urls]

    def _graph(self, sitemap_found=True, sitemap_urls=None):
        from lib import sitegraph
        base = "https://x.com/"
        # chain: base -> a -> b -> c -> d (depth 4); e crawled but never linked
        crawled = [base] + [f"https://x.com/{p}" for p in ("a", "b", "c", "d", "e")]
        pages_links = {
            base: self._links("https://x.com/a"),
            "https://x.com/a": self._links("https://x.com/b"),
            "https://x.com/b": self._links("https://x.com/c"),
            "https://x.com/c": self._links("https://x.com/d",
                                           "https://x.com/uncrawled"),
            "https://x.com/d": [{"url": "https://elsewhere.com/", "internal": False}],
            "https://x.com/e": [],
        }
        return sitegraph.analyze(
            base, crawled, pages_links,
            sitemap_urls if sitemap_urls is not None else crawled
            + ["https://x.com/orphan"],
            sitemap_found)

    def test_click_depth_and_deep_pages(self):
        g = self._graph()
        self.assertEqual(g["max_depth"], 4)
        self.assertEqual([p["url"] for p in g["deep_pages"]], ["https://x.com/d"])

    def test_unreachable_and_zero_inbound(self):
        g = self._graph()
        self.assertEqual(g["unreachable_from_start"], ["https://x.com/e"])
        self.assertEqual(g["zero_inbound"], ["https://x.com/e"])   # base excluded

    def test_orphan_candidates_only_with_sitemap(self):
        g = self._graph()
        self.assertTrue(g["orphans"]["checked"])
        self.assertEqual(g["orphans"]["candidates"], ["https://x.com/orphan"])
        # /uncrawled was linked from /c, so it is NOT an orphan candidate
        g2 = self._graph(sitemap_found=False)
        self.assertFalse(g2["orphans"]["checked"])
        self.assertEqual(g2["orphans"]["candidates"], [])

    def test_trailing_slash_and_fragment_are_one_node(self):
        from lib import sitegraph
        base = "https://x.com/"
        crawled = [base, "https://x.com/a/"]
        pages_links = {base: [{"url": "https://x.com/a#section", "internal": True}]}
        g = sitegraph.analyze(base, crawled, pages_links, [], False)
        self.assertEqual(g["unreachable_from_start"], [])   # /a/ == /a#section
        self.assertEqual(g["max_depth"], 1)

    def test_render_markdown_states_sample_size(self):
        from lib import sitegraph
        md = "\n".join(sitegraph.render_markdown(self._graph(), sitemap_total=7))
        self.assertIn("Site structure (6 crawled pages", md)
        self.assertIn("Orphan candidates", md)
        self.assertIn("crawl sample", md)                  # honesty note
        self.assertIn("Raise `--max-pages`", md)


class TestCompare(unittest.TestCase):
    """Offline tests for `narwhal compare` (#21): facts extraction, gap
    analysis, and rendering — everything except the network fetch."""

    RIVAL = """
    <html><head><title>Complete guide to widget calibration (2026)</title>
    <meta name="description" content="A thorough, evidence-backed guide to calibrating widgets, with data.">
    <meta property="og:title" content="t"><meta property="og:description" content="d">
    <meta property="og:image" content="i"><meta name="twitter:card" content="summary">
    <meta name="author" content="Jane"><meta property="article:published_time" content="2026-01-01">
    <link rel="canonical" href="https://rival.com/guide">
    <script type="application/ld+json">{"@type":"Article","headline":"x"}</script>
    <script type="application/ld+json">{"@graph":[{"@type":"FAQPage"},{"@type":"Organization"}]}</script>
    </head><body><h1>Guide</h1><h2>What is calibration?</h2><h2>How do you calibrate?</h2>
    <p>According to a 2026 study, 45% of widgets drift. """ + "calibration detail word " * 200 + """</p>
    </body></html>"""

    YOURS = """
    <html><head><title>Widgets</title></head>
    <body><h1>Widgets</h1><h2>Overview</h2><p>""" + "brief text word " * 40 + "</p></body></html>"

    def _facts(self, html, url):
        import compare
        doc = htmlx.parse(html, base_url=url)
        rep = Report(url, final_url=url, fetched_status=200)
        resp = http.Response(url, url, 200, {}, html, 1)
        for fn in (audit_technical.audit, audit_content.audit,
                   audit_schema.audit, audit_geo.audit):
            fn(doc, resp, rep, {})
        return compare.facts(rep, doc)

    def test_facts_extraction(self):
        f = self._facts(self.RIVAL, "https://rival.com/guide")
        self.assertEqual(f["schema_types"], ["Article", "FAQPage", "Organization"])
        self.assertTrue(f["og_complete"] and f["twitter_card"] and f["canonical"])
        self.assertTrue(f["author_signal"] and f["date_signal"])
        self.assertEqual(f["question_ratio"], 1.0)     # both H2s are questions
        self.assertGreater(f["meta_desc_len"], 0)
        self.assertGreater(f["stats_cites"], 0)         # "45%" + "according to"

    def test_gap_analysis_finds_their_advantages(self):
        import compare
        you = self._facts(self.YOURS, "https://you.com/widgets")
        rival = self._facts(self.RIVAL, "https://rival.com/guide")
        r = compare.gap_analysis(you, [rival])
        whats = {g["what"] for g in r["gaps"]}
        self.assertIn("Meta description", whats)
        self.assertTrue(any(w.startswith("Schema types:") and "FAQPage" in w
                        for w in whats))
        self.assertIn("Content depth", whats)
        self.assertIn("Question-based headings", whats)
        self.assertIn("Complete Open Graph tags", whats)

    def test_gap_analysis_reports_your_leads(self):
        import compare
        you = self._facts(self.RIVAL, "https://you.com/guide")     # you are strong
        rival = self._facts(self.YOURS, "https://rival.com/weak")  # rival is weak
        r = compare.gap_analysis(you, [rival])
        self.assertEqual(r["gaps"], [])   # nothing they have that you don't
        lead_whats = " ".join(l["what"] for l in r["leads"])
        self.assertIn("Meta description", lead_whats)
        self.assertIn("Schema types only you have", lead_whats)

    def test_render_markdown_shape(self):
        import compare
        you = self._facts(self.YOURS, "https://you.com/widgets")
        rival = self._facts(self.RIVAL, "https://rival.com/guide")
        md = compare.render_markdown(
            {"failed": [], "you": you, "competitors": [rival],
             **compare.gap_analysis(you, [rival])})
        self.assertIn("## Scoreboard", md)
        self.assertIn("## Side by side", md)
        self.assertIn("## Gaps to close", md)
        self.assertIn("not proof of why anyone ranks", md)   # honesty footer

    def test_main_requires_two_urls(self):
        import contextlib
        import io
        import compare
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(compare.main(["https://only-one.com"]), 2)

    def test_one_dead_url_does_not_sink_the_run(self):
        # Live testing found an unresolvable competitor host raised SSRFError
        # and crashed the whole comparison — it must be skipped instead.
        import unittest.mock
        import compare

        def fake_scan(url, **kw):
            if "dead" in url:
                raise http.SSRFError("Cannot resolve host")
            doc = htmlx.parse("<title>Fine page title here</title><h1>ok</h1>"
                              "<p>" + "word " * 350 + "</p>", base_url=url)
            rep = Report(url, final_url=url, fetched_status=200)
            rep._doc = doc
            return rep

        with unittest.mock.patch.object(compare.scanner, "scan", fake_scan):
            r = compare.run(["https://you.com", "https://dead.example",
                             "https://rival.com"])
        self.assertEqual(len(r["failed"]), 1)
        self.assertNotIn("error", r)                 # compare still ran
        self.assertEqual(r["you"]["url"], "https://you.com")
        self.assertEqual(len(r["competitors"]), 1)


class TestRenderReport(unittest.TestCase):
    def setUp(self):
        import render_report
        self.rr = render_report

    def test_renders_branded_self_contained_html(self):
        html = self.rr.render("# My Audit\n\nSome **bold** text.", subtitle="https://x.com")
        self.assertTrue(html.lstrip().startswith("<!DOCTYPE html>"))
        self.assertIn('<header class="brand">', html)          # branded
        self.assertIn("data:image/png;base64,", html)          # inline logo
        self.assertIn("<strong>bold</strong>", html)
        self.assertNotIn("<script", html)

    def test_first_h1_becomes_title_and_leaves_body(self):
        html = self.rr.render("# Narwhal Site Audit\n\n## Summary\n\nBody.")
        self.assertIn("Narwhal Site Audit", html)              # used as the title
        self.assertNotIn("# Narwhal Site Audit", html)          # H1 removed from body
        self.assertIn("<h2>Summary</h2>", html)                 # rest of body intact

    def test_explicit_title_overrides(self):
        html = self.rr.render("# Ignored\n\nBody.", title="Custom Title")
        self.assertIn("Custom Title", html)

    def test_markdown_links_render(self):
        html = self.rr.render("See [the docs](https://example.com/docs).")
        self.assertIn('<a href="https://example.com/docs">the docs</a>', html)


class TestAuditVitals(unittest.TestCase):
    def _data(self, vitals):
        from collections import Counter
        page = Report("https://x.com", final_url="https://x.com", fetched_status=200)
        page.add("technical", "high", "Meta description missing")
        return {
            "site": "https://x.com", "page": page,
            "site_result": {"base": "https://x.com", "avg_score": 72,
                            "pages_scanned": 2, "pages": [], "recurring": Counter(),
                            "links": {"broken": [], "checked": 3, "skipped_over_cap": 0},
                            "duplicates": []},
            "sitemap": {"start": "https://x.com", "seeds": []},
            "vitals": vitals,
        }

    def test_field_vitals_in_all_formats(self):
        import json
        field = {"found": True, "target": "origin https://x.com", "form_factor": None,
                 "cwv_pass": True, "period": "2026-06-28",
                 "rows": [{"metric": "LCP", "key": "largest_contentful_paint",
                           "unit": "ms", "p75": 2100.0, "rating": "good", "core": True}]}
        data = self._data({"field": field, "lab": None})
        md = audit_mod.render_markdown(data)
        self.assertIn("## 4. Core Web Vitals", md)
        self.assertIn("CWV (field): pass", md)
        self.assertIn("Core Web Vitals", audit_mod.render_html(data))
        self.assertEqual(json.loads(audit_mod.render_json(data))["vitals"]["field"]["cwv_pass"], True)

    def test_lab_fallback_when_no_field(self):
        lab = {"found": True, "url": "https://x.com", "strategy": "mobile",
               "perf_score": 83, "perf_rating": "needs-improvement",
               "rows": [{"metric": "LCP", "id": "largest-contentful-paint",
                         "unit": "ms", "value": 2600.0, "display": "2.6 s",
                         "rating": "needs-improvement", "core": True}],
               "lighthouse_version": "11"}
        data = self._data({"field": {"found": False, "error": "no data"}, "lab": lab})
        md = audit_mod.render_markdown(data)
        self.assertIn("Perf (lab): 83/100", md)
        self.assertIn("lab", md.lower())

    def test_no_vitals_key_means_no_section(self):
        data = self._data(None)
        del data["vitals"]
        self.assertNotIn("Core Web Vitals", audit_mod.render_markdown(data))


class TestPsiLab(unittest.TestCase):
    def setUp(self):
        import psi
        self.psi = psi

    def _lhr(self, score=0.87, lcp=2100, tbt=150, cls=0.05):
        return {"lighthouseVersion": "11.0",
                "categories": {"performance": {"score": score}},
                "audits": {
                    "largest-contentful-paint": {"numericValue": lcp, "displayValue": "2.1 s"},
                    "total-blocking-time": {"numericValue": tbt, "displayValue": "150 ms"},
                    "cumulative-layout-shift": {"numericValue": cls, "displayValue": "0.05"},
                    "first-contentful-paint": {"numericValue": 1600, "displayValue": "1.6 s"},
                    "speed-index": {"numericValue": 3000, "displayValue": "3.0 s"},
                    "interactive": {"numericValue": 4200, "displayValue": "4.2 s"},
                }}

    def test_score_bands(self):
        self.assertEqual(self.psi.rate_score(95), "good")
        self.assertEqual(self.psi.rate_score(70), "needs-improvement")
        self.assertEqual(self.psi.rate_score(30), "poor")

    def test_parse_lighthouse(self):
        p = self.psi.parse_lighthouse(self._lhr())
        self.assertEqual(p["perf_score"], 87)             # 0.87 -> 87
        self.assertEqual(p["perf_rating"], "needs-improvement")
        labels = {r["metric"]: r for r in p["rows"]}
        self.assertEqual(labels["LCP"]["rating"], "good")
        self.assertTrue(labels["LCP"]["core"])
        self.assertFalse(labels["FCP"]["core"])           # secondary
        self.assertEqual(len(p["rows"]), 6)

    def test_tbt_thresholds_as_inp_proxy(self):
        p = self.psi.parse_lighthouse(self._lhr(tbt=700))
        tbt = [r for r in p["rows"] if r["metric"] == "TBT"][0]
        self.assertEqual(tbt["rating"], "poor")           # >600ms

    def test_missing_metric_skipped(self):
        lhr = self._lhr()
        del lhr["audits"]["speed-index"]
        p = self.psi.parse_lighthouse(lhr)
        self.assertNotIn("SI", {r["metric"] for r in p["rows"]})

    def test_render_not_found_suggests_key_on_quota(self):
        md = self.psi.render_markdown(
            {"found": False, "url": "https://x.com", "strategy": "mobile",
             "error": "Quota exceeded for quota metric 'Queries'"})
        self.assertIn("PAGESPEED_API_KEY", md)

    def test_crux_no_data_points_to_lab(self):
        import crux
        md = crux.render_markdown(
            {"found": False, "target": "https://x.com/", "error": "no data"})
        self.assertIn("--lab", md)


class TestRenderHardening(unittest.TestCase):
    def test_missing_browser_gives_actionable_hint(self):
        # Playwright installed but Chromium binary absent — the message must tell
        # the user exactly how to fix it, not surface a raw stack string.
        msg = http._browser_launch_hint(
            Exception("Executable doesn't exist at /home/.cache/ms-playwright/..."))
        self.assertIn("playwright install chromium", msg)

    def test_generic_render_error_is_labelled(self):
        msg = http._browser_launch_hint(Exception("some other failure"))
        self.assertIn("Playwright render failed", msg)
        self.assertIn("some other failure", msg)

    def test_chromium_pdf_backend_absent_is_graceful(self):
        # Without Playwright installed, the Chromium backend must return False
        # (not raise), so pdf_from_html can fall through to the HTML fallback.
        try:
            import playwright  # noqa: F401
            self.skipTest("Playwright installed; can't test the absent path")
        except ImportError:
            self.assertFalse(report_lib._pdf_via_chromium("<html></html>", "x.pdf"))

    def test_pdf_from_html_survives_missing_native_libs(self):
        # Simulate WeasyPrint present but its native libs missing (OSError on
        # import) — pdf_from_html must return False, not raise.
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "weasyprint":
                raise OSError("cannot load library 'libgobject-2.0-0'")
            return real_import(name, *a, **k)

        builtins.__import__ = fake_import
        try:
            self.assertFalse(report_lib.pdf_from_html("<html></html>", "x.pdf"))
        finally:
            builtins.__import__ = real_import


class TestMcpServer(unittest.TestCase):
    def setUp(self):
        import mcp_server
        self.m = mcp_server

    def test_tool_names_are_stable(self):
        names = [n for _, n in self.m._TOOLS]
        self.assertEqual(
            set(names),
            {"scan_page", "compare_pages", "crawl_site", "audit_site",
             "validate_sitemap", "generate_llms", "generate_schema",
             "diff_reports"})
        self.assertEqual(len(names), len(set(names)))   # no dupes

    def test_every_tool_has_a_docstring(self):
        # FastMCP surfaces the docstring as the tool description — required.
        for fn, _ in self.m._TOOLS:
            self.assertTrue((fn.__doc__ or "").strip(), fn.__name__)

    def test_schema_tool_offline(self):
        s = self.m._schema("Article", {"headline": "How GEO works"})
        self.assertEqual(s["@type"], "Article")
        self.assertEqual(s["headline"], "How GEO works")

    def test_diff_tool_offline(self):
        import json
        old = json.dumps({"final_url": "https://x.com", "score": 80,
                          "findings": [{"category": "technical", "severity": "high",
                                        "title": "Meta description missing"}]})
        new = json.dumps({"final_url": "https://x.com", "score": 90, "findings": []})
        d = self.m._diff(old, new)
        self.assertEqual(d["score_delta"], 10)
        self.assertEqual(len(d["resolved"]), 1)

    def test_server_builds_when_mcp_present_else_reports_missing(self):
        import contextlib
        import io
        try:
            import mcp.server.fastmcp  # noqa: F401
            have_mcp = True
        except ImportError:
            have_mcp = False
        if have_mcp:
            server = self.m.build_server()
            self.assertEqual(type(server).__name__, "FastMCP")
        else:
            # Graceful path: no `mcp` package -> friendly message, exit 1, no server.
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(self.m.main([]), 1)


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


class TestGscAnalysis(unittest.TestCase):
    """Pure GSC analysis: canned Search Analytics rows in, insights out.

    Row shape mirrors the API: keys=[page, query], clicks, impressions, ctr,
    position. No network anywhere in these tests."""

    def setUp(self):
        import gsc
        self.gsc = gsc

    @staticmethod
    def _row(page, query, clicks, impressions, position):
        return {"keys": [page, query], "clicks": clicks,
                "impressions": impressions,
                "ctr": (clicks / impressions) if impressions else 0.0,
                "position": position}

    def test_striking_distance_selection(self):
        rows = [
            self._row("https://x.com/a", "widget guide", 5, 400, 11.2),   # in
            self._row("https://x.com/b", "widget price", 2, 80, 9.0),     # in
            self._row("https://x.com/c", "widgets", 50, 5000, 3.1),       # pos too good
            self._row("https://x.com/d", "widget kit", 0, 900, 34.0),     # pos too deep
            self._row("https://x.com/e", "buy widget", 0, 10, 12.0),      # too few impressions
        ]
        r = self.gsc.analyze(rows, [])
        picked = [(s["query"], s["page"]) for s in r["striking"]]
        self.assertEqual(picked, [("widget guide", "https://x.com/a"),
                                  ("widget price", "https://x.com/b")])  # impressions desc

    def test_ctr_laggard_needs_low_ctr_and_top10(self):
        rows = [
            # pos 3, CTR 0.5% vs expected ~10% -> laggard
            self._row("https://x.com/lag", "q1", 5, 1000, 3.0),
            # pos 3, healthy CTR -> not a laggard
            self._row("https://x.com/ok", "q2", 100, 1000, 3.0),
            # terrible CTR but pos 15 (not top-10) -> not a laggard
            self._row("https://x.com/deep", "q3", 1, 1000, 15.0),
        ]
        r = self.gsc.analyze(rows, [])
        pages = [entry["page"] for entry in r["laggards"]]
        self.assertEqual(pages, ["https://x.com/lag"])
        self.assertLess(r["laggards"][0]["ctr"],
                        r["laggards"][0]["expected_ctr"] / 2)

    def test_decaying_pages_need_drop_and_floor(self):
        prev = [
            self._row("https://x.com/fall", "q", 100, 2000, 5.0),
            self._row("https://x.com/tiny", "q", 4, 50, 5.0),    # below floor
            self._row("https://x.com/hold", "q", 100, 2000, 5.0),
        ]
        now = [
            self._row("https://x.com/fall", "q", 40, 1800, 6.0),   # -60% clicks
            self._row("https://x.com/tiny", "q", 1, 40, 5.0),      # -75% but tiny
            self._row("https://x.com/hold", "q", 95, 2100, 5.0),   # -5%
        ]
        r = self.gsc.analyze(now, prev)
        self.assertEqual([d["page"] for d in r["decaying"]], ["https://x.com/fall"])
        d = r["decaying"][0]
        self.assertEqual((d["clicks_prev"], d["clicks_now"]), (100, 40))

    def test_cannibalization_two_pages_sharing_a_query(self):
        rows = [
            self._row("https://x.com/a", "red widget", 10, 300, 6.0),
            self._row("https://x.com/b", "red widget", 8, 280, 8.0),
            self._row("https://x.com/a", "solo query", 20, 500, 4.0),  # one page only
            # two pages but second has a negligible share:
            self._row("https://x.com/c", "blue widget", 30, 950, 5.0),
            self._row("https://x.com/d", "blue widget", 0, 20, 40.0),
        ]
        r = self.gsc.analyze(rows, [])
        self.assertEqual([c["query"] for c in r["cannibalization"]], ["red widget"])
        self.assertEqual(len(r["cannibalization"][0]["pages"]), 2)

    def test_summary_totals_and_deltas(self):
        prev = [self._row("https://x.com/a", "q", 50, 1000, 8.0)]
        now = [self._row("https://x.com/a", "q", 80, 1000, 6.0)]
        s = self.gsc.analyze(now, prev)["summary"]
        self.assertEqual((s["clicks"], s["clicks_prev"]), (80, 50))
        self.assertEqual(s["impressions"], 1000)
        self.assertAlmostEqual(s["ctr"], 0.08)
        self.assertAlmostEqual(s["position"], 6.0)

    def test_expected_ctr_is_monotonic_and_clamped(self):
        e = self.gsc.expected_ctr
        self.assertGreater(e(1), e(5))
        self.assertGreater(e(5), e(10))
        self.assertEqual(e(10), e(30))   # clamped past position 10
        self.assertEqual(e(0.5), e(1))   # clamped above position 1

    def test_render_markdown_mentions_every_section(self):
        rows = [self._row("https://x.com/a", "widget guide", 5, 400, 11.2)]
        md = self.gsc.render_markdown(
            {"found": True, "property": "sc-domain:x.com", "days": 28,
             **self.gsc.analyze(rows, rows)}, "https://x.com")
        for needle in ("Striking distance", "heuristic"):
            self.assertIn(needle, md)

    def test_render_markdown_not_found(self):
        md = self.gsc.render_markdown(
            {"found": False, "error": "no matching property"}, "https://x.com")
        self.assertIn("no matching property", md)

    def test_min_impressions_zero_does_not_crash(self):
        rows = [self._row("https://x.com/a", "q", 0, 0, 5.0)]
        r = self.gsc.analyze(rows, rows, min_impressions=0)  # clamped to 1
        self.assertEqual(r["laggards"], [])

    def test_capped_result_is_flagged_in_report(self):
        md = self.gsc.render_markdown(
            {"found": True, "property": "sc-domain:x.com", "days": 28,
             "capped": True, **self.gsc.analyze([], [])}, "https://x.com")
        self.assertIn("row cap", md)


class TestGscProperty(unittest.TestCase):
    def setUp(self):
        import gsc
        self.pick = gsc.pick_property

    SITES = [{"siteUrl": "sc-domain:example.com"},
             {"siteUrl": "https://other.example.org/"},
             {"siteUrl": "https://example.com/blog/"}]

    def test_url_prefix_beats_domain_property(self):
        self.assertEqual(self.pick(self.SITES, "https://example.com/blog/post"),
                         "https://example.com/blog/")

    def test_domain_property_matches_any_scheme_and_www(self):
        self.assertEqual(self.pick(self.SITES, "http://www.example.com/page"),
                         "sc-domain:example.com")

    def test_no_match_returns_none(self):
        self.assertIsNone(self.pick(self.SITES, "https://unrelated.net/"))


class TestGscCli(unittest.TestCase):
    def test_no_credentials_is_honest_exit_2(self):
        import contextlib
        import io
        import gsc
        saved = {k: os.environ.get(k) for k in
                 ("GSC_ACCESS_TOKEN", "GSC_CLIENT_ID", "GSC_CLIENT_SECRET",
                  "GSC_REFRESH_TOKEN")}
        os.environ.update({k: "" for k in saved})  # blank out, incl. any .env
        try:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = gsc.main(["https://example.com"])
            self.assertEqual(rc, 2)
            for needle in ("GSC_ACCESS_TOKEN", "--auth", "GSC_REFRESH_TOKEN"):
                self.assertIn(needle, err.getvalue())
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


class TestAuditGsc(unittest.TestCase):
    def _data(self, gsc_block):
        from collections import Counter
        page = Report("https://x.com", final_url="https://x.com", fetched_status=200)
        data = {
            "site": "https://x.com", "page": page,
            "site_result": {"base": "https://x.com", "avg_score": 72,
                            "pages_scanned": 2, "pages": [], "recurring": Counter(),
                            "links": {"broken": [], "checked": 3, "skipped_over_cap": 0},
                            "duplicates": []},
            "sitemap": {"start": "https://x.com", "seeds": []},
        }
        if gsc_block is not None:
            data["gsc"] = gsc_block
        return data

    def _gsc_block(self):
        import gsc
        row = {"keys": ["https://x.com/a", "widget guide"], "clicks": 5,
               "impressions": 400, "ctr": 0.0125, "position": 11.2}
        return {"found": True, "property": "sc-domain:x.com", "days": 28,
                **gsc.analyze([row], [row])}

    def test_gsc_section_without_vitals_numbers_correctly(self):
        import json
        md = audit_mod.render_markdown(self._data(self._gsc_block()))
        self.assertIn("## 4. Search performance", md)
        self.assertIn("Search performance", audit_mod.render_html(self._data(self._gsc_block())))
        payload = json.loads(audit_mod.render_json(self._data(self._gsc_block())))
        self.assertTrue(payload["gsc"]["found"])

    def test_gsc_after_vitals_is_section_5(self):
        data = self._data(self._gsc_block())
        data["vitals"] = {"field": {"found": False, "target": "origin https://x.com",
                                    "form_factor": None, "error": "no data"},
                          "lab": None}
        md = audit_mod.render_markdown(data)
        self.assertIn("## 4. Core Web Vitals", md)
        self.assertIn("## 5. Search performance", md)

    def test_no_gsc_means_no_section(self):
        self.assertNotIn("Search performance",
                         audit_mod.render_markdown(self._data(None)))


if __name__ == "__main__":
    unittest.main()
