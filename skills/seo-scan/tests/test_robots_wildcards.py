"""Robots wildcard matching must not enumerate exponential partitions."""

import itertools
from pathlib import Path
import random
import re
import subprocess
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import crawl_site
from lib.robots import RobotsTxt, _comparison_path, _match_len


def old_regex(pattern):
    """Small-input oracle only; never run the adversarial rule through regex."""
    canonical = _comparison_path(pattern, pattern=True)
    anchored = canonical.endswith('$')
    p = canonical[:-1] if anchored else canonical
    return re.compile('^' + ''.join('.*' if ch == '*' else re.escape(ch) for ch in p) + ('$' if anchored else ''))


class TestRobotsWildcards(unittest.TestCase):
    def test_exhaustive_small_rules_match_prior_regex_including_newlines(self):
        words = [''.join(chars) for size in range(5) for chars in itertools.product('ab*', repeat=size)]
        paths = ['/' + ''.join(chars) for size in range(5) for chars in itertools.product('ab\n', repeat=size)]
        for word in words:
            for suffix in ('', '$'):
                pattern = '/' + word + suffix
                oracle = old_regex(pattern)
                length = len(_comparison_path(pattern, pattern=True))
                for path in paths:
                    self.assertEqual(length if oracle.search(path) else -1, _match_len(pattern, path), (pattern, path))

    def test_seeded_encoded_literal_and_unicode_cases_match_prior_regex(self):
        rng = random.Random(9309)
        tokens = ('a', '/', '*', '$', '?', '.', '[', '\\', '%61', '%2a', '%24', '%2F', 'é', ';')
        for _ in range(3000):
            pattern = '/' + ''.join(rng.choices(tokens, k=rng.randrange(1, 9)))
            if rng.randrange(2):
                pattern += '$'
            raw_path = '/' + ''.join(rng.choices(tokens, k=rng.randrange(1, 12)))
            if rng.randrange(2):
                raw_path = pattern.replace('*', 'abc').rstrip('$')
            path = _comparison_path(raw_path)
            expected = len(_comparison_path(pattern, pattern=True)) if old_regex(pattern).search(path) else -1
            self.assertEqual(expected, _match_len(pattern, path), (pattern, raw_path))

    def test_anchored_suffix_can_use_a_later_nonoverlapping_occurrence(self):
        for pattern, path, expected in (('/*ab$','/abab', True), ('/*ab*ab$','/ab', False),
                                         ('/*a*a$','/aaa', True), ('/a**b$', '/ab', True),
                                         ('/a*', '/a\nrest', True), ('/a*b$', '/a\nb', False),
                                         ('/a*b$', '/ab\n', True), ('/a*b$', '/ab\n\n', False)):
            self.assertEqual(expected, _match_len(pattern, path) >= 0, (pattern, path))

    def test_adversarial_rules_complete_in_owned_timeout_bounded_process(self):
        code = ('import sys; sys.path.insert(0, ' + repr(str(SCRIPTS)) + '); '
                'from lib.robots import RobotsTxt; '
                'rt=RobotsTxt.parse("User-agent: *\\nDisallow: /"+"*a"*64+"z$"); '
                'assert rt.disallowed("/"+"a"*128+"z", "Bot"); '
                'assert rt.allowed("/"+"a"*128, "Bot"); print("matched and nonmatched")')
        result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=10)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('matched and nonmatched', result.stdout.strip())

    def test_precedence_specificity_and_crawl_selection_remain_unchanged(self):
        text = 'User-agent: *\nDisallow: /a*b\nAllow: /a*b\nDisallow: /private*\nAllow: /private/public*'
        rt = RobotsTxt.parse(text)
        base = 'https://example.test/'
        urls = [base, base + 'aab', base + 'private/secret', base + 'private/public/x']
        self.assertEqual(([urls[0], urls[1], urls[3]], 1), crawl_site.select_urls(urls, base, rt, True, 4))
        self.assertEqual(len('/a*b'), _match_len('/a*b', '/aab'))
        self.assertFalse(RobotsTxt.parse('User-agent: *\nDisallow: /%2A$').allowed('/%2A', 'Bot'))
        self.assertTrue(RobotsTxt.parse('User-agent: *\nDisallow: /%2A$').allowed('/a', 'Bot'))


if __name__ == '__main__':
    unittest.main()
