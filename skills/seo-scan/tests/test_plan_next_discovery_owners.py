"""Next.js discovery metadata owners retain deployment-verification authority."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan


class TestNextDiscoveryOwners(unittest.TestCase):
    def test_generated_and_static_metadata_sources_are_observed_owners(self):
        for prefix in ('app', 'src/app'):
            for artifact, stem, static in (('robots_txt', 'robots', 'txt'), ('sitemap', 'sitemap', 'xml')):
                for extension in ('ts', 'js', static):
                    rel = '{}/{}.{}'.format(prefix, stem, extension)
                    with self.subTest(path=rel), tempfile.TemporaryDirectory() as tmp:
                        root = Path(tmp).resolve()
                        owner = root / rel
                        owner.parent.mkdir(parents=True)
                        owner.write_text('Fixture source', encoding='utf-8')
                        with mock.patch.object(plan, '_route_candidates', side_effect=AssertionError('Not a page route')):
                            owners = plan.likely_files(root, [rel], 'nextjs', artifact, 'https://example.test/pricing')
                        self.assertEqual(rel, owners[0]['path'])
                        self.assertTrue(owners[0]['exists'])

    def test_additional_spellings_require_inventory_and_do_not_extend_other_frameworks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / 'app').mkdir()
            (root / 'app/robots.js').write_text('Fixture source', encoding='utf-8')
            for artifact in ('robots_txt', 'sitemap'):
                with self.subTest(artifact=artifact):
                    owners = plan.likely_files(root, [], 'nextjs', artifact, 'https://example.test/')
                    self.assertEqual(set(plan.FRAMEWORK_CANDIDATES['nextjs'][artifact]), {o['path'] for o in owners})
            owners = plan.likely_files(root, ['app/robots.js'], 'astro', 'robots_txt', 'https://example.test/')
            self.assertNotIn('app/robots.js', [o['path'] for o in owners])

    def test_mcp_plan_is_read_only_and_requires_deployed_resource_verification(self):
        report = {'url': 'https://example.test/', 'findings': [
            {'rule_id': 'technical.no.robots.txt.found', 'category': 'technical', 'severity': 'medium', 'title': 'No robots.txt found'},
            {'rule_id': 'technical.no.xml.sitemap.found', 'category': 'technical', 'severity': 'medium', 'title': 'No XML sitemap found'}]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            repo = root / 'site'
            (repo / 'app').mkdir(parents=True)
            (repo / 'package.json').write_text('{"dependencies":{"next":"*"}}', encoding='utf-8')
            for name in ('robots', 'sitemap'):
                (repo / 'app' / (name + '.js')).write_text('export default function Metadata() { return {} }', encoding='utf-8')
            before = {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob('*') if p.is_file()}
            with mock.patch.object(Path, 'cwd', return_value=root):
                built = mcp_server._plan(report, 'site')
            self.assertEqual(before, {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob('*') if p.is_file()})
        for action in built['actions']:
            expected = 'app/robots.js' if action['artifact'] == 'robots_txt' else 'app/sitemap.js'
            self.assertEqual(expected, action['likely_files'][0]['path'])
            self.assertEqual('deploy_verification', action['safety'])
            self.assertTrue(action['requires_deploy'])
            self.assertNotIn('automation_eligibility', action)
            self.assertTrue(any('after deploy' in step for step in action['verification']))

    def test_symlinked_generator_does_not_become_an_owner(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp).resolve()
            (root / 'app').mkdir()
            target = Path(outside) / 'robots.js'
            target.write_text('Outside fixture', encoding='utf-8')
            try:
                (root / 'app/robots.js').symlink_to(target)
            except OSError:
                self.skipTest('symlinks unavailable')
            warnings = []
            owners = plan.likely_files(root, ['app/robots.js'], 'nextjs', 'robots_txt',
                                       'https://example.test/', warnings)
            self.assertNotIn('app/robots.js', [o['path'] for o in owners])
            self.assertIn(plan.SOURCE_CANDIDATE_WARNING, warnings)


if __name__ == '__main__':
    unittest.main()
