"""Execute emitted verification arguments against the real diff gate."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diff_scan
import mcp_server
import plan

REPO = 'skills/seo-scan/tests/fixtures/planner/plain_html'


def page():
    return {'url': 'https://example.test/', 'score': 90, 'findings': [],
            'meta': {'scan_scope': {'requested': ['technical'], 'completed': ['technical']}}}


def wrap(value, kind):
    return value if kind == 'scan' else {'schema_version': '2.0', 'site': value['url'],
        'overall_score': value['score'], 'homepage': value,
        'crawl': {'pages': [{'url': value['url']}], 'recurring': []}, 'sitemap': {}}


def execute(before, after, kind):
    command = plan.verification_for('sitemap', before.get('url', before.get('site')),
                                     '--before.json', kind)[-1]
    args = shlex.split(command)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / '--before.json').write_text(json.dumps(before), encoding='utf-8')
        (root / 'after.json').write_text(json.dumps(after), encoding='utf-8')
        original = Path.cwd()
        try:
            os.chdir(root)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = diff_scan.main(args[2:])
            assert json.loads((root / '--before.json').read_text(encoding='utf-8')) == before
        finally:
            os.chdir(original)
    return code


class TestPlanRegressionGate(unittest.TestCase):
    def test_generated_commands_fail_on_measured_regression_and_pass_stable_reports(self):
        for kind in ('scan', 'audit'):
            before = page()
            after = copy.deepcopy(before)
            after['score'] = 80
            for value, expected in ((before, 0), (after, 1)):
                with self.subTest(kind=kind, expected=expected):
                    self.assertEqual(expected, execute(wrap(before, kind), wrap(value, kind), kind))

    def test_known_incomplete_execution_cannot_pass_generated_gate(self):
        for kind in ('scan', 'audit'):
            before = page()
            after = copy.deepcopy(before)
            after['meta']['scan_scope']['completed'] = []
            self.assertEqual(2, execute(wrap(before, kind), wrap(after, kind), kind))

    def test_unknown_legacy_coverage_cannot_pass_generated_gate(self):
        for kind in ('scan', 'audit'):
            for before_known, after_known in ((False, False), (False, True), (True, False)):
                before, after = page(), page()
                if not before_known:
                    before.pop('meta')
                if not after_known:
                    after.pop('meta')
                self.assertEqual(2, execute(wrap(before, kind), wrap(after, kind), kind))

    def test_generated_audit_gate_rejects_missing_crawl_rule_evidence(self):
        before, after = wrap(page(), 'audit'), wrap(page(), 'audit')
        after['crawl'].pop('recurring')
        self.assertEqual(2, execute(before, after, 'audit'))

    def test_mcp_and_markdown_preserve_strict_gate_and_existing_safety(self):
        data = page()
        data['findings'] = [{'category': 'technical', 'severity': 'high',
                             'rule_id': 'technical.no.title.tag', 'title': 'No title tag'}]
        original = copy.deepcopy(data)
        built = mcp_server._plan(data, REPO)
        for action in built['actions']:
            command = next(step for step in action['verification'] if step.startswith('narwhal diff '))
            self.assertIn('--fail-on-regression', shlex.split(command))
            self.assertIn('--require-comparable', shlex.split(command))
            self.assertIn(command, plan.render_markdown(built))
        self.assertTrue(built['actions'])
        self.assertEqual(original, data)


if __name__ == '__main__':
    unittest.main()
