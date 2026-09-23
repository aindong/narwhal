"""Offline tests grouped by area; no network or required third-party dependencies."""

try:
    from ._smoke_support import *  # noqa: F401,F403
except ImportError:  # direct discovery with ``-s tests``
    from _smoke_support import *  # type: ignore  # noqa: F401,F403

import audit_content
import audit_geo
import audit_schema
import audit_technical
import generate_llms
import generate_schema
from lib import config as configlib
from lib import htmlx, http
from lib.report import Report


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

class TestSchemaGenerator(unittest.TestCase):
    def test_required_placeholder(self):
        node = generate_schema.build("Product", {})
        self.assertEqual(node["@type"], "Product")
        self.assertIn("TODO", node["name"])
        self.assertIn("TODO", node["offers"]["priceCurrency"])
        self.assertIn("TODO", node["offers"]["availability"])

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

class TestBrief(unittest.TestCase):
    """Offline tests for `narwhal brief` (#26): GSC page slicing, subtopic
    gaps, question extraction, honest degradation — everything but the fetch."""

    GSC = {"found": True, "property": "sc-domain:you.com",
           "window": {"start": "2026-06-01", "end": "2026-06-28"},
           "striking": [
               {"page": "https://www.you.com/guide/",
                "query": "how to calibrate widgets",
                "position": 9.2, "impressions": 800, "clicks": 12},
               {"page": "https://you.com/other", "query": "widget parts",
                "position": 12.0, "impressions": 300, "clicks": 3}],
           "laggards": [{"page": "https://you.com/guide", "position": 6.0,
                         "ctr": 0.005, "expected_ctr": 0.04,
                         "clicks": 4, "impressions": 900}],
           "decaying": [],
           "cannibalization": [
               {"query": "widget calibration", "impressions": 500, "pages": [
                   {"page": "https://you.com/guide", "share": 0.5, "clicks": 1,
                    "impressions": 250, "position": 9.0},
                   {"page": "https://you.com/blog/cal", "share": 0.4,
                    "clicks": 1, "impressions": 200, "position": 11.0}]}]}

    RIVAL_HTML = """
    <html><head><title>Complete widget calibration guide with torque data</title>
    <meta name="description" content="Thorough, evidence-backed calibration guide.">
    <script type="application/ld+json">{"@type":"HowTo","name":"x"}</script>
    </head><body><h1>Guide</h1>
    <h2>What is widget calibration?</h2>
    <h2>Torque tolerance tables</h2>
    <h2>Comments</h2>
    <h2>Tools</h2>
    <h3>How often should you recalibrate?</h3>
    <p>According to a 2026 study, 45% of widgets drift. """ + \
        "calibration torque tolerance drift detail word " * 150 + """</p>
    </body></html>"""

    YOURS_HTML = """
    <html><head><title>Widget calibration</title></head>
    <body><h1>Widget calibration</h1><h2>Overview</h2>
    <p>""" + "widgets are things you calibrate " * 40 + "</p></body></html>"

    def _pagedict(self, html, url):
        import compare
        doc = htmlx.parse(html, base_url=url)
        rep = Report(url, final_url=url, fetched_status=200)
        resp = http.Response(url, url, 200, {}, html, 1)
        for fn in (audit_technical.audit, audit_content.audit,
                   audit_schema.audit, audit_geo.audit):
            fn(doc, resp, rep, {})
        return {"url": url, "facts": compare.facts(rep, doc),
                "headings": list(doc.headings), "text": doc.body_text or ""}

    def test_norm_page_is_scheme_www_slash_insensitive(self):
        import brief
        for u in ("https://www.you.com/guide/", "http://you.com/guide",
                  "https://YOU.com/guide#part"):
            self.assertEqual(brief.norm_page(u), "you.com/guide")
        self.assertNotEqual(brief.norm_page("https://you.com/guide?p=2"),
                            brief.norm_page("https://you.com/guide"))

    def test_page_queries_slices_one_page(self):
        import brief
        pq = brief.page_queries(self.GSC, "http://you.com/guide")
        self.assertEqual([s["query"] for s in pq["striking"]],
                         ["how to calibrate widgets"])   # www/slash variant matched
        self.assertIsNotNone(pq["laggard"])
        self.assertEqual(pq["cannibalized"], ["widget calibration"])
        empty = brief.page_queries(self.GSC, "https://you.com/nowhere")
        self.assertEqual(empty["striking"], [])
        self.assertIsNone(empty["laggard"])

    def test_topic_queries_match_inflections(self):
        import brief
        # "widget calibration" must catch "calibrate widgets" (crude stemming).
        qs = brief.topic_queries(self.GSC, "widget calibration")
        self.assertEqual(len(qs), 2)
        self.assertEqual(brief.topic_queries(self.GSC, "unrelated subject"), [])

    def test_subtopic_gaps_skip_noise_and_covered(self):
        import brief
        you = self._pagedict(self.YOURS_HTML, "https://you.com/guide")
        rival = self._pagedict(self.RIVAL_HTML, "https://rival.com/guide")
        heads = [s["heading"] for s in brief.subtopic_gaps(you, [rival])]
        self.assertIn("Torque tolerance tables", heads)          # real gap
        self.assertIn("How often should you recalibrate?", heads)
        self.assertNotIn("Comments", heads)                      # noise list
        self.assertNotIn("Tools", heads)                         # one-word nav
        # Covered: "widget calibration" terms are all over your page text.
        self.assertNotIn("What is widget calibration?", heads)

    def test_questions_merge_headings_and_striking_queries(self):
        import brief
        subs = [{"heading": "How often should you recalibrate?",
                 "who": "https://rival.com/guide", "question": True},
                {"heading": "Torque tolerance tables",
                 "who": "https://rival.com/guide", "question": False}]
        striking = brief.page_queries(self.GSC, "https://you.com/guide")["striking"]
        qs = brief.questions_to_answer(subs, striking)
        texts = [q["question"] for q in qs]
        self.assertIn("How often should you recalibrate?", texts)
        self.assertIn("how to calibrate widgets", texts)
        self.assertNotIn("Torque tolerance tables", texts)

    def test_synthesize_grounded_and_rendered(self):
        import brief
        you = self._pagedict(self.YOURS_HTML, "https://you.com/guide")
        rival = self._pagedict(self.RIVAL_HTML, "https://rival.com/guide")
        b = brief.synthesize(you, [rival], self.GSC)
        self.assertEqual(b["grounding"], "queries+pages")
        self.assertEqual(b["structure"]["target_words"],
                         rival["facts"]["words"])
        self.assertIn("HowTo", [s["type"] for s in b["schema"]])
        md = brief.render_markdown(b)
        self.assertIn("your real Search Console queries", md)
        self.assertIn("how to calibrate widgets", md)
        self.assertIn("CTR laggard", md)
        self.assertIn("not proof of why anyone ranks", md)   # honesty footer
        # Structural gaps live under structure targets, not the gap list.
        self.assertNotIn("**Content depth** — seen on", md)

    def test_degrades_honestly_without_gsc(self):
        import brief
        you = self._pagedict(self.YOURS_HTML, "https://you.com/guide")
        rival = self._pagedict(self.RIVAL_HTML, "https://rival.com/guide")
        md = brief.render_markdown(
            brief.synthesize(you, [rival], {"found": False, "error": "no creds"}))
        self.assertIn("Structure-only brief", md)
        self.assertIn("no creds", md)
        self.assertNotIn("## Target queries", md)   # omitted, never invented

    def test_gsc_connected_but_no_page_queries(self):
        import brief
        you = self._pagedict(self.YOURS_HTML, "https://you.com/elsewhere")
        md = brief.render_markdown(brief.synthesize(you, [], self.GSC))
        self.assertIn("no striking-distance queries for this page", md)
        self.assertNotIn("Structure-only brief", md)

    def test_topic_mode(self):
        import brief
        rival = self._pagedict(self.RIVAL_HTML, "https://rival.com/guide")
        b = brief.synthesize(None, [rival], None, topic="widget calibration")
        md = brief.render_markdown(b)
        self.assertIn("Content brief — widget calibration", md)
        self.assertIn("Subtopics the winning pages cover", md)
        self.assertNotIn("Gaps vs the pages that win", md)   # nothing to diff

    def test_structure_targets_exclude_hub_rivals(self):
        import brief
        you = self._pagedict(self.YOURS_HTML, "https://you.com/guide")
        hub = self._pagedict(self.RIVAL_HTML, "https://rival.com/")
        hub["facts"]["page_kind"] = "hub"
        self.assertEqual(brief.structure_targets(you, [hub]), {})

    def test_compare_no_depth_lead_when_all_rivals_are_hubs(self):
        # Regression (found live): with only hub rivals the all() over non-hub
        # rivals was vacuously true and a thin page "led" on content depth.
        import compare
        you = self._pagedict(self.YOURS_HTML, "https://you.com/guide")["facts"]
        hub = self._pagedict(self.RIVAL_HTML, "https://rival.com/")["facts"]
        hub["page_kind"] = "hub"
        leads = compare.gap_analysis(you, [hub])["leads"]
        self.assertNotIn("Content depth", [l["what"] for l in leads])

    def test_main_arg_validation(self):
        import contextlib
        import io
        import brief
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(brief.main([]), 2)                 # no URLs
            self.assertEqual(brief.main(["--topic", "x"]), 2)   # no competitors


if __name__ == "__main__":
    unittest.main()
