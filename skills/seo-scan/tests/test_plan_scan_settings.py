"""Verification templates preserve supported recorded scan inputs, not guessed invocations."""
import copy
from pathlib import Path
import shlex
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan
import mcp_server

REPO = str(Path(__file__).parent / 'fixtures' / 'planner' / 'plain_html')


def report():
    return {'url': 'https://example.test/', 'findings': [
        {'category': 'technical', 'severity': 'high', 'title': 'Missing title',
         'rule_id': 'technical.missing.title'}], 'meta': {
        'scan_scope': {'requested': ['technical', 'geo'], 'completed': ['technical', 'geo']},
        'scan_settings': {'render_requested': True, 'rendered': False, 'image_checks': False}}}


class TestScanSettings(unittest.TestCase):
    def command(self, data):
        built = plan.build_plan(data, REPO, report_source='before.json')
        return next(step for step in built['actions'][0]['verification'] if step.startswith('narwhal scan '))

    def test_selected_auditors_requested_rendering_and_images_survive_handoff(self):
        data = report()
        original = copy.deepcopy(data)
        tokens = shlex.split(self.command(data))
        self.assertEqual('technical,geo', tokens[tokens.index('--only') + 1])
        self.assertIn('--render', tokens)  # requested mode, not a false claim that rendering succeeded
        self.assertIn('--no-image-checks', tokens)
        self.assertLess(tokens.index('--render'), tokens.index('--'))
        self.assertEqual(original, data)

    def test_requested_not_completed_auditors_are_retried(self):
        data = report()
        data['meta']['scan_scope']['completed'] = ['technical']
        self.assertIn('--only technical,geo', self.command(data))

    def test_malformed_or_missing_receipts_do_not_invent_flags(self):
        for meta in (None, [], 'opaque', {}, {'scan_scope': {'requested': ['technical; touch sentinel'], 'completed': []}},
                     {'scan_settings': {'render_requested': 'true', 'rendered': True, 'image_checks': 0}},
                     {'scan_settings': {'render_requested': 1, 'image_checks': 0}},
                     {'scan_scope': {'requested': ['technical'], 'completed': ['geo']}}):
            data = report()
            data['meta'] = meta
            tokens = shlex.split(self.command(data))
            self.assertNotIn('--only', tokens)
            self.assertNotIn('--render', tokens)
            self.assertNotIn('--no-image-checks', tokens)

    def test_false_render_and_enabled_images_do_not_emit_opposite_flags(self):
        data = report()
        data['meta']['scan_settings'] = {'render_requested': False, 'image_checks': True}
        tokens = shlex.split(self.command(data))
        self.assertNotIn('--render', tokens)
        self.assertNotIn('--no-image-checks', tokens)

    def test_deployed_scan_and_local_audit_scan_use_same_recorded_page_options(self):
        data = report()
        data['findings'][0].update(title='No robots.txt found', rule_id='technical.no.robots.txt.found')
        deployed = shlex.split(self.command(data), comments=True)
        self.assertIn('--render', deployed)
        self.assertNotIn('--allow-private', deployed)
        page = report()
        audit = {'site': page['url'], 'homepage': page, 'crawl': {}, 'sitemap': {}}
        built = plan.build_plan(audit, REPO)
        local = next(step for step in built['actions'][0]['verification'] if step.startswith('narwhal scan '))
        self.assertIn('--only technical,geo', local)
        final = next(step for step in built['actions'][0]['verification'] if step.startswith('narwhal audit '))
        self.assertNotIn('--only', final)  # page receipts cannot reconstruct site invocation

    def test_settings_prerequisite_visible_before_commands_in_json_and_markdown(self):
        built = plan.build_plan(report(), REPO)
        steps = built['actions'][0]['verification']
        self.assertIn(plan.SCAN_SETTINGS_INSTRUCTION, steps)
        self.assertLess(steps.index(plan.SCAN_SETTINGS_INSTRUCTION), next(i for i,s in enumerate(steps) if s.startswith('narwhal scan ')))
        markdown = plan.render_markdown(built)
        self.assertEqual(1, markdown.count(plan.SCAN_SETTINGS_INSTRUCTION))
        self.assertLess(markdown.index(plan.SCAN_SETTINGS_INSTRUCTION), markdown.index('```sh'))
        self.assertIn('--only technical,geo --render --no-image-checks', markdown)

    def test_mcp_uses_recorded_settings_without_saving_or_changing_baseline(self):
        data = report()
        original = copy.deepcopy(data)
        built = mcp_server._plan(data, 'skills/seo-scan/tests/fixtures/planner/plain_html')
        self.assertTrue(any('--only technical,geo --render --no-image-checks' in step
                            for step in built['actions'][0]['verification']))
        self.assertEqual(original, data)


if __name__ == '__main__':
    unittest.main()
