"""Full URLs retain semicolon path components during robots filtering."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import crawl_site
from lib.robots import RobotsTxt


class TestRobotsPathParameters(unittest.TestCase):
    def test_full_url_and_path_have_the_same_semicolon_suffix(self):
        rt = RobotsTxt.parse('User-agent: *\nDisallow: /private;draft')
        for target in ('/private;draft', 'https://example.test/private;draft',
                       '//example.test/private;draft',
                       'https://example.test/private;draft?preview=1#ignored'):
            with self.subTest(target=target):
                self.assertTrue(rt.disallowed(target, 'TestBot'))
        self.assertTrue(rt.allowed('https://example.test/private;published', 'TestBot'))

    def test_anchored_parameter_rule_keeps_query_and_excludes_fragment(self):
        rt = RobotsTxt.parse('User-agent: *\nDisallow: /private;draft?preview=1$')
        self.assertTrue(rt.disallowed('https://example.test/private;draft?preview=1#ignored', 'TestBot'))
        self.assertTrue(rt.allowed('https://example.test/private;draft?preview=10', 'TestBot'))
        self.assertTrue(rt.allowed('https://example.test/private?preview=1', 'TestBot'))

    def test_parameterized_allow_is_more_specific_than_path_disallow(self):
        rt = RobotsTxt.parse('User-agent: *\nDisallow: /private\nAllow: /private;public$')
        self.assertTrue(rt.allowed('https://example.test/private;public', 'TestBot'))
        self.assertTrue(rt.disallowed('https://example.test/private;draft', 'TestBot'))

    def test_encoded_semicolon_does_not_become_a_literal_delimiter(self):
        rt = RobotsTxt.parse('User-agent: *\nDisallow: /private;draft$')
        self.assertTrue(rt.allowed('https://example.test/private%3Bdraft', 'TestBot'))
        rt = RobotsTxt.parse('User-agent: *\nDisallow: /private%3Bdraft$')
        self.assertTrue(rt.disallowed('https://example.test/private%3bdraft', 'TestBot'))
        self.assertTrue(rt.allowed('https://example.test/private;draft', 'TestBot'))

    def test_crawl_selection_keeps_parameterized_allow_and_skips_disallow(self):
        base = 'https://example.test/'
        rt = RobotsTxt.parse('User-agent: *\nDisallow: /private\nAllow: /private;public$')
        urls, skipped = crawl_site.select_urls(
            [base, base + 'private;public', base + 'private;draft'], base, rt, True, 5)
        self.assertEqual([base, base + 'private;public'], urls)
        self.assertEqual(1, skipped)


if __name__ == '__main__':
    unittest.main()
