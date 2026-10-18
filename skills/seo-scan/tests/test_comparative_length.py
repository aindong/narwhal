"""Comparison and brief lengths are recorded counts, not depth or writing targets."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import brief
import compare
from lib import htmlx, length_observation
from lib.report import Report, md_to_html


def page(url, text, kind=None):
    doc = htmlx.Doc(base_url=url, title='Guide', text=text, headings=[(1, 'Guide')])
    report = Report(url, fetched_status=200)
    facts = compare.facts(report, doc)
    if kind:
        facts['page_kind'] = kind
    return {'url': url, 'facts': facts, 'headings': doc.headings, 'text': text}


def result(you, rival):
    return {'you': you['facts'], 'competitors': [rival['facts']], 'failed': [],
            **compare.gap_analysis(you['facts'], [rival['facts']])}


class TestComparativeLength(unittest.TestCase):
    def setUp(self):
        self.you = page('https://you.test/guide', '自然历史与海洋保护。' * 600)
        self.rival = page('https://rival.test/guide', 'word ' * 600)

    def test_facts_retain_the_legacy_alias_with_its_actual_count_basis(self):
        facts = self.you['facts']
        self.assertEqual(1, facts['words'])
        self.assertEqual(1, facts['text_length']['whitespace_tokens'])
        self.assertEqual(6000, facts['text_length']['code_points'])
        self.assertEqual('python_str_split', facts['text_length']['basis'])
        self.assertIn('not universal word counts', facts['text_length']['limits'])

    def test_whitespace_and_unicode_code_points_are_literal_not_dictionary_words(self):
        for text, count in (('', 0), (' \n\t', 0), ('one\u00a0two\u2003three', 3), ('中文没有空格', 1)):
            receipt = length_observation.observe(text, 'visible text')
            self.assertEqual(count, receipt['whitespace_tokens'])
            self.assertEqual(len(text), receipt['code_points'])

    def test_length_never_creates_a_depth_gap_or_lead_in_either_direction(self):
        for own, rival in ((self.you, self.rival), (self.rival, self.you)):
            data = result(own, rival)
            self.assertNotIn('Content depth', [g['what'] for g in data['gaps'] + data['leads']])
            self.assertEqual('observation_not_target', data['text_length']['interpretation'])
            self.assertEqual(own['facts']['words'], data['text_length']['your_count'])

    def test_brief_does_not_convert_the_longest_compared_count_to_a_word_target(self):
        data = brief.synthesize(self.you, [self.rival], None)
        self.assertNotIn('target_words', data['structure'])
        self.assertNotIn('your_words', data['structure'])
        self.assertEqual(600, data['text_length']['compared'][0]['count'])
        text = brief.render_markdown(data)
        self.assertIn('600–600 whitespace tokens', text)
        self.assertIn('not a target', text)
        self.assertNotIn('**Depth:**', text)
        self.assertNotIn('deepest compared page', text)

    def test_topic_mode_records_no_own_page_instead_of_an_invented_zero(self):
        data = brief.synthesize(None, [self.rival], None, topic='A guide')
        self.assertIsNone(data['text_length']['your_count'])
        self.assertEqual('not_supplied', data['text_length']['your_status'])
        self.assertNotIn('Your page: 0', brief.render_markdown(data))
        self.assertNotIn('target_words', data['structure'])

    def test_hub_counts_remain_observations_without_becoming_structure_targets(self):
        self.rival['facts']['page_kind'] = 'hub'
        data = brief.synthesize(self.you, [self.rival], None)
        self.assertEqual({}, data['structure'])
        self.assertEqual(600, data['text_length']['compared'][0]['count'])

    def test_legacy_words_alone_never_establish_a_measurement_unit(self):
        del self.rival['facts']['text_length']
        self.rival['facts']['tool_version'] = '1.30.19'
        data = result(self.you, self.rival)
        self.assertIsNone(data['text_length']['compared'][0]['count'])
        self.assertEqual('unrecorded', data['text_length']['compared'][0]['status'])
        text = compare.render_markdown(data)
        self.assertIn('600 (basis unrecorded)', text)
        self.assertNotIn('| Words |', text)
        self.assertIn('no recorded whitespace-token measurements', text)

    def test_conflicting_legacy_alias_and_new_receipt_stays_unverified(self):
        facts = copy.deepcopy(self.rival['facts'])
        facts['words'] = 999
        self.assertIsNone(length_observation.recorded(facts))
        self.assertEqual('999 (basis unrecorded)', length_observation.cell(facts))
        self.assertEqual('Unrecorded', length_observation.cell(facts, code_points=True))

    def test_missing_extraction_provenance_does_not_validate_length_receipts(self):
        for key in ('source_basis', 'source_basis_clipped'):
            facts = copy.deepcopy(self.rival['facts'])
            del facts['text_length'][key]
            self.assertIsNone(length_observation.recorded(facts))
            self.assertEqual('600 (basis unrecorded)', length_observation.cell(facts))
            value = length_observation.comparison(None, [facts])
            self.assertEqual('unrecorded', value['compared'][0]['status'])

    def test_malformed_extraction_labels_and_clipping_flags_stay_unrecorded(self):
        for key, bad in (('source_basis', None), ('source_basis', ''), ('source_basis', ' \t'),
                          ('source_basis', []), ('source_basis', 'x' * 161),
                          ('source_basis_clipped', None), ('source_basis_clipped', 'false'),
                          ('source_basis_clipped', 0), ('source_basis_clipped', 1)):
            facts = copy.deepcopy(self.rival['facts'])
            facts['text_length'][key] = bad
            with self.subTest(key=key, bad=bad):
                self.assertIsNone(length_observation.recorded(facts))
        for label, clipped in (('visible text', False), ('x' * 160, True)):
            facts = {'words': 1, 'text_length': length_observation.observe('Guide', label)}
            facts['text_length']['source_basis_clipped'] = clipped
            self.assertIsNotNone(length_observation.recorded(facts))

    def test_zero_is_recorded_and_not_confused_with_a_missing_measurement(self):
        empty = page('https://empty.test/', '')
        value = length_observation.comparison(empty['facts'], [empty['facts']])
        self.assertEqual('recorded', value['your_status'])
        self.assertEqual(0, value['your_count'])
        self.assertIn('0–0 whitespace tokens', ' '.join(length_observation.summary(value)))

    def test_malformed_counts_and_versions_do_not_get_coerced(self):
        for key, value in (('version', True), ('basis', 'words'), ('whitespace_tokens', False),
                           ('whitespace_tokens', -1), ('whitespace_tokens', 10 ** 100),
                           ('code_points', 0)):
            facts = copy.deepcopy(self.rival['facts'])
            facts['text_length'][key] = value
            with self.subTest(key=key, value=value):
                self.assertIsNone(length_observation.recorded(facts))
        for value in (False, '600', -1, 10 ** 100):
            self.assertEqual('Unrecorded', length_observation.cell({'words': value}))

    def test_summary_does_not_render_untrusted_labels_urls_or_limits(self):
        value = length_observation.comparison(self.you['facts'], [self.rival['facts']])
        value['limits'] = '<img src="https://evil.test/pixel">'
        value['compared'][0]['url'] = '[bad](https://evil.test)'
        text = ' '.join(length_observation.summary(value))
        self.assertNotIn('evil.test', text)
        self.assertIn(length_observation.LIMITS, text)
        for key, bad in (('version', True), ('your_count', False), ('compared', [{}]),
                          ('compared', [{}] * 101), ('your_status', ['bad'])):
            malformed = dict(value, **{key: bad})
            self.assertIn('unrecorded or unsupported', ' '.join(length_observation.summary(malformed)))

    def test_legacy_compare_depth_verdicts_are_not_repeated_as_advice(self):
        data = result(self.you, self.rival)
        data['gaps'].append({'what': 'Content depth', 'who': [self.rival['url']], 'action': 'EXPAND_TO_TARGET'})
        data['leads'].append({'what': 'Content depth', 'detail': 'DEEPER_IS_BETTER'})
        before = compare.render_json(data)
        text = compare.render_markdown(data)
        self.assertNotIn('EXPAND_TO_TARGET', text)
        self.assertNotIn('DEEPER_IS_BETTER', text)
        self.assertIn('legacy content-depth gap/lead', text)
        self.assertEqual(before, compare.render_json(data))

    def test_legacy_brief_targets_are_labelled_unrecorded_not_recommended(self):
        data = brief.synthesize(self.you, [self.rival], None)
        data['structure'].update({'target_words': '<img src=https://evil.test>', 'your_words': 1})
        data['gaps'].append({'what': 'Content depth', 'who': [self.rival['url']], 'action': 'EXPAND_TO_TARGET'})
        data['leads'] = [{'what': 'Content depth', 'detail': 'DEEPER_IS_BETTER'}]
        before = brief.render_json(data)
        text = brief.render_markdown(data)
        self.assertIn('Legacy length-target fields', text)
        self.assertNotIn('EXPAND_TO_TARGET', text)
        self.assertNotIn('DEEPER_IS_BETTER', text)
        self.assertNotIn('evil.test', text)
        self.assertEqual(before, brief.render_json(data))

    def test_other_gaps_and_measurements_are_preserved_and_rendering_is_read_only(self):
        self.rival['facts']['canonical'] = True
        data = result(self.you, self.rival)
        self.assertIn('Canonical URL', [g['what'] for g in data['gaps']])
        for value, renderer, serializer in ((data, compare.render_markdown, compare.render_json),
                                           (brief.synthesize(self.you, [self.rival], None), brief.render_markdown, brief.render_json)):
            before = serializer(value)
            with mock.patch('socket.socket', side_effect=AssertionError('No network')):
                md_to_html(renderer(value))
            self.assertEqual(before, serializer(value))

    def test_length_review_coverage_is_only_read_from_an_explicit_boolean(self):
        url = 'https://example.test/'
        doc = htmlx.Doc(url, text='A guide')
        for raw, expected in ((True, True), (False, False), (None, None), (1, None), ('false', None)):
            report = Report(url, meta={'scan_settings': {'content_length_reviewed': raw}})
            self.assertIs(expected, compare.facts(report, doc)['content_length_reviewed'])

    def test_missing_summary_can_use_explicit_fact_receipts_but_not_legacy_aliases(self):
        data = result(self.you, self.rival)
        del data['text_length']
        self.assertIn('600–600 whitespace tokens', compare.render_markdown(data))
        del data['you']['text_length']
        del data['competitors'][0]['text_length']
        self.assertIn('no recorded whitespace-token measurements', compare.render_markdown(data))
        self.assertNotIn('600–600 whitespace tokens', compare.render_markdown(data))


if __name__ == '__main__':
    unittest.main()
