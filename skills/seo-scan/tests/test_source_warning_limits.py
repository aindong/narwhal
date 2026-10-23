"""Source warning budgets bound output, without stopping valid extraction."""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_schema
from lib import ecommerce, htmlx, merchant_source, microdata, rdfa
from lib.report import Report

URL = "https://example.test/"


def microdata_page(count):
    return '<div itemscope itemtype="https://schema.org/Thing">' + ''.join(
        '<a itemprop="url" href="http://[bad%d">x</a>' % i for i in range(count)) + '<span itemprop="name">Valid tail</span></div>'


def rdfa_page(count):
    return '<div vocab="https://schema.org/" typeof="Thing">' + ''.join(
        '<span property="[unknown:field%d]">x</span>' % i for i in range(count)) + '<span property="name">Valid tail</span></div>'


class TestSourceWarningLimits(unittest.TestCase):
    def test_microdata_warning_fanout_is_bounded_and_tail_still_extracted(self):
        nodes, warnings = microdata.extract(microdata_page(1000), URL)
        self.assertEqual(microdata.MAX_WARNINGS + 1, len(warnings))
        self.assertIn("warning limit reached (64)", warnings[-1])
        self.assertIn("partial", warnings[-1])
        self.assertEqual("Valid tail", nodes[0]["name"])

    def test_rdfa_warning_fanout_is_bounded_and_tail_still_extracted(self):
        nodes, warnings = rdfa.extract(rdfa_page(1000), URL)
        self.assertEqual(microdata.MAX_WARNINGS + 1, len(warnings))
        self.assertIn("RDFa warning limit", warnings[-1])
        self.assertEqual("Valid tail", nodes[0]["name"])

    def test_duplicate_at_cap_does_not_create_false_omission_notice(self):
        tree = microdata._Tree(URL, warning_limit=2)
        for message in ("one", "two", "one", "two"):
            tree.warn(message)
        self.assertEqual(["one", "two"], tree.warnings)
        self.assertFalse(tree.warnings_suppressed)
        tree.warn("three")
        self.assertEqual(3, len(tree.warnings))
        self.assertTrue(tree.warnings_suppressed)
        self.assertEqual(2, len(tree._warning_seen))
        tree.warn("four")
        self.assertEqual(3, len(tree.warnings))

    def test_long_details_are_explicitly_truncated(self):
        tree = microdata._Tree(URL)
        tree.warn('Diagnostic detail ' + 'x' * 10000)
        self.assertLessEqual(len(tree.warnings[0]), microdata.MAX_WARNING_CHARS)
        self.assertIn('warning detail truncated', tree.warnings[0])

    def test_long_invalid_url_values_are_omitted_not_serialized_as_prefixes(self):
        html = '<div itemscope itemtype="https://schema.org/Thing"><a itemprop="url" href="http://[bad' + 'x' * 10000 + '">x</a></div>'
        _, warnings = microdata.extract(html, URL)
        self.assertEqual(1, len(warnings))
        self.assertLessEqual(len(warnings[0]), microdata.MAX_WARNING_CHARS)
        self.assertIn('source value omitted', warnings[0])
        self.assertNotIn('http://[bad', warnings[0])
        _, rdfa_warnings = rdfa.extract('<div typeof="[unknown:' + 'x' * 10000 + ']"></div>', URL)
        self.assertLessEqual(len(rdfa_warnings[0]), microdata.MAX_WARNING_CHARS)
        self.assertIn("warning detail truncated", rdfa_warnings[0])

    def test_warning_budget_is_per_extraction(self):
        for _ in range(2):
            with mock.patch.object(microdata, "MAX_WARNINGS", 2):
                _, warnings = microdata.extract(microdata_page(10), URL)
            self.assertEqual(3, len(warnings))
            self.assertIn("warning limit reached (2)", warnings[-1])

    def test_merchant_source_shares_detail_limit_and_retains_explicit_cap(self):
        html = ''.join('<a itemprop="availability" href="http://[bad%d">Stock</a>' % i for i in range(100))
        result = merchant_source.extract(html, URL)
        self.assertEqual(merchant_source.MAX_WARNINGS + 1, len(result["warnings"]))
        self.assertTrue(all(len(w) <= microdata.MAX_WARNING_CHARS for w in result["warnings"]))
        report = Report(URL)
        ecommerce.audit(htmlx.parse(html, URL), report)
        self.assertIn("Merchant evidence warning limit reached (64)", report.to_html())

    def test_serialized_scan_reports_keep_stable_coverage_findings(self):
        for html, key, rule in ((microdata_page(1000), "microdata_warnings", "schema.microdata.extraction"),
                                (rdfa_page(1000), "rdfa_warnings", "schema.rdfa.extraction")):
            report = Report(URL)
            audit_schema.audit(htmlx.parse(html, URL), None, report)
            payload = json.loads(report.to_json())
            self.assertEqual(65, len(payload["meta"]["structured_data"][key]))
            self.assertIn(rule, {f.rule_id for f in report.findings})
            self.assertLess(len(report.to_json()), 50000)
            self.assertIn("warning limit reached (64)", report.to_markdown())
            self.assertIn("warning limit reached (64)", report.to_html())

    def test_truncation_is_visible_in_html_recommendation(self):
        html = '<div typeof="[unknown:' + 'x' * 10000 + ']"></div>'
        report = Report(URL)
        audit_schema.audit(htmlx.parse(html, URL), None, report)
        self.assertIn("truncated at 512 characters", report.to_html())

    def test_parser_backends_expose_identical_bounded_warning_evidence(self):
        html = microdata_page(100) + rdfa_page(100)
        stdlib, optional = htmlx._parse_stdlib(html, URL), htmlx.parse(html, URL)
        self.assertEqual(stdlib.microdata_warnings, optional.microdata_warnings)
        self.assertEqual(stdlib.rdfa_warnings, optional.rdfa_warnings)
        self.assertEqual(stdlib.microdata, optional.microdata)
        self.assertEqual(stdlib.rdfa, optional.rdfa)


if __name__ == "__main__":
    unittest.main()
