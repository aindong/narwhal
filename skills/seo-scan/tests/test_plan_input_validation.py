"""Malformed consumed evidence must fail before inventory or output writes."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan
import mcp_server

REPO = str(Path(__file__).parent / 'fixtures' / 'planner' / 'plain_html')


def baseline():
    return {'url': 'https://example.test/', 'score': 80, 'findings': [
        {'category': 'technical', 'severity': 'high', 'title': 'Missing title',
         'rule_id': 'technical.missing.title'}]}


class TestPlanInputValidation(unittest.TestCase):
    def test_invalid_finding_fields_raise_named_errors_before_inventory(self):
        for field, value in (
            ('severity', []), ('severity', 'urgent'), ('title', None), ('title', '\ud800'), ('category', {}),
            ('rule_id', ['technical.no.responsive.viewport.tag']), ('rule_id', '  '), ('rule_id', '\ud800'),
            ('confidence', True), ('confidence', float('nan')), ('confidence', 1.1),
            ('scope', 'global'), ('detail', {}), ('evidence', []), ('recommendation', None),
            ('count', '3'), ('count', 0), ('occurrences', float('inf')),
        ):
            with self.subTest(field=field, value=value):
                data = baseline()
                data['findings'][0][field] = value
                original = copy.deepcopy(data)
                with mock.patch.object(plan, 'inventory') as inventory:
                    with self.assertRaisesRegex(ValueError, r'findings\[0\]\.' + field):
                        plan.build_plan(data, REPO)
                    inventory.assert_not_called()
                # NaN is intentionally not equal to itself.
                self.assertEqual(json.dumps(original), json.dumps(data))

    def test_core_report_and_audit_containers_are_checked(self):
        invalid = [({'findings': None}, 'findings'), ({'findings': [None]}, 'findings'),
                   ({'homepage': []}, 'homepage'),
                   ({'findings': [], 'homepage': {'findings': []}}, 'ambiguous'),
                   ({'findings': [], 'url': ['https://example.test']}, 'URL'),
                   ({'findings': [], 'schema_version': {}}, 'schema_version')]
        for field, value in (('crawl', None), ('sitemap', [])):
            invalid.append(({'homepage': {'findings': []}, field: value}, field))
        for field, value in (('pages', None), ('pages', [None]), ('recurring', {}),
                             ('recurring', [dict(baseline()['findings'][0], count='oops')])):
            invalid.append(({'homepage': {'findings': []}, 'crawl': {field: value}}, 'crawl.' + field))
        for data, location in invalid:
            with self.subTest(location=location):
                with self.assertRaisesRegex(ValueError, location):
                    plan.build_plan(data, REPO)

    def test_scores_must_be_finite_measured_numbers_when_present(self):
        for score in (False, True, '80', -1, 101, float('nan'), float('inf')):
            for kind in ('scan', 'audit'):
                with self.subTest(score=score, kind=kind):
                    data = baseline()
                    field = 'score'
                    if kind == 'audit':
                        data = {'homepage': data, 'overall_score': score}
                        field = 'overall_score'
                    else:
                        data['score'] = score
                    with self.assertRaisesRegex(ValueError, field):
                        plan.build_plan(data, REPO)

    def test_tool_version_is_validated_before_inventory_and_keeps_legacy_strings(self):
        for kind in ('scan', 'audit'):
            for value in ({}, None, '\ud800'):
                with self.subTest(kind=kind, value=value):
                    data = baseline()
                    if kind == 'audit':
                        data = {'homepage': data}
                    data['tool_version'] = value
                    original = copy.deepcopy(data)
                    with mock.patch.object(plan, 'inventory', wraps=plan.inventory) as inventory:
                        with self.assertRaisesRegex(ValueError, r'Report\.tool_version'):
                            plan.build_plan(data, REPO)
                        with self.assertRaisesRegex(ValueError, r'Report\.tool_version'):
                            mcp_server._plan(data, 'skills/seo-scan/tests/fixtures/planner/plain_html')
                        inventory.assert_not_called()
                    self.assertEqual(original, data)
        for version in ('future-producer', ''):
            data = dict(baseline(), tool_version=version)
            self.assertEqual(version, plan.build_plan(data, REPO)['provenance']['report_tool_version'])
        self.assertEqual('unknown', plan.build_plan(baseline(), REPO)['provenance']['report_tool_version'])

    def test_legacy_missing_fields_and_null_optional_evidence_stay_supported(self):
        data = {'findings': [{'title': 'Missing title', 'evidence': None, 'detail': None}]}
        built = plan.build_plan(data, REPO)
        self.assertIsNone(built['source_score'])
        action = built['actions'][0]
        self.assertEqual('unknown.missing.title', action['rule_id'])
        self.assertEqual('low', action['severity'])
        self.assertEqual('', action['evidence'])
        data['findings'][0].update(rule_id='custom.rule', title='', confidence=0)
        self.assertEqual(0, plan.build_plan(data, REPO)['actions'][0]['confidence'])
        self.assertEqual([], plan.build_plan({'homepage': {}}, REPO)['actions'])

    def test_unusable_legacy_identity_is_rejected_even_on_good_findings(self):
        for finding in ({'title': '???'}, {'severity': 'good', 'title': '???'}, {}):
            with self.assertRaisesRegex(ValueError, 'identity'):
                plan.build_plan({'findings': [finding]}, REPO)

    def test_cli_rejects_invalid_json_and_evidence_without_touching_outputs(self):
        cases = [json.dumps({'findings': [dict(baseline()['findings'][0], severity=[])]}).encode(),
                 json.dumps({'findings': [], 'tool_version': {}}).encode(),
                 json.dumps({'findings': [], 'tool_version': '\ud800'}).encode(),
                 b'\xff', ('[' * 2000 + '0' + ']' * 2000).encode(),
                 ('{"findings": [], "score": ' + '9' * 5000 + '}').encode()]
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / 'before.json', Path(tmp) / 'plan.json'
            for body in cases:
                source.write_bytes(body)
                for existing in (False, True):
                    if existing:
                        output.write_bytes(b'keep this output')
                    elif output.exists():
                        output.unlink()
                    out, err = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        code = plan.main([str(source), '--repo', REPO, '-o', str(output)])
                    self.assertEqual(2, code)
                    self.assertEqual('', out.getvalue())
                    self.assertTrue(err.getvalue().startswith('Error: '))
                    self.assertNotIn('Traceback', err.getvalue())
                    self.assertLess(len(err.getvalue()), 500)
                    self.assertEqual(body, source.read_bytes())
                    self.assertEqual(b'keep this output' if existing else None,
                                     output.read_bytes() if output.exists() else None)

    def test_mcp_rejects_the_same_evidence_without_mutation(self):
        data = baseline()
        data['findings'][0]['confidence'] = 'certain'
        original = copy.deepcopy(data)
        with self.assertRaisesRegex(ValueError, 'confidence'):
            mcp_server._plan(data, 'skills/seo-scan/tests/fixtures/planner/plain_html')
        self.assertEqual(original, data)


if __name__ == '__main__':
    unittest.main()
