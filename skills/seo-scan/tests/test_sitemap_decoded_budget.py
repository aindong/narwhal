"""Decoded sitemap bytes must be bounded before XML extraction or sampling."""

import gzip
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import validate_sitemap as validator
from lib import http, sitemap as sm

BASE = 'https://example.test/'
XML = b'<urlset><url><loc>https://example.test/valid</loc></url></urlset>'


def analyze(body):
    with mock.patch.object(http, 'assert_public_host'), \
            mock.patch.object(http, 'fetch_bytes', return_value=(body, None)), \
            mock.patch.object(http, 'head', return_value=(200, None)) as head:
        result = validator.analyze(BASE + 'sitemap.xml.gz')
    return result, head


class TestSitemapDecodedBudget(unittest.TestCase):
    def test_exact_plain_and_gzip_byte_boundaries_are_not_character_budgets(self):
        source = '<urlset><!-- café 🐳 --></urlset>'.encode()
        for raw in (source, gzip.compress(source)):
            with self.subTest(gzip=raw != source):
                self.assertEqual((source.decode(), None), sm.decode_checked(raw, max_bytes=len(source)))
                self.assertEqual(('', 'decoded_byte_limit'), sm.decode_checked(raw, max_bytes=len(source)-1))

    def test_high_expansion_is_cut_off_by_a_sized_read_not_decompress_all(self):
        compressed = gzip.compress(b' ' * 4_000_000)
        original_read = gzip.GzipFile.read
        reads = []

        def read(stream, size=-1):
            reads.append(size)
            return original_read(stream, size)

        with mock.patch.object(gzip, 'decompress', side_effect=AssertionError('No whole-buffer expansion')), \
                mock.patch.object(gzip.GzipFile, 'read', read):
            self.assertEqual(('', 'decoded_byte_limit'), sm.decode_checked(compressed, max_bytes=1024))
        self.assertEqual([1025], reads)
        self.assertLess(len(compressed), 4096)

    def test_concatenated_members_share_one_budget(self):
        first, second = XML[:20], XML[20:]
        compressed = gzip.compress(first) + gzip.compress(second)
        self.assertEqual((XML.decode(), None), sm.decode_checked(compressed, max_bytes=len(XML)))
        self.assertEqual(('', 'decoded_byte_limit'), sm.decode_checked(compressed, max_bytes=len(first)))
        self.assertEqual((XML.decode(), None), sm.decode_checked(compressed + b'\x00' * 8, max_bytes=len(XML)))

    def test_truncated_crc_corrupt_and_trailing_garbage_withhold_all_text(self):
        raw = gzip.compress(XML)
        corrupt = bytearray(raw)
        corrupt[-8] ^= 1
        cases = (raw[:12], raw[:-1], bytes(corrupt), raw + b'not another gzip member',
                 raw + gzip.compress(b'ignored')[:-2], b'\x1f\x8bnot-gzip')
        for body in cases:
            with self.subTest(body=body[:12]):
                self.assertEqual(('', 'gzip_decode_failed'), sm.decode_checked(body, max_bytes=1024))

    def test_empty_and_plain_decoding_retain_existing_utf8_replacement(self):
        for raw, expected in ((b'', ''), (gzip.compress(b''), ''), (b'\xff', '\ufffd')):
            self.assertEqual((expected, None), sm.decode_checked(raw, max_bytes=1))

    def test_invalid_budgets_fail_before_starting_decompression(self):
        for budget in (True, 0, -1, 1.5, '1024'):
            with self.subTest(budget=budget), mock.patch.object(gzip, 'GzipFile') as stream:
                with self.assertRaises(ValueError):
                    sm.decode_checked(gzip.compress(XML), max_bytes=budget)
                stream.assert_not_called()

    def test_validator_does_not_parse_or_sample_over_budget_prefixes(self):
        source = XML + b' ' * 200
        with mock.patch.object(sm, 'MAX_DECODED_BYTES', len(XML)), \
                mock.patch.object(sm, 'parse_checked', side_effect=AssertionError('No prefix extraction')):
            result, head = analyze(gzip.compress(source))
        self.assertEqual(1, result['sitemaps_fetched'])
        self.assertEqual(1, result['gzip'])
        self.assertEqual(0, result['total_urls'])
        self.assertEqual({'decoded_byte_limit': 1}, result['parse_coverage']['reasons'])
        self.assertEqual(len(XML), result['parse_coverage']['decoded_byte_limit'])
        self.assertNotIn('Sitemap looks healthy', validator.render_markdown(result))
        self.assertIn('decoded sitemap byte limit reached', validator.render_markdown(result))
        head.assert_not_called()

    def test_corrupt_member_does_not_turn_a_valid_prefix_into_a_sample(self):
        result, head = analyze(gzip.compress(XML)[:-1])
        self.assertEqual({'gzip_decode_failed': 1}, result['parse_coverage']['reasons'])
        self.assertFalse(result['sample'])
        self.assertEqual(0, result['total_urls'])
        head.assert_not_called()

    def test_bad_sibling_does_not_hide_a_valid_sitemap(self):
        index = ('<sitemapindex><sitemap><loc>' + BASE + 'bad.xml.gz</loc></sitemap>'
                 '<sitemap><loc>' + BASE + 'good.xml.gz</loc></sitemap></sitemapindex>').encode()
        bodies = {BASE + 'sitemap.xml': index,
                  BASE + 'bad.xml.gz': gzip.compress(XML + b' ' * 1000),
                  BASE + 'good.xml.gz': gzip.compress(XML)}
        with mock.patch.object(sm, 'MAX_DECODED_BYTES', 256), \
                mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, 'fetch_bytes', side_effect=lambda url, **kw: (bodies[url], None)), \
                mock.patch.object(http, 'head', return_value=(200, None)) as head:
            result = validator.analyze(BASE + 'sitemap.xml')
        self.assertEqual(2, result['parse_coverage']['verified_files'])
        self.assertEqual(1, result['parse_coverage']['unverified_files'])
        self.assertEqual(1, result['total_urls'])
        head.assert_called_once()
        self.assertIn('verified files only', validator.render_markdown(result))

    def test_legacy_decode_is_also_bounded_and_unexpected_errors_propagate(self):
        with mock.patch.object(sm, 'MAX_DECODED_BYTES', 32):
            self.assertEqual('', sm.decode(gzip.compress(XML)))
        with mock.patch.object(gzip.GzipFile, 'read', side_effect=RuntimeError('bug')):
            with self.assertRaisesRegex(RuntimeError, 'bug'):
                sm.decode_checked(gzip.compress(XML))


if __name__ == '__main__':
    unittest.main()
