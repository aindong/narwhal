"""Compact low-priority findings retain safe, bounded reported-field previews."""
from html.parser import HTMLParser
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_technical
from lib import htmlx
from lib.report import Report, md_to_html


class Text(HTMLParser):
    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.data, self.tags = [], []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.data.append(data)

    def joined(self):
        return ''.join(self.data)


class TestQuickWinPreviews(unittest.TestCase):
    def report(self, detail='', evidence=''):
        report = Report('https://example.test/guide', fetched_status=200)
        report.add('technical', 'low', 'Synthetic quick win', detail,
                   'Review this controlled example.', evidence=evidence)
        return report

    def test_real_heading_observation_survives_compact_rendering(self):
        report = Report('https://example.test/guide', fetched_status=200)
        audit_technical._headings(htmlx._parse_stdlib('<h1>Guide</h1><h4>Details</h4>', report.url), report)
        for markup in (report.to_html(), md_to_html(report.to_markdown())):
            text = Text(markup).joined()
            self.assertIn('An H1 is followed by an H4.', text)
            self.assertIn('Observed (preview)', text)

    def test_detail_and_evidence_are_literal_not_executable_markup_or_links(self):
        payload = '<img src="https://evil.test/pixel" onerror="alert(1)"> [fake](https://evil.test) **bold** | ~x~'
        report = self.report(payload, payload)
        for markup in (report.to_html(), md_to_html(report.to_markdown())):
            parsed = Text(markup)
            self.assertEqual(2, parsed.joined().count(payload))
            self.assertFalse(any(tag in ('script', 'img') and attrs.get('src', '').startswith('https://evil.test')
                                 for tag, attrs in parsed.tags))
            self.assertFalse(any(tag == 'a' and 'evil.test' in attrs.get('href', '') for tag, attrs in parsed.tags))

    def test_backtick_runs_and_fence_lookalikes_stay_inside_literal_previews(self):
        for value in ('`one`', '``two```', '```text\n# fake heading\n```', '`', '~~~~', 'a ` b `` c ``` d'):
            with self.subTest(value=value):
                expected = ' '.join(value.split())
                report = self.report(value, value)
                for markup in (report.to_html(), md_to_html(report.to_markdown())):
                    self.assertIn(expected, Text(markup).joined())
                    self.assertNotIn('<h1>fake heading', markup)

    def test_whitespace_is_normalized_in_preview_but_not_json(self):
        value = '  first\r\n\tsecond\u2003third  '
        report = self.report(value)
        before = report.to_json()
        for markup in (report.to_html(), md_to_html(report.to_markdown())):
            text = Text(markup).joined()
            self.assertIn('first second third', text)
            self.assertIn('whitespace-normalized', text)
        self.assertEqual(before, report.to_json())
        self.assertEqual(value, report.findings[0].detail)

    def test_character_cap_marks_omissions_and_preserves_full_json(self):
        report = self.report('x' * 400 + 'HIDDEN_DETAIL', 'y' * 400 + 'HIDDEN_EVIDENCE')
        before, score, counts = report.to_json(), report.score(), report.counts()
        for markup in (report.to_html(), md_to_html(report.to_markdown())):
            text = Text(markup).joined()
            self.assertIn('x' * 400 + '…', text)
            self.assertIn('y' * 400 + '…', text)
            self.assertNotIn('HIDDEN_DETAIL', text)
            self.assertNotIn('HIDDEN_EVIDENCE', text)
            self.assertEqual(2, text.count('truncated; full value in JSON'))
        self.assertEqual(before, report.to_json())
        self.assertEqual((score, counts), (report.score(), report.counts()))

    def test_exact_character_limit_is_not_marked_truncated(self):
        report = self.report('x' * 400)
        for markup in (report.to_html(), md_to_html(report.to_markdown())):
            self.assertNotIn('truncated; full value in JSON', Text(markup).joined())

    def test_blank_or_missing_fields_do_not_invent_observations(self):
        for detail, evidence in (('', ''), (' \t\n', ''), (None, None)):
            report = self.report(detail, evidence)
            for markup in (report.to_html(), report.to_markdown()):
                self.assertNotIn('Observed (preview)', markup)
                self.assertNotIn('Evidence (preview)', markup)
                self.assertNotIn('whitespace-normalized', markup)

    def test_evidence_only_finding_retains_its_label(self):
        report = self.report(evidence='A source witness')
        for markup in (report.to_html(), md_to_html(report.to_markdown())):
            text = Text(markup).joined()
            self.assertIn('Evidence (preview)', text)
            self.assertIn('A source witness', text)
            self.assertNotIn('Observed (preview)', text)


if __name__ == '__main__':
    unittest.main()
