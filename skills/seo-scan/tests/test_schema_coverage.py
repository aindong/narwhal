"""Extractor limits/errors cannot certify schema absence or score improvements."""
import copy
from collections import Counter
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_schema
import audit
import brief
import compare
import crawl_site
import diff_scan
import scan
from lib import htmlx, http, microdata, rdfa, schema_coverage as coverage
from lib.report import Report, md_to_html, recorded_schema_extraction_problem

RECIPE = ('<div itemscope itemtype="https://schema.org/Recipe"><span itemprop="name">Soup</span>'
          '<meta itemprop="image" content="https://example.test/soup.jpg"></div>')
THING = '<div itemscope itemtype="https://schema.org/Thing"></div>'


def page(name, markup='', parser=htmlx._parse_stdlib, ignore=None):
    url = 'https://' + name + '.test/guide'
    doc = parser('<h1>Guide</h1><p>Useful reader instructions.</p>' + markup, url)
    report = Report(url, fetched_status=200, ignore=ignore)
    audit_schema.audit(doc, None, report, {})
    return {'url': url, 'facts': compare.facts(report, doc), 'headings': doc.headings, 'text': doc.body_text}, report


def scan_page(source, only=None):
    url = 'https://example.test/guide'
    response = http.Response(url, url, 200, {'content-type': 'text/html'}, source, 1)
    with mock.patch.object(scan.http, 'fetch', return_value=response):
        return scan.scan(url, only=only or ['schema'], ctx={'sitemap_found': True, 'llms_txt': True}, check_images=False)


def comparison(you, rival):
    return {'you': you['facts'], 'competitors': [rival['facts']], 'failed': [],
            **compare.gap_analysis(you['facts'], [rival['facts']])}


class TestSchemaCoverage(unittest.TestCase):
    def setUp(self):
        self.clean, self.clean_report = page('clean', RECIPE)
        self.empty, _ = page('empty')
        with mock.patch.object(microdata, 'MAX_ITEMS', 2):
            self.partial, self.partial_report = page('partial', THING * 2 + RECIPE)

    def test_actual_default_item_budget_counterexample_withholds_false_absence_gap(self):
        you, report = page('large', THING * microdata.MAX_ITEMS + RECIPE)
        self.assertNotIn('Recipe', you['facts']['schema_types'])
        self.assertTrue(report.meta['structured_data']['microdata_warnings'])
        self.assertEqual('unverified', coverage.fact_state(you['facts']))
        result = comparison(you, self.clean)
        self.assertNotIn('Schema types: Recipe', [g['what'] for g in result['gaps']])
        self.assertEqual('unverified', result['schema_comparison']['status'])

    def test_observed_types_scores_and_page_findings_are_not_removed(self):
        self.assertEqual(['Thing'], self.partial['facts']['schema_types'])
        self.assertEqual(self.partial_report.score(), self.partial['facts']['score'])
        self.assertTrue(any(f.rule_id == 'schema.microdata.extraction' for f in self.partial_report.findings))
        receipt = self.partial['facts']['schema_extraction']
        self.assertEqual(receipt, self.partial_report.meta['structured_data']['extraction_coverage'])
        self.assertGreater(receipt['microdata_warning_details'], 0)

    def test_clean_supported_subset_still_allows_conditional_schema_gap_review(self):
        result = comparison(self.empty, self.clean)
        self.assertIn('Schema types: Recipe', [g['what'] for g in result['gaps']])
        self.assertEqual('no_known_problem', result['schema_comparison']['status'])
        self.assertIn('No known problem is not proof of exhaustive extraction', coverage.LIMITS)

    def test_positive_observations_on_partial_rival_are_preserved_without_absence_certification(self):
        result = comparison(self.empty, self.partial)
        self.assertIn('Schema types: Thing', [g['what'] for g in result['gaps']])
        self.assertEqual('unverified', result['schema_comparison']['status'])

    def test_schema_only_you_have_leads_require_known_supported_extraction_on_all_pages(self):
        result = comparison(self.clean, self.partial)
        self.assertFalse(any(g['what'].startswith('Schema types only you have:') for g in result['leads']))
        known = comparison(self.clean, self.empty)
        self.assertTrue(any(g['what'].startswith('Schema types only you have:') for g in known['leads']))

    def test_partial_own_page_keeps_candidates_but_marks_existing_markup_unverified(self):
        data = brief.synthesize(self.partial, [self.clean], None)
        recipe, = [s for s in data['schema'] if s['type'] == 'Recipe']
        self.assertEqual('unverified', recipe['existing_markup_status'])
        self.assertIn('inspect before adding or duplicating', recipe['reason'])
        self.assertIn('Existing own-page markup is unverified', brief.render_markdown(data))

    def test_topic_mode_does_not_invent_an_own_page_or_claim_existing_markup_absence(self):
        data = brief.synthesize(None, [self.partial], None, topic='A guide')
        self.assertEqual('not_supplied', data['schema_comparison']['your_status'])
        self.assertTrue(all(s['existing_markup_status'] == 'not_applicable' for s in data['schema']))
        self.assertNotIn('Your page —', brief.render_markdown(data))

    def test_jsonld_parse_and_processing_errors_are_explicit_coverage_problems(self):
        for markup in ('<script type="application/ld+json">{bad json</script>',
                       '<script type="application/ld+json">' + '[' * 1500 + '0' + ']' * 1500 + '</script>'):
            value, report = page('json-error', markup)
            receipt = value['facts']['schema_extraction']
            self.assertEqual((1, 1), (receipt['jsonld_blocks'], receipt['jsonld_errors']))
            self.assertEqual('unverified', receipt['status'])
            self.assertIsNotNone(recorded_schema_extraction_problem(report.meta))

    def test_valid_jsonld_types_survive_alongside_an_invalid_block(self):
        value, _ = page('mixed', '<script type="application/ld+json">{"@type":"FAQPage"}</script>'
                        '<script type="application/ld+json">{bad</script>')
        self.assertEqual(['FAQPage'], value['facts']['schema_types'])
        self.assertEqual('unverified', coverage.fact_state(value['facts']))

    def test_rdfa_node_limit_is_also_unverified(self):
        source = '<div vocab="https://schema.org/">' + ''.join(
            '<div typeof="Thing" about="#item' + str(i) + '"></div>' for i in range(3)) + '</div>'
        with mock.patch.object(rdfa, 'MAX_NODES', 2):
            value, report = page('rdfa-limit', source)
        self.assertGreater(value['facts']['schema_extraction']['rdfa_warning_details'], 0)
        self.assertIsNotNone(recorded_schema_extraction_problem(report.meta))

    def test_parser_paths_produce_same_limit_receipt(self):
        receipts = []
        for parser in (htmlx._parse_stdlib, htmlx.parse):
            with mock.patch.object(microdata, 'MAX_ITEMS', 2):
                value, _ = page('limited', THING * 2 + RECIPE, parser)
                receipts.append(value['facts']['schema_extraction'])
        self.assertEqual(receipts[0], receipts[1])

    def test_legacy_missing_receipt_and_tool_version_do_not_invent_coverage(self):
        facts = copy.deepcopy(self.empty['facts'])
        del facts['schema_extraction']
        facts['tool_version'] = '1.30.19'
        self.assertEqual('unknown', coverage.fact_state(facts))
        self.assertFalse(coverage.absence_review(facts))
        self.assertEqual('unknown', coverage.comparison(facts, [self.clean['facts']])['status'])

    def test_malformed_counts_markers_and_statuses_are_not_coerced(self):
        for key, bad in (('version', True), ('basis', 'full_schema_validation'), ('source_basis', []),
                         ('source_basis', ''), ('jsonld_blocks', False), ('jsonld_errors', 1),
                         ('rdfa_warning_details', -1), ('microdata_warning_details', 10 ** 100),
                         ('status', 'unverified')):
            receipt = copy.deepcopy(self.empty['facts']['schema_extraction'])
            receipt[key] = bad
            with self.subTest(key=key, bad=bad):
                self.assertIsNone(coverage.recorded(receipt))

    def test_report_scope_note_survives_ignored_extraction_findings(self):
        with mock.patch.object(microdata, 'MAX_ITEMS', 2):
            _, report = page('ignored', THING * 2 + RECIPE, ignore=lambda *args: True)
        self.assertEqual([], report.findings)
        self.assertIn('schema/overall score comparisons are unverified', report.to_markdown())
        self.assertIn('schema/overall score comparisons are unverified', report.to_html())

    def test_focused_non_schema_scan_does_not_get_a_false_score_guard(self):
        report = scan_page('<h1>A guide</h1>', only=['content'])
        self.assertNotIn('schema_extraction_reviewed', report.meta['scan_settings'])
        meta = copy.deepcopy(report.meta)
        meta['structured_data'] = self.partial_report.meta['structured_data']
        self.assertIsNone(recorded_schema_extraction_problem(meta, for_score=True))

    def test_real_scan_flags_are_explicit_bools_only_after_schema_execution(self):
        clean = scan_page(RECIPE)
        broken = scan_page('<script type="application/ld+json">{bad</script>')
        self.assertIs(True, clean.meta['scan_settings']['schema_extraction_reviewed'])
        self.assertIs(False, broken.meta['scan_settings']['schema_extraction_reviewed'])

    def test_matching_unverified_page_diffs_cannot_claim_improvement_or_resolution(self):
        old = json.loads(scan_page('<script type="application/ld+json">{bad</script>').to_json())
        new = copy.deepcopy(old)
        new['score'] = 100
        new['findings'] = []
        result = diff_scan.diff_reports(old, new)
        self.assertEqual('incomparable', result['comparison']['status'])
        self.assertIsNone(result['score_delta'])
        self.assertEqual([], result['resolved'])

    def test_clean_schema_page_diffs_remain_usable(self):
        data = json.loads(scan_page(RECIPE).to_json())
        result = diff_scan.diff_reports(data, data)
        self.assertEqual('comparable', result['comparison']['status'])
        self.assertEqual(0, result['score_delta'])

    def test_known_schema_problems_do_not_block_focused_content_only_diffs(self):
        data = json.loads(scan_page('<h1>Guide</h1>', only=['content']).to_json())
        data['meta']['structured_data'] = self.partial_report.meta['structured_data']
        data['meta']['scan_settings']['schema_extraction_reviewed'] = False
        result = diff_scan.diff_reports(data, data)
        self.assertEqual('comparable', result['comparison']['status'])

    def test_a_claimed_good_flag_cannot_hide_positive_problem_counts(self):
        meta = copy.deepcopy(self.partial_report.meta)
        meta['scan_settings'] = {'schema_extraction_reviewed': True}
        self.assertIsNotNone(recorded_schema_extraction_problem(meta, for_score=True))

    def test_legacy_missing_receipt_without_positive_warning_does_not_certify_or_fabricate_a_problem(self):
        self.assertIsNone(recorded_schema_extraction_problem({'structured_data': {'microdata_warnings': [], 'rdfa_warnings': []}}))
        self.assertEqual('unknown', coverage.fact_state({'schema_types': [], 'tool_version': '1.30.19'}))

    def test_common_crawl_leaf_uncertainty_blocks_audit_overall_diff(self):
        hp = json.loads(scan_page(RECIPE).to_json())
        old = {'site': hp['url'], 'overall_score': 90, 'homepage': hp,
               'crawl': {'pages': [{'url': 'https://example.test/leaf', 'score': 95,
                                   'scan_settings': {'schema_extraction_reviewed': False}}]}}
        new = copy.deepcopy(old)
        new['overall_score'] = 100
        result = diff_scan.diff_reports(old, new)
        self.assertEqual('incomparable', result['comparison']['status'])
        self.assertTrue(any('structured-data extraction' in reason for reason in result['comparison']['reasons']))
        self.assertIsNone(result['score_delta'])

    def test_explicit_legacy_warning_lists_and_unsupported_receipts_are_not_healthy(self):
        for meta in ({'structured_data': {'microdata_warnings': ['item limit']}},
                     {'structured_data': {'rdfa_warnings': ['unsupported relation']}},
                     {'structured_data': {'extraction_coverage': None}},
                     {'scan_settings': {'schema_extraction_reviewed': False}}):
            self.assertIsNotNone(recorded_schema_extraction_problem(meta, for_score=True))
        self.assertIsNone(recorded_schema_extraction_problem({'structured_data': {}}))

    def test_crawl_and_audit_headlines_qualify_known_leaf_extraction_gaps(self):
        site = {'base': 'https://example.test/', 'pages_scanned': 2, 'avg_score': 95,
                'pages': [{'url': 'https://example.test/', 'score': 100},
                          {'url': 'https://example.test/leaf', 'score': 90,
                           'scan_settings': {'schema_extraction_reviewed': False}}], 'recurring': Counter()}
        data = {'site': site['base'], 'page': self.clean_report, 'site_result': site,
                'sitemap': {'start': site['base'], 'seeds': []}}
        before = crawl_site.render_json(site)
        note = crawl_site.schema_extraction_note(site)
        self.assertIn('1 scanned page(s)', note)
        self.assertIn('Raw scores are retained, not proof of improvement', note)
        self.assertLess(crawl_site.render_markdown(site).index(note), crawl_site.render_markdown(site).index('## Weakest pages'))
        self.assertLess(audit.render_markdown(data).index(note), audit.render_markdown(data).index('## 1. Homepage audit'))
        html = audit.render_html(data)
        self.assertLess(html.index(note), html.index('1. Homepage audit'))
        self.assertEqual(before, crawl_site.render_json(site))
        self.assertEqual(95, audit.overall_score(data))

    def test_crawl_warning_flags_are_strict_and_legacy_absence_is_not_a_problem(self):
        for value in (None, False, 0, 1, 'true', [], {}):
            self.assertEqual('', crawl_site.schema_extraction_note({'pages': [{'schema_extraction_unverified': value}]}))
        self.assertEqual('', crawl_site.schema_extraction_note({'pages': [{}]}))
        self.assertIn('1 scanned page(s)', crawl_site.schema_extraction_note({'pages': [
            {'schema_extraction_unverified': True, 'scan_settings': {'schema_extraction_reviewed': False}}]}))

    def test_audit_headline_also_qualifies_homepage_only_uncertainty(self):
        data = {'page': self.partial_report, 'site_result': {'pages': []}}
        self.assertIn('schema/overall score comparisons are unverified', audit._schema_score_note(data))
        data['page'] = self.clean_report
        self.assertEqual('', audit._schema_score_note(data))

    def test_legacy_json_claims_are_not_repeated_as_absence_advice(self):
        data = comparison(self.partial, self.clean)
        data['gaps'].append({'what': 'Schema types: Recipe', 'who': [self.clean['url']], 'action': 'ADD_DUPLICATE_SCHEMA'})
        data['leads'].append({'what': 'Schema types only you have: Thing', 'detail': 'EXCLUSIVE_SCHEMA'})
        text = compare.render_markdown(data)
        self.assertNotIn('ADD_DUPLICATE_SCHEMA', text)
        self.assertNotIn('EXCLUSIVE_SCHEMA', text)
        self.assertIn('absence-based claims are withheld', text)
        self.assertIn('schema extraction unverified', text)

    def test_stale_candidate_absence_flag_cannot_bypass_real_fact_coverage(self):
        data = brief.synthesize(self.partial, [self.clean], None)
        data['schema'][0]['existing_markup_status'] = 'not_observed_in_supported_subset'
        self.assertIn('Existing own-page markup is unverified', brief.render_markdown(data))

    def test_readonly_offline_notes_ignore_untrusted_labels_and_limits(self):
        for value, renderer, serializer in ((comparison(self.partial, self.clean), compare.render_markdown, compare.render_json),
                                            (brief.synthesize(self.partial, [self.clean], None), brief.render_markdown, brief.render_json)):
            before = serializer(value)
            with mock.patch('socket.socket', side_effect=AssertionError('No network')):
                md_to_html(renderer(value))
            self.assertEqual(before, serializer(value))
        facts = copy.deepcopy(self.partial['facts'])
        facts['schema_extraction']['limits'] = '<img src="https://evil.test/pixel">'
        self.assertNotIn('evil.test', ' '.join(coverage.summary(facts, [facts])))
        self.assertIn('unrecorded or unsupported', ' '.join(coverage.summary(None, [{}] * 101)))


if __name__ == '__main__':
    unittest.main()
