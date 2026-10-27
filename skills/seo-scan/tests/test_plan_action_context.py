"""Markdown action context must retain normalized scope and count without inventing totals."""
import copy
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan
import render_report
from test_plan_crawl_page_owners import audit_data, BASE, RULE


class TestPlanActionContext(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.workspace = Path(folder.name).resolve()
        self.repo = self.workspace / 'site'
        for rel in ['index.html'] + ['page-{}/index.html'.format(i) for i in range(7)]:
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('Fixture source', encoding='utf-8')
        self.data = audit_data([BASE + 'page-{}/'.format(i) for i in range(7)])

    def test_native_site_count_survives_bounded_url_and_owner_previews(self):
        built = plan.build_plan(self.data, str(self.repo))
        action = next(a for a in built['actions'] if a['rule_id'] == RULE)
        self.assertEqual(('site', 7), (action['scope'], action['occurrences']))
        self.assertEqual(5, len(action['likely_files']))
        self.assertIn('- **Plan scope:** `site` · **Occurrences:** 7', plan.render_markdown(built))

    def test_scope_hints_and_count_defaults_are_labeled_as_plan_values(self):
        for scope in ('page', 'site', 'external'):
            for field in ('count', 'occurrences', None):
                with self.subTest(scope=scope, field=field):
                    row = {'rule_id': 'technical.missing.title', 'category': 'technical',
                           'severity': 'high', 'title': 'Missing title', 'scope': scope}
                    if field:
                        row[field] = 4
                    built = plan.build_plan({'url': BASE, 'findings': [row]}, str(self.repo))
                    text = plan.render_markdown(built)
                    self.assertIn('- **Plan scope:** `' + scope + '` · **Occurrences:** ' + ('4' if field else '1'), text)
                    self.assertIn('maximum supplied count', text)
                    self.assertIn('default to 1', text)
                    self.assertIn('not distinct affected-page totals', text)
        row = {'rule_id': 'technical.missing.title', 'category': 'technical',
               'severity': 'high', 'title': 'Missing title'}
        built = plan.build_plan({'url': BASE, 'findings': [row]}, str(self.repo))
        self.assertIn('- **Plan scope:** `page` · **Occurrences:** 1', plan.render_markdown(built))

    def test_repeated_observations_show_maximum_count_and_keep_selection_note(self):
        high = {'rule_id': RULE, 'category': 'technical', 'severity': 'high',
                'title': 'No H1 heading', 'occurrences': 3}
        low = dict(high, severity='low', occurrences=8, scope='site')
        for rows in ([high, low], [low, high]):
            built = plan.build_plan({'url': BASE, 'findings': rows}, str(self.repo))
            action = built['actions'][0]
            self.assertEqual(2, action['observation_selection']['normalized_observations'])
            text = plan.render_markdown(built)
            self.assertIn('- **Plan scope:** `site` · **Occurrences:** 8', text)
            self.assertIn('2 normalized observations', text)

    def test_schema_verification_retains_specific_scope_beside_plan_context(self):
        for scope, label in (('page', 'Page report'), ('site', 'Site sample/rollup'), ('external', 'External')):
            with self.subTest(scope=scope):
                data = {'url': BASE, 'findings': [{'rule_id': 'schema.extraction.unverified',
                        'category': 'schema', 'severity': 'low', 'title': 'Verify extraction',
                        'scope': scope, 'occurrences': 6}]}
                built = plan.build_plan(data, str(self.repo))
                text = plan.render_markdown(built)
                self.assertIn('- **Plan scope:** `' + scope + '` · **Occurrences:** 6', text)
                self.assertIn('- **Verification scope:** ' + label, text)
                self.assertTrue(built['actions'][0]['manual_action'])

    def test_html_export_keeps_the_scope_and_nondefault_count_visible(self):
        parts = []

        class Text(HTMLParser):
            def handle_data(self, data):
                parts.append(data)

        built = plan.build_plan(self.data, str(self.repo))
        parser = Text()
        parser.feed(render_report.render(plan.render_markdown(built)))
        self.assertIn('Plan scope: site · Occurrences: 7', ''.join(parts))

    def test_markdown_json_and_offline_mcp_agree_without_changing_inputs(self):
        original = copy.deepcopy(self.data)
        baseline = self.workspace / 'audit-before.json'
        baseline.write_text(json.dumps(self.data), encoding='utf-8')
        saved = baseline.read_bytes()
        sources = {p: p.read_bytes() for p in self.repo.rglob('*') if p.is_file()}
        with mock.patch.object(Path, 'cwd', return_value=self.workspace), \
                mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            received = mcp_server._plan(self.data, 'site')
        before = copy.deepcopy(received)
        action = next(a for a in received['actions'] if a['rule_id'] == RULE)
        self.assertEqual(('site', 7), (action['scope'], action['occurrences']))
        self.assertIn('- **Plan scope:** `site` · **Occurrences:** 7', plan.render_markdown(received))
        self.assertEqual(before, json.loads(plan.render_json(received)))
        self.assertEqual(before, received)
        self.assertEqual(original, self.data)
        self.assertEqual(saved, baseline.read_bytes())
        self.assertEqual(sources, {p: p.read_bytes() for p in self.repo.rglob('*') if p.is_file()})


if __name__ == '__main__':
    unittest.main()
