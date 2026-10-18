"""Literal style counts cannot establish padding, originality or required edits."""
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_content
import diff_scan
import plan
import scan
from lib import content_quality, htmlx, http
from lib.config import Config
from lib.report import Report
from test_content_phrases import BASE

URL = 'https://example.test/guide'
FIXTURE = Path(__file__).parent / 'fixtures/planner/plain_html'
RATE = 'content.filler.padding.language'
COUNT = 'content.some.filler.phrasing'
RATIO = 'content.repetitive.vocabulary'
INSTRUCTIONS = 'Close the inlet valve. Open the outlet valve. Check the inlet valve and outlet valve. ' * 35
QUOTED = 'The guide asks reviewers to quote when it comes to while comparing consistent terminology. ' * 35


def measured(text, basis='visible text'):
    report = Report(URL, final_url=URL, fetched_status=200)
    audit_content._quality(text, report, basis=basis)
    return report


def selected(report, rule):
    return next(f for f in report.findings if f.rule_id == rule)


class TestStyleReview(unittest.TestCase):
    def test_repeated_instruction_terms_are_not_a_spun_content_diagnosis(self):
        finding = selected(measured(INSTRUCTIONS), RATIO)
        self.assertEqual('low', finding.severity)
        self.assertEqual('Review lower type/token ratio', finding.title)
        self.assertIn('525 matches', finding.detail)
        self.assertIn('8 distinct lowercased matches', finding.detail)
        self.assertIn('0.015', finding.detail)
        self.assertIn('not padding, thin/spun content', finding.detail)
        self.assertIn('consistent technical terms', finding.recommendation)
        self.assertNotIn('heavy repetition signals', finding.recommendation)

    def test_quoted_phrase_is_a_low_review_with_literal_examples(self):
        finding = selected(measured(QUOTED), RATE)
        q = content_quality.analyze(QUOTED)
        self.assertEqual('low', finding.severity)
        self.assertEqual('Review configured phrase-match rate', finding.title)
        self.assertIn(str(q['filler_count']) + ' configured phrase matches', finding.detail)
        self.assertIn(str(q['word_count']) + ' matches', finding.detail)
        self.assertEqual('when it comes to', finding.evidence)
        self.assertIn('quoted examples', finding.recommendation)

    def test_count_branch_retains_its_id_and_selection(self):
        text = BASE * 8 + ' when it comes to when it comes to'
        q = content_quality.analyze(text)
        self.assertEqual(2, q['filler_count'])
        self.assertLess(q['filler_per_100w'], 1)
        finding = selected(measured(text), COUNT)
        self.assertEqual('low', finding.severity)
        self.assertEqual('Review configured phrase matches', finding.title)
        self.assertIn('review cutoff >=2 below the rate cutoff', finding.detail)

    def test_original_helper_keys_keep_counts_and_rounding(self):
        q = content_quality.analyze('Valve valve when it comes to. In conclusion.')
        self.assertEqual(8, q['word_count'])
        self.assertEqual(7, q['unique_word_count'])
        self.assertEqual(.875, q['lexical_diversity'])
        self.assertEqual(1, q['filler_count'])
        self.assertEqual(0, q['filler_per_100w'])
        self.assertEqual(['when it comes to'], q['filler_examples'])
        self.assertEqual(1, q['ai_distinct'])

    def test_doubling_identical_text_can_reduce_ratio_without_changing_vocabulary(self):
        first = content_quality.analyze(BASE)
        second = content_quality.analyze(BASE * 2)
        self.assertEqual(first['unique_word_count'], second['unique_word_count'])
        self.assertEqual(first['word_count'] * 2, second['word_count'])
        self.assertLess(second['lexical_diversity'], first['lexical_diversity'])

    def test_ratio_cutoff_is_strict_and_keeps_historical_rounding(self):
        terms = ['term' + chr(65 + i // 26) + chr(65 + i % 26) for i in range(140)]
        at_cutoff = ' '.join(terms + [terms[0]] * 260)
        below_cutoff = ' '.join(terms[:-1] + [terms[0]] * 261)
        self.assertEqual(.35, content_quality.analyze(at_cutoff)['lexical_diversity'])
        self.assertNotIn(RATIO, [f.rule_id for f in measured(at_cutoff).findings])
        self.assertIn(RATIO, [f.rule_id for f in measured(below_cutoff).findings])

    def test_ascii_fragments_are_not_relabelled_linguistic_words(self):
        q = content_quality.analyze('naïve naïve unit')
        self.assertEqual(5, q['word_count'])
        self.assertEqual(3, q['unique_word_count'])
        self.assertEqual(.6, q['lexical_diversity'])
        self.assertIn('ASCII-only matcher', selected(measured(INSTRUCTIONS), RATIO).detail)

    def test_under_100_minimum_is_preserved(self):
        self.assertEqual([], measured('valve ' * 99).findings)
        self.assertEqual([], measured('when it comes to').findings)

    def test_400_ratio_minimum_and_rounded_rate_cutoff_are_preserved(self):
        self.assertNotIn(RATIO, [f.rule_id for f in measured('valve ' * 399).findings])
        self.assertIn(RATIO, [f.rule_id for f in measured('valve ' * 400).findings])
        text = 'when it comes to ' * 2 + 'valve ' * 193
        self.assertEqual(1.0, content_quality.analyze(text)['filler_per_100w'])
        self.assertIn(RATE, [f.rule_id for f in measured(text).findings])

    def test_pass_is_still_a_literal_count_not_quality_certification(self):
        finding = selected(measured(BASE), 'content.clean.specific.writing')
        self.assertEqual('good', finding.severity)
        self.assertIn('distinct lowercased matches', finding.detail)
        self.assertIn('This does not establish originality or content quality', finding.detail)

    def test_source_basis_is_bounded_and_html_is_literal(self):
        basis = '<script>window.styleProbe=1</script>' + 'X' * 200
        report = measured(INSTRUCTIONS, basis)
        self.assertIn(basis[:160], selected(report, RATIO).detail)
        self.assertNotIn(basis[:161], selected(report, RATIO).detail)
        self.assertNotIn('<script>window.styleProbe=1</script>', report.to_html())
        self.assertIn('&lt;script&gt;', report.to_html())

    def test_language_scope_and_parser_paths_are_unchanged(self):
        for parser in (htmlx._parse_stdlib, htmlx.parse):
            for language, expected in (('en', True), ('en-GB', True), ('', True), ('fr', False)):
                doc = parser('<html lang="' + language + '"><body><p>' + INSTRUCTIONS + '</p></body></html>', URL)
                report = Report(URL)
                audit_content.audit(doc, None, report)
                self.assertEqual(expected, RATIO in [f.rule_id for f in report.findings])
                if expected: self.assertIn(str(doc.extraction), selected(report, RATIO).detail)

    def test_title_ignore_filters_can_suppress_new_review_titles(self):
        config = Config({'ignore': {'titles': ['Review lower type/token ratio']}})
        report = Report(URL, ignore=config.is_ignored)
        audit_content._quality(INSTRUCTIONS, report)
        self.assertNotIn(RATIO, [f.rule_id for f in report.findings])

    def test_real_scan_formats_keep_literal_counts_without_network(self):
        response = http.Response(url=URL, final_url=URL, status=200,
            headers={'content-type': 'text/html'}, text='<html lang="en"><body><p>' + QUOTED + '</p></body></html>', elapsed_ms=1)
        with mock.patch.object(http, 'fetch', return_value=response), mock.patch('socket.socket', side_effect=AssertionError('No network')):
            report = scan.scan(URL, only=['content'], ctx={}, check_images=False)
        for output in (report.to_json(), report.to_markdown(), report.to_html()):
            self.assertIn('Review configured phrase-match rate', output)
            self.assertIn('when it comes to', output)
            self.assertNotIn('padding dilutes', output)
            self.assertNotIn('heavy repetition signals', output)
        self.assertEqual(['content'], report.meta['scan_scope']['completed'])

    def test_legacy_and_current_plans_require_context_not_synonym_substitution(self):
        for rid, title in ((RATE, 'Filler / padding language'), (COUNT, 'Some filler phrasing'),
                           (RATIO, 'Repetitive vocabulary'), (RATIO, 'Review lower type/token ratio')):
            report = Report(URL)
            report.add('content', 'medium', title, recommendation='OLD_SPUN_CLAIM', rule_id=rid)
            result = plan.build_plan(json.loads(report.to_json()), str(FIXTURE))
            before = json.dumps(result, sort_keys=True)
            action, = result['actions']
            self.assertEqual(title, action['title'])
            self.assertEqual('medium', action['severity'])
            self.assertEqual('review_required', action['safety'])
            self.assertIn('consistent technical terms', action['proposed_change'])
            markdown = plan.render_markdown(result)
            self.assertIn('Review recorded style-pattern observation', markdown)
            self.assertIn('not verified padding', markdown)
            self.assertNotIn('OLD_SPUN_CLAIM', markdown)
            self.assertEqual(before, json.dumps(result, sort_keys=True))

    def test_diff_matches_stable_id_and_records_priority_calibration_only(self):
        old = Report(URL, final_url=URL, fetched_status=200)
        old.add('content', 'medium', 'Filler / padding language')
        new = Report(URL, final_url=URL, fetched_status=200)
        new.findings.append(selected(measured(QUOTED), RATE))
        delta = diff_scan.diff_reports(json.loads(old.to_json()), json.loads(new.to_json()))
        self.assertEqual([], delta['added'])
        self.assertEqual([], delta['resolved'])
        self.assertEqual(1, len(delta['improved']))
        self.assertEqual(2, new.score() - old.score())  # priority correction, no page changed


if __name__ == '__main__': unittest.main()
