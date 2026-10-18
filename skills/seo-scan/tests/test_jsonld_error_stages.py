"""A tool processing limit is not evidence of invalid JSON source syntax."""
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_schema
import compare
import diff_scan
import plan
from lib import htmlx, structured_data
from lib.report import Report
from test_page_schema_review import FIXTURE
from test_schema_coverage import scan_page

URL = 'https://example.test/guide'
DEPTH = '[' * 1500 + '0' + ']' * 1500
LITERAL = '{"@value":' + '[' * 600 + '0' + ']' * 600 + ',"@type":"@json"}'
UNICODE = '{"@type":"Thing","name":"\\ud800"}'
RECIPE = '{"@type":"Recipe","name":"Soup","image":"https://example.test/soup.jpg"}'
COUNTS = ('syntax_errors', 'decoder_processing_errors', 'node_processing_errors', 'unclassified_errors')


def source(blobs):
    return '<article><h1>Guide</h1>' + ''.join('<script type="application/ld+json">' + b + '</script>' for b in blobs) + '</article>'


def page(blobs, parser=htmlx._parse_stdlib, ignore=None):
    doc = parser(source(blobs), URL)
    report = Report(URL, fetched_status=200, ignore=ignore)
    audit_schema.audit(doc, None, report, {})
    return doc, report


def stages(report):
    return report.meta['structured_data']['jsonld_error_stages']


def depth_stage():
    try:
        json.loads(DEPTH)
    except RecursionError:
        return 'decode'
    return 'nodes'  # decoder/processing limits differ by interpreter, not source syntax


class TestJsonldErrorStages(unittest.TestCase):
    def test_actual_deep_json_limit_is_processing_not_source_syntax_invalidity(self):
        expected = (0, 1, 0, 0) if depth_stage() == 'decode' else (0, 0, 1, 0)
        before = sys.getrecursionlimit()
        with mock.patch.object(sys, 'setrecursionlimit', side_effect=AssertionError('Do not raise limits')):
            _, report = page([DEPTH])
        self.assertEqual(before, sys.getrecursionlimit())
        self.assertEqual(expected, tuple(stages(report)[key] for key in COUNTS))
        finding, = report.findings
        self.assertEqual(('schema.jsonld.processing.unverified', 'low'), (finding.rule_id, finding.severity))
        self.assertNotIn('malformed blocks are ignored', finding.recommendation)

    def test_actual_json_syntax_error_keeps_its_high_id_and_repair_path(self):
        _, report = page(['{bad'])
        self.assertEqual((1, 0, 0, 0), tuple(stages(report)[key] for key in COUNTS))
        finding, = report.findings
        self.assertEqual(('schema.invalid.json.ld', 'high'), (finding.rule_id, finding.severity))
        self.assertIn('repair verified JSON syntax errors', finding.recommendation)

    def test_decoded_unicode_fingerprint_failure_is_node_processing(self):
        json.loads(UNICODE)
        _, report = page([UNICODE])
        self.assertEqual((0, 0, 1, 0), tuple(stages(report)[key] for key in COUNTS))
        self.assertNotIn('schema.invalid.json.ld', {f.rule_id for f in report.findings})
        report.to_json().encode('utf-8')

    def test_decoded_opaque_literal_copy_limit_is_node_processing(self):
        json.loads(LITERAL)
        _, report = page([LITERAL])
        self.assertEqual((0, 0, 1, 0), tuple(stages(report)[key] for key in COUNTS))
        self.assertEqual('schema.jsonld.processing.unverified', report.findings[0].rule_id)

    def test_python_integer_digit_guard_is_processing_not_syntax(self):
        limit = getattr(sys, 'get_int_max_str_digits', lambda: 0)()
        if not 0 < limit <= 10000:
            self.skipTest('Interpreter has no enabled bounded integer-digit guard')
        _, report = page(['{"number":' + '9' * (limit + 1) + '}'])
        self.assertEqual((0, 1, 0, 0), tuple(stages(report)[key] for key in COUNTS))
        self.assertEqual(limit, sys.get_int_max_str_digits())
        self.assertNotIn('schema.invalid.json.ld', {f.rule_id for f in report.findings})

    def test_message_text_does_not_classify_a_value_error_as_source_syntax(self):
        with mock.patch.object(structured_data.json, 'loads', side_effect=ValueError('Expecting property name')):
            _, report = page(['{}'])
        self.assertEqual((0, 1, 0, 0), tuple(stages(report)[key] for key in COUNTS))
        self.assertEqual('schema.jsonld.processing.unverified', report.findings[0].rule_id)

    def test_decode_exception_raised_during_node_work_is_still_processing(self):
        exc = json.JSONDecodeError('nested decoder failed', '{}', 0)
        doc = htmlx._parse_stdlib(source(['{}']), URL)
        diagnostics = []
        with mock.patch.object(structured_data, '_normalize', side_effect=[exc, [], []]):
            _, errors = structured_data.collect(doc, diagnostics=diagnostics)
        self.assertEqual(1, len(errors))
        self.assertEqual([{'block': 1, 'kind': 'processing', 'stage': 'nodes'}], diagnostics)

    def test_caller_provided_non_string_block_is_not_a_claim_about_source_syntax(self):
        doc = htmlx.Doc(URL, scripts_ld=[None])
        report = Report(URL)
        audit_schema.audit(doc, None, report, {})
        self.assertEqual((0, 1, 0, 0), tuple(stages(report)[key] for key in COUNTS))

    def test_legacy_collector_return_shape_and_optional_diagnostics_are_preserved(self):
        doc = htmlx._parse_stdlib(source(['{bad', DEPTH, UNICODE]), URL)
        diagnostics = []
        records, errors = structured_data.collect(doc, diagnostics=diagnostics)
        self.assertEqual((records, errors), structured_data.collect(doc))
        self.assertEqual([1, 2, 3], [block for block, _ in errors])
        self.assertTrue(all(type(message) is str for _, message in errors))
        self.assertEqual([{'block': 1, 'kind': 'syntax', 'stage': 'decode'},
                          {'block': 2, 'kind': 'processing', 'stage': depth_stage()},
                          {'block': 3, 'kind': 'processing', 'stage': 'nodes'}], diagnostics)

    def test_mixed_blocks_keep_positive_nodes_and_independent_error_kinds(self):
        doc, report = page([RECIPE, '{bad', DEPTH, UNICODE])
        facts = compare.facts(report, doc)
        self.assertEqual(['Recipe'], facts['schema_types'])
        expected = (1, 1, 1, 0) if depth_stage() == 'decode' else (1, 0, 2, 0)
        self.assertEqual(expected, tuple(stages(report)[key] for key in COUNTS))
        self.assertEqual(3, report.meta['structured_data']['extraction_coverage']['jsonld_errors'])
        self.assertEqual('unverified', facts['schema_extraction']['status'])
        self.assertEqual(2, sum(f.rule_id == 'schema.jsonld.processing.unverified' for f in report.findings))

    def test_observed_recipe_defects_are_not_hidden_by_an_unrelated_processing_error(self):
        _, report = page(['{"@type":"Recipe"}', DEPTH])
        self.assertIn('schema.recipe.missing.required.image', {f.rule_id for f in report.findings})
        self.assertIn('schema.recipe.missing.required.name', {f.rule_id for f in report.findings})

    def test_clean_supported_formats_keep_zero_error_counts_and_no_new_finding(self):
        for markup in (source([RECIPE]), '<div itemscope itemtype="https://schema.org/Recipe"></div>',
                       '<div vocab="https://schema.org/" typeof="Recipe"></div>'):
            doc = htmlx._parse_stdlib(markup, URL)
            report = Report(URL)
            audit_schema.audit(doc, None, report, {})
            self.assertTrue(all(stages(report)[key] == 0 for key in COUNTS))
            self.assertFalse({'schema.invalid.json.ld', 'schema.jsonld.processing.unverified'} & {f.rule_id for f in report.findings})

    def test_optional_parser_path_preserves_error_classification(self):
        receipts = []
        for parser in (htmlx._parse_stdlib, htmlx.parse):
            _, report = page(['{bad', DEPTH, UNICODE], parser=parser)
            receipts.append(stages(report))
        self.assertEqual(receipts[0], receipts[1])

    def test_unclassified_legacy_error_messages_are_not_backfilled_as_syntax_errors(self):
        with mock.patch.object(structured_data, 'collect', return_value=([], [(1, 'legacy error')])):
            _, report = page(['{}'])
        self.assertEqual((0, 0, 0, 1), tuple(stages(report)[key] for key in COUNTS))
        self.assertNotIn('schema.invalid.json.ld', {f.rule_id for f in report.findings})

    def test_processing_plan_is_verification_only_without_generation_owners_or_duplicate_task(self):
        _, report = page([DEPTH])
        result = plan.build_plan(json.loads(report.to_json()), str(FIXTURE))
        action, = result['actions']
        self.assertEqual('schema.jsonld.processing.unverified', action['rule_id'])
        self.assertTrue(action['manual_action'])
        self.assertEqual([], action['likely_files'])
        self.assertFalse(action['requires_deploy'])
        self.assertEqual([], result['groups'])

    def test_actual_syntax_repairs_keep_likely_owners_alongside_manual_processing_review(self):
        _, report = page(['{bad', DEPTH])
        result = plan.build_plan(json.loads(report.to_json()), str(FIXTURE))
        actions = {a['rule_id']: a for a in result['actions']}
        self.assertEqual('review_required', actions['schema.invalid.json.ld']['safety'])
        self.assertTrue(actions['schema.invalid.json.ld']['likely_files'])
        self.assertEqual('manual_external', actions['schema.jsonld.processing.unverified']['safety'])

    def test_product_heuristic_also_survives_decoder_limit_value_errors(self):
        doc = htmlx._parse_stdlib(source(['{}']), URL)
        with mock.patch.object(htmlx.json, 'loads', side_effect=ValueError('decoder guard')):
            self.assertFalse(htmlx.looks_product(doc))

    def test_ignored_findings_still_expose_uncertainty_and_manual_verification(self):
        _, report = page([DEPTH], ignore=lambda *args: True)
        self.assertEqual([], report.findings)
        self.assertIn('schema/overall score comparisons are unverified', report.to_markdown())
        result = plan.build_plan(json.loads(report.to_json()), str(FIXTURE))
        self.assertEqual('schema.extraction.unverified', result['actions'][0]['rule_id'])

    def test_real_scan_keeps_processing_uncertainty_in_page_diff_gates(self):
        report = scan_page(source([DEPTH]))
        self.assertIs(False, report.meta['scan_settings']['schema_extraction_reviewed'])
        value = json.loads(report.to_json())
        delta = diff_scan.diff_reports(value, value)
        self.assertEqual('incomparable', delta['comparison']['status'])
        self.assertIsNone(delta['score_delta'])
        self.assertEqual([], delta['resolved'])

    def test_counts_are_small_static_metadata_not_copied_source_or_error_messages(self):
        _, report = page(['{"PRIVATE_MARKUP":bad}'])
        value = stages(report)
        self.assertEqual(1, value['version'])
        self.assertEqual('decoder_and_node_processing_exceptions', value['basis'])
        self.assertNotIn('PRIVATE_MARKUP', json.dumps(value))
        self.assertEqual(sum(value[key] for key in COUNTS), report.meta['structured_data']['extraction_coverage']['jsonld_errors'])

    def test_error_reporting_and_planning_are_offline_readonly(self):
        with mock.patch('socket.socket', side_effect=AssertionError('No network')):
            _, report = page([DEPTH, UNICODE])
            before = report.to_json()
            result = plan.build_plan(json.loads(before), str(FIXTURE))
            report.to_html()
            plan.render_markdown(result)
        self.assertEqual(before, report.to_json())


if __name__ == '__main__':
    unittest.main()
