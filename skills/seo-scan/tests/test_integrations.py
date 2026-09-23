"""Offline tests grouped by area; no network or required third-party dependencies."""

try:
    from ._smoke_support import *  # noqa: F401,F403
except ImportError:  # direct discovery with ``-s tests``
    from _smoke_support import *  # type: ignore  # noqa: F401,F403

import audit as audit_mod
import crawl_site
import generate_llms
import generate_schema
from lib import http, links
from lib.report import Report


class TestSSRF(unittest.TestCase):
    def test_blocks_private_host(self):
        with self.assertRaises(http.SSRFError):
            http.assert_public_host("http://127.0.0.1/admin")

    def test_normalize_adds_scheme(self):
        self.assertTrue(http.normalize_url("example.com").startswith("https://"))

    def test_rejects_bad_scheme(self):
        with self.assertRaises(ValueError):
            http.normalize_url("ftp://example.com")

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

class TestMcpServer(unittest.TestCase):
    def setUp(self):
        import mcp_server
        self.m = mcp_server

    def test_tool_names_are_stable(self):
        names = [n for _, n in self.m._TOOLS]
        self.assertEqual(
            set(names),
            {"scan_page", "compare_pages", "content_brief", "crawl_site",
             "audit_site", "validate_sitemap", "generate_llms",
             "generate_schema", "diff_reports", "plan_remediation"})
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
            server_type = "FastMCP"
        except ImportError:
            try:
                import mcp.server.mcpserver  # noqa: F401
                server_type = "MCPServer"
            except ImportError:
                server_type = None
        if server_type:
            server = self.m.build_server()
            self.assertEqual(type(server).__name__, server_type)
        else:
            # Graceful path: no `mcp` package -> friendly message, exit 1, no server.
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(self.m.main([]), 1)

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
