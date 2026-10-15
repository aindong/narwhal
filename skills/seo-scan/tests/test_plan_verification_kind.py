"""A planner must not suggest comparing page scores with audit overall scores."""

import copy
import json
import shlex
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diff_scan
import mcp_server
import plan

FIXTURES = Path(__file__).parent / 'fixtures' / 'planner'
ALL = ['technical', 'content', 'schema', 'geo']


def audit_report():
    page = json.loads((FIXTURES / 'input-report.fixture.json').read_text())
    page['meta'] = {'scan_scope': {'requested': ALL, 'completed': ALL}}
    return {'schema_version': '2.0', 'site': page['url'], 'overall_score': page['score'],
            'homepage': page, 'crawl': {}, 'sitemap': {}}


class TestPlanVerificationKind(unittest.TestCase):
    def test_page_action_separates_local_scan_from_final_audit_comparison(self):
        built = plan.build_plan(audit_report(), str(FIXTURES / 'plain_html'),
                                report_source='audit-before.json')
        action = next(item for item in built['actions'] if item['artifact'] == 'title')
        commands = action['verification']
        self.assertEqual(['narwhal', 'scan', '--allow-private', '--format', 'json',
                          '-o', 'page-after.json', '--', '<local-preview-url>'], shlex.split(commands[0]))
        self.assertIn('page-level', commands[1])
        self.assertIn('do not compare', commands[1])
        self.assertIn('original audit configuration', commands[-3])
        self.assertIn('not record the complete invocation', commands[-3])
        self.assertEqual(['narwhal', 'audit', '--format', 'json', '-o', 'after.json',
                          '--', built['target']], shlex.split(commands[-2], comments=True))
        self.assertEqual(['narwhal', 'diff', '--', 'audit-before.json', 'after.json'],
                         shlex.split(commands[-1]))
        self.assertFalse(action['requires_deploy'])  # local page proof remains possible

    def test_deployed_artifacts_do_not_suggest_local_site_verification(self):
        for artifact in ('robots_txt', 'sitemap', 'llms_txt', 'server_config'):
            with self.subTest(artifact=artifact):
                commands = plan.verification_for(artifact, 'https://example.test',
                                                 'audit.json', 'audit')
                self.assertEqual(3, len(commands))
                self.assertFalse(any('narwhal scan' in item for item in commands))
                self.assertIn('run after deploy', commands[-2])

    def test_schema_review_stays_before_local_and_deployed_checks(self):
        for artifact in ('json_ld', 'product_schema'):
            commands = plan.verification_for(artifact, 'https://example.test', '<memory>', 'audit')
            self.assertIn('replace every TODO', commands[0])
            self.assertIn('-o page-after.json', commands[1])
            self.assertEqual('narwhal diff -- before.json after.json', commands[-1])

    def test_scan_contract_does_not_change(self):
        for artifact in ('title', 'json_ld', 'sitemap', 'server_config'):
            self.assertEqual(plan.verification_for(artifact, 'https://example.test', 'before.json'),
                             plan.verification_for(artifact, 'https://example.test', 'before.json', 'scan'))
        commands = plan.verification_for('title', 'https://example.test', 'before.json')
        self.assertIn('-o after.json', commands[0])
        self.assertFalse(any('narwhal audit' in item for item in commands))

    def test_same_kind_keeps_real_diff_while_cross_kind_stays_blocked(self):
        before = audit_report()
        after = copy.deepcopy(before)
        after['homepage']['findings'] = []
        result = diff_scan.diff_reports(before, after)
        self.assertEqual('comparable', result['comparison']['status'])
        self.assertTrue(result['resolved'])
        mismatch = diff_scan.diff_reports(before, after['homepage'])
        self.assertEqual('incomparable', mismatch['comparison']['status'])
        self.assertEqual([], mismatch['resolved'])

    def test_known_scope_mismatch_is_not_made_comparable_by_planner(self):
        before = audit_report()
        after = copy.deepcopy(before)
        after['homepage']['meta']['scan_scope'] = {'requested': ['schema'], 'completed': ['schema']}
        built = plan.build_plan(before, str(FIXTURES / 'plain_html'))
        action = next(item for item in built['actions'] if item['artifact'] == 'title')
        self.assertIn('matching report kind alone', action['verification'][-3])
        self.assertEqual('incomparable', diff_scan.diff_reports(before, after)['comparison']['status'])

    def test_legacy_audit_gets_no_invented_configuration_or_private_access(self):
        report = audit_report()
        del report['schema_version']
        report['homepage'].pop('meta')
        built = plan.build_plan(report, str(FIXTURES / 'plain_html'))
        action = next(item for item in built['actions'] if item['artifact'] == 'title')
        command = action['verification'][-2]
        self.assertNotIn('--allow-private', command)
        self.assertNotIn('--max-pages', command)
        self.assertNotIn('--no-config', command)
        self.assertEqual('audit', built['provenance']['report_kind'])

    def test_mcp_handoff_uses_the_same_audit_verification_without_mutation(self):
        report = audit_report()
        original = copy.deepcopy(report)
        built = mcp_server._plan(report, 'skills/seo-scan/tests/fixtures/planner/plain_html')
        action = next(item for item in built['actions'] if item['artifact'] == 'title')
        self.assertIn('narwhal audit', action['verification'][-2])
        self.assertEqual(report, original)

    def test_markdown_exposes_audit_rerun_and_settings_not_only_diff(self):
        built = plan.build_plan(audit_report(), str(FIXTURES / 'plain_html'),
                                report_source='audit-before.json')
        markdown = plan.render_markdown(built)
        self.assertIn('## Audit verification', markdown)
        self.assertIn('narwhal audit', markdown)
        self.assertIn('run after deploy', markdown)
        self.assertIn('original audit configuration', markdown)
        self.assertIn('do not diff it against the audit baseline', markdown)
        self.assertNotIn('narwhal scan', markdown)


if __name__ == '__main__':
    unittest.main()
