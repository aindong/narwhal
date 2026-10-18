"""Brief heading-term candidates do not establish missing semantic content."""
import copy
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import brief
from lib import subtopic_observation as observation
from lib.report import md_to_html
from test_brief_grounding import page, BASE, RIVAL


def data(text='Automobile coverage premiums.', heading='Car insurance costs', topic=False):
    own = page(BASE, '<h1>A guide</h1><p>' + text + '</p>')
    rival = page(RIVAL, '<h1>Reference guide</h1><h2>' + heading + '</h2><p>Reference instructions.</p>')
    return brief.synthesize(None if topic else own, [rival], None, topic='A guide' if topic else None)


class TestSubtopicObservation(unittest.TestCase):
    def test_synonym_counterexample_remains_a_candidate_not_a_semantic_gap(self):
        value = data()
        candidate, = value['missing_subtopics']
        self.assertEqual('Car insurance costs', candidate['heading'])
        receipt = candidate['term_match']
        self.assertEqual((0, 3, 2), (receipt['matched_terms'], receipt['terms_examined'], receipt['review_cutoff']))
        text = brief.render_markdown(value)
        self.assertIn('0/3 heading terms matched', text)
        self.assertIn('synonyms can be missed', text)
        self.assertNotIn("Missing subtopics — sections they have, your text doesn't", text)
        self.assertIn('not proof of missing content', text)

    def test_unrelated_occurrences_can_match_without_proving_semantic_coverage(self):
        value = data('A car arrived. Insurance software changed. Costs of paper fell.')
        self.assertEqual([], value['missing_subtopics'])
        text = brief.render_markdown(value)
        self.assertIn('unrelated word occurrences can match', text)
        self.assertIn('does not establish complete topic coverage', text)

    def test_exact_half_threshold_preserves_historical_candidate_selection(self):
        for text, expected, examined, cutoff in [('alpha', 1, 4, 2), ('alpha beta', 0, 4, 2),
                                                  ('alpha', 1, 3, 2), ('alpha beta', 0, 3, 2)]:
            heading = 'alpha beta gamma delta' if examined == 4 else 'alpha beta gamma'
            candidates = brief.subtopic_gaps({'text': text, 'headings': []},
                                             [{'url': RIVAL, 'headings': [(2, heading)]}])
            self.assertEqual(expected, len(candidates))
            if candidates:
                self.assertEqual(cutoff, candidates[0]['term_match']['review_cutoff'])

    def test_prefix_match_is_heuristic_and_not_changed_to_a_semantic_matcher(self):
        self.assertTrue(brief._match('calibration', 'calibrate'))
        self.assertFalse(brief._match('car', 'automobile'))
        self.assertIn('same first six characters', observation.LIMITS)

    def test_topic_counts_do_not_invent_zero_own_page_matches(self):
        value = data(topic=True)
        candidate, = value['missing_subtopics']
        self.assertIsNone(candidate['term_match']['matched_terms'])
        self.assertEqual('topic', value['subtopic_review']['mode'])
        text = brief.render_markdown(value)
        self.assertIn('3 eligible heading terms; topic mode has no own-page match measurement', text)
        self.assertNotIn('0/3 heading terms matched', text)

    def test_non_ascii_only_heading_is_not_interpreted_as_complete_coverage(self):
        value = data('', '汽车保险费用')
        self.assertEqual([], value['missing_subtopics'])
        text = brief.render_markdown(value)
        self.assertIn('ASCII-letter terms', text)
        self.assertIn('does not establish complete topic coverage', text)

    def test_only_h2_h3_candidates_but_all_own_heading_labels_participate(self):
        rival = {'url': RIVAL, 'headings': [(1, 'Title terms'), (2, 'Alpha beta'),
                                           (3, 'Gamma delta'), (4, 'Nested terms')]}
        own = {'text': '', 'headings': [(4, 'alpha beta')]}
        candidates = brief.subtopic_gaps(own, [rival])
        self.assertEqual(['Gamma delta'], [c['heading'] for c in candidates])
        self.assertEqual(3, candidates[0]['term_match']['heading_level'])

    def test_source_order_noise_filter_and_candidate_dedup_remain(self):
        rival = {'url': RIVAL, 'headings': [(2, 'Gamma delta'), (2, 'Comments'), (3, 'Alpha beta'),
                                          (2, ' gamma DELTA '), (2, 'Tools')]}
        candidates = brief.subtopic_gaps(None, [rival, rival])
        self.assertEqual(['Gamma delta', 'Alpha beta'], [c['heading'] for c in candidates])

    def test_legacy_fields_remain_reviewable_without_backfilled_counts(self):
        value = data()
        del value['subtopic_review']
        del value['missing_subtopics'][0]['term_match']
        text = brief.render_markdown(value)
        self.assertIn('Car insurance costs', text)
        self.assertIn('Legacy candidate-selection basis is unrecorded', text)
        self.assertIn('Term-match counts/basis unrecorded or unsupported', text)
        self.assertNotIn('0/3 heading terms matched', text)

    def test_malformed_counts_and_markers_are_not_coerced(self):
        for key, bad in [('version', True), ('basis', 'semantic_coverage'), ('heading_level', True),
                         ('terms_examined', True), ('terms_examined', 0), ('terms_examined', 10**100),
                         ('matched_terms', False), ('matched_terms', -1), ('matched_terms', 2),
                         ('review_cutoff', True), ('review_cutoff', 1), ('heading_sha256', None)]:
            value = data()
            value['missing_subtopics'][0]['term_match'][key] = bad
            with self.subTest(key=key, bad=bad):
                self.assertIn('Term-match counts/basis unrecorded or unsupported', brief.render_markdown(value))

    def test_stale_heading_or_context_cannot_reuse_the_original_counts(self):
        value = data()
        value['missing_subtopics'][0]['heading'] = 'A different heading'
        self.assertIn('Term-match counts/basis unrecorded or unsupported', brief.render_markdown(value))
        value = data()
        value['subtopic_review']['mode'] = 'topic'
        self.assertIn('Legacy candidate-selection basis is unrecorded', brief.render_markdown(value))
        self.assertNotIn('0/3 heading terms matched', brief.render_markdown(value))

    def test_missing_topic_match_field_does_not_invent_a_receipt(self):
        value = data(topic=True)
        del value['missing_subtopics'][0]['term_match']['matched_terms']
        text = brief.render_markdown(value)
        self.assertIn('Term-match counts/basis unrecorded or unsupported', text)
        self.assertNotIn('3 eligible heading terms;', text)

    def test_unknown_root_context_is_not_an_observed_filter_even_with_no_candidates(self):
        for key, bad in [('version', True), ('basis', 'semantic'), ('mode', 'unknown'), ('interpretation', 'coverage')]:
            value = data('Car insurance costs.')
            value['subtopic_review'][key] = bad
            text = brief.render_markdown(value)
            self.assertIn('No candidate records supplied', text)
            self.assertNotIn('No additional candidates from this recorded filter', text)

    def test_question_candidates_keep_their_source_kind_and_no_query_inference(self):
        value = data(heading='How are car insurance costs determined?')
        self.assertEqual('compared_heading', value['questions'][0]['source_kind'])
        self.assertIn('Compared-page heading; not verified query data', brief.render_markdown(value))

    def test_readonly_offline_rendering_ignores_supplied_scope_text(self):
        value = data()
        value['subtopic_review']['limits'] = 'FETCH https://evil.test/pixel'
        value['missing_subtopics'][0]['term_match']['limits'] = '<img src="https://evil.test/pixel">'
        before = brief.render_json(value)
        with mock.patch('socket.socket', side_effect=AssertionError('No network')):
            output = md_to_html(brief.render_markdown(value))
        self.assertNotIn('evil.test', output)
        self.assertEqual(before, brief.render_json(value))

    def test_existing_candidate_values_facts_scores_and_other_advice_stay_intact(self):
        value = data()
        before = copy.deepcopy(value)
        brief.render_markdown(value)
        self.assertEqual(before, value)
        candidate, = value['missing_subtopics']
        self.assertEqual({'heading': 'Car insurance costs', 'who': RIVAL, 'question': False},
                         {key: val for key, val in candidate.items() if key != 'term_match'})

    def test_mcp_brief_description_preserves_candidate_scope(self):
        import mcp_server
        self.assertIn('not missing semantic content', mcp_server._brief.__doc__)
        self.assertIn('legacy missing receipts remain unrecorded', mcp_server._brief.__doc__)


if __name__ == '__main__':
    unittest.main()
