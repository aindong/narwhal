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
        scans = [step for step in commands if step.startswith('narwhal scan ')]
        self.assertEqual(['narwhal', 'scan', '--allow-private', '--format', 'json',
                          '-o', 'page-before.json', '--only', ','.join(ALL), '--', '<local-preview-url>'], shlex.split(scans[0]))
        self.assertIn('-o page-after.json', scans[1])
        self.assertTrue(any('page-level' in step and 'do not compare' in step for step in commands))
        self.assertIn('original audit configuration', commands[-3])
        self.assertIn('not record the complete invocation', commands[-3])
        self.assertEqual(['narwhal', 'audit', '--format', 'json', '-o', 'after.json',
                          '--', built['target']], shlex.split(commands[-2], comments=True))
        self.assertEqual(['narwhal', 'diff', '--fail-on-regression', '--require-comparable', '--', 'audit-before.json', 'after.json'],
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
            self.assertEqual(plan.MEMORY_BASELINE_INSTRUCTION, commands[0])
            baseline = next(i for i, step in enumerate(commands) if '-o page-before.json' in step)
            validation = next(i for i, step in enumerate(commands) if 'replace every TODO' in step)
            after = next(i for i, step in enumerate(commands) if '-o page-after.json' in step)
            self.assertLess(baseline, validation)
            self.assertLess(validation, after)
            self.assertTrue(any('-o page-before.json' in step for step in commands))
            self.assertTrue(any('-o page-after.json' in step for step in commands))
            self.assertEqual('narwhal diff --fail-on-regression --require-comparable -- before.json after.json', commands[-1])

    def test_scan_contract_does_not_change(self):
        for artifact in ('title', 'json_ld', 'sitemap', 'server_config'):
            self.assertEqual(plan.verification_for(artifact, 'https://example.test', 'before.json'),
                             plan.verification_for(artifact, 'https://example.test', 'before.json', 'scan'))
        commands = plan.verification_for('title', 'https://example.test', 'before.json')
        self.assertTrue(any('-o after.json' in step for step in commands))
        self.assertFalse(any('narwhal audit' in item for item in commands))

    def test_built_plan_keeps_report_kind_zero_score_and_matching_rerun(self):
        for kind in ('scan', 'audit'):
            for score in (0, 0.0):
                with self.subTest(kind=kind, score=score):
                    data = audit_report()
                    data['homepage'].update(url='https://example.test/original/',
                                            final_url='https://example.test/fetched/')
                    if kind == 'scan':
                        data = data['homepage']
                        data['score'] = score
                        target = data['final_url']
                    else:
                        data['overall_score'] = score
                        target = data['site']
                    original = copy.deepcopy(data)
                    built = plan.build_plan(data, str(FIXTURES / 'plain_html'), report_source='<mcp-object>')
                    self.assertEqual(kind, built['provenance']['report_kind'])
                    self.assertEqual(target, built['target'])
                    self.assertEqual(0, built['source_score'])
                    self.assertIn(type(built['source_score']), (int, float))
                    action = next(a for a in built['actions'] if a['artifact'] == 'title')
                    command = shlex.split(action['verification'][-2], comments=True)
                    self.assertEqual(['narwhal', kind], command[:2])
                    self.assertEqual(['--', target], command[-2:])
                    self.assertEqual('after.json', command[command.index('-o') + 1])
                    self.assertEqual(built, mcp_server._plan(data, 'skills/seo-scan/tests/fixtures/planner/plain_html'))
                    self.assertEqual(original, data)

    def test_legacy_audit_fallback_targets_remain_literal_in_verification(self):
        original_url = 'https://example.test/original?source=old'
        final_url = 'https://example.test/fetched?view=full&lang=en#part'
        for site, labels, target in (
                ('example.test', {'url': original_url, 'final_url': final_url}, 'example.test'),
                (None, {'url': original_url, 'final_url': final_url}, final_url),
                ('', {'url': original_url}, original_url),
                (None, {}, '')):
            with self.subTest(site=site, labels=labels):
                data = audit_report()
                data.pop('site')
                if site is not None:
                    data['site'] = site
                for field in ('url', 'final_url'):
                    data['homepage'].pop(field, None)
                data['homepage'].update(labels)
                original = copy.deepcopy(data)
                built = plan.build_plan(data, str(FIXTURES / 'plain_html'), report_source='<mcp-object>')
                self.assertEqual('audit', built['provenance']['report_kind'])
                self.assertEqual(target, built['target'])
                action = next(a for a in built['actions'] if a['artifact'] == 'title')
                command = shlex.split(action['verification'][-2], comments=True)
                self.assertEqual(['narwhal', 'audit'], command[:2])
                self.assertEqual(['--', target], command[-2:])
                if not target:
                    self.assertTrue(any('not a supported recorded HTTP(S) URL label' in w for w in built['warnings']))
                self.assertEqual(built, mcp_server._plan(data, 'skills/seo-scan/tests/fixtures/planner/plain_html'))
                self.assertEqual(original, data)

    def test_scan_score_ignores_audit_only_fields(self):
        page = audit_report()['homepage']
        for score in (0, 80, None, 'missing'):
            control = copy.deepcopy(page)
            if score == 'missing':
                control.pop('score')
            else:
                control['score'] = score
            expected = plan.build_plan(control, str(FIXTURES / 'plain_html'), report_source='<mcp-object>')
            for extra in (20, None, {}, 'future-field'):
                with self.subTest(score=score, extra=extra):
                    supplied = dict(control, overall_score=extra)
                    original = copy.deepcopy(supplied)
                    built = plan.build_plan(supplied, str(FIXTURES / 'plain_html'), report_source='<mcp-object>')
                    self.assertEqual(None if score == 'missing' else score, built['source_score'])
                    self.assertEqual(expected, built)
                    self.assertEqual(built, mcp_server._plan(supplied, 'skills/seo-scan/tests/fixtures/planner/plain_html'))
                    self.assertEqual(original, supplied)

    def test_audit_without_overall_score_does_not_invent_site_measurement(self):
        for overall in (0, 20, None, 'missing'):
            for page_score in (80, 'not-a-site-score'):
                with self.subTest(overall=overall, page_score=page_score):
                    supplied = audit_report()
                    supplied['homepage']['score'] = page_score
                    supplied['score'] = 99
                    if overall == 'missing':
                        supplied.pop('overall_score')
                    else:
                        supplied['overall_score'] = overall
                    original = copy.deepcopy(supplied)
                    built = plan.build_plan(supplied, str(FIXTURES / 'plain_html'), report_source='<mcp-object>')
                    self.assertEqual(None if overall == 'missing' else overall, built['source_score'])
                    self.assertEqual('audit', built['provenance']['report_kind'])
                    self.assertTrue(built['actions'])
                    for action in built['actions']:
                        command = shlex.split(action['verification'][-2], comments=True)
                        self.assertEqual(['narwhal', 'audit'], command[:2])
                    self.assertEqual(built, mcp_server._plan(supplied, 'skills/seo-scan/tests/fixtures/planner/plain_html'))
                    self.assertEqual(original, supplied)

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
        self.assertIn('narwhal scan --allow-private', markdown)
        self.assertIn('do not compare page-after.json', markdown)


if __name__ == '__main__':
    unittest.main()
