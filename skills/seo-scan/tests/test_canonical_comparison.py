"""Canonical component observations, not resource/search-selection proofs."""
import copy
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit
import audit_technical
import brief
import compare
import crawl_site
import diff_scan
import plan
import scan
from lib import canonical, htmlx, http
from lib.report import Report

URL = 'https://example.test/guide'
UNVERIFIED = 'technical.canonical.comparison.unverified'
SELF = 'technical.self.referencing.canonical'
ELSEWHERE = 'technical.canonical.points.elsewhere'
FIXTURE = Path(__file__).parent / 'fixtures/planner/plain_html'


def measured(href, url=URL, prefix='', parser=htmlx._parse_stdlib):
    markup = prefix + '<link rel="canonical" href="' + href + '"><p>Controlled example.</p>'
    doc = parser(markup, url)
    response = http.Response(url, url, 200, {'content-type': 'text/html'}, markup, 0)
    report = Report(url, final_url=url, fetched_status=200)
    audit_technical._canonical(doc, response, report)
    return doc, report


DISTINCT = [
    ('https://example.test/Product', 'https://example.test/product'),
    ('https://example.test/p?id=1', 'https://example.test/p?id=2'),
    ('https://example.test/p?id=A', 'https://example.test/p?id=a'),
    ('https://example.test/p', 'http://example.test/p'),
    ('https://example.test/p', 'https://example.test/p/'),
    ('https://example.test/p', 'https://example.test/p//'),
    ('https://example.test/p', 'https://example.test:8443/p'),
    ('https://example.test/p', 'https://other.test/p'),
    ('https://example.test/p', 'https://example.test/p?'),
    ('https://example.test/p', 'https://example.test/p#'),
    ('https://example.test/p', 'https://example.test/p#part'),
    ('https://example.test/a%2Fb', 'https://example.test/a/b'),
    ('https://example.test/p?x=1&y=2', 'https://example.test/p?y=2&x=1'),
    ('https://example.test/p;one', 'https://example.test/p;two'),
]
EQUIVALENT = [
    ('https://example.test/p', 'HTTPS://EXAMPLE.TEST:443/p'),
    ('http://example.test/p', 'http://example.test:80/p'),
    ('https://example.test', 'https://example.test/'),
    ('http://example.test:/', 'http://example.test/'),
    ('https://example.test/~user', 'https://example.test/%7euser'),
    ('https://example.test/a%2Fb', 'https://example.test/a%2fb'),
    ('https://example.test/p?x=~', 'https://example.test/p?x=%7e'),
    ('https://example.test/p#~', 'https://example.test/p#%7e'),
    ('https://example.test/a/b', 'https://example.test/a/./b'),
    ('https://example.test/a/b', 'https://example.test/a/c/../b'),
    ('https://example.test/a/', 'https://example.test/a/b/..'),
    ('https://example.test/', 'https://example.test/../../'),
    ('https://example.test/a/b', 'https://example.test/a/%2E/b'),
]


class TestCanonicalComparison(unittest.TestCase):
    def test_distinct_components_do_not_pass_as_self_referencing(self):
        for current, target in DISTINCT:
            with self.subTest(current=current, target=target):
                self.assertNotEqual(canonical.key(current), canonical.key(target))
                for parser in (htmlx._parse_stdlib, htmlx.parse):
                    doc, report = measured(target, current, parser=parser)
                    finding, = report.findings
                    self.assertEqual(ELSEWHERE, finding.rule_id)
                    self.assertEqual('low', finding.severity)
                    self.assertEqual('differs', report.meta['canonical_comparison']['status'])
                    self.assertIn('Differing components:', finding.detail)

    def test_standard_normalizations_match_in_both_parser_paths(self):
        for current, target in EQUIVALENT:
            with self.subTest(current=current, target=target):
                self.assertIsNotNone(canonical.key(current))
                self.assertEqual(canonical.key(current), canonical.key(target))
                for parser in (htmlx._parse_stdlib, htmlx.parse):
                    doc, report = measured(target, current, parser=parser)
                    self.assertEqual([SELF], [f.rule_id for f in report.findings])
                    self.assertEqual('matches', report.meta['canonical_comparison']['status'])

    def test_duplicate_clusters_use_the_same_component_identity(self):
        for pairs, expected in ((DISTINCT, False), (EQUIVALENT, True)):
            for a, b in pairs:
                pages = [{'url': 'one', 'fingerprint': 12345, 'canonical': a},
                         {'url': 'two', 'fingerprint': 12345, 'canonical': b}]
                cluster, = crawl_site.find_duplicates(pages, 90)
                self.assertIs(expected, cluster['canonical_ok'], (a, b))

    def test_missing_and_malformed_cluster_targets_do_not_certify_consistency(self):
        for target in (None, '', 'mailto:owner@example.test', 'https://[', 'https://example.test:bad/p'):
            pages = [{'url': 'one', 'fingerprint': 12345, 'canonical': target},
                     {'url': 'two', 'fingerprint': 12345, 'canonical': target}]
            self.assertFalse(crawl_site.find_duplicates(pages, 90)[0]['canonical_ok'])

    def test_dot_normalization_preserves_repeated_path_separators(self):
        for path, expected in (('/a//b', '/a//b'), ('/a//.', '/a//'),
                               ('/a//../b', '/a/b'), ('/a/../', '/'), ('/.', '/')):
            self.assertEqual(expected, canonical.key('https://example.test' + path)[3])

    def test_relative_canonical_uses_first_active_href_base_in_both_parsers(self):
        prefix = ('<template><base href="https://fake.test/"></template><base target="_blank">'
                  '<base href="https://example.test/docs/"><base href="https://ignored.test/">')
        for parser in (htmlx._parse_stdlib, htmlx.parse):
            doc, report = measured('../guide', prefix=prefix, parser=parser)
            self.assertEqual(URL, doc.canonical())
            self.assertEqual([SELF], [f.rule_id for f in report.findings])

    def test_relative_base_is_resolved_against_final_document_url(self):
        doc, report = measured('page', 'https://example.test/docs/page', '<base href="./">')
        self.assertEqual('https://example.test/docs/page', doc.canonical())
        self.assertEqual([SELF], [f.rule_id for f in report.findings])

    def test_explicit_empty_query_and_fragment_survive_resolution(self):
        for href, expected in (('?', URL + '?'), ('#', URL + '?old=1#'), ('?#', URL + '?#')):
            doc, report = measured(href, URL + '?old=1')
            self.assertEqual(expected, doc.canonical())
            self.assertEqual([ELSEWHERE], [f.rule_id for f in report.findings])

    def test_inherited_empty_query_is_preserved_for_fragment_and_empty_base_references(self):
        doc, report = measured('#part', URL + '?')
        self.assertEqual(URL + '?#part', doc.canonical())
        doc, report = measured('#part', URL + '?', '<base href="">')
        self.assertEqual(URL + '?#part', doc.canonical())
        self.assertEqual(URL + '?', canonical.resolve(URL + '?', '?'))
        self.assertEqual(URL + '?x=?#part', canonical.resolve(URL + '?x=?', '#part'))

    def test_same_scheme_references_without_authority_are_not_repaired_into_matches(self):
        for href in ('https:guide', 'https:/guide', 'https:'):
            doc, report = measured(href)
            self.assertEqual(href, doc.canonical())
            self.assertTrue(canonical.unverified(report.meta))
        self.assertTrue(canonical.unverified(measured('guide', prefix='<base href="https:">')[1].meta))

    def test_relative_resolution_preserves_repeated_separators_and_explicit_authority(self):
        doc, report = measured('b//c', 'https://example.test/a/b/c', '<base href="/a/">')
        self.assertEqual('https://example.test/a/b//c', doc.canonical())
        self.assertEqual('differs', report.meta['canonical_comparison']['status'])
        self.assertTrue(canonical.unverified(measured('///guide')[1].meta))
        doc, report = measured('//example.test/guide')
        self.assertEqual(URL, doc.canonical())
        self.assertEqual('matches', report.meta['canonical_comparison']['status'])

    def test_empty_base_and_absolute_canonical_are_not_lost(self):
        self.assertEqual(URL, measured(URL, prefix='<base href="">')[0].canonical())
        self.assertEqual(URL, measured(URL, prefix='<base href="https://[">')[0].canonical())

    def test_base_extraction_is_cached_but_programmatic_document_base_stays_live(self):
        doc = htmlx._parse_stdlib('<base href="./"><link rel="canonical" href="page">', URL)
        with mock.patch.object(canonical, 'first_base', wraps=canonical.first_base) as extract:
            self.assertEqual('https://example.test/page', doc.canonical())
            doc.base_url = 'https://other.test/docs/guide'
            self.assertEqual('https://other.test/docs/page', doc.canonical())
            self.assertEqual(1, extract.call_count)

    def test_unsupported_and_malformed_declarations_are_review_notes_not_absence(self):
        for href in ('', '   ', 'mailto:owner@example.test', 'https://[', 'https://example.test:bad/p',
                     'https://example.test:99999/p', 'https://example.test/a b', 'https://example.test/%zz',
                     'https://user:password@example.test/p'):
            with self.subTest(href=href):
                doc, report = measured(href)
                self.assertEqual([UNVERIFIED], [f.rule_id for f in report.findings])
                self.assertTrue(canonical.unverified(report.meta))
                self.assertIn(canonical.ERROR, report._scope_note())
                self.assertNotIn('technical.no.canonical.url', [f.rule_id for f in report.findings])

    def test_missing_declaration_retains_the_existing_missing_rule(self):
        doc = htmlx._parse_stdlib('<p>No declaration.</p>', URL)
        report = Report(URL)
        audit_technical._canonical(doc, http.Response(URL, URL, 200, {}, '', 0), report)
        self.assertEqual('missing', report.meta['canonical_comparison']['status'])
        self.assertEqual(['technical.no.canonical.url'], [f.rule_id for f in report.findings])

    def test_unknown_receipt_is_not_invented_from_legacy_or_boolean_version(self):
        self.assertFalse(canonical.unverified({}))
        self.assertFalse(canonical.unverified({'canonical_comparison': {'version': True, 'basis': canonical.BASIS, 'status': 'unverified', 'differences': []}}))

    def test_control_repair_and_non_ascii_ports_do_not_create_version_dependent_matches(self):
        for href in ('https://example.test/\nguide', 'https://example.test/\x7fguide',
                     'https://example.test:\uff14\uff14\uff13/guide'):
            doc, report = measured(href)
            self.assertTrue(canonical.unverified(report.meta), repr(href))
        doc, report = measured('guide', prefix='<base href="https://exam\nple.test/">')
        self.assertTrue(canonical.unverified(report.meta))
        self.assertEqual(canonical.key('https://[2001:db8::1]:443/p'), canonical.key('https://[2001:DB8::1]/p'))

    def test_real_scan_retains_malformed_candidate_without_crashing_fingerprint_or_compare(self):
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'},
                                 '<link rel="canonical" href="https://["><p>Controlled sample.</p>', 0)
        with mock.patch.object(http, 'fetch', return_value=response), mock.patch.object(socket, 'socket', side_effect=AssertionError('No network')):
            report = scan.scan(URL, ctx={}, collect_fingerprint=True, check_images=False)
            facts = compare.facts(report, report._doc)
            with mock.patch.object(compare.scanner, 'scan', return_value=report):
                result = compare.run([URL, 'https://rival.test/p'])
                with self.assertRaisesRegex(RuntimeError, 'canonical comparison needs verification'):
                    brief._page(URL)
        self.assertEqual('https://[', report.meta['canonical'])
        self.assertTrue(facts['canonical'])  # candidate presence, not validity
        self.assertIn('canonical comparison unverified', compare._score_cell(facts, 99))
        self.assertTrue(canonical.unverified(report.meta))
        self.assertNotIn('you', result)
        self.assertTrue(all(row['canonical_comparison_unverified'] for row in result['failed']))

    def test_known_unverified_scan_and_crawl_scope_block_diff_fix_claims(self):
        doc, report = measured('https://[')
        report.meta['scan_scope'] = {'requested': ['technical'], 'completed': ['technical']}
        before = json.loads(report.to_json()); after = copy.deepcopy(before)
        after['findings'] = []; after['score'] = 100
        delta = diff_scan.diff_reports(before, after)
        self.assertEqual('incomparable', delta['comparison']['status'])
        self.assertEqual([], delta['resolved'])
        audit_before = {'site': URL, 'homepage': after, 'overall_score': 80,
                        'crawl': {'pages': [{'url': URL, 'canonical_comparison_unverified': True}]}}
        audit_after = copy.deepcopy(audit_before); audit_after['overall_score'] = 100
        delta = diff_scan.diff_reports(audit_before, audit_after)
        self.assertEqual('incomparable', delta['comparison']['status'])

    def test_unverified_plans_are_manual_without_source_owners_or_duplicate_generation(self):
        doc, report = measured('https://[')
        result = plan.build_plan(json.loads(report.to_json()), str(FIXTURE))
        action, = result['actions']
        self.assertEqual('canonical', action['artifact'])
        self.assertEqual('manual_external', action['safety'])
        self.assertEqual([], action['likely_files'])
        self.assertIn('do not add duplicate', action['proposed_change'])

    def test_different_target_plans_preserve_intended_variants_not_force_self_reference(self):
        doc, report = measured(URL + '?variant=one')
        result = plan.build_plan(json.loads(report.to_json()), str(FIXTURE))
        action, = result['actions']
        self.assertEqual('canonical', action['artifact'])
        self.assertEqual('review_required', action['safety'])
        self.assertIn('Preserve intended consolidation', action['proposed_change'])
        self.assertIn('Do not force self-reference', action['proposed_change'])

    def test_actual_crawl_propagates_unverified_scope_into_audit_markdown_and_html(self):
        doc, report = measured('https://[')
        with mock.patch.object(crawl_site.scanner, 'gather_context', return_value={}), \
                mock.patch.object(crawl_site, 'discover', return_value=[URL]), \
                mock.patch.object(crawl_site.scanner, 'scan', return_value=report), \
                mock.patch.object(socket, 'socket', side_effect=AssertionError('No network')):
            site = crawl_site.crawl(URL, max_pages=1, concurrency=1)
        self.assertTrue(site['pages'][0]['canonical_comparison_unverified'])
        data = {'site': URL, 'page': Report(URL), 'site_result': site, 'sitemap': {'start': URL, 'seeds': []}}
        for output in (crawl_site.render_markdown(site), audit.render_markdown(data), audit.render_html(data)):
            self.assertIn('HTML canonical comparison needs verification on 1 scanned page(s)', output)
            self.assertIn('technical/overall score comparisons', output)

    def test_duplicate_guidance_does_not_require_consolidating_every_similar_page(self):
        pages = [{'url': URL, 'fingerprint': 12345, 'canonical': URL + '?one'},
                 {'url': URL + '/two', 'fingerprint': 12345, 'canonical': URL + '?two'}]
        site = {'base': URL, 'pages_scanned': 2, 'avg_score': 99, 'pages': [],
                'recurring': {}, 'duplicates': crawl_site.find_duplicates(pages, 90)}
        output = crawl_site.render_markdown(site)
        self.assertIn('preserve intentional distinct pages', output)
        self.assertNotIn('pick one URL per cluster', output)

    def test_rendering_keeps_literal_target_evidence_and_comparison_limits(self):
        doc, report = measured('/other?x=&lt;script&gt;window.canonicalProbe=1&lt;/script&gt;')
        before = report.to_json()
        for output in (report.to_markdown(), report.to_html()):
            self.assertIn('Review unverified canonical comparison', output)
            self.assertIn('do not add a duplicate canonical', output)
        self.assertIn('No target fetch', report.to_json())
        self.assertNotIn('<script>window.canonicalProbe=1</script>', report.to_html())
        self.assertIn('`https://example.test/other?x=<script>', report.to_markdown())
        self.assertEqual(before, report.to_json())

    def test_comparison_does_not_fetch_or_authorize_private_targets(self):
        with mock.patch.object(http, 'fetch', side_effect=AssertionError('No target fetch')), \
                mock.patch.object(socket, 'socket', side_effect=AssertionError('No DNS/network')):
            doc, report = measured('http://127.0.0.1/private')
        self.assertEqual([ELSEWHERE], [f.rule_id for f in report.findings])
        self.assertIsNotNone(canonical.key(doc.canonical()))  # comparison key is not a fetch guard


if __name__ == '__main__': unittest.main()
