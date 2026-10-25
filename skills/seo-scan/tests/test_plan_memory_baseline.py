"""In-memory verification requires an explicitly preserved original baseline."""

import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diff_scan
import mcp_server
import plan
from lib import http

REPO = str(Path(__file__).parent / 'fixtures' / 'planner' / 'plain_html')
PAGE = {'url': 'https://example.test/', 'score': 94, 'findings': [
    {'category': 'technical', 'severity': 'high', 'rule_id': 'technical.missing.title', 'title': 'Missing title'}]}


class TestPlanMemoryBaseline(unittest.TestCase):
    def test_memory_prerequisite_precedes_every_diff_producing_workflow(self):
        for source in ('<memory>', '<mcp-object>', '<stdin>'):
            for kind in ('scan', 'audit'):
                for artifact in ('title', 'json_ld', 'sitemap', 'server_config'):
                    with self.subTest(source=source, kind=kind, artifact=artifact):
                        steps = plan.verification_for(artifact, PAGE['url'], source, kind)
                        self.assertEqual(plan.MEMORY_BASELINE_INSTRUCTION, steps[0])
                        self.assertIn('original input report JSON', steps[0])
                        self.assertIn('keeping all fields', steps[0])
                        self.assertIn('distinct fresh verification output paths', steps[0])
                        self.assertIn('Do not overwrite files or substitute a new scan', steps[0])
                        self.assertIn('has not saved a baseline', steps[0])
                        self.assertEqual('narwhal diff --fail-on-regression -- before.json after.json', steps[-1])

    def test_file_backed_reports_do_not_get_a_fictitious_save_requirement(self):
        for source in ('before.json', '/reports/after.json', r'C:\reports\page-after.json'):
            for kind in ('scan', 'audit'):
                steps = plan.verification_for('title', PAGE['url'], source, kind)
                self.assertNotIn(plan.MEMORY_BASELINE_INSTRUCTION, steps)
                self.assertTrue(any(step.startswith('narwhal scan ') for step in steps))

    def test_mcp_plan_changes_neither_report_nor_repository_and_saves_no_baseline(self):
        report = copy.deepcopy(PAGE)
        original = copy.deepcopy(report)
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'index.html').write_text('<title>Controlled fixture</title>')
            files = {path.name: path.read_bytes() for path in root.iterdir()}
            try:
                os.chdir(root)
                with mock.patch.object(http, 'fetch', side_effect=AssertionError('No network')):
                    built = mcp_server._plan(report, '.')
                self.assertEqual(files, {path.name: path.read_bytes() for path in root.iterdir()})
                self.assertFalse((root / 'before.json').exists())
            finally:
                os.chdir(previous)
        self.assertEqual(original, report)
        self.assertEqual('<mcp-object>', built['provenance']['report'])
        self.assertEqual(plan.MEMORY_BASELINE_INSTRUCTION, built['actions'][0]['verification'][0])

    def test_audit_markdown_keeps_save_instruction_outside_executable_block(self):
        report = {'site': PAGE['url'], 'homepage': copy.deepcopy(PAGE), 'crawl': {}, 'sitemap': {}}
        built = plan.build_plan(report, REPO)
        markdown = plan.render_markdown(built)
        self.assertLess(markdown.index(plan.MEMORY_BASELINE_INSTRUCTION), markdown.index('## Audit verification'))
        code = markdown.split('```sh\n', 1)[1].split('```', 1)[0].strip().splitlines()
        self.assertEqual(2, len(code))
        self.assertTrue(code[0].startswith('narwhal audit '))
        self.assertEqual('narwhal diff --fail-on-regression -- before.json after.json', code[1])
        self.assertNotIn(plan.MEMORY_BASELINE_INSTRUCTION, '\n'.join(code))

    def test_manual_only_and_empty_plans_do_not_invent_an_audit_diff(self):
        report = {'schema_version': '2.0', 'site': PAGE['url'], 'homepage': {'findings': []},
                  'crawl': {}, 'sitemap': {'errors': ['opaque note'], 'sitemaps_attempted': 1,
                                           'sitemaps_fetched': 0, 'fetch_failures': 1}}
        for data in (report, dict(report, sitemap={})):
            built = plan.build_plan(data, REPO)
            for action in built['actions']:
                self.assertNotIn(plan.MEMORY_BASELINE_INSTRUCTION, action['verification'])
                self.assertFalse(any(step.startswith('narwhal diff ') for step in action['verification']))
            markdown = plan.render_markdown(built)
            self.assertNotIn('## Audit verification', markdown)
            self.assertNotIn('narwhal diff ', markdown)
            self.assertNotIn(plan.MEMORY_BASELINE_INSTRUCTION, markdown)

    def test_save_guidance_does_not_upgrade_unknown_legacy_coverage(self):
        report = copy.deepcopy(PAGE)
        original = copy.deepcopy(report)
        built = plan.build_plan(report, REPO)
        self.assertEqual(original, report)
        self.assertEqual('legacy', built['provenance']['report_schema_version'])
        comparison = diff_scan.diff_reports(report, report)['comparison']
        self.assertEqual('unknown', comparison['status'])
        self.assertIsNone(comparison['old_scope'])

    def test_non_sitemap_manual_check_does_not_invent_shared_audit_commands(self):
        page = {'url': PAGE['url'], 'findings': [{'category': 'technical', 'severity': 'critical',
                'title': 'Page not served over HTTPS', 'rule_id': 'technical.page.not.served.over.https'}]}
        built = plan.build_plan({'site': PAGE['url'], 'homepage': page, 'crawl': {}, 'sitemap': {}}, REPO)
        self.assertTrue(built['actions'][0]['manual_action'])
        built['actions'][0]['verification'] = ['Review the hosting policy manually; no rerun requested.']
        markdown = plan.render_markdown(built)
        self.assertNotIn('## Audit verification', markdown)
        self.assertNotIn('narwhal audit ', markdown)
        self.assertNotIn(plan.MEMORY_BASELINE_INSTRUCTION, markdown)

    def test_manual_hosting_remediation_retains_its_requested_deployed_audit(self):
        page = {'url': PAGE['url'], 'findings': [{'category': 'technical', 'severity': 'critical',
                'title': 'Page not served over HTTPS', 'rule_id': 'technical.page.not.served.over.https'}]}
        built = plan.build_plan({'site': PAGE['url'], 'homepage': page, 'crawl': {}, 'sitemap': {}}, REPO)
        action = built['actions'][0]
        self.assertTrue(action['manual_action'])
        self.assertTrue(action['requires_deploy'])
        self.assertTrue(any(step.startswith('narwhal audit ') for step in action['verification']))
        markdown = plan.render_markdown(built)
        self.assertIn('## Audit verification', markdown)
        self.assertIn('narwhal audit ', markdown)
        self.assertIn('run after deploy', markdown)
        self.assertNotIn('narwhal scan ', markdown)


if __name__ == '__main__':
    unittest.main()
