"""Exact heading-pattern review and question-candidate provenance regressions."""
import copy
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_geo
import brief
import compare
from lib import htmlx, question_observation as cues
from lib.report import Report, md_to_html


def page(name, matched, examined):
    url = 'https://' + name + '.test/guide'
    headings = [(1, 'Manual')] + [(2, 'How to calibrate ' + str(i)) for i in range(matched)]
    headings += [(2, 'Calibration procedure ' + str(i)) for i in range(examined - matched)]
    doc = htmlx.Doc(url, title='Manual', text='Useful manual text.', headings=headings)
    return {'url': url, 'facts': compare.facts(Report(url, fetched_status=200), doc),
            'headings': doc.headings, 'text': doc.body_text}


def result(you, rival):
    return {'you': you['facts'], 'competitors': [rival['facts']], 'failed': [],
            **compare.gap_analysis(you['facts'], [rival['facts']])}


class TestQuestionObservation(unittest.TestCase):
    def setUp(self):
        self.below = page('below', 8, 41)
        self.zero = page('zero', 0, 1)
        self.edge = page('edge', 1, 5)

    def test_preserves_rounded_alias_but_records_actual_8_of_41_counts(self):
        facts = self.below['facts']
        self.assertEqual(0.2, facts['question_ratio'])
        self.assertEqual((8, 41), (facts['question_cues']['matched'], facts['question_cues']['examined']))
        self.assertIs(False, cues.at_threshold(facts))
        self.assertIn('8/41 heading-pattern matches', cues.cell(facts))

    def test_rounded_rival_does_not_create_a_false_gap_or_structure_flag(self):
        self.assertNotIn(cues.REVIEW_LABEL, [g['what'] for g in result(self.zero, self.below)['gaps']])
        self.assertEqual({}, brief.structure_targets(self.zero, [self.below]))
        self.assertEqual({}, brief.structure_targets(None, [self.below]))

    def test_rounded_own_ratio_no_longer_hides_a_genuine_heuristic_difference(self):
        data = result(self.below, self.edge)
        self.assertIn(cues.REVIEW_LABEL, [g['what'] for g in data['gaps']])
        self.assertEqual({'question_headings': True}, brief.structure_targets(self.below, [self.edge]))
        text = compare.render_markdown(data)
        self.assertIn('Questions are optional', text)
        self.assertNotIn('Rephrase key H2/H3s', text)

    def test_exact_one_in_five_boundary_and_zero_eligible_are_distinct(self):
        self.assertIs(True, cues.at_threshold(self.edge['facts']))
        empty = page('empty', 0, 0)
        self.assertIsNone(cues.at_threshold(empty['facts']))
        self.assertIn('no eligible headings', cues.cell(empty['facts']))
        self.assertEqual({}, brief.structure_targets(empty, [self.edge]))
        self.assertNotIn(cues.REVIEW_LABEL, [g['what'] for g in result(empty, self.edge)['gaps']])

    def test_threshold_is_integer_exact_even_when_a_float_fraction_rounds_to_point_two(self):
        facts = copy.deepcopy(self.edge['facts'])
        matched = 2 ** 56
        facts['question_cues'].update({'matched': matched, 'examined': matched * 5 + 1})
        self.assertEqual(0.2, cues.fraction(facts['question_cues']))
        self.assertIs(False, cues.at_threshold(facts))

    def test_legacy_ratio_and_version_never_invent_exact_counts(self):
        facts = {'question_ratio': 0.2, 'tool_version': '1.30.19'}
        self.assertIsNone(cues.recorded(facts))
        self.assertIsNone(cues.at_threshold(facts))
        self.assertIn('counts/basis unrecorded', cues.cell(facts))
        self.assertNotIn('20%', cues.cell(facts))

    def test_conflicting_alias_and_malformed_receipts_remain_unverified(self):
        for key, value in (('version', True), ('basis', 'real_queries'), ('matched', False),
                           ('matched', -1), ('matched', 10 ** 100), ('examined', 0),
                           ('interpretation', 'engine_requirement')):
            facts = copy.deepcopy(self.edge['facts'])
            facts['question_cues'][key] = value
            with self.subTest(key=key, value=value):
                self.assertIsNone(cues.recorded(facts))
        for alias in (False, float('nan'), float('inf'), -1, '0.2', 10 ** 1000, 0.19):
            facts = copy.deepcopy(self.edge['facts'])
            facts['question_ratio'] = alias
            self.assertIsNone(cues.recorded(facts))
            self.assertIsNone(cues.at_threshold(facts))

    def test_match_rule_and_level_scope_preserve_the_page_auditor_counts(self):
        headings = [(1, 'How to calibrate?'), (2, 'How to calibrate'), (3, 'Detailed procedure?  '),
                    (4, '怎么校准？'), (5, 'Cómo calibrar?'), (6, 'Howl frequency'),
                    (2, ''), (2, '  ')]
        doc = htmlx.Doc('https://example.test/', headings=headings)
        report = Report(doc.base_url, fetched_status=200)
        audit_geo._question_headings(doc, report)
        receipt = cues.observe(headings, compare._QUESTION_WORDS)
        old = report.meta['geo_text_cues']['checks']['question_headings']
        self.assertEqual((old['matched'], old['examined']), (receipt['matched'], receipt['examined']))
        self.assertEqual((3, 6), (receipt['matched'], receipt['examined']))

    def test_hub_counts_are_observed_but_not_brief_structure_benchmarks(self):
        self.edge['facts']['page_kind'] = 'hub'
        value = brief.synthesize(None, [self.edge], None, topic='Manual')
        self.assertEqual({}, value['structure'])
        self.assertIn('1/5 heading-pattern matches', brief.render_markdown(value))

    def test_old_gap_and_legacy_structure_flag_are_not_instructions(self):
        data = result(self.zero, self.below)
        data['gaps'].append({'what': 'Question-based headings', 'who': [self.below['url']], 'action': 'REWRITE_ALL_HEADINGS'})
        self.assertNotIn('REWRITE_ALL_HEADINGS', compare.render_markdown(data))
        value = brief.synthesize(self.zero, [self.below], None)
        value['structure']['question_headings'] = True  # stale rounded legacy decision
        text = brief.render_markdown(value)
        self.assertIn('flag is unverified', text)
        self.assertNotIn('## Structure review (optional)', text)

    def test_missing_receipts_cannot_validate_a_legacy_structure_flag(self):
        value = brief.synthesize(self.zero, [self.edge], None)
        del value['you']['question_cues']
        del value['competitors'][0]['question_cues']
        self.assertIn('flag is unverified', brief.render_markdown(value))

    def test_optional_structure_review_uses_actual_facts_not_rounded_alias(self):
        value = brief.synthesize(self.below, [self.edge], None)
        text = brief.render_markdown(value)
        self.assertIn('## Structure review (optional)', text)
        self.assertIn('Keep useful descriptive headings', text)
        self.assertNotIn('as the questions users ask', text)

    def test_candidate_sources_distinguish_compared_headings_from_recorded_gsc_queries(self):
        subs = [{'heading': 'How to calibrate?', 'who': 'https://rival.test/', 'question': True}]
        striking = [{'query': 'why widgets drift', 'impressions': 25}]
        values = brief.questions_to_answer(subs, striking)  # synthetic GSC input, not live API validation
        self.assertEqual(['compared_heading', 'gsc_query'], [q['source_kind'] for q in values])
        value = brief.synthesize(self.zero, [self.edge], None)
        value['questions'] = values
        text = brief.render_markdown(value)
        self.assertIn('Compared-page heading; not verified query data', text)
        self.assertIn('Recorded GSC query', text)
        self.assertNotIn('citable passages are what AI answer engines lift', text)
        self.assertIn('only when useful', text)

    def test_legacy_question_source_string_does_not_infer_gsc_provenance(self):
        value = brief.synthesize(self.zero, [self.edge], None)
        value['questions'] = [{'question': 'How to calibrate?', 'source': 'your own striking-distance query (25 impressions)'}]
        text = brief.render_markdown(value)
        self.assertIn('Source kind unrecorded; query grounding unverified', text)
        self.assertNotIn('Recorded GSC query', text)

    def test_rendering_is_read_only_offline_and_summary_ignores_untrusted_labels(self):
        data = result(self.zero, self.edge)
        value = brief.synthesize(self.zero, [self.edge], None)
        for report, renderer, serializer in ((data, compare.render_markdown, compare.render_json),
                                             (value, brief.render_markdown, brief.render_json)):
            before = serializer(report)
            with mock.patch('socket.socket', side_effect=AssertionError('No network')):
                md_to_html(renderer(report))
            self.assertEqual(before, serializer(report))
        facts = copy.deepcopy(self.edge['facts'])
        facts['question_cues']['limits'] = '<img src="https://evil.test/pixel">'
        facts['url'] = '[bad](https://evil.test)'
        self.assertNotIn('evil.test', ' '.join(cues.summary(facts, [facts])))
        for rivals in (None, {}, [{}] * 101):
            self.assertIn('unrecorded or unsupported', ' '.join(cues.summary(None, rivals)))


if __name__ == '__main__':
    unittest.main()
