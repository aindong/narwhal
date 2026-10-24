"""Starter discovery must use the address that actually served the homepage."""
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import generate_llms as llms
from lib import http

SOURCE = 'https://old.example.test/start'
FINAL = 'https://new.example.test/docs/?mode=A'


class TestLlmsRedirectContext(unittest.TestCase):
    def test_final_origin_rules_and_candidates_govern_selected_links(self):
        good, blocked = 'https://new.example.test/docs/guide', 'https://new.example.test/private'
        def fetch(url, **kwargs):
            final = FINAL if url == SOURCE else url
            return http.Response(url, final, 200, {}, '<title>Destination</title>', 1)
        with mock.patch.object(http, 'fetch', side_effect=fetch) as fetched, \
                mock.patch.object(http, 'fetch_text', return_value='User-agent: *\nDisallow: /private') as robots, \
                mock.patch.object(llms.crawl_site, 'discover', return_value=[FINAL, good, blocked]) as discover:
            result = llms.build(SOURCE, max_pages=3, allow_private=True, timeout=7)
        robots.assert_called_once_with('https://new.example.test/robots.txt', allow_private=True, timeout=7)
        discover.assert_called_once_with(FINAL, allow_private=True, timeout=7, limit=6,
                                         robots_txt='User-agent: *\nDisallow: /private')
        self.assertEqual([SOURCE, FINAL, good], [call.args[0] for call in fetched.call_args_list])
        self.assertTrue(all(call.kwargs == {'allow_private': True, 'timeout': 7} for call in fetched.call_args_list))
        self.assertEqual([FINAL, good], [page['url'] for _, pages in result['sections'] for page in pages])
        self.assertEqual(2, result['coverage']['attempted_pages'])

    def test_same_origin_path_redirect_and_absent_final_url(self):
        for final, expected in (('https://old.example.test/docs/', 'https://old.example.test/docs/'),
                                ('', SOURCE)):
            with self.subTest(final=final):
                with mock.patch.object(http, 'fetch', return_value=http.Response(SOURCE, final, 200, {}, '<title>Home</title>', 1)), \
                        mock.patch.object(http, 'fetch_text', return_value='') as robots, \
                        mock.patch.object(llms.crawl_site, 'discover', return_value=[]) as discover:
                    llms.build(SOURCE)
                self.assertEqual(expected, discover.call_args.args[0])
                robots.assert_called_once_with('https://old.example.test/robots.txt', allow_private=False, timeout=20)

    def test_failed_destination_does_not_fall_back_to_old_site(self):
        home = http.Response(SOURCE, FINAL, 503, {}, '', 1)
        with mock.patch.object(http, 'fetch', return_value=home), \
                mock.patch.object(http, 'fetch_text') as robots, \
                mock.patch.object(llms.crawl_site, 'discover') as discover:
            with self.assertRaises(llms.GenerationError):
                llms.build(SOURCE)
            robots.assert_not_called(); discover.assert_not_called()

    def test_guard_rejection_propagates_without_relaxing_private_access(self):
        with mock.patch.object(http, 'fetch', side_effect=http.SSRFError('blocked destination')) as fetched, \
                mock.patch.object(http, 'fetch_text') as robots, \
                mock.patch.object(llms.crawl_site, 'discover') as discover:
            with self.assertRaises(http.SSRFError):
                llms.build(SOURCE)
            fetched.assert_called_once_with(SOURCE, allow_private=False, timeout=20)
            robots.assert_not_called(); discover.assert_not_called()


if __name__ == '__main__':
    unittest.main()
