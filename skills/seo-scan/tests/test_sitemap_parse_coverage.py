"""Fetched bytes are not proof of supported, complete XML extraction."""

import gzip
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan
import validate_sitemap
from lib import http, sitemap as sm

BASE = 'https://example.test/'
INDEX = BASE + 'sitemap.xml'
PAGE = BASE + 'valid?a=1&b=2'
NS = 'http://www.sitemaps.org/schemas/sitemap/0.9'
GOOD = '<urlset><url><loc>https://example.test/valid?a=1&amp;b=2</loc></url></urlset>'


def analyze(body, head_result=(200, None), **kwargs):
    raw = body if isinstance(body, bytes) else body.encode()
    with mock.patch.object(http, 'assert_public_host'), \
            mock.patch.object(http, 'fetch_bytes', return_value=(raw, None)), \
            mock.patch.object(http, 'head', return_value=head_result) as head:
        result = validate_sitemap.analyze(INDEX, **kwargs)
    return result, head


class TestSitemapParseCoverage(unittest.TestCase):
    def test_nonbroken_responses_are_not_automatically_successes(self):
        for response in ((403, None), (429, None), (301, None), (999, None),
                         (200, 'incomplete response')):
            with self.subTest(response=response):
                result, _ = analyze(GOOD, head_result=response)
                text = validate_sitemap.render_markdown(result)
                self.assertEqual([], result['broken_sample'])
                self.assertIn('0/1 URLs returned successful 2xx', text)
                self.assertIn('reachability unverified', text)
                self.assertNotIn('Sitemap looks healthy', text)

    def test_positive_and_skipped_samples_are_qualified(self):
        result, _ = analyze(GOOD)
        text = validate_sitemap.render_markdown(result)
        self.assertIn('1/1 URLs returned successful 2xx', text)
        self.assertIn('healthy for the checks performed', text)
        result, head = analyze(GOOD, sample=0)
        text = validate_sitemap.render_markdown(result)
        self.assertIn('not run; URL reachability unverified', text)
        self.assertIn('healthy for the checks performed', text)
        head.assert_not_called()

    def test_non_sitemap_content_never_becomes_a_healthy_zero(self):
        for body in ('not an XML sitemap', '<html><body>Not a sitemap</body></html>',
                     '<feed><loc>' + BASE + 'hidden</loc></feed>'):
            with self.subTest(body=body):
                result, head = analyze(body)
                coverage = result['parse_coverage']
                self.assertEqual(0, coverage['verified_files'])
                self.assertEqual(1, coverage['unverified_files'])
                self.assertEqual(0, result['total_urls'])
                self.assertNotIn('Sitemap looks healthy', validate_sitemap.render_markdown(result))
                self.assertIn('XML extraction unverified', validate_sitemap.render_markdown(result))
                head.assert_not_called()

    def test_malformed_suffix_discards_the_entire_prefix_measurement(self):
        result, head = analyze(GOOD[:-9] + '<broken>')
        self.assertEqual({'unparseable_xml': 1}, result['parse_coverage']['reasons'])
        self.assertEqual(0, result['total_urls'])
        self.assertFalse(result['sample'])
        head.assert_not_called()

    def test_marker_text_in_comments_does_not_establish_sitemap_kind(self):
        result, head = analyze('<html><!-- <urlset><url><loc>' + BASE + 'fake</loc></url></urlset> --></html>')
        self.assertEqual({'unrecognized_root': 1}, result['parse_coverage']['reasons'])
        head.assert_not_called()

    def test_supported_namespaces_and_xml_escaping_are_measured(self):
        for body in (GOOD, GOOD.replace('<urlset>', '<urlset xmlns="' + NS + '">'),
                     '<s:urlset xmlns:s="' + NS + '"><s:url><s:loc>https://example.test/valid?a=1&amp;b=2</s:loc></s:url></s:urlset>'):
            with self.subTest(body=body):
                result, head = analyze(body)
                self.assertEqual(1, result['parse_coverage']['verified_files'])
                self.assertEqual(0, result['parse_coverage']['unverified_files'])
                self.assertEqual(1, result['total_urls'])
                self.assertEqual(PAGE, head.call_args.args[0])
                self.assertIn('Sitemap looks healthy', validate_sitemap.render_markdown(result))

    def test_foreign_namespaces_and_nested_examples_are_not_page_entries(self):
        body = ('<urlset xmlns:x="urn:examples"><x:url><x:loc>' + BASE + 'fake</x:loc></x:url>'
                '<url><loc>' + BASE + 'real</loc><x:image><x:loc>' + BASE + 'image</x:loc></x:image></url></urlset>')
        kind, entries, problem = sm.parse_checked(body)
        self.assertEqual(('urlset', [{'loc': BASE + 'real', 'lastmod': None}], None),
                         (kind, entries, problem))
        self.assertEqual('unrecognized_root', sm.parse_checked('<urlset xmlns="urn:foreign"/>')[2])

    def test_comments_and_cdata_examples_do_not_become_entities(self):
        body = '<urlset><!-- <url><loc>' + BASE + 'fake</loc></url> --><![CDATA[<url><loc>fake</loc></url>]]>' + GOOD[8:]
        self.assertEqual([{'loc': PAGE, 'lastmod': None}], sm.parse_checked(body)[1])

    def test_missing_duplicate_and_nested_loc_shapes_are_unverified_not_guessed(self):
        for entry in ('<url/>', '<url><loc>a</loc><loc>b</loc></url>',
                      '<url><loc><b>' + BASE + 'fake</b></loc></url>'):
            with self.subTest(entry=entry):
                self.assertEqual('unsupported_entry_shape', sm.parse_checked('<urlset>' + entry + '</urlset>')[2])

    def test_doctype_and_external_entity_declarations_never_trigger_io(self):
        source = '<!DOCTYPE urlset [<!ENTITY secret SYSTEM "http://127.0.0.1/private">]><urlset><url><loc>&secret;</loc></url></urlset>'
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')), \
                mock.patch('urllib.request.urlopen', side_effect=AssertionError('No I/O')):
            kind, entries, problem = sm.parse_checked(source)
        self.assertEqual('unsupported_dtd', problem)
        self.assertFalse(entries)

    def test_depth_element_and_entry_limits_withhold_partial_entries(self):
        cases = [('MAX_XML_DEPTH', 2, 'xml_depth_limit'),
                 ('MAX_XML_ELEMENTS', 2, 'xml_element_limit'),
                 ('MAX_XML_ENTRIES', 0, 'entry_limit')]
        for name, limit, reason in cases:
            with self.subTest(name=name), mock.patch.object(sm, name, limit):
                _, entries, problem = sm.parse_checked(GOOD)
                self.assertEqual(reason, problem)
                self.assertFalse(entries)

    def test_unknown_child_does_not_hide_valid_sibling_measurements(self):
        child = BASE + 'good.xml'
        bad = BASE + 'unsupported.xml'
        index = '<sitemapindex><sitemap><loc>' + bad + '</loc></sitemap><sitemap><loc>' + child + '</loc></sitemap></sitemapindex>'
        bodies = {INDEX: index.encode(), bad: b'<feed/>', child: GOOD.encode()}
        with mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, 'fetch_bytes', side_effect=lambda url, **kw: (bodies[url], None)), \
                mock.patch.object(http, 'head', return_value=(200, None)) as head:
            result = validate_sitemap.analyze(INDEX)
        self.assertEqual(3, result['sitemaps_fetched'])
        self.assertEqual(2, result['parse_coverage']['verified_files'])
        self.assertEqual(1, result['parse_coverage']['unverified_files'])
        self.assertEqual(1, result['total_urls'])
        head.assert_called_once()
        self.assertIn('verified files only', validate_sitemap.render_markdown(result))
        self.assertNotIn('Sitemap looks healthy', validate_sitemap.render_markdown(result))

    def test_empty_supported_files_are_not_proof_of_healthy_url_coverage(self):
        for source in ('<urlset/>', '<sitemapindex/>'):
            with self.subTest(source=source):
                result, _ = analyze(source)
                self.assertEqual(1, result['parse_coverage']['verified_files'])
                self.assertNotIn('Sitemap looks healthy', validate_sitemap.render_markdown(result))

    def test_gzip_valid_and_truncated_payloads_degrade_without_crashing(self):
        result, _ = analyze(gzip.compress(GOOD.encode()))
        self.assertEqual(1, result['total_urls'])
        truncated = gzip.compress(GOOD.encode())[:12]
        result, head = analyze(truncated)
        self.assertEqual(1, result['parse_coverage']['unverified_files'])
        head.assert_not_called()

    def test_parser_errors_do_not_echo_source_or_secret_tokens(self):
        result, _ = analyze('<urlset><url><loc>secret-password</loc></url>')
        self.assertNotIn('secret-password', validate_sitemap.render_json(result))
        self.assertNotIn('secret-password', validate_sitemap.render_markdown(result))

    def test_missing_legacy_coverage_is_explicitly_unrecorded_not_a_pass(self):
        result, _ = analyze(GOOD)
        result.pop('parse_coverage')
        text = validate_sitemap.render_markdown(result)
        self.assertIn('XML extraction coverage was not recorded', text)
        self.assertNotIn('Sitemap looks healthy', text)

    def test_unexpected_parser_errors_are_not_silenced(self):
        with mock.patch.object(sm, 'parse_checked', side_effect=RuntimeError('bug')):
            with self.assertRaisesRegex(RuntimeError, 'bug'):
                analyze(GOOD)

    def test_inconsistent_and_future_coverage_receipts_do_not_certify_health(self):
        result, _ = analyze(GOOD)
        valid = result['parse_coverage']
        cases = [{**valid, 'basis': 'future_parser'}, {**valid, 'verified_files': True},
                 {**valid, 'verified_files': -1}, {**valid, 'unverified_files': 1},
                 {**valid, 'reasons': {'unrecognized_future_reason': 1}}]
        for receipt in cases:
            with self.subTest(receipt=receipt):
                result['parse_coverage'] = receipt
                self.assertIsNone(sm.recorded_parse_coverage(receipt, result['sitemaps_fetched']))
                self.assertNotIn('Sitemap looks healthy', validate_sitemap.render_markdown(result))

    def test_index_and_field_namespaces_do_not_resolve_remote_resources(self):
        body = ('<s:sitemapindex xmlns:s="' + NS + '"><s:sitemap><s:loc>'
                + BASE + 'child.xml</s:loc><s:lastmod>2026-10-15</s:lastmod></s:sitemap></s:sitemapindex>')
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No namespace I/O')):
            kind, entries, problem = sm.parse_checked(body)
        self.assertEqual('index', kind)
        self.assertEqual([{'loc': BASE + 'child.xml', 'lastmod': '2026-10-15'}], entries)
        self.assertIsNone(problem)

    def test_planner_treats_parser_gaps_as_manual_verification_not_source_rewrite(self):
        result, _ = analyze('<feed/>')
        report = {'schema_version': '2.0', 'site': BASE, 'overall_score': 90,
                  'homepage': {'url': BASE, 'score': 90, 'findings': []},
                  'crawl': {}, 'sitemap': result}
        repo = Path(__file__).resolve().parent / 'fixtures/planner/plain_html'
        output = plan.build_plan(report, str(repo))
        action = next(a for a in output['actions'] if a['rule_id'] == 'technical.sitemap.extraction.unverified')
        self.assertTrue(action['manual_action'])
        self.assertEqual('manual_external', action['safety'])
        self.assertIn('Do not rewrite', action['proposed_change'])


if __name__ == '__main__':
    unittest.main()
