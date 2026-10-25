"""Reported recommendations remain bounded literal data beside planner guidance."""
import copy
import json
from pathlib import Path
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan
import render_report
from test_plan_repeated_evidence import finding, report, build, REPO

LABEL = 'Reported recommendation (preview, review required)'


class TestRecommendationPreview(unittest.TestCase):
    def test_specific_report_guidance_is_visible_without_replacing_planner_change(self):
        row = finding('high', 'Title')
        row['recommendation'] = 'Use the published service name and verified location in the title.'
        data = report([row]); original = copy.deepcopy(data)
        built = build(data); action = built['actions'][0]; text = plan.render_markdown(built)
        self.assertIn(LABEL, text)
        self.assertIn(row['recommendation'], text)
        self.assertIn(action['proposed_change'], text)
        self.assertNotEqual(row['recommendation'], action['proposed_change'])
        self.assertEqual(original, data)

    def test_recommendation_is_a_literal_text_block_not_an_executable_template(self):
        row = finding('high', 'Title')
        payload = 'narwhal publish --unsafe\n```\n## Injected section\n<script>bad()</script>'
        row['recommendation'] = payload
        built = build(report([row])); text = plan.render_markdown(built)
        self.assertIn('````text\n' + payload + '\n````', text)
        commands = re.findall(r'(?ms)^(`{3,})sh\n(.*?)^\1$', text)
        self.assertTrue(commands)
        self.assertTrue(all('publish --unsafe' not in body for _, body in commands))
        self.assertEqual(payload, built['actions'][0]['source_recommendation'])
        html = render_report.render(text)
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)

    def test_bounded_preview_retains_full_json_and_existing_evidence_preview(self):
        row = finding('high', 'Title')
        row['evidence'] = 'e' * 700
        row['recommendation'] = 'r' * 700 + 'END_RECOMMENDATION'
        built = build(report([row])); text = plan.render_markdown(built)
        self.assertIn('r' * 600, text)
        self.assertNotIn('r' * 601, text)
        self.assertNotIn('END_RECOMMENDATION', text)
        self.assertIn('full action source_recommendation remains in plan JSON', text)
        self.assertIn('full action evidence remains in plan JSON', text)
        self.assertEqual(row['recommendation'], json.loads(plan.render_json(built))['actions'][0]['source_recommendation'])

    def test_absent_empty_and_legacy_action_fields_do_not_create_empty_sections(self):
        for value in (None, ''):
            row = finding('high', 'Title')
            if value is None: row.pop('recommendation')
            else: row['recommendation'] = value
            built = build(report([row]))
            self.assertNotIn(LABEL, plan.render_markdown(built))
            built['actions'][0].pop('source_recommendation')
            self.assertNotIn(LABEL, plan.render_markdown(built))

    def test_known_contextual_overrides_do_not_reintroduce_legacy_recommendations(self):
        for rule in ('content.content.is.very.hard.to.read', 'technical.sitemap.sample.unverified'):
            row = finding('high', 'Legacy guidance finding')
            row.update(rule_id=rule, category=rule.split('.')[0], recommendation='UNSUPPORTED_LEGACY_CLAIM')
            built = build(report([row])); text = plan.render_markdown(built)
            self.assertNotIn('UNSUPPORTED_LEGACY_CLAIM', text)
            self.assertNotIn(LABEL, text)
            self.assertIn('use the contextual review/verification guidance above', text)
            self.assertEqual('UNSUPPORTED_LEGACY_CLAIM', built['actions'][0]['source_recommendation'])

    def test_worst_observation_guidance_is_displayed_with_offline_mcp_parity(self):
        data = report([finding('low', 'weak'), finding('high', 'strong')])
        original = copy.deepcopy(data)
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            built = mcp_server._plan(data, REPO)
        text = plan.render_markdown(built)
        self.assertIn('strong advice', text)
        self.assertNotIn('weak advice', text)
        self.assertEqual(build(data), built)
        self.assertEqual('manual_external', built['actions'][0]['safety'])
        self.assertEqual(original, data)


if __name__ == '__main__':
    unittest.main()
