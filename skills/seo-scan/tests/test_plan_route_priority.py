"""Page route conventions should not lose to unrelated alphabetical fallbacks."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan

CASES = {
    'nextjs': ('app/page.tsx', 'app/pricing/page.tsx', 'app/layout.tsx'),
    'astro': ('src/pages/index.astro', 'src/pages/pricing.astro', 'src/layouts/Layout.astro'),
    'nuxt': ('pages/index.vue', 'pages/pricing.vue', 'nuxt.config.ts'),
    'hugo': ('content/_index.md', 'content/pricing.md', 'layouts/partials/head.html'),
    'jekyll': ('index.md', 'pricing.md', '_includes/head.html'),
    'plain_html': ('index.html', 'pricing/index.html', 'index.html'),
}


def put(root, rel):
    path = root / rel; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('Fixture source', encoding='utf-8')
    return path


def candidates(root, framework, artifact, target='https://example.test/pricing', warnings=None):
    files = plan.inventory(root)['files']
    return plan.likely_files(root, files, framework, artifact, target, warnings)


class TestRoutePriority(unittest.TestCase):
    def test_existing_content_routes_rank_first_for_all_supported_frameworks(self):
        for framework, paths in CASES.items():
            with self.subTest(framework=framework), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                for path in paths: put(root, path)
                for artifact in ('content', 'headings', 'image_alt'):
                    result = candidates(root, framework, artifact)
                    self.assertEqual(paths[1], result[0]['path'])
                    self.assertTrue(result[0]['exists'])
                    self.assertIn('Existing route convention', result[0]['reason'])
                    self.assertIn('confirm source ownership', result[0]['reason'])

    def test_plain_html_head_prefers_route_while_framework_head_order_is_preserved(self):
        for framework, paths in CASES.items():
            with self.subTest(framework=framework), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                for path in paths: put(root, path)
                result = candidates(root, framework, 'title')
                self.assertEqual(paths[1] if framework in ('plain_html', 'hugo') else paths[2], result[0]['path'])

    def test_missing_routes_do_not_displace_existing_fallbacks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); put(root, 'index.html')
            for artifact in ('title', 'content', 'headings', 'image_alt'):
                result = candidates(root, 'plain_html', artifact)
                self.assertEqual('index.html', result[0]['path'])
                self.assertTrue(result[0]['exists'])
                self.assertTrue(any(not item['exists'] for item in result))

    def test_discovery_files_do_not_acquire_page_route_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); put(root, 'index.html'); put(root, 'pricing/index.html')
            with mock.patch.object(plan, '_route_candidates', side_effect=AssertionError('No page route for site files')):
                for artifact in ('robots_txt', 'sitemap', 'llms_txt'):
                    result = candidates(root, 'plain_html', artifact)
                    self.assertNotIn('pricing/index.html', [item['path'] for item in result])

    def test_unsafe_or_symlinked_route_does_not_become_preferred_owner(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp).resolve(); put(root, 'index.html'); target = put(Path(outside), 'owner.html')
            (root / 'pricing').mkdir()
            try: (root / 'pricing/index.html').symlink_to(target)
            except OSError: self.skipTest('symlinks unavailable')
            warnings = []
            result = candidates(root, 'plain_html', 'title', warnings=warnings)
            self.assertEqual('index.html', result[0]['path'])
            self.assertNotIn('pricing/index.html', [item['path'] for item in result])
            self.assertIn(plan.SOURCE_CANDIDATE_WARNING, warnings)
            result = candidates(root, 'plain_html', 'content', target='https://example.test/../outside', warnings=warnings)
            self.assertEqual('index.html', result[0]['path'])

    def test_offline_mcp_prioritizes_page_source_without_new_edit_authority(self):
        data = {'url': 'https://example.test/pricing', 'findings': [
            {'rule_id': 'technical.missing.title', 'category': 'technical', 'severity': 'high', 'title': 'Missing title'}]}
        original = copy.deepcopy(data)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); repo = root / 'source'
            owners = [put(repo, rel) for rel in ('index.html', 'pricing/index.html')]
            snapshots = [owner.read_bytes() for owner in owners]
            with mock.patch.object(Path, 'cwd', return_value=root), \
                    mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
                built = mcp_server._plan(data, 'source')
            self.assertEqual(snapshots, [owner.read_bytes() for owner in owners])
        action = built['actions'][0]
        self.assertEqual('pricing/index.html', action['likely_files'][0]['path'])
        self.assertEqual('review_required', action['safety'])
        self.assertNotIn('automation_eligibility', action)
        self.assertEqual(original, data)


if __name__ == '__main__':
    unittest.main()
