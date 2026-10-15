"""One file-start UTF-8 marker must not hide robots rules or sitemaps."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_geo
import crawl_site
from lib import sitemap
from lib.report import Report
from lib.robots import RobotsTxt


class TestRobotsBOM(unittest.TestCase):
    def test_initial_marker_keeps_first_wildcard_group_across_line_endings(self):
        for newline in ('\n', '\r', '\r\n'):
            with self.subTest(newline=newline):
                text = newline.join(('User-agent: *', 'Disallow: /private', 'Allow: /private/public'))
                plain, marked = RobotsTxt.parse(text), RobotsTxt.parse('\ufeff' + text)
                for path, expected in (('/private', False), ('/private/public', True), ('/', True)):
                    self.assertEqual(expected, marked.allowed(path, 'seo-scan'))
                    self.assertEqual(plain.allowed(path, 'seo-scan'), marked.allowed(path, 'seo-scan'))

    def test_initial_named_group_retains_specificity_and_subsequent_groups(self):
        text = 'User-agent: OAI-SearchBot\nDisallow: /\nUser-agent: *\nAllow: /'
        rt = RobotsTxt.parse('\ufeff' + text)
        self.assertTrue(rt.disallowed('/', 'OAI-SearchBot'))
        self.assertTrue(rt.allowed('/', 'OtherBot'))

    def test_initial_marker_before_whitespace_comment_or_empty_document(self):
        for text in (' User-agent: *\nDisallow: /', '# note\nUser-agent: *\nDisallow: /',
                     '\nUser-agent: *\nDisallow: /'):
            self.assertTrue(RobotsTxt.parse('\ufeff' + text).disallowed('/', 'Bot'))
        for text in ('', '\ufeff', '\ufeff\n'):
            self.assertTrue(RobotsTxt.parse(text).allowed('/', 'Bot'))

    def test_marker_in_path_is_literal_and_later_marker_is_not_a_file_prefix(self):
        rt = RobotsTxt.parse('\ufeffUser-agent: *\nDisallow: /\ufeffprivate')
        self.assertFalse(rt.allowed('/\ufeffprivate', 'Bot'))
        self.assertFalse(rt.allowed('/%EF%BB%BFprivate', 'Bot'))
        self.assertTrue(rt.allowed('/private', 'Bot'))
        rt = RobotsTxt.parse('User-agent: *\n\ufeffDisallow: /private')
        self.assertTrue(rt.allowed('/private', 'Bot'))
        self.assertTrue(RobotsTxt.parse('\ufeff\ufeffUser-agent: *\nDisallow: /').allowed('/', 'Bot'))

    def test_first_sitemap_declaration_survives_marker_in_both_readers(self):
        for newline in ('\n', '\r', '\r\n'):
            text = '\ufeffSitemap: https://example.test/custom.xml' + newline + 'User-agent: *' + newline + 'Disallow:'
            self.assertEqual(['https://example.test/custom.xml'], RobotsTxt.parse(text).sitemaps)
            self.assertEqual(['https://example.test/custom.xml'], sitemap.robots_sitemaps(text))

    def test_sitemap_marker_handling_preserves_reference_validation_and_literals(self):
        diagnostics = {}
        text = '\ufeffSitemap: /relative.xml\nSitemap: https://example.test/\ufeffmap.xml\n\ufeffSitemap: https://example.test/later.xml'
        self.assertEqual(['https://example.test/\ufeffmap.xml'], sitemap.robots_sitemaps(text, diagnostics=diagnostics))
        self.assertEqual({'robots_directives': 1}, diagnostics)
        self.assertEqual([], sitemap.robots_sitemaps(None))
        self.assertEqual([], sitemap.robots_sitemaps('\ufeff'))

    def test_geo_cannot_report_root_allowance_when_first_group_denies_it(self):
        for prefix in ('', '\ufeff'):
            rep = Report('https://example.test/')
            audit_geo._ai_crawler_access({'robots_txt': prefix + 'User-agent: *\nDisallow: /'}, rep)
            self.assertEqual([('high', 'AI crawlers are blocked in robots.txt')], [(f.severity, f.title) for f in rep.findings])
            self.assertTrue(all(row['disallowed'] for row in rep.meta['ai_crawler_access']['agents']))

    def test_crawl_filters_blocked_leaf_but_preserves_explicit_base_override(self):
        base = 'https://example.test/'
        rt = RobotsTxt.parse('\ufeffUser-agent: *\nDisallow: /')
        urls = [base, base + 'private']
        self.assertEqual(([base], 1), crawl_site.select_urls(urls, base, rt, True, 2))
        self.assertEqual((urls, 0), crawl_site.select_urls(urls, base, rt, False, 2))


if __name__ == '__main__':
    unittest.main()
