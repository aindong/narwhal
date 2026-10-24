"""Markdown handoffs must preserve prerequisites and executable verification steps."""

import json
from html.parser import HTMLParser
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan
import render_report

FIXTURES = Path(__file__).parent / 'fixtures' / 'planner'


class TestMarkdownVerification(unittest.TestCase):
    def built(self, kind='scan', source='before.json'):
        page = {'url': 'https://example.test/', 'findings': [
            {'category': 'schema', 'severity': 'high', 'title': 'No structured data (JSON-LD)',
             'rule_id': 'schema.no.structured.data.json.ld'}]}
        report = page if kind == 'scan' else {'site': page['url'], 'homepage': page, 'crawl': {}, 'sitemap': {}}
        return plan.build_plan(report, str(FIXTURES / 'plain_html'), report_source=source)

    def test_scan_markdown_keeps_validation_scan_and_diff_in_order(self):
        built = self.built()
        markdown = plan.render_markdown(built)
        section = markdown.split('### HIGH', 1)[1]
        previous = -1
        for step in built['actions'][0]['verification']:
            position = section.index(step)
            self.assertGreater(position, previous)
            previous = position
        self.assertIn("-- '<local-preview-url>'", section)
        self.assertIn('replace every TODO', section)

    def test_audit_action_keeps_local_scope_and_deployment_prerequisites(self):
        built = self.built('audit')
        section = plan.render_markdown(built).split('### HIGH', 1)[1]
        previous = -1
        for step in built['actions'][0]['verification']:
            position = section.index(step)
            self.assertGreater(position, previous)
            previous = position
        self.assertIn('do not compare page-after.json', section)
        self.assertIn('run after deploy', section)

    def test_manual_steps_are_all_visible_without_invented_commands(self):
        built = self.built()
        steps = ['Inspect the actual hosting policy.', 'Confirm endpoint access.', 'Record the observed result.']
        built['actions'][0]['verification'] = steps
        markdown = plan.render_markdown(built)
        for step in steps:
            self.assertIn(step, markdown)
        self.assertNotIn('```sh', markdown)
        self.assertNotIn('narwhal diff', markdown)

    def test_command_fences_preserve_backticks_and_newlines_in_literal_paths(self):
        source = 'reports/```literal\nname.json'
        built = self.built(source=source)
        step = built['actions'][0]['verification'][-1]
        markdown = plan.render_markdown(built)
        self.assertIn('````sh\n' + step + '\n````', markdown)
        self.assertIn("'reports/```literal\nname.json'", markdown)

    def test_shared_memory_prerequisite_is_visible_once_before_commands(self):
        built = self.built(source='<mcp-object>')
        markdown = plan.render_markdown(built)
        self.assertEqual(1, markdown.count(plan.MEMORY_BASELINE_INSTRUCTION))
        self.assertLess(markdown.index(plan.MEMORY_BASELINE_INSTRUCTION), markdown.index('```sh'))

    def test_shared_audit_commands_also_keep_literal_fence_markers(self):
        built = self.built('audit', 'reports/```literal\nname.json')
        markdown = plan.render_markdown(built)
        shared = markdown.split('## Audit verification', 1)[1].split('## Review required', 1)[0]
        self.assertIn('````sh\nnarwhal audit ', shared)
        self.assertIn(built['actions'][0]['verification'][-1] + '\n````', shared)

    def test_html_export_keeps_commands_literal_and_instructions_outside_code(self):
        class CodeText(HTMLParser):
            def __init__(self):
                super().__init__()
                self.inside = False
                self.blocks = []

            def handle_starttag(self, tag, attrs):
                if tag == 'pre':
                    self.inside = True
                    self.blocks.append('')

            def handle_endtag(self, tag):
                if tag == 'pre':
                    self.inside = False

            def handle_data(self, data):
                if self.inside:
                    self.blocks[-1] += data

        built = self.built(source='reports/```literal\n<script>.json')
        parser = CodeText()
        parser.feed(render_report.render(plan.render_markdown(built)))
        commands = [step for step in built['actions'][0]['verification'] if step.startswith('narwhal ')]
        self.assertEqual(commands, [block.rstrip('\n') for block in parser.blocks])
        self.assertFalse(any('replace every TODO' in block for block in parser.blocks))

    def test_render_does_not_mutate_json_handoff(self):
        built = self.built('audit', '<mcp-object>')
        before = json.dumps(built, sort_keys=True)
        plan.render_markdown(built)
        self.assertEqual(before, json.dumps(built, sort_keys=True))


if __name__ == '__main__':
    unittest.main()
