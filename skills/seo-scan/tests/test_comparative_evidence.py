"""Literal comparison cue counts never certify evidence or require quotas."""
import copy
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import brief
import compare
from lib import evidence_observation, htmlx
from lib.report import Report, md_to_html


def page(name, source):
    url = 'https://' + name + '.test/guide'
    doc = htmlx._parse_stdlib(source, url)
    report = Report(url, fetched_status=200)
    return {'url': url, 'facts': compare.facts(report, doc), 'headings': doc.headings, 'text': doc.body_text}


def result(you, rival):
    return {'you': you['facts'], 'competitors': [rival['facts']], 'failed': [],
            **compare.gap_analysis(you['facts'], [rival['facts']])}


class TestComparativeEvidence(unittest.TestCase):
    def setUp(self):
        self.linked = page('linked', '<h1>Manual</h1><p>Consult the '
                           '<a href="https://primary.test/spec">original specification</a>.</p>')
        self.labels = page('labels', '<h1>Labels</h1><p>study research report survey cited source: according to</p>')

    def test_reference_link_can_have_zero_patterns_without_a_missing_evidence_claim(self):
        facts = self.linked['facts']
        self.assertEqual(0, facts['stats_cites'])
        self.assertEqual(0, facts['evidence_cues']['total_matches'])
        self.assertIs(False, facts['evidence_cues']['source_validity_checked'])
        text = compare.render_markdown(result(self.linked, self.labels))
        self.assertIn('Other numbers, links and references may exist', text)
        self.assertNotIn('Evidence density (stats/citations)', text)

    def test_lexical_labels_are_matches_not_six_validated_sources(self):
        facts = self.labels['facts']
        self.assertEqual(6, facts['stats_cites'])
        self.assertEqual(6, facts['evidence_cues']['citation_cue_matches'])
        self.assertEqual(0, facts['evidence_cues']['statistic_matches'])
        self.assertIn('not verified statistics, citations or sources', evidence_observation.LIMITS)

    def test_statistic_and_citation_cues_keep_original_regex_counting(self):
        facts = page('mixed', '<p>45% according to a study, with 2 million samples.</p>')['facts']
        self.assertEqual(4, facts['stats_cites'])
        self.assertEqual(2, facts['evidence_cues']['statistic_matches'])
        self.assertEqual(2, facts['evidence_cues']['citation_cue_matches'])
        self.assertIn('2 statistic-pattern + 2 citation-cue matches', evidence_observation.cell(facts))

    def test_neither_direction_creates_a_semantic_evidence_gap(self):
        for own, rival in ((self.linked, self.labels), (self.labels, self.linked)):
            data = result(own, rival)
            self.assertNotIn('Evidence density (stats/citations)', [g['what'] for g in data['gaps'] + data['leads']])

    def test_zero_topic_cues_do_not_become_a_zero_evidence_target(self):
        value = brief.synthesize(None, [self.linked], None, topic='Manual')
        self.assertEqual({}, value['structure'])
        text = brief.render_markdown(value)
        self.assertIn('0–0 combined pattern matches', text)
        self.assertNotIn('Your page:', text)
        self.assertNotIn('add concrete numbers', text)

    def test_positive_topic_and_existing_page_counts_do_not_become_source_quotas(self):
        for own in (None, self.linked):
            value = brief.synthesize(own, [self.labels], None, topic='Manual' if own is None else None)
            self.assertNotIn('evidence_target', value['structure'])
            self.assertNotIn('your_evidence', value['structure'])
            self.assertIn('6–6 combined pattern matches', brief.render_markdown(value))

    def test_hub_observations_remain_visible_without_becoming_structure_targets(self):
        self.labels['facts']['page_kind'] = 'hub'
        value = brief.synthesize(self.linked, [self.labels], None)
        self.assertEqual({}, value['structure'])
        self.assertIn('6–6 combined pattern matches', brief.render_markdown(value))

    def test_legacy_scalar_does_not_supply_missing_units_or_pattern_basis(self):
        facts = {'stats_cites': 6, 'tool_version': '1.30.19'}
        self.assertIsNone(evidence_observation.recorded(facts))
        self.assertEqual('6 (basis unrecorded)', evidence_observation.cell(facts))
        self.assertIn('no recorded cue measurements', ' '.join(evidence_observation.summary(None, [facts])))

    def test_conflicting_alias_malformed_counts_or_unrecognized_basis_stay_unknown(self):
        for key, value in (('version', True), ('basis', 'citations'), ('source_validity_checked', 0),
                           ('total_matches', 7), ('statistic_matches', -1),
                           ('citation_cue_matches', False), ('citation_cue_matches', 10 ** 100)):
            facts = copy.deepcopy(self.labels['facts'])
            facts['evidence_cues'][key] = value
            with self.subTest(key=key, value=value):
                self.assertIsNone(evidence_observation.recorded(facts))
        facts = copy.deepcopy(self.labels['facts'])
        facts['stats_cites'] = 7
        self.assertIsNone(evidence_observation.recorded(facts))
        for value in (True, -1, '6', 10 ** 100):
            self.assertEqual('Unrecorded', evidence_observation.cell({'stats_cites': value}))

    def test_extraction_receipt_is_bounded_without_retaining_raw_text(self):
        receipt = evidence_observation.observe(0, 0, 'x' * 161)
        self.assertEqual('x' * 160, receipt['source_basis'])
        self.assertIs(True, receipt['source_basis_clipped'])
        self.assertNotIn('text', receipt)

    def test_summary_never_renders_untrusted_receipt_fields(self):
        facts = copy.deepcopy(self.labels['facts'])
        for key in ('source_basis', 'limits'):
            facts['evidence_cues'][key] = '<img src="https://evil.test/pixel">'
        facts['url'] = '[injected](https://evil.test)'
        self.assertNotIn('evil.test', ' '.join(evidence_observation.summary(facts, [facts])))
        for rivals in (None, {}, [{}] * 101):
            self.assertIn('unrecorded or unsupported', ' '.join(evidence_observation.summary(None, rivals)))

    def test_legacy_targets_and_verdicts_are_not_repeated_and_json_stays_unchanged(self):
        comparison = result(self.linked, self.labels)
        value = brief.synthesize(self.linked, [self.labels], None)
        value['structure'].update({'evidence_target': '<img src="https://evil.test/pixel">',
                                   'your_evidence': 'INVENT_SOURCES'})
        for report, renderer, serializer in ((comparison, compare.render_markdown, compare.render_json),
                                             (value, brief.render_markdown, brief.render_json)):
            report['gaps'].append({'what': 'Evidence density (stats/citations)',
                                   'who': [self.labels['url']], 'action': 'ADD_TO_QUOTA'})
            report['leads'].append({'what': 'Evidence density (stats/citations)', 'detail': 'SIX_REAL_SOURCES'})
            before = serializer(report)
            with mock.patch('socket.socket', side_effect=AssertionError('No network')):
                text = renderer(report)
                md_to_html(text)
            for marker in ('evil.test', 'INVENT_SOURCES', 'ADD_TO_QUOTA', 'SIX_REAL_SOURCES'):
                self.assertNotIn(marker, text)
            self.assertEqual(before, serializer(report))
        self.assertIn('Legacy evidence-target fields', brief.render_markdown(value))

    def test_other_gaps_scores_and_facts_are_not_mutated(self):
        self.labels['facts']['canonical'] = True
        before = copy.deepcopy([self.linked['facts'], self.labels['facts']])
        data = result(self.linked, self.labels)
        self.assertIn('Canonical URL', [g['what'] for g in data['gaps']])
        brief.synthesize(self.linked, [self.labels], None)
        self.assertEqual(before, [self.linked['facts'], self.labels['facts']])


if __name__ == '__main__':
    unittest.main()
