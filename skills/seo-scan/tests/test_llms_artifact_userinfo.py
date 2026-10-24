"""Authentication belongs to fetching, not public starter links or host labels."""
import copy
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import generate_llms as llms
import mcp_server
from lib import http

SECRET = 'fixture-password'
SOURCE = 'https://fixture-user:' + SECRET + '@Example.test:8443/guide?mode=A'
PUBLIC = 'https://Example.test:8443/guide?mode=A'


class TestLlmsArtifactUserinfo(unittest.TestCase):
    def test_build_preserves_authentication_for_fetching_but_not_artifact_fields(self):
        def fetch(url, **kwargs):
            return http.Response(url, url, 200, {'content-type': 'text/html'},
                                 '<html><body>Example without title</body></html>', 1)
        with mock.patch.object(http, 'fetch', side_effect=fetch) as fetched, \
                mock.patch.object(http, 'fetch_text', return_value='') as robots, \
                mock.patch.object(llms.crawl_site, 'discover', return_value=[SOURCE]) as discover:
            data = llms.build(SOURCE)
        self.assertTrue(all(call.args[0] == SOURCE for call in fetched.call_args_list))
        self.assertIn('fixture-user:' + SECRET + '@', robots.call_args.args[0])
        self.assertEqual(SOURCE, discover.call_args.args[0])
        self.assertEqual('Example.test:8443', data['site_name'])
        page = data['sections'][0][1][0]
        self.assertEqual(PUBLIC, page['url'])
        self.assertTrue(data['coverage']['authentication_removed'])
        output = llms.render_llms_txt(data['site_name'], data['description'], data['sections'], coverage=data['coverage'])
        self.assertNotIn(SECRET, output)
        self.assertNotIn('fixture-user', output)
        self.assertIn(PUBLIC, output)
        self.assertIn('Verify candidate links are publicly accessible', output)

    def test_direct_renderer_removes_userinfo_without_mutating_supplied_pages(self):
        sections = [('Main', [{'url': SOURCE, 'title': 'Guide', 'description': 'Read this guide.'}])]
        original = copy.deepcopy(sections)
        output = llms.render_llms_txt('Example', '', sections)
        self.assertNotIn(SECRET, output)
        self.assertIn('- [Guide](' + PUBLIC + '): Read this guide.', output)
        self.assertIn('URL userinfo was removed', output)
        self.assertEqual(original, sections)

    def test_only_authority_userinfo_changes_literal_url_components(self):
        cases = [
            ('https://user@example.test/a@b?q=user@host#part', 'https://example.test/a@b?q=user@host#part'),
            ('https://u%40name:p%3Ass@example.test/path?', 'https://example.test/path?'),
            ('http://user:pass@[2001:db8::1]:8080/a//B?x=1&x=2', 'http://[2001:db8::1]:8080/a//B?x=1&x=2'),
            ('https://example.test/a@b?token=unchanged#part', 'https://example.test/a@b?token=unchanged#part'),
        ]
        for before, after in cases:
            with self.subTest(before=before):
                self.assertEqual(after, llms._without_userinfo(before))

    def test_redirect_metadata_is_sanitized_even_if_original_url_has_no_authentication(self):
        original = 'https://example.test/'
        def fetch(url, **kwargs):
            return http.Response(url, SOURCE, 200, {}, '<title>Named site</title>', 1)
        with mock.patch.object(http, 'fetch', side_effect=fetch), \
                mock.patch.object(http, 'fetch_text', return_value=''), \
                mock.patch.object(llms.crawl_site, 'discover', return_value=[original]):
            data = llms.build(original)
        self.assertEqual('Named site', data['site_name'])
        self.assertEqual(PUBLIC, data['sections'][0][1][0]['url'])
        self.assertTrue(data['coverage']['authentication_removed'])

    def test_mcp_keeps_public_access_caveat_when_build_already_sanitized_links(self):
        data = {'site_name': 'Example', 'description': '', 'pages': 1,
                'sections': [('Main', [{'url': PUBLIC, 'title': 'Guide', 'description': ''}])],
                'coverage': {'authentication_removed': True, 'omitted_pages': 0}}
        with mock.patch.object(llms, 'build', return_value=data):
            output = mcp_server._llms('https://example.test/')
        self.assertIn('URL userinfo was removed', output)
        self.assertIn('Verify candidate links are publicly accessible', output)
        self.assertNotIn(SECRET, output)

    def test_no_redaction_receipt_or_note_is_invented_for_ordinary_pages(self):
        url = 'https://example.test/a@b?mode=A'
        with mock.patch.object(http, 'fetch', return_value=http.Response(url, url, 200, {}, '<title>Example</title>', 1)), \
                mock.patch.object(http, 'fetch_text', return_value=''), \
                mock.patch.object(llms.crawl_site, 'discover', return_value=[url]):
            data = llms.build(url)
        self.assertNotIn('authentication_removed', data['coverage'])
        output = llms.render_llms_txt(data['site_name'], data['description'], data['sections'], coverage=data['coverage'])
        self.assertNotIn('userinfo', output)
        self.assertIn(url, output)


if __name__ == '__main__':
    unittest.main()
