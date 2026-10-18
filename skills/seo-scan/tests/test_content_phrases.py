"""Phrase matches are review prompts, never authorship or SEO-risk detection."""

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

URL = 'https://example.test/catalog'
HIGH_ID = 'content.reads.as.ai.generated.generic'
LOW_ID = 'content.some.generic.ai.sounding.phrasing'
PASS_ID = 'content.clean.specific.writing'
BASE = '''The museum catalog records a wool textile from the northern workshop.
The object measures two metres across and weighs nine kilograms after cleaning.
Its blue border contains a repaired seam, while the central panel shows boats,
buildings, birds and a narrow stone bridge. Conservators inspected the reverse
under diffuse light and photographed every damaged section before treatment.
A removable mount supports the fragile lower edge without covering the original
stitching. Visitors can inspect the repaired corner through the glass case without
touching the textile. The catalog distinguishes observed materials from uncertain
workshop attribution and describes the repair method so future conservators can
assess whether further intervention is needed. The measured dimensions refer to
the textile rather than its modern display frame.'''
FOUR = BASE + ' In conclusion, in summary, the seamless tapestry remains on display.'


def quality(text):
    report = Report(URL, final_url=URL, fetched_status=200)
    audit_content._quality(text, report)
    return report


def phrases(report):
    return [finding for finding in report.findings if finding.rule_id in (HIGH_ID, LOW_ID)]


class TestContentPhrases(unittest.TestCase):
    def test_four_matches_are_low_priority_contextual_advice_not_authorship(self):
        report = quality(FOUR)
        finding, = phrases(report)
        self.assertEqual(HIGH_ID, finding.rule_id)
        self.assertEqual('low', finding.severity)
        self.assertEqual('Common phrases worth reviewing', finding.title)
        self.assertIn('4 distinct configured phrase matches (4 total)', finding.detail)
        self.assertIn('do not determine authorship, originality, helpfulness or ranking impact', finding.detail)
        self.assertIn('keep useful wording', finding.recommendation)
        self.assertEqual('in conclusion; in summary; seamless; tapestry', finding.evidence)
        self.assertNotIn('helpful-content risk', finding.recommendation)
        self.assertTrue(finding.reference_url.endswith('#filler--phrase-review'))

    def test_two_and_three_distinct_matches_keep_the_lower_legacy_id(self):
        for suffix, count in (('In conclusion, the tapestry.', 2),
                              ('In conclusion, the seamless tapestry.', 3)):
            with self.subTest(count=count):
                finding, = phrases(quality(BASE + suffix))
                self.assertEqual(LOW_ID, finding.rule_id)
                self.assertEqual('low', finding.severity)
                self.assertEqual('Some common phrases worth reviewing', finding.title)
                self.assertIn(str(count) + ' distinct configured phrase matches', finding.detail)
                self.assertIn('do not determine authorship', finding.detail)

    def test_many_repetitions_of_one_phrase_do_not_become_distinct_matches(self):
        text = BASE + ' In conclusion.' * 10
        counts = content_quality.analyze(text)
        self.assertEqual(1, counts['ai_distinct'])
        self.assertEqual(10, counts['ai_pattern_count'])
        self.assertEqual([], phrases(quality(text)))

    def test_short_text_retains_its_existing_skip(self):
        self.assertEqual([], quality('In conclusion, in summary, a seamless tapestry.').findings)

    def test_absence_of_matches_is_not_a_positive_quality_or_authorship_verdict(self):
        finding, = [f for f in quality(BASE).findings if f.rule_id == PASS_ID]
        self.assertEqual('good', finding.severity)
        self.assertEqual('Few configured style-pattern matches', finding.title)
        self.assertIn('0 configured phrase matches; 0 distinct common-phrase matches', finding.detail)
        self.assertIn('does not establish originality or content quality', finding.detail)
        self.assertNotIn('Clean, specific writing', quality(BASE).to_markdown())

    def test_legacy_helper_keys_remain_literal_counts_not_probabilities(self):
        counts = content_quality.analyze(FOUR)
        self.assertEqual(4, counts['ai_distinct'])
        self.assertEqual(4, counts['ai_pattern_count'])
        self.assertEqual(['in conclusion', 'in summary', 'seamless', 'tapestry'], counts['ai_examples'])
        self.assertNotIn('ai_probability', counts)

    def test_filler_and_vocabulary_rules_are_not_disabled(self):
        report = quality((BASE + " In today's digital world, when it comes to repairs. ") * 4)
        ids = {f.rule_id: f for f in report.findings}
        self.assertIn('content.filler.padding.language', ids)
        self.assertEqual('low', ids['content.filler.padding.language'].severity)
        self.assertIn('content.repetitive.vocabulary', ids)

    def test_language_scope_and_both_parser_paths_are_preserved(self):
        for parser in (htmlx._parse_stdlib, htmlx.parse):
            for lang, expected in (('en', 1), ('en-GB', 1), ('fr', 0)):
                with self.subTest(parser=parser.__name__, lang=lang):
                    html = '<html lang="' + lang + '"><body><p>' + FOUR + '</p></body></html>'
                    report = Report(URL)
                    audit_content.audit(parser(html, URL), None, report)
                    self.assertEqual(expected, len(phrases(report)))

    def test_scan_json_markdown_html_keep_evidence_and_caveats_without_network(self):
        html = '<html lang="en"><head><title>Museum catalog</title></head><body><p>' + FOUR + '</p></body></html>'
        response = http.Response(url=URL, final_url=URL, status=200,
                                 headers={'content-type': 'text/html'}, text=html, elapsed_ms=1)
        with mock.patch.object(http, 'fetch', return_value=response), \
                mock.patch('socket.socket', side_effect=AssertionError('No network')):
            report = scan.scan(URL, only=['content'], ctx={}, check_images=False)
        data = json.loads(report.to_json())
        finding, = [f for f in data['findings'] if f['rule_id'] == HIGH_ID]
        self.assertEqual('low', finding['severity'])
        for output in (report.to_json(), report.to_markdown(), report.to_html()):
            self.assertIn('Common phrases worth reviewing', output)
            self.assertIn('authorship, originality, helpfulness or ranking impact', output)
            self.assertIn('in conclusion; in summary; seamless; tapestry', output)
            self.assertNotIn('Reads as AI-generated', output)
            self.assertNotIn('helpful-content risk', output)
        self.assertEqual(['content'], data['meta']['scan_scope']['completed'])

    def test_diff_matches_the_existing_rule_instead_of_inventing_resolution(self):
        old = Report(URL, final_url=URL, fetched_status=200)
        old.add('content', 'medium', 'Reads as AI-generated / generic')
        new = Report(URL, final_url=URL, fetched_status=200)
        finding, = phrases(quality(FOUR))
        new.findings.append(finding)
        delta = diff_scan.diff_reports(json.loads(old.to_json()), json.loads(new.to_json()))
        self.assertEqual([], delta['added'])
        self.assertEqual([], delta['resolved'])
        self.assertEqual([], delta['worsened'])
        self.assertEqual(1, len(delta['improved']))
        self.assertEqual(2, new.score() - old.score())  # rule correction, not page/outcome improvement

    def test_current_title_filters_can_suppress_editorial_advice(self):
        config = Config({'ignore': {'titles': ['common phrases worth reviewing']}})
        report = Report(URL, ignore=config.is_ignored)
        audit_content._quality(FOUR, report)
        self.assertEqual([], phrases(report))

    def test_planner_does_not_turn_new_or_legacy_phrase_reports_into_required_rewrites(self):
        fixture = Path(__file__).parent / 'fixtures/planner/plain_html'
        for rule_id, title in ((HIGH_ID, 'Common phrases worth reviewing'),
                               (HIGH_ID, 'Reads as AI-generated / generic'),
                               (LOW_ID, 'Some common phrases worth reviewing'),
                               (LOW_ID, 'Some generic/AI-sounding phrasing')):
            with self.subTest(title=title):
                report = Report(URL, final_url=URL, fetched_status=200)
                report.add('content', 'low', title, evidence='tapestry', rule_id=rule_id)
                built = plan.build_plan(json.loads(report.to_json()), str(fixture))
                action, = built['actions']
                self.assertEqual('content', action['artifact'])
                self.assertEqual('review_required', action['safety'])
                self.assertIn('Keep useful wording', action['proposed_change'])
                self.assertIn('do not determine authorship', action['proposed_change'])
                self.assertNotIn('Revise the owning page content', action['proposed_change'])
                self.assertEqual('tapestry', action['evidence'])
                self.assertIn('Keep useful wording', plan.render_markdown(built))


if __name__ == '__main__':
    unittest.main()
