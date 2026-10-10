"""Offline tests grouped by area; no network or required third-party dependencies."""

try:
    from ._smoke_support import *  # noqa: F401,F403
except ImportError:  # direct discovery with ``-s tests``
    from _smoke_support import *  # type: ignore  # noqa: F401,F403

import audit_content
import audit_geo
import audit_schema
import audit_technical
import crawl_site
from lib import htmlx, http, links
from lib import sitemap as sm
from lib import text as textlib
from lib.report import Report
from lib.robots import RobotsTxt


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

class TestRound2Tuning(unittest.TestCase):
    """Regression tests for the 2026-07 Round 2 tuning sweep fixes."""

    def test_og_image_rate_limited_is_not_broken(self):
        # A 429 from an image CDN is gating, not a dead og:image.
        from lib import images
        html = '<meta property="og:image" content="/og.png">'
        doc = htmlx.parse(html, base_url="https://x.com/")
        facts = images.audit_images(
            doc, "https://x.com/",
            head_info=lambda u, **kw: (429, {}, None),
            fetch_range=lambda u, n, **kw: (b"", None))
        rep = Report("u")
        images.findings(facts, rep)
        sev = {f.title: f.severity for f in rep.findings}
        self.assertEqual(sev.get("og:image could not be verified"), "low")
        self.assertNotIn("og:image is broken", sev)

    def test_unfetchable_page_scores_zero(self):
        rep = Report("u", hard_fail=True)
        rep.add("technical", "critical", "Page could not be fetched")
        self.assertEqual(rep.score(), 0)

    def test_non_english_page_skips_english_calibrated_checks(self):
        html = ('<html lang="fr"><body><p>'
                + "Ceci est un texte français assez long pour l'analyse. " * 40
                + "</p></body></html>")
        doc = htmlx.parse(html, base_url="https://x.fr/")
        rep = Report("u")
        resp = http.Response("u", "u", 200, {}, html, 1)
        audit_content.audit(doc, resp, rep, {})
        titles = {f.title for f in rep.findings}
        self.assertFalse(any("read" in t.lower() for t in titles))      # no Flesch
        self.assertNotIn("Clean, specific writing", titles)             # no claim
        self.assertNotIn("Filler / padding language", titles)

    def test_very_hard_readability_low_on_non_article(self):
        # dense fragments; guarantee non-hub (few links) and non-article
        dense = ("Infrastructure orchestration automation transformation "
                 "internationalization decentralization synchronization "
                 "implementation. " * 40)
        doc = htmlx.parse(f"<p>{dense}</p>", base_url="https://x.com/pricing")
        rep = Report("u")
        resp = http.Response("u", "u", 200, {}, "", 1)
        audit_content.audit(doc, resp, rep, {})
        sev = {f.title: f.severity for f in rep.findings}
        if "Content is very hard to read" in sev:                       # Flesch<30
            self.assertEqual(sev["Content is very hard to read"], "low")
        art = htmlx.parse('<meta property="og:type" content="article">'
                          f"<p>{dense}</p>", base_url="https://x.com/post")
        rep2 = Report("u")
        audit_content.audit(art, resp, rep2, {})
        sev2 = {f.title: f.severity for f in rep2.findings}
        if "Content is very hard to read" in sev2:
            self.assertEqual(sev2["Content is very hard to read"], "medium")

    def test_heavy_image_with_srcset_is_fallback_weight_low(self):
        # srcset means browsers fetch smaller variants — the raw-src weight is
        # the scraper/fallback path, so the severity caps at low + honest text.
        from lib import images
        html = '<img src="/hero.jpg" srcset="/hero-640.webp 640w" width="1" height="1">'
        doc = htmlx.parse(html, base_url="https://x.com/")
        facts = images.audit_images(
            doc, "https://x.com/",
            head_info=lambda u, **kw: (200, {"content-length": str(900 * 1024),
                                             "content-type": "image/jpeg"}, None),
            fetch_range=lambda u, n, **kw: (b"", None))
        rep = Report("u")
        images.findings(facts, rep)
        heavy = [f for f in rep.findings if f.title.startswith("Heavy images")]
        self.assertEqual(heavy[0].severity, "low")           # 900KB but srcset
        self.assertIn("fallback weight", heavy[0].detail)

    NOSCRIPT_SHELL = ('<title>T</title><body><noscript><main>'
                      '<h1>Real Headline</h1><a href="/x">Real link text</a>'
                      "<p>" + "fallback content word " * 30 + "</p>"
                      '</main></noscript><div id="root"></div></body>')

    def test_noscript_fallback_content_is_measured(self):
        # Live find: a JS-shell site served ALL content inside <noscript> and
        # scanned as "~0 words" with empty headings/links. The fallback is what
        # non-rendering crawlers read — measure it, labeled honestly.
        d = htmlx.parse(self.NOSCRIPT_SHELL, base_url="https://x.com/")
        self.assertEqual(d.text, "")                          # visible text honest
        self.assertGreater(len(d.noscript_text.split()), 50)
        # with trafilatura installed it isolates the same content itself
        self.assertIn(d.extraction,
                      ("noscript fallback", "main-content (trafilatura)"))
        self.assertIn("fallback content", d.body_text)
        self.assertIn((1, "Real Headline"), d.headings)       # not empty-text
        self.assertIn("Real link text", [l.text for l in d.links])

    def test_noscript_only_architecture_finding(self):
        d = htmlx.parse(self.NOSCRIPT_SHELL, base_url="https://x.com/")
        rep = Report("u")
        resp = http.Response("u", "u", 200, {}, "", 1)
        audit_technical.audit(d, resp, rep, {})
        sev = {f.title: f.severity for f in rep.findings}
        self.assertEqual(sev.get("Content served only as a <noscript> fallback"),
                         "medium")
        # normal pages: no such finding
        d2 = htmlx.parse("<p>" + "word " * 100 + "</p>", base_url="https://x.com/")
        rep2 = Report("u")
        audit_technical.audit(d2, resp, rep2, {})
        self.assertNotIn("Content served only as a <noscript> fallback",
                         {f.title for f in rep2.findings})

    def test_font_loader_noscript_does_not_pollute_text(self):
        # The common tiny-noscript case (font CSS fallback) must not change
        # visible-text behavior or fire the architecture finding.
        html = ('<noscript><link rel="stylesheet" href="f.css"></noscript>'
                "<p>" + "regular visible word " * 40 + "</p>")
        d = htmlx.parse(html, base_url="https://x.com/")
        self.assertIn(d.extraction,
                      ("visible text", "main-content (trafilatura)"))
        self.assertNotIn("f.css", d.body_text)

    def test_no_jsonld_low_on_hub_pages(self):
        links_html = "".join(f'<a href="/{i}">interesting story number {i}</a> '
                             for i in range(30))
        hub = htmlx.parse(f"<body>{links_html}</body>", base_url="https://x.com/")
        rep = Report("u")
        resp = http.Response("u", "u", 200, {}, "", 1)
        audit_schema.audit(hub, resp, rep, {})
        sev = {f.title: f.severity for f in rep.findings}
        self.assertEqual(sev.get("No structured data (JSON-LD)"), "low")
        prose = htmlx.parse("<p>" + "word " * 400 + "</p>",
                            base_url="https://x.com/post")
        rep2 = Report("u")
        audit_schema.audit(prose, resp, rep2, {})
        sev2 = {f.title: f.severity for f in rep2.findings}
        self.assertEqual(sev2.get("No structured data (JSON-LD)"), "medium")

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
