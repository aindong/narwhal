"""ASCII counts cannot establish multilingual word count, thinness or SEO outcomes."""
from decimal import Decimal
from fractions import Fraction
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_content
import diff_scan
import plan
import scan
from lib import content_length, htmlx, http
from lib.config import Config
from lib.report import Report

URL = 'https://example.test/guide'
IDS = {'content.thin.content', 'content.content.is.on.the.short.side',
       'content.link.hub.page.with.little.prose', 'content.sufficient.content.depth'}


def audit(text, language='en', thresholds=None, parser=htmlx._parse_stdlib):
    source = '<html lang="' + language + '"><head><title>Guide</title></head><body><p>' + text + '</p></body></html>'
    doc = parser(source, URL)
    report = Report(URL, final_url=URL, fetched_status=200)
    audit_content.audit(doc, None, report, {'thresholds': thresholds or {}})
    return report


def length_findings(report):
    return [f for f in report.findings if f.rule_id in IDS]


class TestContentLength(unittest.TestCase):
    def test_historical_ascii_pattern_is_recorded_not_called_a_word_count(self):
        receipt = content_length.observe('I a an a- can’t 中文')
        self.assertEqual(3, receipt['ascii_pattern_matches'])
        self.assertEqual(2, receipt['non_ascii_letters_or_marks'])
        self.assertEqual('not_performed', receipt['word_segmentation'])
        self.assertEqual('uninterpreted', receipt['threshold_status'])
        self.assertEqual(r"[A-Za-z][A-Za-z'-]+", receipt['pattern'])

    def test_substantial_non_latin_text_is_not_zero_word_thin_content(self):
        for language, text in (('zh', '自然历史与海洋保护。' * 400),
                               ('ja', '自然と海洋についての説明です。' * 400),
                               ('ar', 'دليل مفصل عن الحياة البحرية. ' * 200),
                               ('', '自然历史与海洋保护。' * 400),
                               ('en', '自然历史与海洋保护。' * 400)):
            with self.subTest(language=language):
                report = audit(text, language)
                self.assertEqual([], length_findings(report))
                receipt = report.meta['content_length']
                self.assertEqual('uninterpreted', receipt['threshold_status'])
                self.assertGreater(receipt['text_characters'], 2000)
                self.assertGreater(receipt['non_ascii_letters_or_marks'], 0)
                self.assertIn('Threshold review was not applied', report.to_markdown())
                self.assertNotIn('~0 words', report.to_markdown())

    def test_declared_non_english_ascii_text_is_not_assumed_english(self):
        for lang in ('fr', 'FR-ca', 'ja', 'enochian', 'en_US'):
            with self.subTest(lang=lang):
                report = audit('A concise definition.', lang)
                self.assertEqual([], length_findings(report))
                self.assertIn('declared_non_english', report.meta['content_length']['uninterpreted_reasons'])

    def test_accented_and_combining_mark_text_remains_uninterpreted(self):
        for text in ('Résumé and café.', 'Re\u0301sume\u0301 and cafe\u0301.'):
            with self.subTest(text=text):
                report = audit(text)
                self.assertEqual([], length_findings(report))
                self.assertIn('non_ascii_letters_or_marks', report.meta['content_length']['uninterpreted_reasons'])

    def test_non_letter_punctuation_does_not_change_pattern_scope(self):
        for lang in ('en', 'en-GB', '', ' EN-us '):
            report = audit('A concise definition — directly stated.', lang)
            finding, = length_findings(report)
            self.assertEqual('content.thin.content', finding.rule_id)
            self.assertEqual('low', finding.severity)
            self.assertIn('ASCII-only pattern', finding.detail)
            self.assertIn('not engine requirements', finding.detail)
            self.assertIn('Do not pad content', finding.recommendation)

    def test_legacy_threshold_keys_and_exact_boundaries_keep_comparison_order(self):
        for count, expected, rule in ((2, 'below_lower', 'content.thin.content'),
                                      (3, 'below_upper', 'content.content.is.on.the.short.side'),
                                      (4, 'below_upper', 'content.content.is.on.the.short.side'),
                                      (5, 'no_below_range_match', 'content.sufficient.content.depth')):
            report = audit('term ' * count, thresholds={'thin_content': 3, 'short_content': 5})
            self.assertEqual(expected, report.meta['content_length']['threshold_status'])
            finding, = length_findings(report)
            self.assertEqual(rule, finding.rule_id)
            self.assertIn('not universal word counts', finding.detail)
            self.assertNotIn('Sufficient content depth', finding.title)

    def test_hub_uses_its_existing_identity_without_a_depth_verdict(self):
        source = ''.join('<a href="/%d">story headline</a> ' % i for i in range(30))
        report = Report(URL)
        audit_content.audit(htmlx._parse_stdlib(source, URL), None, report, {})
        finding, = length_findings(report)
        self.assertEqual('content.link.hub.page.with.little.prose', finding.rule_id)
        self.assertEqual('low', finding.severity)
        self.assertIn('hub', finding.title)

    def test_receipt_records_extraction_and_clipped_declarations_without_reinterpreting_prefixes(self):
        receipt = content_length.observe('short text', language='f' * 100, basis='b' * 200)
        self.assertEqual('f' * 80, receipt['declared_language'])
        self.assertTrue(receipt['declared_language_clipped'])
        self.assertEqual('b' * 160, receipt['source_basis'])
        self.assertTrue(receipt['source_basis_clipped'])
        self.assertEqual('uninterpreted', receipt['threshold_status'])

    def test_programmatic_numeric_bounds_stay_exact_and_json_safe(self):
        for lower in (Decimal('2.0000000000000000001'), Fraction(20000001, 10000000)):
            report = audit('short text', thresholds={'thin_content': lower, 'short_content': 10})
            self.assertEqual('below_lower', report.meta['content_length']['threshold_status'])
            self.assertEqual(str(lower), report.meta['content_length']['bounds']['thin_content']['value'])
            json.dumps(json.loads(report.to_json()), allow_nan=False)

    def test_custom_numeric_comparison_does_not_require_conversion_hooks(self):
        class Bound:
            def __gt__(self, other):
                return 100 > other
            def __str__(self):
                raise AssertionError('No custom conversion')
        report = audit('short text', thresholds={'thin_content': Bound(), 'short_content': 200})
        self.assertEqual({'kind': 'unrecorded_numeric_type'}, report.meta['content_length']['bounds']['thin_content'])
        self.assertEqual('below_lower', report.meta['content_length']['threshold_status'])
        report.to_json()

    def test_uninterpreted_coverage_does_not_execute_a_threshold_comparison(self):
        class Bound:
            def __gt__(self, other):
                raise AssertionError('Unsupported text must not be judged against this bound')
            def __str__(self):
                raise AssertionError('No custom conversion')
        receipt = content_length.observe('自然历史。', language='zh', thresholds={'thin_content': Bound()})
        self.assertEqual('uninterpreted', receipt['threshold_status'])
        json.dumps(receipt, allow_nan=False)

    def test_malformed_or_legacy_metadata_cannot_invent_a_note_or_crash_rendering(self):
        receipt = content_length.observe('short text')
        self.assertIsNone(content_length.note({}))
        for key, value in (('version', True), ('text_characters', True), ('ascii_pattern_matches', -1),
                           ('ascii_pattern_matches', 10 ** 100), ('uninterpreted_reasons', [{}]),
                           ('uninterpreted_reasons', ['declared_non_english'] * 3),
                           ('threshold_status', ['bad']), ('pattern', 'different')):
            bad = dict(receipt, **{key: value})
            with self.subTest(key=key):
                self.assertIsNone(content_length.note({'content_length': bad}))

    def test_report_note_uses_typed_counts_not_untrusted_basis_or_language_markup(self):
        receipt = content_length.observe('short text', language='<img src=https://evil.test>', basis='<script>bad</script>')
        report = Report(URL, meta={'content_length': receipt})
        for output in (report.to_markdown(), report.to_html()):
            self.assertIn('Text-length observation (not content quality)', output)
            self.assertIn('Threshold review was not applied', output)
            self.assertNotIn('evil.test', output)
            self.assertNotIn('<script>bad', output)

    def test_complete_scan_receipts_and_scope_survive_both_parser_paths_offline(self):
        text = '自然历史与海洋保护。' * 400
        source = '<html lang="zh"><body>' + text + '</body></html>'
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, source, 1)
        for parser in (htmlx._parse_stdlib, htmlx.parse):
            with self.subTest(parser=parser.__name__), mock.patch.object(http, 'fetch', return_value=response), \
                    mock.patch.object(scan.htmlx, 'parse', side_effect=parser), \
                    mock.patch('socket.socket', side_effect=AssertionError('No network')):
                report = scan.scan(URL, only=['content'], ctx={}, check_images=False)
                self.assertEqual([], length_findings(report))
                self.assertEqual(['content'], report.meta['scan_scope']['completed'])
                self.assertEqual('uninterpreted', json.loads(report.to_json())['meta']['content_length']['threshold_status'])

    def test_diff_keeps_existing_identity_when_priority_is_corrected(self):
        old = Report(URL, final_url=URL, fetched_status=200)
        old.add('content', 'high', 'Thin content')
        new = Report(URL, final_url=URL, fetched_status=200)
        new.findings.extend(length_findings(audit('A concise definition.')))
        delta = diff_scan.diff_reports(json.loads(old.to_json()), json.loads(new.to_json()))
        self.assertEqual([], delta['added'])
        self.assertEqual([], delta['resolved'])
        self.assertEqual(1, len(delta['improved']))
        self.assertEqual(5, new.score() - old.score())  # priority correction, not an improved page

    def test_changed_known_threshold_coverage_is_not_a_resolved_page_issue(self):
        def scanned(language, text):
            source = '<html lang="' + language + '"><body>' + text + '</body></html>'
            response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, source, 1)
            with mock.patch.object(http, 'fetch', return_value=response):
                return json.loads(scan.scan(URL, only=['content'], ctx={}, check_images=False).to_json())
        old = scanned('en', 'A concise definition.')
        new = scanned('zh', '自然历史与海洋保护。' * 400)
        self.assertTrue(old['meta']['scan_settings']['content_length_reviewed'])
        self.assertFalse(new['meta']['scan_settings']['content_length_reviewed'])
        delta = diff_scan.diff_reports(old, new)
        self.assertEqual('incomparable', delta['comparison']['status'])
        self.assertIsNone(delta['score_delta'])
        self.assertEqual([], delta['resolved'])
        self.assertTrue(any('Content-length threshold coverage' in reason for reason in delta['comparison']['reasons']))

    def test_matching_uninterpreted_scope_is_not_automatically_a_diff_failure(self):
        report = Report(URL, fetched_status=200, meta={
            'scan_scope': {'requested': ['content'], 'completed': ['content']},
            'scan_settings': {'content_length_reviewed': False}})
        data = json.loads(report.to_json())
        delta = diff_scan.diff_reports(data, data)
        self.assertEqual('comparable', delta['comparison']['status'])
        self.assertEqual(0, delta['score_delta'])

    def test_known_crawl_scope_changes_are_joined_by_page_url(self):
        old = {'url': URL, 'overall_score': 90, 'homepage': {'findings': []}, 'crawl': {
            'pages': [{'url': URL, 'scan_settings': {'content_length_reviewed': True}}]}}
        new = {'url': URL, 'overall_score': 95, 'homepage': {'findings': []}, 'crawl': {
            'pages': [{'url': URL, 'scan_settings': {'content_length_reviewed': False}}]}}
        delta = diff_scan.diff_reports(old, new)
        self.assertEqual('incomparable', delta['comparison']['status'])
        self.assertIsNone(delta['score_delta'])

    def test_legacy_missing_scope_is_not_inferred_from_the_language(self):
        report = Report(URL, fetched_status=200, meta={
            'scan_scope': {'requested': ['content'], 'completed': ['content']}})
        data = json.loads(report.to_json())
        delta = diff_scan.diff_reports(data, data)
        self.assertNotIn('content_length_reviewed', delta['comparison']['old_settings'])

    def test_cli_known_coverage_change_has_the_existing_incomparable_exit_code(self):
        old = json.loads(Report(URL, fetched_status=200, meta={
            'scan_scope': {'requested': ['content'], 'completed': ['content']},
            'scan_settings': {'content_length_reviewed': True}}).to_json())
        new = json.loads(json.dumps(old))
        new['meta']['scan_settings']['content_length_reviewed'] = False
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            root = Path(directory)
            before, after, output = (root / name for name in ('before.json', 'after.json', 'diff.json'))
            before.write_text(json.dumps(old), encoding='utf-8')
            after.write_text(json.dumps(new), encoding='utf-8')
            status = diff_scan.main([str(before), str(after), '--format', 'json', '-o', str(output), '--fail-on-regression'])
            self.assertEqual(2, status)
            delta = json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual('incomparable', delta['comparison']['status'])
            self.assertIsNone(delta['score_delta'])

    def test_title_filters_use_new_labels_and_do_not_change_stable_identity(self):
        config = Config({'ignore': {'titles': ['limited ASCII-token count']}})
        report = Report(URL, ignore=config.is_ignored)
        audit_content.audit(htmlx._parse_stdlib('A concise definition.', URL), None, report)
        self.assertEqual([], length_findings(report))

    def test_planner_keeps_current_and_legacy_length_advice_conditional(self):
        fixture = Path(__file__).parent / 'fixtures/planner/plain_html'
        for rule in IDS - {'content.sufficient.content.depth'}:
            for title in ('Thin content', 'Review limited ASCII-token count'):
                report = Report(URL)
                report.add('content', 'high', title, rule_id=rule)
                built = plan.build_plan(json.loads(report.to_json()), str(fixture))
                action, = built['actions']
                self.assertEqual('review_required', action['safety'])
                self.assertIn('do not pad content', action['proposed_change'])
                self.assertIn('language/tokenizer coverage', action['proposed_change'])
                self.assertNotIn('Revise the owning page content', action['proposed_change'])


if __name__ == '__main__':
    unittest.main()
