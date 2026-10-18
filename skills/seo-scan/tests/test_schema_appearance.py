"""Dated appearance context survives comparisons/briefs without banning markup."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_schema
import brief
import compare
import generate_schema
from lib import htmlx, schema_appearance as appearance
from lib.report import Report, md_to_html

MARKUP = {
    'jsonld': '<script type="application/ld+json">{"@graph":[{"@type":"FAQPage"},{"@type":"HowTo"}]}</script>',
    'microdata': '<div itemscope itemtype="https://schema.org/FAQPage"></div><div itemscope itemtype="https://schema.org/HowTo"></div>',
    'rdfa': '<div vocab="https://schema.org/"><div typeof="FAQPage"></div><div typeof="HowTo"></div></div>',
}


def page(name, markup='', parser=htmlx._parse_stdlib):
    url = 'https://' + name + '.test/guide'
    doc = parser('<h1>Manual</h1><p>Useful reader instructions.</p>' + markup, url)
    report = Report(url, fetched_status=200)
    audit_schema.audit(doc, None, report, {})
    before = report.to_json()
    value = {'url': url, 'facts': compare.facts(report, doc), 'headings': doc.headings, 'text': doc.body_text}
    assert before == report.to_json(), 'Fact projection must not change the page report'
    return value, report


def comparison(you, rival):
    return {'you': you['facts'], 'competitors': [rival['facts']], 'failed': [],
            **compare.gap_analysis(you['facts'], [rival['facts']])}


class TestSchemaAppearance(unittest.TestCase):
    def setUp(self):
        self.you, _ = page('you')
        self.rival, self.report = page('rival', MARKUP['jsonld'])

    def test_fact_snapshot_preserves_the_same_types_and_page_notice_shape(self):
        facts = self.rival['facts']
        self.assertEqual(['FAQPage', 'HowTo'], facts['schema_types'])
        value = facts['schema_search_features']
        self.assertEqual('2026-10-12', value['checked_on'])
        self.assertEqual('dated_google_retirement_snapshot', value['basis'])
        self.assertEqual(self.report.meta['structured_data']['google_rich_result_notices'], value['notices'])
        self.assertIsNotNone(appearance.recorded(value, facts['schema_types']))

    def test_jsonld_microdata_and_rdfa_retain_the_same_context_on_both_parsing_paths(self):
        outputs = []
        for format_, source in MARKUP.items():
            for parser in (htmlx._parse_stdlib, htmlx.parse):
                with self.subTest(format=format_, parser=parser.__name__):
                    value, report = page('rival', source, parser)
                    outputs.append(value['facts']['schema_search_features'])
                    self.assertEqual(['FAQPage', 'HowTo'], value['facts']['schema_types'])
                    self.assertEqual(2, len(report.meta['structured_data']['google_rich_result_notices']))
        self.assertTrue(all(value == outputs[0] for value in outputs))

    def test_comparison_keeps_the_observed_gap_but_exposes_retirement_and_limits(self):
        value = comparison(self.you, self.rival)
        self.assertIn('Schema types: FAQPage, HowTo', [g['what'] for g in value['gaps']])
        text = compare.render_markdown(value)
        self.assertIn('retired Google Search rich-result appearance', text)
        self.assertIn('not a live Google eligibility test', text)
        self.assertIn('does not invalidate schema.org', text)
        self.assertIn('real visible content and the intended consumer', text)

    def test_brief_semantic_candidates_remain_available_with_per_candidate_notices(self):
        value = brief.synthesize(self.you, [self.rival], None)
        self.assertEqual(['FAQPage', 'HowTo'], [row['type'] for row in value['schema']])
        for row in value['schema']:
            self.assertEqual(row['type'], row['google_search_appearance']['notices'][0]['type'])
        text = brief.render_markdown(value)
        self.assertIn('Semantic schema candidates (review)', text)
        self.assertIn('retired Google Search rich-result appearance', text)
        self.assertNotIn('## Schema to add', text)

    def test_planned_faq_candidate_also_gets_a_notice_without_inventing_observed_schema(self):
        candidates = brief.schema_suggestions(None, [], [{'question': 'What is a widget?'}])
        self.assertEqual('FAQPage', candidates[0]['type'])
        self.assertEqual('retired', candidates[0]['google_search_appearance']['notices'][0]['status'])
        self.assertEqual([], self.you['facts']['schema_search_features']['notices'])

    def test_unknown_or_shared_types_are_not_retired_or_certified_eligible(self):
        types = ['Course', 'VideoObject', 'Product', 'Car', 'Book', 'UnrecognizedType']
        value = appearance.observe(types)
        self.assertEqual([], value['notices'])
        text = ' '.join(appearance.lines(value, types))
        self.assertIn('not a supported/eligible/validity verdict', text)
        self.assertIn('not certified supported', appearance.LIMITS)
        self.assertIsNone(appearance.notice('Course'))

    def test_claimreview_preserves_its_separate_consumer_and_primary_source(self):
        text = ' '.join(appearance.lines(appearance.observe(['ClaimReview']), ['ClaimReview']))
        self.assertIn('Fact Check Explorer', text)
        self.assertIn('https://developers.google.com/search/docs/appearance/structured-data/factcheck', text)

    def test_page_auditor_module_names_and_notice_identity_remain_compatible(self):
        self.assertIs(audit_schema.DEPRECATED, appearance.DEPRECATED)
        self.assertEqual(audit_schema.FEATURE_STATUS_CHECKED, appearance.FEATURE_STATUS_CHECKED)
        self.assertEqual(2, len([f for f in self.report.findings if f.rule_id.startswith('schema.deprecated.rich.result.type.')]))
        self.assertTrue(all(f.severity == 'low' for f in self.report.findings if f.rule_id.startswith('schema.deprecated.rich.result.type.')))

    def test_missing_legacy_receipts_never_infer_status_from_type_or_version(self):
        facts = {'schema_types': ['FAQPage'], 'tool_version': '1.30.19'}
        text = ' '.join(appearance.summary(facts, [facts]))
        self.assertIn('snapshot unrecorded or unsupported', text)
        self.assertNotIn('retired Google Search', text)

    def test_malformed_or_conflicting_receipts_and_unrecognized_snapshots_stay_unverified(self):
        known = self.rival['facts']['schema_search_features']
        for key, value in (('version', True), ('version', 2), ('basis', 'Google live test'),
                           ('checked_on', '2099-01-01'), ('notices', None), ('notices', []),
                           ('notices', [{}] * 5)):
            receipt = copy.deepcopy(known)
            receipt[key] = value
            with self.subTest(key=key, value=value):
                self.assertIsNone(appearance.recorded(receipt, ['FAQPage', 'HowTo']))
        self.assertIsNone(appearance.recorded(known, ['Product']))
        for types in (None, {}, [True], [['FAQPage']]):
            self.assertIsNone(appearance.recorded(known, types))

    def test_supplied_policy_links_or_statuses_are_not_rendered(self):
        for key, bad in (('source', 'https://evil.test/pixel'), ('additional_sources', ['javascript:alert(1)']),
                          ('status', 'eligible'), ('scope', '<img src=https://evil.test>')):
            value = copy.deepcopy(self.rival['facts']['schema_search_features'])
            value['notices'][0][key] = bad
            text = ' '.join(appearance.lines(value, ['FAQPage', 'HowTo']))
            self.assertIn('unrecorded or unsupported', text)
            self.assertNotIn('evil.test', text)
            self.assertNotIn('javascript:', text)

    def test_untrusted_labels_and_limits_are_ignored_and_note_page_limit_is_explicit(self):
        facts = copy.deepcopy(self.rival['facts'])
        facts['url'] = '<img src="https://evil.test/pixel">'
        facts['schema_search_features']['limits'] = facts['url']
        text = ' '.join(appearance.summary(None, [facts]))
        self.assertNotIn('evil.test', text)
        self.assertIn('not a live Google eligibility test', text)
        self.assertIn('unrecorded or unsupported', ' '.join(appearance.summary(None, [{}] * 101)))

    def test_generation_for_real_semantic_faq_content_is_not_removed(self):
        value = generate_schema.build('FAQPage', {'mainEntity': json.dumps([{'@type': 'Question', 'name': 'What is a widget?',
                                       'acceptedAnswer': {'@type': 'Answer', 'text': 'A named example device.'}}])})
        self.assertEqual('FAQPage', value['@type'])
        self.assertEqual('A named example device.', value['mainEntity'][0]['acceptedAnswer']['text'])

    def test_fresh_notices_do_not_share_mutable_source_arrays(self):
        a, b = appearance.notice('ClaimReview'), appearance.notice('ClaimReview')
        a['additional_sources'].append('https://evil.test/')
        self.assertNotIn('https://evil.test/', b['additional_sources'])

    def test_rendering_is_offline_and_does_not_mutate_report_scores_facts_or_json(self):
        values = [(comparison(self.you, self.rival), compare.render_markdown, compare.render_json),
                  (brief.synthesize(self.you, [self.rival], None), brief.render_markdown, brief.render_json)]
        for value, renderer, serializer in values:
            before = serializer(value)
            with mock.patch('socket.socket', side_effect=AssertionError('No policy source fetch')):
                md_to_html(renderer(value))
            self.assertEqual(before, serializer(value))


if __name__ == '__main__':
    unittest.main()
