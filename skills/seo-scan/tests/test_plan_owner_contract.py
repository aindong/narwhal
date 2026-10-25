"""Bounded, distinct source-owner evidence across planner conventions."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan


class TestOwnerContract(unittest.TestCase):
    def test_candidates_are_bounded_distinct_and_have_valid_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            files = ['index.html', 'app/layout.tsx', 'app/page.tsx', 'pages/index.js']
            files += ['components/Layout{:02}.tsx'.format(i) for i in range(20)]
            for rel in files:
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('Fixture source', encoding='utf-8')
            for framework in plan.FRAMEWORK_CANDIDATES:
                for artifact in sorted(plan.HEAD_ARTIFACTS | {'content', 'headings', 'image_alt',
                                                             'robots_txt', 'sitemap', 'llms_txt'}):
                    with self.subTest(framework=framework, artifact=artifact):
                        owners = plan.likely_files(root, files, framework, artifact, 'https://example.test/')
                        paths = [owner['path'] for owner in owners]
                        self.assertLessEqual(len(paths), 8)
                        self.assertEqual(len(paths), len(set(paths)))
                        for owner in owners:
                            self.assertIs(type(owner['exists']), bool)
                            self.assertEqual(owner['exists'], owner['path'] in files)
                            self.assertGreaterEqual(owner['confidence'], 0)
                            self.assertLessEqual(owner['confidence'], 1)
                            self.assertTrue(owner['reason'])

    def test_manual_or_unknown_artifacts_never_assign_a_source_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / 'index.html').write_text('Fixture', encoding='utf-8')
            for framework in (*plan.FRAMEWORK_CANDIDATES, 'unrecognized_framework'):
                for artifact in ('server_config', 'unknown'):
                    with self.subTest(framework=framework, artifact=artifact):
                        self.assertEqual([], plan.likely_files(root, ['index.html'], framework,
                                                               artifact, 'https://example.test/'))

    def test_generic_content_source_formats_remain_discoverable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            for extension in ('html', 'md', 'mdx', 'tsx', 'jsx', 'vue', 'astro'):
                rel = 'custom.' + extension.upper()
                (root / rel).write_text('Fixture', encoding='utf-8')
                for artifact in ('content', 'headings', 'image_alt'):
                    with self.subTest(extension=extension, artifact=artifact):
                        owners = plan.likely_files(root, [rel], 'unknown', artifact, 'https://example.test/elsewhere')
                        self.assertEqual(rel, owners[0]['path'])
                        self.assertTrue(owners[0]['exists'])

    def test_generic_head_conventions_and_unknown_framework_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            for rel in ('CustomLAYOUT.tsx', 'SpecialHEAD.jsx', '_DOCUMENT.js', 'APP.VUE'):
                (root / rel).write_text('Fixture', encoding='utf-8')
                with self.subTest(path=rel):
                    owners = plan.likely_files(root, [rel], 'unrecognized_framework', 'title', 'https://example.test/')
                    self.assertEqual(rel, owners[0]['path'])
                    self.assertTrue(owners[0]['exists'])


if __name__ == '__main__':
    unittest.main()
