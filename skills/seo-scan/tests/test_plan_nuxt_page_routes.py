"""Observed Nuxt page candidates for current and legacy directory layouts.

https://github.com/nuxt/nuxt/blob/main/docs/1.getting-started/07.routing.md
"""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan


class TestNuxtPageRoutes(unittest.TestCase):
    def test_current_and_legacy_pages_precede_unrelated_capped_fallbacks(self):
        for prefix in ('app/pages', 'pages'):
            for suffix, target in (('index.vue', 'https://example.test/'),
                                   ('guides/zz-widget.vue', 'https://example.test/guides/zz-widget'),
                                   ('guides/zz-widget/index.vue', 'https://example.test/guides/zz-widget/')):
                route = prefix + '/' + suffix
                with self.subTest(route=route), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp).resolve()
                    files = ['nuxt.config.ts'] + ['components/aaa-{:02}.vue'.format(i) for i in range(20)] + [route]
                    for rel in files:
                        path = root / rel
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text('Fixture source', encoding='utf-8')
                    for artifact in ('content', 'headings', 'image_alt'):
                        owners = plan.likely_files(root, files, 'nuxt', artifact, target)
                        self.assertEqual(route, owners[0]['path'])
                        self.assertTrue(owners[0]['exists'])
                        self.assertTrue(owners[0]['reason'].startswith('Existing route convention;'))
                    head = plan.likely_files(root, files, 'nuxt', 'title', target)
                    self.assertEqual('nuxt.config.ts', head[0]['path'])
                    self.assertIn(route, [owner['path'] for owner in head])

    def test_new_locations_require_inventory_and_invalid_targets_do_not_imply_homepage(self):
        self.assertEqual(['pages/widget.vue', 'pages/widget/index.vue'],
                         plan._route_candidates('https://example.test/widget', 'nuxt'))
        for target in ('', '/', 'file://example.test/', 'https://example.test///'):
            with self.subTest(target=target):
                self.assertEqual([], plan._route_candidates(target, 'nuxt', files={'app/pages/index.vue'}))
        for target in ('https://example.test?review=1', 'http://example.test/'):
            with self.subTest(target=target):
                self.assertEqual(['app/pages/index.vue'], plan._route_candidates(
                    target, 'nuxt', files={'app/pages/index.vue'}))
                self.assertEqual([], plan._route_candidates(target, 'nuxt'))

    def test_symlinked_current_page_is_omitted_with_warning(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp).resolve()
            (root / 'app/pages').mkdir(parents=True)
            target = Path(outside) / 'widget.vue'
            target.write_text('Outside fixture', encoding='utf-8')
            try:
                (root / 'app/pages/widget.vue').symlink_to(target)
            except OSError:
                self.skipTest('symlinks unavailable')
            warnings = []
            owners = plan.likely_files(root, ['app/pages/widget.vue'], 'nuxt', 'headings',
                                       'https://example.test/widget', warnings)
            self.assertNotIn('app/pages/widget.vue', [owner['path'] for owner in owners])
            self.assertIn(plan.SOURCE_CANDIDATE_WARNING, warnings)
            self.assertEqual('Outside fixture', target.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
