"""Offline tests grouped by area; no network or required third-party dependencies."""

try:
    from ._smoke_support import *  # noqa: F401,F403
except ImportError:  # direct discovery with ``-s tests``
    from _smoke_support import *  # type: ignore  # noqa: F401,F403

import audit_content
import crawl_site
from lib import content_quality as cq
from lib import htmlx, links, simhash
from lib import text as textlib
from lib.report import Report


class TestParser(unittest.TestCase):
    def test_extracts_core_elements(self):
        doc = htmlx.parse(GOOD_PAGE, base_url="https://example.com/geo")
        self.assertIn("What is GEO", doc.title)
        self.assertEqual(doc.lang, "en")
        self.assertEqual([lvl for lvl, _ in doc.headings], [1, 2])
        self.assertEqual(len(doc.scripts_ld), 1)
        self.assertEqual(doc.canonical(), "https://example.com/geo")
        self.assertTrue(doc.meta_by_name("description"))

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
