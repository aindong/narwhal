"""Golden tests for complete Markdown, JSON, and HTML report output."""

import unittest

try:
    from .golden_reports import SNAPSHOTS, render_all
except ImportError:  # direct discovery with ``-s tests``
    from golden_reports import SNAPSHOTS, render_all


class TestFullReportSnapshots(unittest.TestCase):
    def test_fixed_html_matches_all_committed_report_formats(self):
        for name, actual in render_all().items():
            with self.subTest(format=name.rsplit(".", 1)[-1]):
                expected = (SNAPSHOTS / name).read_text(encoding="utf-8")
                self.assertMultiLineEqual(expected, actual)


if __name__ == "__main__":
    unittest.main()
