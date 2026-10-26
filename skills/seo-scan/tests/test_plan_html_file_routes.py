"""Explicit HTML URL paths retain their literal source-file convention."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan
from test_plan_route_priority import put, candidates


class TestHtmlFileRoutes(unittest.TestCase):
    def test_observed_htm_fallbacks_locate_home_and_extensionless_page_owners(self):
        for target, rel in (('/', 'index.htm'), ('/pricing', 'pricing.htm'),
                            ('/pricing/', 'pricing/index.htm')):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                owner = put(root, rel)
                if target != '/':
                    put(root, 'index.html')
                original = owner.read_bytes()
                for artifact in ('title', 'content', 'headings', 'image_alt'):
                    result = candidates(root, 'plain_html', artifact, 'https://example.test' + target)
                    self.assertEqual(rel, result[0]['path'])
                    self.assertTrue(result[0]['exists'])
                data = {'url': 'https://example.test' + target, 'findings': [
                    {'rule_id': 'technical.missing.title', 'category': 'technical',
                     'severity': 'high', 'title': 'Missing title'}]}
                built = plan.build_plan(data, str(root))
                self.assertEqual('plain_html', built['framework']['name'])
                self.assertEqual(rel, built['actions'][0]['likely_files'][0]['path'])
                with mock.patch.object(Path, 'cwd', return_value=root.parent), \
                        mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
                    received = mcp_server._plan(data, root.name)
                self.assertEqual(built['actions'][0]['likely_files'], received['actions'][0]['likely_files'])
                self.assertEqual(original, owner.read_bytes())

    def test_htm_fallbacks_do_not_displace_html_or_propose_unobserved_files(self):
        for target, html, htm in (('/', 'index.html', 'index.htm'),
                                   ('/pricing', 'pricing.html', 'pricing.htm'),
                                   ('/pricing/', 'pricing/index.html', 'pricing/index.htm')):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                put(root, html)
                put(root, htm)
                result = candidates(root, 'plain_html', 'title', 'https://example.test' + target)
                self.assertEqual(html, result[0]['path'])
                (root / html).unlink()
                (root / htm).unlink()
                self.assertNotIn(htm, plan._route_candidates('https://example.test' + target,
                                                           'plain_html', files=[]))

    def test_html_htm_case_and_nested_literal_files_rank_before_homepage(self):
        for rel in ('pricing.html', 'pricing.htm', 'pricing.HTML', 'pricing.HtM', '.well-known/info.html', 'guides/café.html'):
            with self.subTest(rel=rel), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve(); put(root, 'index.html'); put(root, rel)
                for artifact in ('title', 'content', 'headings', 'image_alt'):
                    result = candidates(root, 'plain_html', artifact, 'https://example.test/' + rel + '?mode=1#section')
                    self.assertEqual(rel, result[0]['path'])
                    self.assertTrue(result[0]['exists'])
                    self.assertIn('confirm source ownership', result[0]['reason'])

    def test_extensionless_and_framework_routes_retain_their_conventions(self):
        self.assertEqual(['pricing.html', 'pricing/index.html'], plan._route_candidates('https://example.test/pricing', 'plain_html'))
        self.assertEqual(['pricing.html', 'pricing.html.html', 'pricing.html/index.html'],
                         plan._route_candidates('https://example.test/pricing.html', 'plain_html'))
        self.assertEqual(['pricing.html.html', 'pricing.html/index.html'],
                         plan._route_candidates('https://example.test/pricing.html/', 'plain_html'))
        self.assertEqual(['src/pages/pricing.html.astro', 'src/pages/pricing.html/index.astro'],
                         plan._route_candidates('https://example.test/pricing.html', 'astro'))

    def test_missing_literal_file_retains_existing_fallback_conventions(self):
        for legacy in ('pricing.html.html', 'pricing.html/index.html'):
            with self.subTest(legacy=legacy), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve(); put(root, 'index.html'); put(root, legacy)
                result = candidates(root, 'plain_html', 'title', 'https://example.test/pricing.html')
                self.assertEqual(legacy, result[0]['path'])
                self.assertTrue(result[0]['exists'])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); put(root, 'index.html')
            result = candidates(root, 'plain_html', 'title', 'https://example.test/pricing.html')
            self.assertEqual('index.html', result[0]['path'])

    def test_url_encoded_spelling_is_literal_and_not_decoded_to_an_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); put(root, 'index.html'); put(root, 'pricing.html')
            target = 'https://example.test/%70ricing.html'
            result = candidates(root, 'plain_html', 'title', target)
            self.assertEqual('index.html', result[0]['path'])
            put(root, '%70ricing.html')
            result = candidates(root, 'plain_html', 'title', target)
            self.assertEqual('%70ricing.html', result[0]['path'])

    def test_literal_file_still_passes_symlink_and_traversal_guards(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp).resolve(); put(root, 'index.html'); external = put(Path(outside), 'pricing.html')
            try: (root / 'pricing.html').symlink_to(external)
            except OSError: self.skipTest('symlinks unavailable')
            warnings = []
            result = candidates(root, 'plain_html', 'title', 'https://example.test/pricing.html', warnings)
            self.assertEqual('index.html', result[0]['path'])
            self.assertNotIn('pricing.html', [item['path'] for item in result])
            self.assertIn(plan.SOURCE_CANDIDATE_WARNING, warnings)
            self.assertEqual([], plan._route_candidates('https://example.test/../pricing.html', 'plain_html', warnings))

    def test_mcp_literal_file_mapping_is_offline_read_only_and_review_required(self):
        data = {'url': 'https://example.test/pricing.html', 'findings': [
            {'rule_id': 'technical.missing.title', 'category': 'technical', 'severity': 'high', 'title': 'Missing title'}]}
        original = copy.deepcopy(data)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); repo = root / 'source'
            owners = [put(repo, rel) for rel in ('index.html', 'pricing.html')]
            snapshots = [owner.read_bytes() for owner in owners]
            with mock.patch.object(Path, 'cwd', return_value=root), \
                    mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
                built = mcp_server._plan(data, 'source')
            self.assertEqual(snapshots, [owner.read_bytes() for owner in owners])
        action = built['actions'][0]
        self.assertEqual('pricing.html', action['likely_files'][0]['path'])
        self.assertEqual('review_required', action['safety'])
        self.assertEqual(original, data)


if __name__ == '__main__':
    unittest.main()
