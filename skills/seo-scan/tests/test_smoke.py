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
        # Ensure no ambient key so we exercise the "key required" guard.
        with unittest.mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CRUX_API_KEY", None)
            with contextlib.redirect_stderr(io.StringIO()):
                rc = self.crux.main(["https://example.com"])
        self.assertEqual(rc, 2)


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
            {"scan_page", "crawl_site", "audit_site", "validate_sitemap",
             "generate_llms", "generate_schema", "diff_reports"})
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


if __name__ == "__main__":
    unittest.main()
