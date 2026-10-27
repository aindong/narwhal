"""A successfully parsed HTML prefix cannot establish missing schema types."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_schema
import plan
import scan
import diff_scan
from lib import ecommerce, htmlx, http
from lib.report import Report, recorded_schema_extraction_problem

URL = 'https://example.test/guide'
REPO = Path(__file__).parent / 'fixtures/planner/plain_html'
THING = '<div itemscope itemtype="https://schema.org/Thing"></div>'
TYPES = '<script type="application/ld+json">[{"@type":"Article"},{"@type":"Organization"},{"@type":"Product"}]</script>'
MERCHANT = '<meta property="og:type" content="product"><meta property="product:price:amount" content="19.99">'


def scanned(source, *, truncated=False, only=None):
    headers = {'content-type': 'text/html'}
    if truncated:
        headers['x-narwhal-truncated'] = 'true'
    response = http.Response(URL, URL, 200, headers, source, 1)
    with mock.patch.object(http, 'fetch', return_value=response):
        return scan.scan(URL, only=only or ['schema'], ctx={}, check_images=False)


class TestSchemaSourceCoverage(unittest.TestCase):
    def test_native_prefix_does_not_penalize_unobserved_types_hidden_in_the_unread_suffix(self):
        for prefix in ('<h1>Guide</h1>', '<article><h1>Guide</h1>' + THING + '</article>', MERCHANT):
            with self.subTest(prefix=prefix):
                partial = scanned(prefix, truncated=True)
                complete = scanned(prefix + TYPES)
                self.assertFalse(plan.SCHEMA_ABSENCE_RULES & {f.rule_id for f in partial.findings})
                self.assertEqual('no_known_problem', partial.meta['structured_data']['extraction_coverage']['status'])
                self.assertIsNotNone(recorded_schema_extraction_problem(partial.meta, for_score=True))
                self.assertEqual(['schema'], partial.meta['scan_scope']['completed'])
                self.assertIn('technical.response.truncated', {f.rule_id for f in partial.findings})
                self.assertIn('Article', complete.meta['structured_data']['types_by_format']['jsonld'])
                self.assertIsNone(recorded_schema_extraction_problem(complete.meta, for_score=True))

    def test_standalone_auditors_honor_recorded_partial_and_truncated_source(self):
        for metadata in ({'response_truncated': True}, {'response_partial': True},
                         {'coverage': {'response_truncated': True}},
                         {'coverage': {'server_range': {'basis': http.SERVER_RANGE_BASIS, 'observed': True}}}):
            for standalone in (False, True):
                with self.subTest(metadata=metadata, standalone=standalone):
                    doc = htmlx._parse_stdlib(MERCHANT + '<article>' + THING + '</article>', URL)
                    report = Report(URL, fetched_status=200)
                    report.meta.update(copy.deepcopy(metadata))
                    if standalone:
                        ecommerce.audit(doc, report)
                    else:
                        audit_schema.audit(doc, None, report, {})
                    self.assertFalse(plan.SCHEMA_ABSENCE_RULES & {f.rule_id for f in report.findings})

    def test_observed_property_repairs_survive_but_stale_absence_advice_is_withheld(self):
        report = scanned('<script type="application/ld+json">{"@type":"Recipe"}</script>', truncated=True)
        data = json.loads(report.to_json())
        data['findings'].append({'category': 'schema', 'severity': 'medium', 'title': 'No structured data',
                                 'rule_id': 'schema.no.structured.data'})
        original = copy.deepcopy(data)
        built = plan.build_plan(data, str(REPO))
        actions = {a['rule_id']: a for a in built['actions']}
        self.assertFalse(plan.SCHEMA_ABSENCE_RULES & set(actions))
        verification = actions['schema.extraction.unverified']
        self.assertEqual('manual_external', verification['safety'])
        self.assertEqual([], verification['likely_files'])
        self.assertFalse(verification['requires_deploy'])
        repairs = [a for rule, a in actions.items() if rule.startswith('schema.recipe.missing.required.')]
        self.assertEqual(2, len(repairs))
        self.assertTrue(all(a['safety'] == 'review_required' and a['likely_files'] for a in repairs))
        self.assertEqual(original, data)
        result = diff_scan.diff_reports(data, data)
        self.assertEqual('incomparable', result['comparison']['status'])
        self.assertIsNone(result['score_delta'])
        self.assertEqual([], result['resolved'])

    def test_complete_absence_and_unselected_schema_controls_remain_usable(self):
        complete = scanned('<h1>Guide</h1>')
        self.assertIn('schema.no.structured.data', {f.rule_id for f in complete.findings})
        self.assertIsNone(recorded_schema_extraction_problem(complete.meta, for_score=True))
        content = scanned('<h1>Guide</h1>', truncated=True, only=['content'])
        self.assertIsNone(recorded_schema_extraction_problem(content.meta, for_score=True))


if __name__ == '__main__':
    unittest.main()
