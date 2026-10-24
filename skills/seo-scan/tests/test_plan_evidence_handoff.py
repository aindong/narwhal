"""Retain sampled failure witnesses and show bounded literal evidence beside actions."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan
import render_report
try:
    from .test_code_fences import Parsed
    from .test_plan_sitemap_verification import report as audit_report, SOURCE, SAMPLE
except ImportError:
    from test_code_fences import Parsed
    from test_plan_sitemap_verification import report as audit_report, SOURCE, SAMPLE

REPO = Path(__file__).parent / 'fixtures/planner/plain_html'
PAYLOAD = 'HTTP 404 https://example.test/gone`x\n````\n# Injected\n<script>alert(1)</script>\n[link](https://other.test)\n~~~'


def page_report(evidence):
    return {'url': 'https://example.test/', 'findings': [{
        'category': 'technical', 'severity': 'high', 'title': 'Missing title',
        'rule_id': 'technical.missing.title', 'evidence': evidence}]}


class TestPlanEvidenceHandoff(unittest.TestCase):
    def test_confirmed_failures_retain_status_and_url_without_promoting_uncertain_probes(self):
        samples = [{'url': 'https://example.test/gone', 'status': 404, 'error': None},
                   {'url': 'https://example.test/gated', 'status': 403, 'error': None},
                   {'url': 'https://example.test/timeout', 'status': 0, 'error': 'timeout'}]
        data = audit_report(errors=[], fetch_failures=0, sitemaps_attempted=1, sitemaps_fetched=1,
                            sample=samples, broken_sample=[samples[0], samples[2]])
        original = copy.deepcopy(data)
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            built = plan.build_plan(data, str(REPO))
        actions = {action['rule_id']: action for action in built['actions']}
        self.assertEqual({SOURCE, SAMPLE}, set(actions))
        self.assertIn('https://example.test/gone', actions[SOURCE]['evidence'])
        self.assertIn('"status": 404', actions[SOURCE]['evidence'])
        self.assertNotIn('gated', actions[SOURCE]['evidence'])
        self.assertNotIn('timeout', actions[SOURCE]['evidence'])
        self.assertNotEqual('safely_automatable', actions[SOURCE]['safety'])
        self.assertTrue(actions[SAMPLE]['manual_action'])
        self.assertEqual([], actions[SAMPLE]['likely_files'])
        self.assertEqual(original, data)

    def test_witness_display_cap_is_explicit_and_missing_urls_are_not_invented(self):
        samples = [{'url': 'https://example.test/gone' + str(i), 'status': 404, 'error': None} for i in range(7)]
        data = audit_report(errors=[], fetch_failures=0, sitemaps_attempted=1, sitemaps_fetched=1, sample=samples)
        action = next(a for a in plan.build_plan(data, str(REPO))['actions'] if a['rule_id'] == SOURCE)
        self.assertIn('first 5 of 7', action['evidence'])
        self.assertIn('gone4', action['evidence'])
        self.assertNotIn('gone5', action['evidence'])
        data['sitemap']['sample'] = [{'status': 404, 'url': {'unsupported': True}}]
        action = next(a for a in plan.build_plan(data, str(REPO))['actions'] if a['rule_id'] == SOURCE)
        self.assertIn('"url": null', action['evidence'])
        self.assertNotIn('unsupported', action['evidence'])

    def test_native_render_keeps_hostile_evidence_inside_one_literal_text_block(self):
        built = plan.build_plan(page_report(PAYLOAD), str(REPO))
        parsed = Parsed(render_report.render(plan.render_markdown(built)))
        blocks = [b for b in parsed.blocks if b['code_attrs'].get('class') == 'language-text']
        self.assertEqual([PAYLOAD + '\n'], [block['text'] for block in blocks])
        self.assertNotIn('script', parsed.tags)
        self.assertEqual(['code'], blocks[0]['children'])
        baseline = Parsed(render_report.render(plan.render_markdown(plan.build_plan(page_report(''), str(REPO)))))
        self.assertEqual(baseline.tags.count('a'), parsed.tags.count('a'))
        self.assertTrue(any(b['code_attrs'].get('class') == 'language-sh' for b in parsed.blocks))

    def test_preview_is_bounded_while_json_evidence_stays_complete(self):
        evidence = 'x' * 600 + 'END_OF_FULL_EVIDENCE'
        built = plan.build_plan(page_report(evidence), str(REPO))
        original = copy.deepcopy(built)
        text = plan.render_markdown(built)
        self.assertIn('Preview truncated at 600 characters', text)
        self.assertIn('x' * 600, text)
        self.assertNotIn('END_OF_FULL_EVIDENCE', text)
        self.assertEqual(evidence, json.loads(plan.render_json(built))['actions'][0]['evidence'])
        self.assertEqual(original, built)

    def test_empty_evidence_does_not_invent_a_receipt(self):
        for evidence in ('', None):
            built = plan.build_plan(page_report(evidence), str(REPO))
            self.assertNotIn('Reported evidence (preview', plan.render_markdown(built))

    def test_independent_commonmark_parser_keeps_evidence_literal(self):
        try:
            from markdown_it import MarkdownIt
        except ImportError:
            self.skipTest('optional markdown-it-py is unavailable')
        text = plan.render_markdown(plan.build_plan(page_report(PAYLOAD), str(REPO)))
        parsed = Parsed(MarkdownIt('commonmark', {'html': True}).render(text))
        blocks = [b for b in parsed.blocks if b['code_attrs'].get('class') == 'language-text']
        self.assertEqual([PAYLOAD + '\n'], [block['text'] for block in blocks])
        self.assertNotIn('script', parsed.tags)
        self.assertNotIn('a', parsed.tags)

    def test_mcp_handoff_retains_same_evidence_without_mutating_input(self):
        data = page_report(PAYLOAD)
        original = copy.deepcopy(data)
        built = mcp_server._plan(data, 'skills/seo-scan/tests/fixtures/planner/plain_html')
        self.assertEqual(PAYLOAD, built['actions'][0]['evidence'])
        self.assertIn(PAYLOAD, plan.render_markdown(built))
        self.assertEqual(original, data)


if __name__ == '__main__':
    unittest.main()
