"""Current emitted plans must fit the checked-in handoff schema."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None

SCHEMA = json.loads((Path(plan.__file__).parent.parent / 'references/remediation-plan.schema.json').read_text(encoding='utf-8'))
RULE = 'technical.no.responsive.viewport.tag'


class TestPlanSchemaContract(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name).resolve()
        (root / 'index.html').write_text('<html><head></head></html>', encoding='utf-8')
        (root / 'other.html').write_text('<html></html>', encoding='utf-8')
        report = {'url': 'https://example.test/', 'status': 200,
                  'meta': {'scan_scope': {'requested': ['technical'], 'completed': ['technical']}},
                  'findings': [{'rule_id': RULE, 'category': 'technical', 'severity': 'high',
                                'title': 'No responsive viewport tag'}]}
        self.cases = {'complete': plan.build_plan(report, str(root)),
                      'capped': plan.build_plan(report, str(root), max_files=1)}

        def denied_walk(path, *, followlinks, onerror):
            yield str(root), [], ['index.html']
            onerror(PermissionError(13, 'denied', str(root / 'blocked')))
        with mock.patch.object(plan.os, 'walk', side_effect=denied_walk):
            self.cases['walk_error'] = plan.build_plan(report, str(root))
        repeated = copy.deepcopy(report)
        repeated['findings'].append(dict(report['findings'][0], detail='Second observation'))
        self.cases['repeated'] = plan.build_plan(repeated, str(root))
        partial = copy.deepcopy(report)
        partial['status'] = 206
        partial['meta']['scan_scope']['completed'] = []
        partial['findings'] = [{'rule_id': 'technical.response.partial', 'category': 'technical',
                                'severity': 'critical', 'title': 'Ranged response needs full-page verification'}]
        self.cases['manual_verification'] = plan.build_plan(partial, str(root))

    def test_emitted_inventory_and_action_fields_are_declared(self):
        action_properties = SCHEMA['properties']['actions']['items']['properties']
        self.assertEqual(8, action_properties['likely_files'].get('maxItems'))
        self.assertIs(True, action_properties['likely_files'].get('uniqueItems'))
        allowed_blockers = action_properties['automation_eligibility']['properties']['blockers']['items']['enum']
        for name, built in self.cases.items():
            with self.subTest(case=name, part='coverage'):
                self.assertLessEqual(set(built['coverage']), set(SCHEMA['properties']['coverage']['properties']))
            for action in built['actions']:
                with self.subTest(case=name, part='action'):
                    self.assertLessEqual(set(action), set(action_properties))
                if 'automation_eligibility' in action:
                    with self.subTest(case=name, part='blockers'):
                        self.assertLessEqual(set(action['automation_eligibility']['blockers']), set(allowed_blockers))
        self.assertTrue(self.cases['capped']['coverage']['file_inventory_capped'])
        self.assertEqual(1, self.cases['walk_error']['coverage']['file_inventory_walk_errors'])
        self.assertEqual(2, self.cases['repeated']['actions'][0]['observation_selection']['normalized_observations'])

    @unittest.skipIf(Draft202012Validator is None, 'Full schema validation runs with both MCP SDK dependency sets')
    def test_full_schema_accepts_emitted_and_legacy_plans_but_rejects_bad_receipts(self):
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')) as dns, \
                mock.patch('socket.socket.connect', side_effect=AssertionError('No network')) as connect:
            Draft202012Validator.check_schema(SCHEMA)
            validator = Draft202012Validator(SCHEMA)
            for name, built in self.cases.items():
                with self.subTest(case=name):
                    self.assertEqual([], list(validator.iter_errors(built)))
            legacy = copy.deepcopy(self.cases['complete'])
            del legacy['coverage']['file_inventory_walk_errors']
            self.assertEqual([], list(validator.iter_errors(legacy)))
            for value in (-1, True, '1'):
                malformed = copy.deepcopy(self.cases['complete'])
                malformed['coverage']['file_inventory_walk_errors'] = value
                with self.subTest(invalid_count=value):
                    self.assertTrue(list(validator.iter_errors(malformed)))
            malformed = copy.deepcopy(self.cases['repeated'])
            malformed['actions'][0]['observation_selection']['normalized_observations'] = 1
            self.assertTrue(list(validator.iter_errors(malformed)))
            malformed = copy.deepcopy(self.cases['capped'])
            malformed['actions'][0]['automation_eligibility']['blockers'] = ['unrecognized_future_blocker']
            self.assertTrue(list(validator.iter_errors(malformed)))
            for count in (2, 8, 9):
                malformed = copy.deepcopy(self.cases['complete'])
                owner = malformed['actions'][0]['likely_files'][0]
                malformed['actions'][0]['likely_files'] = [dict(owner, path='owner-{}.html'.format(i))
                                                          for i in range(count)]
                if count == 2:
                    malformed['actions'][0]['likely_files'][1] = copy.deepcopy(malformed['actions'][0]['likely_files'][0])
                with self.subTest(invalid_owner_count=count):
                    errors = list(validator.iter_errors(malformed))
                    self.assertEqual(count != 8, bool(errors))
        dns.assert_not_called()
        connect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
