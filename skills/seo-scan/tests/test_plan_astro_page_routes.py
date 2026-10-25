"""Astro page source candidates, not proof of integration or generated routing.

https://docs.astro.build/en/basics/astro-pages/
"""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan


class TestAstroPageRoutes(unittest.TestCase):
    def test_page_formats_precede_unrelated_fallbacks_at_root_and_nested_routes(self):
        for extension in ('astro', 'md', 'mdx', 'html'):
            for stem, target in (('src/pages/index', 'https://example.test/'),
                                 ('src/pages/guides/zz-widget', 'https://example.test/guides/zz-widget'),
                                 ('src/pages/guides/zz-widget/index', 'https://example.test/guides/zz-widget/')):
                route = stem + '.' + extension
                with self.subTest(route=route), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp).resolve()
                    files = ['src/layouts/Layout.astro'] + ['content/aaa-{:02}.md'.format(i) for i in range(20)] + [route]
                    for rel in files:
                        path = root / rel
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text('Fixture source', encoding='utf-8')
                    for artifact in ('content', 'headings', 'image_alt'):
                        owners = plan.likely_files(root, files, 'astro', artifact, target)
                        self.assertEqual(route, owners[0]['path'])
                        self.assertTrue(owners[0]['exists'])
                        self.assertTrue(owners[0]['reason'].startswith('Existing route convention;'))
                    head = plan.likely_files(root, files, 'astro', 'title', target)
                    self.assertEqual('src/layouts/Layout.astro', head[0]['path'])
                    self.assertIn(route, [owner['path'] for owner in head])

    def test_alternative_formats_require_inventory_evidence_and_exclude_endpoints(self):
        target = 'https://example.test/guides/widget'
        expected = ['src/pages/guides/widget.astro', 'src/pages/guides/widget/index.astro']
        self.assertEqual(expected, plan._route_candidates(target, 'astro'))
        self.assertEqual(expected, plan._route_candidates(target, 'astro', files={
            'src/pages/guides/widget.js', 'src/pages/guides/widget.ts', 'src/content/guides/widget.mdx'}))
        for target in ('', '/', 'file://example.test/', 'https://example.test///'):
            with self.subTest(target=target):
                self.assertEqual([], plan._route_candidates(target, 'astro', files={'src/pages/index.md'}))

    def test_root_query_http_and_no_slash_forms_locate_only_observed_homepage(self):
        for target in ('https://example.test?review=1', 'http://example.test/'):
            with self.subTest(target=target):
                self.assertEqual(['src/pages/index.mdx'], plan._route_candidates(
                    target, 'astro', files={'src/pages/index.mdx'}))
                self.assertEqual([], plan._route_candidates(target, 'astro'))

    def test_symlinked_markdown_route_does_not_become_an_owner(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp).resolve()
            (root / 'src/pages').mkdir(parents=True)
            target = Path(outside) / 'widget.md'
            target.write_text('Outside fixture', encoding='utf-8')
            try:
                (root / 'src/pages/widget.md').symlink_to(target)
            except OSError:
                self.skipTest('symlinks unavailable')
            warnings = []
            owners = plan.likely_files(root, ['src/pages/widget.md'], 'astro', 'content',
                                       'https://example.test/widget', warnings)
            self.assertNotIn('src/pages/widget.md', [owner['path'] for owner in owners])
            self.assertIn(plan.SOURCE_CANDIDATE_WARNING, warnings)
            self.assertEqual('Outside fixture', target.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
