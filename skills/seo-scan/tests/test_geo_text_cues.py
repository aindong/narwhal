"""GEO lexical counts must not masquerade as semantic or engine measurements."""

import json
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_geo
import diff_scan
import plan
import scan
from lib import htmlx, http
from lib.config import Config
from lib.report import Report

URL = 'https://example.test/guide'
NEGATIVE = ('geo.few.question.based.headings', 'geo.few.self.contained.citable.passages',
            'geo.no.statistics.or.citations', 'geo.no.direct.answer.up.top')
POSITIVE = ('geo.question.based.headings.present', 'geo.citable.passage.structure',
            'geo.evidence.signals.present', 'geo.direct.answer.near.the.top')


def audit(markup='', parser=htmlx._parse_stdlib):
    doc = parser(markup, URL)
    report = Report(URL, final_url=URL, fetched_status=200)
    audit_geo.audit(doc, None, report, {})
    return report


def run_helper(name, markup, **kwargs):
    report = Report(URL, final_url=URL, fetched_status=200)
    getattr(audit_geo, name)(htmlx._parse_stdlib(markup, URL), report, **kwargs)
    return report


def receipt(report, key):
    return report.meta['geo_text_cues']['checks'][key]


class TestGeoTextCues(unittest.TestCase):
    def test_numbers_and_reference_links_do_not_become_an_absence_verdict(self):
        report = run_helper('_evidence_density', '<p>We inspected 20 records across 3 collections.</p>'
                            '<a href="https://www.loc.gov/">Library of Congress catalog</a>', article=True)
        finding, = report.findings
        self.assertEqual(NEGATIVE[2], finding.rule_id)
        self.assertEqual('low', finding.severity)
        self.assertEqual('No configured statistics/citation cues', finding.title)
        self.assertIn('Other numbers, links or references may exist', finding.detail)
        self.assertIn('does not prove missing evidence', finding.recommendation)
        self.assertIn('Do not invent statistics or citations', finding.recommendation)
        self.assertEqual({'statistic_matches': 0, 'citation_cue_matches': 0,
                          'source_validity_checked': False}, receipt(report, 'evidence_cues'))

    def test_citation_words_and_made_up_statistics_are_not_validated_sources(self):
        report = run_helper('_evidence_density', '<p>No study supports this report. The 40% figure was made up.</p>')
        finding, = report.findings
        self.assertEqual(POSITIVE[2], finding.rule_id)
        self.assertEqual('good', finding.severity)
        self.assertIn('factual support and source validity are not checked', finding.detail)
        self.assertEqual(1, receipt(report, 'evidence_cues')['statistic_matches'])
        self.assertEqual(2, receipt(report, 'evidence_cues')['citation_cue_matches'])

    def test_intro_word_match_does_not_prove_an_answer(self):
        report = run_helper('_direct_answer', '<p>This is an irrelevant opening with no useful answer.</p>')
        finding, = report.findings
        self.assertEqual(POSITIVE[3], finding.rule_id)
        self.assertIn('accuracy and citation impact are not measured', finding.detail)
        self.assertTrue(receipt(report, 'intro_cues')['matched'])

    def test_nonenglish_intro_is_not_called_a_missing_answer(self):
        report = run_helper('_direct_answer', '<p>本页说明织物的保存方法，先检查边缘，再记录尺寸。</p>')
        finding, = report.findings
        self.assertEqual(NEGATIVE[3], finding.rule_id)
        self.assertEqual('No configured introductory answer cues', finding.title)
        self.assertIn('English cue absence does not prove a missing answer', finding.recommendation)
        self.assertFalse(receipt(report, 'intro_cues')['matched'])

    def test_intro_token_limit_and_matching_are_unchanged(self):
        for count, expected in ((79, True), (80, False)):
            with self.subTest(count=count):
                report = run_helper('_direct_answer', '<p>' + 'word ' * count + 'is useful</p>')
                self.assertEqual(expected, receipt(report, 'intro_cues')['matched'])
                self.assertEqual(80, receipt(report, 'intro_cues')['inspected_tokens'])

    def test_question_observations_describe_the_actual_english_ascii_matcher(self):
        markup = ('<h1>How excluded</h1><h2>How the catalog works</h2><h3>Details</h3>'
                  '<h4>如何保养织物？</h4><h5>كيف نحفظ النسيج؟</h5><h6>Autre question?</h6>')
        report = run_helper('_question_headings', markup)
        finding, = report.findings
        self.assertEqual(POSITIVE[0], finding.rule_id)
        self.assertEqual(2, receipt(report, 'question_headings')['matched'])
        self.assertEqual(5, receipt(report, 'question_headings')['examined'])
        self.assertIn('English starters or a terminal ASCII question mark', finding.detail)
        self.assertIn('Question relevance and engine matching are not measured', finding.detail)

    def test_question_fraction_threshold_is_unchanged(self):
        for total, expected in ((5, POSITIVE[0]), (6, NEGATIVE[0])):
            with self.subTest(total=total):
                markup = '<h2>How things work</h2>' + '<h2>Details</h2>' * (total - 1)
                report = run_helper('_question_headings', markup, article=True)
                self.assertEqual(expected, report.findings[0].rule_id)
                self.assertEqual(0.2, receipt(report, 'question_headings')['advisory_below_fraction'])

    def test_question_advice_is_low_and_optional_even_on_articles(self):
        for article in (False, True):
            with self.subTest(article=article):
                report = run_helper('_question_headings', '<h2>Materials</h2>', article=article)
                finding, = report.findings
                self.assertEqual('low', finding.severity)
                self.assertIn('questions are optional when useful', finding.recommendation)
                self.assertNotIn('Rewrite key', finding.recommendation)

    def test_sentence_groups_do_not_claim_real_paragraphs_or_citability(self):
        report = run_helper('_passage_citability', '<p>' + 'word ' * 130 + '</p>')
        finding, = report.findings
        self.assertEqual(NEGATIVE[1], finding.rule_id)
        self.assertEqual('low', finding.severity)
        self.assertEqual(0, receipt(report, 'sentence_groups')['in_range'])
        self.assertEqual(1, receipt(report, 'sentence_groups')['examined'])
        self.assertIn('Actual paragraphs, self-containment and engine citability are not measured', finding.detail)
        self.assertIn('range is not an engine requirement', finding.recommendation)
        self.assertIn('do not pad or split useful text', finding.recommendation)

    def test_in_range_group_is_not_a_positive_citability_verdict(self):
        report = run_helper('_passage_citability', '<p>' + 'word ' * 50 + '</p>')
        finding, = report.findings
        self.assertEqual(POSITIVE[1], finding.rule_id)
        self.assertEqual('Sentence groups in the configured word range', finding.title)
        self.assertIn('engine citability are not measured', finding.detail)
        self.assertEqual(1, receipt(report, 'sentence_groups')['in_range'])

    def test_group_counter_matches_the_legacy_algorithm_with_custom_thresholds(self):
        def legacy(text, lo, hi):
            groups, count = [], 0
            for sentence in re.split(r'(?<=[.!?])\s+(?=[A-Z])', text):
                count += len(re.findall(r"[A-Za-z][A-Za-z'-]+", sentence))
                if count >= lo:
                    groups.append(count)
                    count = 0
            if count:
                groups.append(count)
            return len(groups), sum(lo <= count <= hi for count in groups)
        texts = ('word ' * 130, 'Word. ' * 70, 'Word. lower case. Next group!',
                 "Café l'été. Other text with hyphen-words. 中文。", 'I a 123 中文')
        for text in texts:
            for lo, hi in ((40, 120), (2, 8), (1, 4), (10, 40)):
                with self.subTest(text=text[:12], bounds=(lo, hi)):
                    report = run_helper('_passage_citability', '<p>' + text + '</p>',
                                        th={'passage_min': lo, 'passage_max': hi})
                    data = receipt(report, 'sentence_groups')
                    self.assertEqual(legacy(text, lo, hi), (data['examined'], data['in_range']))
                    self.assertEqual((lo, hi), (data['word_min'], data['word_max']))

    def test_empty_input_records_counts_without_inventing_passes(self):
        report = audit()
        data = report.meta['geo_text_cues']
        self.assertEqual('editorial_review_only', data['interpretation'])
        self.assertEqual(4, len(data['checks']))
        self.assertFalse(any(f.rule_id in POSITIVE for f in report.findings))
        self.assertEqual(0, receipt(report, 'question_headings')['examined'])
        self.assertEqual(0, receipt(report, 'sentence_groups')['examined'])
        self.assertEqual(0, receipt(report, 'intro_cues')['inspected_tokens'])

    def test_decimal_bounds_serialize_exactly_without_rounding_comparisons(self):
        markup = '<p>' + 'word ' * 40 + '</p>'
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, markup, 1)
        for lower, expected in ((Decimal('40'), 1), (Decimal('40.000000000000000000000001'), 0)):
            for source in ('context', 'config'):
                with self.subTest(lower=lower, source=source):
                    bounds = {'passage_min': lower, 'passage_max': Decimal('120')}
                    options = ({'ctx': {'thresholds': bounds}} if source == 'context'
                               else {'ctx': {}, 'config': Config({'thresholds': bounds})})
                    with mock.patch.object(http, 'fetch', return_value=response), \
                            mock.patch.object(htmlx, '_main_content', return_value=''):
                        report = scan.scan(URL, only=['geo'], check_images=False, **options)
                    data = json.loads(report.to_json())['meta']['geo_text_cues']['checks']['sentence_groups']
                    self.assertEqual(expected, data['in_range'])
                    self.assertEqual({'kind': 'decimal', 'value': str(lower)}, data['word_min'])
                    self.assertEqual({'kind': 'decimal', 'value': '120'}, data['word_max'])
                    self.assertNotIn('rule_config', report.meta['scan_settings'])

    def test_fraction_and_nonfinite_float_bounds_have_json_safe_descriptors(self):
        cases = ((Fraction(81, 2), {'kind': 'fraction', 'value': '81/2'}),
                 (float('inf'), {'kind': 'nonfinite_float', 'value': 'inf'}),
                 (float('-inf'), {'kind': 'nonfinite_float', 'value': '-inf'}),
                 (float('nan'), {'kind': 'nonfinite_float', 'value': 'nan'}))
        for lower, expected in cases:
            with self.subTest(lower=lower):
                report = run_helper('_passage_citability', '<p>' + 'word ' * 40 + '</p>',
                                    th={'passage_min': lower, 'passage_max': 120})
                def reject(value):
                    self.fail('Nonfinite JSON literal emitted: ' + value)
                data = json.loads(report.to_json(), parse_constant=reject)
                self.assertEqual(expected, data['meta']['geo_text_cues']['checks']['sentence_groups']['word_min'])

    def test_other_comparable_numeric_types_are_unrecorded_not_stringified_or_rejected(self):
        class Bound:
            def __le__(self, other):
                return 40 <= other
            def __ge__(self, other):
                return 40 >= other
            def __str__(self):
                return '40'
        report = run_helper('_passage_citability', '<p>' + 'word ' * 40 + '</p>',
                            th={'passage_min': Bound(), 'passage_max': 120})
        data = json.loads(report.to_json())['meta']['geo_text_cues']['checks']['sentence_groups']
        self.assertEqual(1, data['in_range'])
        self.assertEqual({'kind': 'unrecorded_numeric_type'}, data['word_min'])

    def test_receipt_itself_does_not_change_score_or_findings(self):
        report = Report(URL)
        audit_geo._record_text_cue(report, 'intro_cues', {'matched': False})
        self.assertEqual(100, report.score())
        self.assertEqual([], report.findings)
        self.assertIn('Not language understanding', json.loads(report.to_json())['meta']['geo_text_cues']['limits'])

    def test_both_parsers_keep_counts_and_stable_ids_on_the_same_extraction_basis(self):
        markup = '<h2>How this works</h2><p>This is a study of 40% of the ' + 'word ' * 50 + '</p>'
        # Compare parsers, not all-visible text against optional main text.
        with mock.patch.object(htmlx, '_main_content', return_value=''):
            reports = [audit(markup, parser) for parser in (htmlx._parse_stdlib, htmlx.parse)]
        self.assertEqual(reports[0].meta['geo_text_cues'], reports[1].meta['geo_text_cues'])
        for report in reports:
            self.assertTrue(set(POSITIVE).issubset({f.rule_id for f in report.findings}))

    def test_intro_receipt_follows_the_selected_text_when_main_extraction_differs(self):
        main = 'This is a study of 40% of the ' + 'word ' * 50
        markup = '<h2>How this works</h2><p>' + main + '</p>'
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, markup, 1)
        reports = []
        for isolated in ('', main):
            with mock.patch.object(http, 'fetch', return_value=response), \
                    mock.patch.object(htmlx, '_main_content', return_value=isolated):
                reports.append(scan.scan(URL, only=['geo'], ctx={}, check_images=False))
        self.assertEqual('visible text', reports[0].meta['extraction'])
        self.assertEqual('main-content (trafilatura)', reports[1].meta['extraction'])
        counts = [receipt(report, 'intro_cues')['inspected_tokens'] for report in reports]
        self.assertEqual([61, 58], counts)
        for report in reports:
            self.assertEqual(min(80, len(report._doc.body_text.split())),
                             receipt(report, 'intro_cues')['inspected_tokens'])
            self.assertTrue(set(POSITIVE).issubset({f.rule_id for f in report.findings}))

    def test_compact_reports_include_caveats_not_just_json_detail(self):
        report = audit('<h2>Materials</h2><p>We inspected 20 records.</p>')
        self.assertTrue(set(NEGATIVE).issubset({f.rule_id for f in report.findings}))
        for output in (report.to_json(), report.to_markdown(), report.to_html()):
            self.assertIn('citation impact is not measured', output)
            self.assertIn('not an engine requirement', output)
            self.assertIn('does not prove missing evidence', output)
            self.assertIn('does not prove a missing answer', output)
            self.assertNotIn('No numbers, data points, or source references detected', output)
            self.assertNotIn('AI engines quote cleanly', output)
            self.assertNotIn('AI overviews lift the top summary', output)

    def test_scan_receipts_are_additive_and_auditor_scope_is_preserved(self):
        markup = '<h2>Materials</h2><p>We inspected 20 records.</p>'
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, markup, 1)
        with mock.patch.object(http, 'fetch', return_value=response), \
                mock.patch('socket.socket', side_effect=AssertionError('No network')):
            report = scan.scan(URL, only=['geo'], ctx={}, check_images=False)
        data = json.loads(report.to_json())
        self.assertEqual(['geo'], data['meta']['scan_scope']['completed'])
        self.assertEqual('configured_english_oriented_patterns', data['meta']['geo_text_cues']['basis'])
        self.assertEqual(1, data['meta']['geo_text_cues']['version'])

    def test_updated_title_filters_suppress_findings_not_literal_counts(self):
        config = Config({'ignore': {'titles': ['configured statistics/citation cues']}})
        report = Report(URL, ignore=config.is_ignored)
        audit_geo._evidence_density(htmlx._parse_stdlib('<p>20 records</p>', URL), report)
        self.assertEqual([], report.findings)
        self.assertEqual(0, receipt(report, 'evidence_cues')['statistic_matches'])

    def test_priority_correction_keeps_diff_identity_without_claiming_page_edits(self):
        old = Report(URL, final_url=URL, fetched_status=200)
        for title in ('Few question-based headings', 'Few self-contained, citable passages',
                      'No statistics or citations'):
            old.add('geo', 'medium', title)
        current = audit('<h2>Materials</h2><p>We inspected 20 records.</p>')
        new = Report(URL, final_url=URL, fetched_status=200,
                     findings=[f for f in current.findings if f.rule_id in NEGATIVE[:3]])
        delta = diff_scan.diff_reports(json.loads(old.to_json()), json.loads(new.to_json()))
        self.assertEqual([], delta['added'])
        self.assertEqual([], delta['resolved'])
        self.assertEqual(3, len(delta['improved']))
        self.assertEqual(6, delta['score_delta'])  # rule correction, not measured SEO/page improvement

    def test_planner_keeps_new_and_legacy_cue_edits_conditional(self):
        fixture = Path(__file__).parent / 'fixtures/planner/plain_html'
        old_titles = ('Few question-based headings', 'Few self-contained, citable passages',
                      'No statistics or citations', 'No direct answer up top')
        current = audit('<h2>Materials</h2><p>We inspected 20 records.</p>')
        sources = [json.loads(current.to_json()), {'url': URL, 'findings': [
            {'category': 'geo', 'severity': 'medium', 'title': title} for title in old_titles]}]
        for source in sources:
            built = plan.build_plan(source, str(fixture))
            actions = {action['rule_id']: action for action in built['actions']}
            for rule_id in NEGATIVE:
                with self.subTest(source=source.get('schema_version'), rule=rule_id):
                    action = actions[rule_id]
                    self.assertEqual('review_required', action['safety'])
                    self.assertIn('Keep useful', action['proposed_change'])
                    self.assertNotIn('Revise the owning page content', action['proposed_change'])
            self.assertIn('do not invent statistics or citations', plan.render_markdown(built))

    def test_crawler_and_resource_observations_are_unchanged(self):
        report = Report(URL)
        audit_geo.audit(htmlx._parse_stdlib('<p>Text.</p>', URL), None, report,
                        {'robots_txt': 'User-agent: OAI-SearchBot\nDisallow: /', 'llms_txt': False})
        findings = {f.rule_id: f for f in report.findings}
        self.assertEqual('high', findings['geo.ai.crawlers.are.blocked.in.robots.txt'].severity)
        self.assertEqual('low', findings['geo.no.llms.txt'].severity)
        self.assertEqual('/', report.meta['ai_crawler_access']['checked_path'])


if __name__ == '__main__':
    unittest.main()
