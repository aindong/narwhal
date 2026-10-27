"""Audit page owners follow the fetched destination; audit reruns retain the input."""
import copy
import json
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan
from lib.report import Report
from test_plan_route_priority import CASES, put

SITE = 'https://example.test/legacy/'
FINAL = 'https://example.test/en/'
VIEWPORT = 'technical.no.responsive.viewport.tag'


def report():
    page = Report(SITE, final_url=FINAL, fetched_status=200)
    page.meta['scan_scope'] = {'requested': ['technical'], 'completed': ['technical']}
    for rule, title in ((VIEWPORT, 'No responsive viewport tag'),
                        ('technical.missing.title', 'Missing title'),
                        ('technical.no.h1.heading', 'No H1 heading')):
        page.add('technical', 'high', title, rule_id=rule)
    payload = json.loads(page.to_json())
    return {'schema_version': payload['schema_version'], 'tool_version': payload['tool_version'],
            'site': SITE, 'homepage': payload, 'crawl': {}}


class TestAuditRedirectSource(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        for rel in ('index.html', 'legacy/index.html', 'en/index.html', 'robots.txt', 'sitemap.xml', 'llms.txt'):
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('Fixture source', encoding='utf-8')

    def test_page_actions_follow_final_url_without_changing_audit_verification(self):
        data = report()
        original = copy.deepcopy(data)
        built = plan.build_plan(data, str(self.root), report_source='audit-before.json')
        self.assertEqual(SITE, built['target'])
        self.assertEqual({'report': 'audit-before.json', 'report_kind': 'audit',
                          'report_schema_version': data['schema_version'],
                          'report_tool_version': data['tool_version'], 'planner': 'narwhal.plan'},
                         built['provenance'])
        for action in built['actions']:
            self.assertEqual('en/index.html', action['likely_files'][0]['path'])
            self.assertTrue(action['likely_files'][0]['exists'])
            self.assertIn('route convention', action['likely_files'][0]['reason'])
            commands = [shlex.split(step, comments=True) for step in action['verification']
                        if step.startswith('narwhal ')]
            self.assertEqual(['scan', 'scan', 'diff', 'audit', 'diff'], [c[1] for c in commands])
            self.assertEqual(SITE, commands[-2][-1])
            self.assertEqual(['audit-before.json', 'after.json'], commands[-1][-2:])
            self.assertEqual({'source': 'narwhal_finding', 'report': 'audit-before.json',
                              'report_schema_version': data['schema_version']}, action['provenance'])
        self.assertEqual(original, data)

    def test_redirected_content_route_is_used_across_all_framework_adapters(self):
        configs = {'nextjs': 'next.config.js', 'astro': 'astro.config.mjs',
                   'hugo': 'hugo.toml', 'jekyll': '_config.yml'}
        for framework, paths in CASES.items():
            with self.subTest(framework=framework), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                for rel in paths:
                    put(root, rel)
                if framework in configs:
                    put(root, configs[framework])
                data = report()
                data['homepage']['final_url'] = 'https://example.test/pricing'
                built = plan.build_plan(data, str(root))
                self.assertEqual(framework, built['framework']['name'])
                action = next(a for a in built['actions'] if a['artifact'] == 'headings')
                self.assertEqual(paths[1], action['likely_files'][0]['path'])
                self.assertEqual(SITE, built['target'])

    def test_recorded_page_url_and_legacy_audit_fallback_remain_usable(self):
        for final, url, expected in ((None, FINAL, 'en/index.html'),
                                     ('', FINAL, 'en/index.html'),
                                     (None, None, 'legacy/index.html'),
                                     (None, '', 'legacy/index.html')):
            with self.subTest(final=final, url=url):
                data = report()
                data['homepage'].update(final_url=final, url=url)
                built = plan.build_plan(data, str(self.root))
                self.assertEqual(expected, built['actions'][0]['likely_files'][0]['path'])

    def test_scan_destination_and_nonredirected_audit_keep_their_owners(self):
        data = report()
        for supplied in (data['homepage'], dict(data, site=FINAL)):
            built = plan.build_plan(supplied, str(self.root))
            self.assertEqual(FINAL, built['target'])
            self.assertEqual('en/index.html', built['actions'][0]['likely_files'][0]['path'])

    def test_bad_recorded_page_labels_still_withhold_automation_without_crashing(self):
        for label in ({'bad': 'label'}, [], False, 0, 'file:///tmp/en', 'https://example.test:bad/en/'):
            with self.subTest(label=label):
                data = report()
                data['homepage']['final_url'] = label
                built = plan.build_plan(data, str(self.root))
                action = next(a for a in built['actions'] if a['rule_id'] == VIEWPORT)
                self.assertFalse(action['automation_eligibility']['eligible'])
                self.assertIn('known_incomplete_source_evidence', action['automation_eligibility']['blockers'])

    def test_discovery_files_and_recurring_page_witnesses_keep_their_own_scope(self):
        data = report()
        for rule in ('technical.robots.txt.missing', 'technical.no.xml.sitemap', 'geo.no.llms.txt'):
            data['homepage']['findings'].append({'rule_id': rule, 'category': 'technical',
                                                'severity': 'medium', 'title': rule})
        data['crawl'] = {'recurring': [dict(data['homepage']['findings'][0], count=1,
            url_sample={'basis': 'recorded_crawl_rule_url_labels_v1', 'urls': [SITE],
                        'truncated': False, 'omitted': 0})]}
        built = plan.build_plan(data, str(self.root))
        for action in built['actions']:
            if action['artifact'] in ('robots_txt', 'sitemap', 'llms_txt'):
                self.assertNotIn('en/index.html', [owner['path'] for owner in action['likely_files']])
        action = next(a for a in built['actions'] if a['rule_id'] == VIEWPORT)
        self.assertEqual({'legacy/index.html', 'en/index.html'}, {o['path'] for o in action['likely_files']})

    def test_offline_mcp_keeps_the_same_destination_owners_and_preserves_all_inputs(self):
        data = report()
        original = copy.deepcopy(data)
        sources = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with mock.patch.object(Path, 'cwd', return_value=self.root.parent), \
                mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            received = mcp_server._plan(data, self.root.name)
        for action in received['actions']:
            self.assertEqual('en/index.html', action['likely_files'][0]['path'])
        self.assertEqual(SITE, received['target'])
        self.assertEqual(original, data)
        self.assertEqual(sources, {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})


if __name__ == '__main__':
    unittest.main()
