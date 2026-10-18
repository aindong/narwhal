"""Paired text counts cannot certify server rendering or JS-only content."""
import copy
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan
import scan
from lib import htmlx, http, jsdiff
from lib.report import Report
from test_page_schema_review import FIXTURE

URL = 'https://example.test/paired'
RAW = '<main><p>Original topic details for readers</p></main>'
REPLACED = '<main><p>Different topic entirely changed afterward</p></main>'


def measured(raw=RAW, rendered=REPLACED):
    dep = jsdiff.analyze(raw, rendered, URL)
    report = Report(URL)
    jsdiff.technical_findings(dep, report)
    jsdiff.geo_finding(dep, report)
    return dep, report


class TestRenderedTextEvidence(unittest.TestCase):
    def test_equal_count_replacement_is_not_server_rendering_pass(self):
        dep, report = measured()
        self.assertEqual((5, 5, 0), tuple(dep[k] for k in ('words_raw', 'words_rendered', 'js_only_pct')))
        self.assertIs(False, dep['text_comparison']['selected_text_equal'])
        finding, = report.findings
        self.assertEqual(('technical.rendered.text.changed', 'low'), (finding.rule_id, finding.severity))
        self.assertIn('text differs', finding.detail)

    def test_shorter_replacement_keeps_negative_delta_without_false_zero_js_verdict(self):
        dep, report = measured(rendered='<main>Replaced content only</main>')
        self.assertEqual(-2, dep['text_comparison']['net_token_delta'])
        self.assertEqual(0, dep['js_only_pct'])
        self.assertFalse(any(f.rule_id == 'technical.content.is.server.rendered' for f in report.findings))

    def test_identical_selected_text_is_only_scoped_equality(self):
        dep, report = measured(rendered=RAW)
        self.assertIs(True, dep['text_comparison']['selected_text_equal'])
        finding, = report.findings
        self.assertEqual(('technical.content.is.server.rendered', 'good'), (finding.rule_id, finding.severity))
        self.assertNotIn('Content is server-rendered', finding.title)
        self.assertIn('not full-page content', finding.detail)

    def test_empty_pair_does_not_certify_content_availability(self):
        dep, report = measured('', '')
        self.assertEqual(0, dep['text_comparison']['served_tokens'])
        self.assertEqual('No selected text observed in either snapshot', report.findings[0].title)
        self.assertEqual(('technical.rendered.text.unobserved', 'low'),
                         (report.findings[0].rule_id, report.findings[0].severity))
        self.assertNotIn('Selected extracted text matches', report.findings[0].detail)
        result = plan.build_plan(json.loads(report.to_json()), str(FIXTURE))
        action, = result['actions']
        self.assertTrue(action['manual_action'])
        self.assertEqual([], action['likely_files'])
        self.assertFalse(action['requires_deploy'])
        self.assertEqual([], result['groups'])

    def test_large_increase_retains_legacy_numbers_and_ids_as_low_reviews(self):
        dep, report = measured('<main>Server intro</main>', '<main>Server intro ' + 'client ' * 98 + '</main>')
        self.assertEqual(98, dep['js_only_pct'])
        self.assertEqual(98, dep['text_comparison']['net_token_delta'])
        self.assertEqual({'technical.most.content.requires.javascript',
                          'geo.ai.answer.engines.may.not.see.this.content'}, {f.rule_id for f in report.findings})
        self.assertTrue(all(f.severity == 'low' for f in report.findings))
        self.assertTrue(all('not a share of JS-only content' in f.detail for f in report.findings))

    def test_middle_band_retains_legacy_id_without_medium_defect_claim(self):
        dep, report = measured('<main>' + 'a ' * 8 + '</main>', '<main>' + 'a ' * 10 + '</main>')
        self.assertEqual(20, dep['js_only_pct'])
        self.assertEqual('technical.significant.content.requires.javascript', report.findings[0].rule_id)
        self.assertEqual('low', report.findings[0].severity)

    def test_small_increase_is_review_not_parity_pass(self):
        _, report = measured('<main>' + 'a ' * 99 + '</main>', '<main>' + 'a ' * 100 + '</main>')
        self.assertEqual('technical.rendered.text.changed', report.findings[0].rule_id)

    def test_non_ascii_counts_are_whitespace_tokens_not_linguistic_words(self):
        dep, report = measured('<main>中文原文</main>', '<main>完全不同</main>')
        self.assertEqual((1, 1), (dep['words_raw'], dep['words_rendered']))
        self.assertIs(False, dep['text_comparison']['selected_text_equal'])
        self.assertEqual('whitespace_tokens', dep['text_comparison']['unit'])

    def test_receipt_keeps_each_extraction_basis_without_copying_text(self):
        dep, _ = measured()
        obs = dep['text_comparison']
        self.assertEqual(htmlx.parse(RAW, URL).extraction, obs['served_extraction'])
        self.assertEqual(htmlx.parse(REPLACED, URL).extraction, obs['rendered_extraction'])
        self.assertNotIn('Original topic', json.dumps(obs))
        self.assertNotIn('Different topic', json.dumps(obs))

    def test_legacy_missing_receipt_is_not_backfilled_from_zero_counts(self):
        dep, _ = measured(rendered=RAW)
        del dep['text_comparison']
        report = Report(URL)
        jsdiff.technical_findings(dep, report)
        self.assertEqual('technical.rendered.text.comparison.unverified', report.findings[0].rule_id)

    def test_malformed_stale_or_boolean_counts_cannot_certify_parity(self):
        dep, _ = measured(rendered=RAW)
        for key, value in [('version', True), ('version', 2), ('basis', 'unknown'),
                           ('served_extraction', None), ('served_extraction', ' '),
                           ('rendered_extraction', True), ('rendered_extraction', 'x' * 161),
                           ('unit', 'words'), ('served_tokens', True), ('rendered_tokens', -1),
                           ('rendered_tokens', 1 << 4096),
                           ('net_token_delta', True), ('net_token_delta', 99),
                           ('positive_net_increase_percent', True), ('positive_net_increase_percent', 10),
                           ('selected_text_equal', 'true')]:
            with self.subTest(key=key, value=value):
                candidate = copy.deepcopy(dep)
                candidate['text_comparison'][key] = value
                self.assertIsNone(jsdiff.text_observation(candidate))
        dep['words_raw'] = 0
        self.assertIsNone(jsdiff.text_observation(dep))

    def test_unequal_token_counts_cannot_accompany_recorded_equal_text(self):
        dep, _ = measured(rendered='<main>Different</main>')
        dep['text_comparison']['selected_text_equal'] = True
        self.assertIsNone(jsdiff.text_observation(dep))

    def test_old_heading_and_metadata_aliases_keep_the_same_observations(self):
        raw = '<title>T</title><script type="application/ld+json">{}</script><h1>A</h1>'
        rendered = raw + '<h2>B</h2><script type="application/ld+json">{}</script>'
        dep, report = measured(raw, rendered)
        self.assertEqual(['B'], dep['js_only_headings'])
        self.assertEqual(1, dep['js_only_heading_count'])
        self.assertIs(True, dep['meta_js_only']['jsonld'])
        finding, = [f for f in report.findings if f.rule_id == 'technical.json.ld.injected.by.javascript']
        self.assertEqual('low', finding.severity)
        self.assertIn('Some may already exist', finding.detail)

    def test_head_metadata_presence_does_not_assert_causation_or_require_rewrite(self):
        _, report = measured('<main>A</main>', '<title>T</title><main>A</main>')
        finding, = [f for f in report.findings if f.rule_id == 'technical.head.metadata.injected.by.javascript']
        self.assertEqual('low', finding.severity)
        self.assertIn('not JavaScript causation', finding.detail)

    def test_parser_paths_preserve_count_equality_and_difference_scope(self):
        with mock.patch.object(htmlx, 'parse', side_effect=htmlx._parse_stdlib):
            stdlib, _ = measured()
        optional, _ = measured()
        for key in ('served_tokens', 'rendered_tokens', 'net_token_delta',
                    'positive_net_increase_percent', 'selected_text_equal'):
            self.assertEqual(stdlib['text_comparison'][key], optional['text_comparison'][key])

    def test_actual_scan_retains_receipt_without_an_extra_evidence_fetch(self):
        responses = [http.Response(URL, URL, 200, {'content-type': 'text/html'}, REPLACED, 1, rendered=True),
                     http.Response(URL, URL, 200, {'content-type': 'text/html'}, RAW, 1)]
        with mock.patch.object(http, 'fetch', side_effect=responses) as fetch:
            report = scan.scan(URL, render=True, only=['technical'], ctx={}, check_images=False)
        self.assertEqual(2, fetch.call_count)
        self.assertIs(False, report.meta['js_dependence']['text_comparison']['selected_text_equal'])
        self.assertEqual('measured', report.meta['coverage']['js_comparison']['status'])

    def test_current_and_legacy_plans_verify_without_assigning_ssr_or_schema_edits(self):
        for rule in sorted(plan.RENDER_VERIFICATION_RULES):
            value = {'url': URL, 'findings': [{'category': rule.split('.')[0], 'rule_id': rule,
                     'severity': 'high', 'title': 'Legacy render claim'}]}
            result = plan.build_plan(value, str(FIXTURE))
            action, = result['actions']
            self.assertEqual('server_rendering', action['artifact'])
            self.assertEqual('manual_external', action['safety'])
            self.assertEqual([], action['likely_files'])
            self.assertFalse(action['requires_deploy'])
            self.assertIn('before proposing source edits', action['proposed_change'])
            self.assertEqual([], result['groups'])

    def test_rendering_and_planning_are_offline_readonly(self):
        with mock.patch.object(socket, 'socket', side_effect=AssertionError('Offline observation')):
            dep, report = measured()
            before = report.to_json()
            dep_before = copy.deepcopy(dep)
            report.to_html()
            report.to_markdown()
            plan.build_plan(json.loads(before), str(FIXTURE))
        self.assertEqual(before, report.to_json())
        self.assertEqual(dep_before, dep)


if __name__ == '__main__':
    unittest.main()
