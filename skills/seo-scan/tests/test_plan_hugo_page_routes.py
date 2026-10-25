"""Observed Hugo branch bundles are page-owner candidates, not route proof.

https://gohugo.io/content-management/page-bundles/
"""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan


class TestHugoPageRoutes(unittest.TestCase):
    def test_home_branch_leaf_and_plain_sources_precede_capped_fallbacks(self):
        cases = [('content/_index.md', 'https://example.test/'),
                 ('content/zz-guides/_index.md', 'https://example.test/zz-guides/'),
                 ('content/zz-guides/nested/_index.md', 'https://example.test/zz-guides/nested'),
                 ('content/zz-guides/widget/index.md', 'https://example.test/zz-guides/widget/'),
                 ('content/zz-guides/widget.md', 'https://example.test/zz-guides/widget')]
        for route, target in cases:
            with self.subTest(route=route), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                files = ['layouts/partials/head.html'] + ['content/aaa-{:02}.md'.format(i) for i in range(20)] + [route]
                for rel in files:
                    path = root / rel
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text('Fixture source', encoding='utf-8')
                for artifact in ('content', 'headings', 'image_alt'):
                    owners = plan.likely_files(root, files, 'hugo', artifact, target)
                    self.assertEqual(route, owners[0]['path'])
                    self.assertTrue(owners[0]['exists'])
                    self.assertTrue(owners[0]['reason'].startswith('Existing route convention;'))
                head = plan.likely_files(root, files, 'hugo', 'title', target)
                self.assertIn(route, [owner['path'] for owner in head])
                self.assertIn('layouts/partials/head.html', [owner['path'] for owner in head])

    def test_branch_candidates_require_inventory_and_do_not_extend_jekyll(self):
        target = 'https://example.test/guides/widget'
        self.assertEqual(['content/guides/widget.md', 'content/guides/widget/index.md', 'widget.md'],
                         plan._route_candidates(target, 'hugo'))
        self.assertEqual(['guides/widget.md', 'guides/widget/index.md', 'widget.md'],
                         plan._route_candidates(target, 'jekyll', files={'guides/widget/_index.md'}))
        for target in ('', '/', 'file://example.test/', 'https://example.test///'):
            with self.subTest(target=target):
                self.assertEqual([], plan._route_candidates(target, 'hugo', files={'content/_index.md'}))
        for target in ('https://example.test?review=1', 'http://example.test/'):
            with self.subTest(target=target):
                self.assertEqual(['content/_index.md'], plan._route_candidates(
                    target, 'hugo', files={'content/_index.md'}))
                self.assertEqual([], plan._route_candidates(target, 'hugo'))

    def test_symlinked_branch_source_is_omitted_with_warning(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp).resolve()
            (root / 'content/guides').mkdir(parents=True)
            target = Path(outside) / '_index.md'
            target.write_text('Outside fixture', encoding='utf-8')
            try:
                (root / 'content/guides/_index.md').symlink_to(target)
            except OSError:
                self.skipTest('symlinks unavailable')
            warnings = []
            owners = plan.likely_files(root, ['content/guides/_index.md'], 'hugo', 'headings',
                                       'https://example.test/guides/', warnings)
            self.assertNotIn('content/guides/_index.md', [owner['path'] for owner in owners])
            self.assertIn(plan.SOURCE_CANDIDATE_WARNING, warnings)
            self.assertEqual('Outside fixture', target.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
