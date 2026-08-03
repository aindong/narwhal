"""Security and machine-contract regression tests."""

import json
import os
import sys
import unittest
from unittest import mock

SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from lib import http  # noqa: E402
from lib.report import Report  # noqa: E402
import diff_scan  # noqa: E402
import scan  # noqa: E402


class _Response:
    def __init__(self, status=200, location=None, chunks=()):
        self.status_code = status
        self.headers = {"location": location} if location else {}
        self.is_redirect = status in (301, 302, 303, 307, 308)
        self.is_permanent_redirect = status in (301, 308)
        self._chunks = list(chunks)
        self.closed = False

    def close(self):
        self.closed = True

    def iter_content(self, chunk_size=65536):
        yield from self._chunks


class _Requests:
    class TooManyRedirects(Exception):
        pass

    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return next(self.responses)


class TestSafeTransport(unittest.TestCase):
    def test_public_redirect_to_loopback_is_rejected_before_second_request(self):
        fake = _Requests([_Response(302, "http://127.0.0.1/admin")])
        with mock.patch.object(http, "assert_public_host", wraps=http.assert_public_host):
            with self.assertRaises(http.SSRFError):
                http._requests_safe(fake, "GET", "https://public.example/", timeout=2,
                                    headers={}, allow_private=False, stream=True)
        self.assertEqual(1, len(fake.calls))

    def test_every_public_redirect_hop_is_validated(self):
        fake = _Requests([_Response(302, "/next"), _Response(200)])
        with mock.patch.object(http, "assert_public_host") as validate:
            response, final, redirects = http._requests_safe(
                fake, "GET", "https://public.example/start", timeout=2,
                headers={}, allow_private=False, stream=True)
        self.assertEqual(200, response.status_code)
        self.assertEqual("https://public.example/next", final)
        self.assertEqual([final], redirects)
        validate.assert_called_once_with(final, allow_private=False)

    def test_stream_reader_never_keeps_more_than_budget(self):
        response = _Response(chunks=[b"abcd", b"efgh"])
        raw, truncated = http._limited_content(response, 5)
        self.assertEqual(b"abcde", raw)
        self.assertTrue(truncated)


class TestReportContract(unittest.TestCase):
    def test_json_is_versioned_and_findings_have_stable_ids(self):
        report = Report("https://example.com")
        report.add("content", "high", "Thin content (210 words)")
        data = json.loads(report.to_json())
        self.assertEqual("2.0", data["schema_version"])
        self.assertTrue(data["tool_version"])
        finding = data["findings"][0]
        self.assertEqual("content.thin.content", finding["rule_id"])
        self.assertEqual("page", finding["scope"])
        self.assertEqual(1.0, finding["confidence"])

    def test_diff_prefers_rule_id_over_changed_human_title(self):
        old = {"url": "u", "score": 90, "findings": [
            {"category": "technical", "severity": "high", "title": "Old title",
             "rule_id": "technical.canonical.missing"}]}
        new = {"url": "u", "score": 93, "findings": [
            {"category": "technical", "severity": "medium", "title": "Clearer title",
             "rule_id": "technical.canonical.missing"}]}
        result = diff_scan.diff_reports(old, new)
        self.assertFalse(result["added"])
        self.assertFalse(result["resolved"])
        self.assertEqual(1, len(result["improved"]))

    def test_unknown_auditor_is_rejected_not_silently_ignored(self):
        with self.assertRaisesRegex(ValueError, "Unknown auditor"):
            scan.scan("https://example.com", only=["techncial"])

    def test_non_html_response_is_a_hard_failure(self):
        response = http.Response(
            "https://example.com/file.pdf", "https://example.com/file.pdf", 200,
            {"content-type": "application/pdf"}, "%PDF", 1)
        with mock.patch.object(scan.http, "fetch", return_value=response):
            report = scan.scan("https://example.com/file.pdf")
        self.assertEqual(0, report.score())
        self.assertEqual("technical.response.non_html", report.findings[0].rule_id)

    def test_truncation_is_exposed_as_coverage_and_finding(self):
        html = "<html><head><title>Example title long enough for a test</title></head>" \
               "<body><h1>Example</h1></body></html>"
        response = http.Response(
            "https://example.com", "https://example.com", 200,
            {"content-type": "text/html", "x-narwhal-truncated": "true"}, html, 1)
        with mock.patch.object(scan.http, "fetch", return_value=response), \
             mock.patch.object(scan, "gather_context", return_value={}):
            report = scan.scan("https://example.com", only=["technical"],
                               check_images=False)
        self.assertTrue(report.meta["coverage"]["response_truncated"])
        self.assertIn("technical.response.truncated",
                      {finding.rule_id for finding in report.findings})


if __name__ == "__main__":
    unittest.main()
