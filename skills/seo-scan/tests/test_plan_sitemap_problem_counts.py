"""Recorded source-problem counts need numeric evidence, not truthiness."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan
from test_plan_sitemap_verification import report, SOURCE, NOTES


class TestSitemapProblemCounts(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        (self.root / 'index.html').write_text('<html></html>', encoding='utf-8')
        (self.root / 'sitemap.xml').write_text(
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            '<url><loc>https://example.test/</loc></url></urlset>', encoding='utf-8')

    def check(self, changes, expected):
        data = report(errors=[], fetch_failures=0, sitemaps_attempted=1,
                      sitemaps_fetched=1, **changes)
        before = copy.deepcopy(data)
        source = {p.name: p.read_bytes() for p in self.root.iterdir()}
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')), \
                mock.patch('socket.socket.connect', side_effect=AssertionError('No network')):
            built = plan.build_plan(data, str(self.root), report_source='<mcp-object>')
            with mock.patch.object(Path, 'cwd', return_value=self.root.parent):
                self.assertEqual(built, mcp_server._plan(data, self.root.name))
        self.assertEqual(before, data)
        self.assertEqual(source, {p.name: p.read_bytes() for p in self.root.iterdir()})
        actions = {a['rule_id']: a for a in built['actions']}
        self.assertEqual(expected, set(actions))
        if NOTES in actions:
            action = actions[NOTES]
            self.assertEqual(('technical', 'low', 'site'),
                             tuple(action[key] for key in ('category', 'severity', 'scope')))
            self.assertEqual('manual_external', action['safety'])
            self.assertTrue(action['manual_action'])
            self.assertFalse(action['requires_deploy'])
            self.assertEqual([], action['likely_files'])
            self.assertIn('count', action['evidence'].lower())
            self.assertNotIn('secret-token', action['evidence'])
            self.assertFalse(any(NOTES in group['rule_ids'] for group in built['groups']))
        if SOURCE in actions:
            self.assertEqual(('technical', 'medium', 'site'),
                             tuple(actions[SOURCE][key] for key in ('category', 'severity', 'scope')))
            self.assertEqual('deploy_verification', actions[SOURCE]['safety'])
            self.assertTrue(actions[SOURCE]['requires_deploy'])
            self.assertFalse(actions[SOURCE]['manual_action'])
            self.assertTrue(any(o['path'] == 'sitemap.xml' and o['exists'] is True
                                for o in actions[SOURCE]['likely_files']))

    def test_zero_and_unrecorded_counts_do_not_create_source_problems(self):
        self.check({}, set())
        self.check({'problems': {'not-absolute': 0, 'cross-host': 0}, 'invalid_lastmod': 0}, set())
        data = report(errors=[], fetch_failures=0, sitemaps_attempted=1, sitemaps_fetched=1)
        data['sitemap'].pop('problems')
        data['sitemap'].pop('invalid_lastmod')
        self.assertEqual([], plan.build_plan(data, str(self.root))['actions'])

    def test_malformed_counts_require_verification_instead_of_source_edits(self):
        for value in (None, False, True, -1, 0.0, 1.0, '0', '2', 'secret-token', [], {}):
            for field in ('invalid_lastmod', 'problem-value'):
                with self.subTest(field=field, value=value):
                    change = ({'invalid_lastmod': value} if field == 'invalid_lastmod'
                              else {'problems': {'not-absolute': value}})
                    self.check(change, {NOTES})
        for value in (None, False, 0, 'secret-token', []):
            with self.subTest(problems=value):
                self.check({'problems': value}, {NOTES})

    def test_confirmed_positive_counts_and_failed_samples_survive_other_unknown_counts(self):
        for changes, expected in (
                ({'problems': {'not-absolute': 1, 'cross-host': 0}}, {SOURCE}),
                ({'invalid_lastmod': 2}, {SOURCE}),
                ({'problems': {'not-absolute': 1, 'future': 'secret-token'}}, {SOURCE, NOTES}),
                ({'problems': [], 'invalid_lastmod': 2}, {SOURCE, NOTES}),
                ({'problems': {'cross-host': 1}, 'invalid_lastmod': -1}, {SOURCE, NOTES}),
                ({'invalid_lastmod': '0', 'sample': [
                    {'status': 404, 'error': None, 'url': 'https://example.test/gone'}]}, {SOURCE, NOTES})):
            with self.subTest(changes=changes):
                self.check(changes, expected)


if __name__ == '__main__':
    unittest.main()
