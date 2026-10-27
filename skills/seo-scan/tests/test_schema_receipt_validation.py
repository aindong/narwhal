"""Unsupported explicit schema evidence cannot authorize absence-based repairs."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan
import mcp_server
import diff_scan
from lib.report import recorded_schema_extraction_problem
from test_schema_coverage import scan_page

REPO = Path(__file__).parent / 'fixtures/planner/plain_html'
VERIFY = 'schema.extraction.unverified'


def baseline():
    return json.loads(scan_page('<h1>Guide</h1>').to_json())


class TestSchemaReceiptValidation(unittest.TestCase):
    def test_requested_schema_and_default_information_are_not_completed_score_scope(self):
        page = baseline()
        page['meta']['structured_data'] = None
        page['meta']['scan_scope'] = {'requested': ['schema', 'content'], 'completed': ['content']}
        self.assertIsNotNone(recorded_schema_extraction_problem(page['meta'], for_score=True))
        self.assertEqual([VERIFY], [a['rule_id'] for a in plan.build_plan(page, str(REPO))['actions']])
        page['meta']['scan_scope'] = {'requested': ['content'], 'completed': ['content']}
        self.assertIsNotNone(recorded_schema_extraction_problem(page['meta']))
        self.assertIsNone(recorded_schema_extraction_problem(page['meta'], for_score=True))

    def test_explicit_bad_containers_and_review_flags_withhold_repairs_and_fix_claims(self):
        cases = [('structured_data', value) for value in (None, False, True, 0, 1.0, 'secret-token', [], ['secret-token'])]
        cases += [('schema_extraction_reviewed', value) for value in (None, 0, 1, 'true', 'secret-token', [], {})]
        files = {p: p.read_bytes() for p in REPO.rglob('*') if p.is_file()}
        for field, value in cases:
            kinds = ('scan', 'audit') if field == 'structured_data' else ('scan', 'audit', 'crawl')
            for kind in kinds:
                with self.subTest(field=field, value=value, kind=kind):
                    page = baseline()
                    if field == 'structured_data':
                        page['meta'][field] = value
                    else:
                        page['meta']['scan_settings'][field] = value
                    data = page if kind == 'scan' else {
                        'site': page['url'], 'overall_score': 90, 'homepage': page, 'crawl': {}}
                    if kind == 'crawl':
                        home = baseline()
                        home['findings'] = []
                        data['homepage'] = home
                        data['crawl'] = {'pages': [{'url': page['url'] + '/leaf', 'status': 200,
                            'scan_scope': page['meta']['scan_scope'], 'scan_settings': page['meta']['scan_settings']}],
                            'recurring': copy.deepcopy(page['findings'])}
                    original = copy.deepcopy(data)
                    with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')), \
                            mock.patch('socket.socket.connect', side_effect=AssertionError('No network')):
                        built = plan.build_plan(data, str(REPO), report_source='<mcp-object>')
                        with mock.patch.object(Path, 'cwd', return_value=REPO.resolve().parent):
                            self.assertEqual(built, mcp_server._plan(data, REPO.name))
                    action, = built['actions']
                    self.assertEqual((VERIFY, 'schema', 'low', 'site' if kind == 'crawl' else 'page', 'manual_external'),
                                     tuple(action[key] for key in ('rule_id', 'category', 'severity', 'scope', 'safety')))
                    self.assertTrue(action['manual_action'])
                    self.assertFalse(action['requires_deploy'])
                    self.assertEqual([], action['likely_files'])
                    self.assertFalse(built['groups'])
                    self.assertEqual(page['score'] if kind == 'scan' else 90, built['source_score'])
                    self.assertNotIn('secret-token', json.dumps(built))
                    newer = copy.deepcopy(data)
                    if kind == 'scan':
                        newer.update(score=100, findings=[])
                    else:
                        newer['overall_score'] = 100
                        newer['homepage']['findings'] = []
                        newer['crawl']['recurring'] = []
                    result = diff_scan.diff_reports(data, newer)
                    self.assertEqual('incomparable', result['comparison']['status'])
                    self.assertIsNone(result['score_delta'])
                    self.assertEqual([], result['resolved'])
                    self.assertTrue(any(isinstance(reason, str) and 'structured-data' in reason.lower()
                                        for reason in result['comparison']['reasons']))
                    self.assertEqual(original, data)
        self.assertTrue(all(p.read_bytes() == before for p, before in files.items()))

    def test_unselected_schema_and_missing_legacy_fields_do_not_invent_problems(self):
        for value in (None, False, [], 'secret-token'):
            page = baseline()
            page['findings'] = []
            page['meta']['scan_scope'] = {'requested': ['content'], 'completed': ['content']}
            page['meta']['structured_data'] = value
            page['meta']['scan_settings']['schema_extraction_reviewed'] = value
            self.assertFalse(plan.build_plan(page, str(REPO))['actions'])
            self.assertEqual('comparable', diff_scan.diff_reports(page, page)['comparison']['status'])
        for metadata in ({}, {'structured_data': {}}, {'scan_settings': {}},
                         {'structured_data': {'microdata_warnings': [], 'rdfa_warnings': []}}):
            page = baseline()
            page['meta'] = metadata
            built = plan.build_plan(page, str(REPO))
            self.assertNotIn(VERIFY, [a['rule_id'] for a in built['actions']])
            self.assertTrue(all(a['safety'] == 'review_required' for a in built['actions']))

    def test_supported_metadata_keeps_conditional_absence_and_independent_property_repairs(self):
        page = baseline()
        built = plan.build_plan(page, str(REPO))
        self.assertEqual(['schema.no.structured.data'], [a['rule_id'] for a in built['actions']])
        self.assertEqual('review_required', built['actions'][0]['safety'])
        self.assertEqual('comparable', diff_scan.diff_reports(page, page)['comparison']['status'])
        page = json.loads(scan_page('<script type="application/ld+json">{"@type":"Recipe"}</script>').to_json())
        page['meta']['structured_data'] = None
        built = plan.build_plan(page, str(REPO))
        repairs = [a for a in built['actions'] if a['rule_id'].startswith('schema.recipe.missing.required.')]
        self.assertEqual(2, len(repairs))
        self.assertTrue(all(a['safety'] == 'review_required' and a['likely_files'] for a in repairs))
        self.assertIn(VERIFY, [a['rule_id'] for a in built['actions']])


if __name__ == '__main__':
    unittest.main()
