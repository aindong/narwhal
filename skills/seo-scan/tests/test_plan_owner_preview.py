"""Markdown owner previews expose inventory evidence without changing plans."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan


class TestOwnerPreview(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        (self.root / 'package.json').write_text('{"dependencies":{"next":"*"}}', encoding='utf-8')
        (self.root / 'app').mkdir()
        (self.root / 'app/layout.tsx').write_text('Fixture source', encoding='utf-8')
        self.report = {'url': 'https://example.test/pricing', 'findings': [
            {'rule_id': 'technical.missing.title', 'category': 'technical',
             'severity': 'high', 'title': 'Missing title'}]}

    def owner_line(self, built):
        return next(line for line in plan.render_markdown(built).splitlines()
                    if line.startswith('- **Likely owner:**'))

    def test_observed_and_unobserved_paths_are_labeled_without_mutating_json(self):
        built = plan.build_plan(self.report, str(self.root))
        original = copy.deepcopy(built)
        owners = built['actions'][0]['likely_files']
        line = self.owner_line(built)
        self.assertIn('`app/layout.tsx` (in file inventory)', line)
        self.assertIn('`app/layout.jsx` (not in file inventory)', line)
        self.assertTrue(any(owner['exists'] for owner in owners[:3]))
        self.assertTrue(any(not owner['exists'] for owner in owners[:3]))
        self.assertEqual(original, built)

    def test_capped_inventory_does_not_call_an_existing_unobserved_file_missing(self):
        built = plan.build_plan(self.report, str(self.root), max_files=1)
        self.assertTrue(built['coverage']['file_inventory_capped'])
        owner = next(owner for owner in built['actions'][0]['likely_files'] if owner['path'] == 'app/layout.tsx')
        self.assertTrue((self.root / owner['path']).is_file())
        self.assertFalse(owner['exists'])
        line = self.owner_line(built)
        self.assertIn('`app/layout.tsx` (not in file inventory)', line)
        self.assertNotIn('missing', line.lower())

    def test_preview_discloses_omitted_candidates_and_keeps_full_json(self):
        for rel in ('app/layout.jsx', 'src/app/layout.tsx', 'src/app/layout.jsx', 'pages/_document.tsx'):
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('Fixture source', encoding='utf-8')
        built = plan.build_plan(self.report, str(self.root))
        owners = built['actions'][0]['likely_files']
        self.assertGreater(len(owners), 3)
        line = self.owner_line(built)
        self.assertIn('additional candidates in JSON: {}'.format(len(owners) - 3), line)
        for owner in owners[3:]:
            self.assertNotIn('`' + owner['path'] + '`', line)
        self.assertEqual(owners, json.loads(plan.render_json(built))['actions'][0]['likely_files'])

    def test_ownerless_and_verification_only_actions_keep_their_distinction(self):
        for rule, title, expected in (
                ('technical.unknown.observation', 'Unmapped observation', 'owner not located'),
                ('technical.sitemap.sample.unverified', 'Sitemap sample unverified', 'not assigned (verification only)')):
            self.report['findings'][0].update(rule_id=rule, title=title)
            built = plan.build_plan(self.report, str(self.root))
            with self.subTest(rule=rule):
                line = self.owner_line(built)
                self.assertEqual('- **Likely owner:** ' + expected, line)

    def test_single_omitted_metadata_candidate_is_disclosed_at_the_boundary(self):
        self.report['findings'][0].update(rule_id='technical.no.robots.txt.found', title='No robots.txt found')
        built = plan.build_plan(self.report, str(self.root))
        self.assertEqual(3, len(built['actions'][0]['likely_files']))
        self.assertNotIn('additional candidates', self.owner_line(built))
        (self.root / 'app/robots.js').write_text('export default function robots() { return {} }', encoding='utf-8')
        built = plan.build_plan(self.report, str(self.root))
        self.assertEqual(4, len(built['actions'][0]['likely_files']))
        self.assertIn('additional candidates in JSON: 1', self.owner_line(built))


if __name__ == '__main__':
    unittest.main()
