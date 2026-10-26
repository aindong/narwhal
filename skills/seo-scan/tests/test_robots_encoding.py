"""Robots rules compare equivalent URI octets without decoding reserved syntax."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import crawl_site
from lib.robots import RobotsTxt
from lib.report import Report


def blocked(pattern, target):
    return RobotsTxt.parse('User-agent: *\nDisallow: ' + pattern).disallowed(target, 'TestBot')


class TestRobotsEncoding(unittest.TestCase):
    def test_unreserved_ascii_escapes_match_their_literal_form(self):
        for pattern, target in (('/private', '/%70rivate'), ('/%70rivate', '/private'),
                                ('/~owner', '/%7eowner'), ('/a-b_c.txt', '/a%2Db%5Fc%2Etxt')):
            with self.subTest(pattern=pattern, target=target):
                self.assertTrue(blocked(pattern, target))

    def test_utf8_literal_and_encoded_paths_are_equivalent(self):
        for literal, encoded in (('/café', '/caf%C3%A9'), ('/資料', '/%E8%B3%87%E6%96%99')):
            for pattern, target in ((literal, encoded), (encoded, literal), (encoded.lower(), encoded)):
                with self.subTest(pattern=pattern, target=target):
                    self.assertTrue(blocked(pattern, target))

    def test_reserved_escaped_separators_are_not_decoded(self):
        for encoded, literal in (('/a%2Fb', '/a/b'), ('/a%3Fb', '/a?b'),
                                  ('/a%23b', '/a#b'), ('/a%26b', '/a&b')):
            with self.subTest(encoded=encoded):
                self.assertTrue(blocked(encoded, encoded.lower()))
                self.assertFalse(blocked(encoded, literal))
                if '#' not in literal:  # raw # starts a robots.txt comment
                    self.assertFalse(blocked(literal + '$', encoded))

    def test_literal_stars_and_dollars_do_not_become_rule_operators(self):
        for encoded, literal in (('/literal%2A', '/literal*'), ('/literal%24', '/literal$')):
            with self.subTest(encoded=encoded):
                self.assertTrue(blocked(encoded, literal))
                self.assertTrue(blocked(encoded, encoded.lower()))
                self.assertFalse(blocked(encoded, '/literalOther'))
        self.assertTrue(blocked('/literal*', '/literalOther'))
        self.assertTrue(blocked('/literal$', '/literal'))
        self.assertFalse(blocked('/literal$', '/literal$'))

    def test_normalized_equivalent_rules_keep_allow_tie_precedence(self):
        rt = RobotsTxt.parse('User-agent: *\nDisallow: /%70rivate\nAllow: /private')
        self.assertTrue(rt.allowed('/private', 'TestBot'))
        self.assertTrue(rt.allowed('/%70rivate', 'TestBot'))
        rt = RobotsTxt.parse('User-agent: *\nDisallow: /private\nAllow: /%70rivate/public')
        self.assertTrue(rt.allowed('/private/public', 'TestBot'))
        self.assertFalse(rt.allowed('/%70rivate/secret', 'TestBot'))
        rt = RobotsTxt.parse('User-agent: *\nDisallow: /caf%C3%A9\nAllow: /café')
        self.assertTrue(rt.allowed('/café', 'TestBot'))
        self.assertTrue(rt.allowed('/caf%C3%A9', 'TestBot'))

    def test_full_urls_keep_query_matching_and_ignore_fragments(self):
        self.assertTrue(blocked('/lookup?q=caf%C3%A9$',
                                'https://example.test/lookup?q=café#ignored'))
        self.assertFalse(blocked('/lookup?q=caf%C3%A9$',
                                 'https://example.test/lookup?q=café&extra=1'))
        self.assertFalse(blocked('/public%23secret', 'https://example.test/public#secret'))

    def test_escaped_percent_is_not_decoded_twice(self):
        self.assertTrue(blocked('/%2570rivate', '/%2570rivate'))
        self.assertFalse(blocked('/private', '/%2570rivate'))
        self.assertFalse(blocked('/a%2Fb', '/a%252Fb'))

    def test_case_sensitivity_and_opaque_non_utf8_octets_are_preserved(self):
        self.assertFalse(blocked('/Private', '/%70rivate'))
        self.assertTrue(blocked('/byte%FF', '/byte%ff'))
        self.assertFalse(blocked('/byte%FF', '/byteÿ'))

    def test_empty_and_legacy_malformed_patterns_do_not_crash(self):
        for pattern in ('/bad%', '/bad%QZ', '/bad%2'):
            with self.subTest(pattern=pattern):
                self.assertTrue(blocked(pattern, pattern))
        self.assertFalse(blocked('', '/private'))

    def test_crawl_uses_gathered_robots_policy_and_forwards_timeout(self):
        base = 'https://example.test/'
        candidates = [base, base + 'private', base + '%70rivate', base + 'public']
        for prefix in ('', '\ufeff'):
            for disallow in ('/private', '/'):
                context = {'robots_txt': prefix + 'User-agent: *\nDisallow: ' + disallow}
                for obey in (True, False):
                    expected = candidates if not obey else ([base] if disallow == '/' else [base, candidates[-1]])
                    options = {} if obey else {'obey_robots': False}
                    with self.subTest(prefix=prefix, disallow=disallow, obey=obey), \
                            mock.patch.object(crawl_site.scanner, 'gather_context', return_value=context) as gather, \
                            mock.patch.object(crawl_site, 'discover', return_value=list(candidates)) as discover, \
                            mock.patch.object(crawl_site.scanner, 'scan', side_effect=lambda url, **kw:
                                Report(url, fetched_status=200)) as scan, \
                            mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
                        result = crawl_site.crawl(base, max_pages=4, concurrency=1, timeout=7,
                                                  detect_dupes=False, **options)
                        self.assertEqual(expected, [call.args[0] for call in scan.call_args_list])
                        self.assertEqual(expected, [page['url'] for page in result['pages']])
                        self.assertEqual(len(candidates) - len(expected), result['skipped_robots'])
                        self.assertEqual(context['robots_txt'], discover.call_args.kwargs.get('robots_txt'))
                        self.assertEqual(7, gather.call_args.kwargs.get('timeout'))
                        self.assertEqual(7, discover.call_args.kwargs.get('timeout'))
                        self.assertTrue(all(call.kwargs.get('timeout') == 7 for call in scan.call_args_list))
                        self.assertIs(type(discover.call_args.kwargs.get('limit')), int)
                        self.assertGreater(discover.call_args.kwargs.get('limit'), 0)

    def test_crawl_candidate_filter_does_not_admit_an_encoded_disallowed_path(self):
        base = 'https://example.test/'
        rt = RobotsTxt.parse('User-agent: *\nDisallow: /private')
        urls, skipped = crawl_site.select_urls([base, base + '%70rivate', base + 'public'],
                                                base, rt, True, 3)
        self.assertEqual([base, base + 'public'], urls)
        self.assertEqual(1, skipped)
        urls, skipped = crawl_site.select_urls([base, base + '%70rivate'], base, rt, False, 3)
        self.assertEqual([base, base + '%70rivate'], urls)
        self.assertEqual(0, skipped)


if __name__ == '__main__':
    unittest.main()
