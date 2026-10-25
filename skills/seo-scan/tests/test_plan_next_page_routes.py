"""Next.js page candidates cover default extensions and directory indexes.

Conventions: https://nextjs.org/docs/pages/api-reference/config/next-config-js/pageExtensions
"""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan


class TestNextPageRoutes(unittest.TestCase):
    def test_existing_homepage_is_preferred_over_unrelated_fallbacks(self):
        for extension in ('tsx', 'ts', 'jsx', 'js'):
            for stem in ('app/page', 'src/app/page', 'pages/index', 'src/pages/index'):
                route = stem + '.' + extension
                with self.subTest(route=route), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp).resolve()
                    paths = ['app/aaa/page.tsx', 'pages/aaa.tsx', route]
                    for rel in paths:
                        path = root / rel
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text('Fixture source', encoding='utf-8')
                    for target in ('https://example.test/', 'https://example.test?review=1'):
                        for artifact in ('content', 'headings', 'image_alt'):
                            owners = plan.likely_files(root, paths, 'nextjs', artifact, target)
                            self.assertEqual(route, owners[0]['path'])
                            self.assertTrue(owners[0]['exists'])
                            self.assertTrue(all(0 <= owner['confidence'] <= 1 for owner in owners))

    def test_missing_or_non_web_target_does_not_imply_a_homepage(self):
        for target in ('', '/', 'file://example.test/', 'https://example.test///'):
            with self.subTest(target=target):
                self.assertEqual([], plan._route_candidates(target, 'nextjs', files={'app/page.js'}))

    def test_absent_alternative_spellings_do_not_expand_creation_suggestions(self):
        routes = plan._route_candidates('https://example.test/pricing', 'nextjs')
        self.assertEqual(['src/app/pricing/page.tsx', 'app/pricing/page.tsx',
                          'src/pages/pricing.tsx', 'pages/pricing.tsx'], routes)

    def test_existing_nested_page_is_preferred_over_unrelated_fallbacks(self):
        for extension in ('tsx', 'ts', 'jsx', 'js'):
            for stem in ('app/pricing/page', 'src/app/pricing/page',
                         'pages/pricing', 'src/pages/pricing',
                         'pages/pricing/index', 'src/pages/pricing/index'):
                route = stem + '.' + extension
                with self.subTest(route=route), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp).resolve()
                    paths = ['app/page.tsx', 'app/layout.tsx', 'pages/aaa.tsx', route]
                    for rel in paths:
                        path = root / rel
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text('Fixture source', encoding='utf-8')
                    for artifact in ('content', 'headings', 'image_alt'):
                        owners = plan.likely_files(root, paths, 'nextjs', artifact, 'https://example.test/pricing')
                        self.assertEqual(route, owners[0]['path'])
                        self.assertTrue(owners[0]['exists'])
                        self.assertIn('confirm source ownership', owners[0]['reason'])
                    head = plan.likely_files(root, paths, 'nextjs', 'title', 'https://example.test/pricing')
                    self.assertIn(route, [owner['path'] for owner in head])
                    self.assertEqual('app/layout.tsx', head[0]['path'])

    def test_mcp_plan_keeps_javascript_page_advisory_and_read_only(self):
        report = {'url': 'https://example.test/pricing', 'findings': [
            {'rule_id': 'technical.h1.missing', 'category': 'technical',
             'severity': 'high', 'title': 'Missing H1'}]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            repo = root / 'site'
            (repo / 'pages/pricing').mkdir(parents=True)
            (repo / 'package.json').write_text('{"dependencies":{"next":"16.0.0"}}', encoding='utf-8')
            owner = repo / 'pages/pricing/index.js'
            owner.write_text('export default function Page() { return null }', encoding='utf-8')
            before = {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob('*') if p.is_file()}
            with mock.patch.object(Path, 'cwd', return_value=root), \
                    mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
                built = mcp_server._plan(report, 'site')
            self.assertEqual(before, {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob('*') if p.is_file()})
        action = built['actions'][0]
        self.assertEqual('pages/pricing/index.js', action['likely_files'][0]['path'])
        self.assertEqual('review_required', action['safety'])
        self.assertNotIn('automation_eligibility', action)

    def test_observed_javascript_symlink_cannot_become_an_owner(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp).resolve()
            (root / 'pages/pricing').mkdir(parents=True)
            (root / 'app').mkdir()
            (root / 'app/page.tsx').write_text('Home fixture', encoding='utf-8')
            target = Path(outside) / 'index.js'
            target.write_text('Outside fixture', encoding='utf-8')
            try:
                (root / 'pages/pricing/index.js').symlink_to(target)
            except OSError:
                self.skipTest('symlinks unavailable')
            warnings = []
            owners = plan.likely_files(root, ['pages/pricing/index.js', 'app/page.tsx'],
                                       'nextjs', 'headings', 'https://example.test/pricing', warnings)
            self.assertEqual('app/page.tsx', owners[0]['path'])
            self.assertNotIn('pages/pricing/index.js', [owner['path'] for owner in owners])
            self.assertIn(plan.SOURCE_CANDIDATE_WARNING, warnings)
            self.assertEqual('Outside fixture', target.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
