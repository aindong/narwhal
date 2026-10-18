"""Extraction uncertainty must not authorize duplicate-schema remediation."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_schema
import plan
from lib import htmlx, microdata, ecommerce
from lib.report import Report

URL = 'https://example.test/guide'
FIXTURE = Path(__file__).parent / 'fixtures/planner/plain_html'
THING = '<div itemscope itemtype="https://schema.org/Thing"></div>'
HIDDEN_TYPES = ('<div itemscope itemtype="https://schema.org/Article"></div>'
                '<div itemscope itemtype="https://schema.org/Organization"></div>')
MERCHANT = '<meta property="og:type" content="product"><meta property="product:price:amount" content="19.99">'
ABSENCE = plan.SCHEMA_ABSENCE_RULES


def page(source, parser=htmlx._parse_stdlib, ignore=None):
    doc = parser('<article><h1>A guide</h1><p>Useful reader instructions.</p>' + source + '</article>', URL)
    report = Report(URL, fetched_status=200, ignore=ignore)
    audit_schema.audit(doc, None, report, {})
    return report


def partial(ignore=None):
    with mock.patch.object(microdata, 'MAX_ITEMS', 2):
        return page(THING * 2 + HIDDEN_TYPES, ignore=ignore)


def payload(report):
    return json.loads(report.to_json())


def finding(rule):
    return {'category': 'schema', 'severity': 'low', 'rule_id': rule, 'title': rule,
            'recommendation': 'LEGACY_ADD_DUPLICATE_MARKUP'}


class TestPageSchemaReview(unittest.TestCase):
    def test_actual_default_element_cap_does_not_become_a_no_markup_penalty(self):
        report = page('<div></div>' * 50000 + HIDDEN_TYPES)
        self.assertEqual('unverified', report.meta['structured_data']['extraction_coverage']['status'])
        self.assertFalse(ABSENCE & {f.rule_id for f in report.findings})
        self.assertTrue(any(f.rule_id == 'schema.microdata.extraction' for f in report.findings))

    def test_actual_default_item_cap_does_not_recommend_hidden_article_and_organization(self):
        report = page(THING * 1000 + HIDDEN_TYPES)
        self.assertFalse(ABSENCE & {f.rule_id for f in report.findings})
        self.assertIn('Thing', report.meta['structured_data']['types_by_format']['microdata'])

    def test_unsupported_rdfa_subtree_is_verification_not_missing_markup(self):
        report = page('<div vocab="https://schema.org/" typeof="Article" rel="offers">'
                      '<span typeof="Organization"></span></div>')
        self.assertTrue(report.meta['structured_data']['rdfa_warnings'])
        self.assertFalse(ABSENCE & {f.rule_id for f in report.findings})

    def test_jsonld_parse_errors_are_retained_without_absence_advice(self):
        report = page('<script type="application/ld+json">{bad</script>')
        rules = {f.rule_id for f in report.findings}
        self.assertIn('schema.invalid.json.ld', rules)
        self.assertFalse(ABSENCE & rules)

    def test_observed_defective_nodes_still_get_property_checks_with_partial_extraction(self):
        with mock.patch.object(microdata, 'MAX_ITEMS', 2):
            report = page('<div itemscope itemtype="https://schema.org/Recipe"></div>' + THING * 2)
        rules = {f.rule_id for f in report.findings}
        self.assertIn("schema.recipe.missing.required.name", rules)
        self.assertIn("schema.recipe.missing.required.image", rules)
        self.assertFalse(ABSENCE & rules)

    def test_supported_no_markup_review_keeps_legacy_id_and_severity_without_feature_promises(self):
        report = page('')
        absent, = [f for f in report.findings if f.rule_id == 'schema.no.structured.data']
        self.assertEqual('medium', absent.severity)
        self.assertIn('supported subset', absent.detail)
        self.assertIn('before adding applicable semantic markup', absent.recommendation)
        self.assertNotIn('unlock rich results', absent.recommendation)
        self.assertIn('benefits are not established', absent.recommendation)

    def test_article_and_site_entity_candidates_remain_conditional_on_clean_extraction(self):
        report = page(THING)
        selected = [f for f in report.findings if f.rule_id in ABSENCE]
        self.assertEqual(2, len(selected))
        self.assertTrue(all(f.severity == 'low' for f in selected))
        self.assertTrue(all('Review' in f.recommendation for f in selected))
        self.assertIn('not a whole-site identity', next(f.detail for f in selected if 'organization' in f.rule_id))

    def test_supported_formats_do_not_require_reencoding_to_jsonld(self):
        sources = ('<script type="application/ld+json">{"@type":"Article"}</script>',
                   '<div itemscope itemtype="https://schema.org/Article"></div>',
                   '<div vocab="https://schema.org/" typeof="Article"></div>')
        for source in sources:
            report = page(source)
            self.assertNotIn('schema.no.structured.data', {f.rule_id for f in report.findings})
            self.assertNotIn('schema.article.like.page.without.article.schema', {f.rule_id for f in report.findings})

    def test_product_after_actual_default_item_limit_is_not_an_absent_product(self):
        report = page(MERCHANT + THING * 1000 + '<div itemscope itemtype="https://schema.org/Product"></div>')
        self.assertTrue(report.meta['ecommerce']['is_product'])
        self.assertTrue(report.meta['ecommerce']['is_merchant'])
        self.assertFalse(ABSENCE & {f.rule_id for f in report.findings})

    def test_healthy_product_nonobservation_keeps_id_severity_and_conditional_advice(self):
        report = page(MERCHANT)
        candidate, = [f for f in report.findings if f.rule_id == 'schema.ecommerce.product.missing']
        self.assertEqual('high', candidate.severity)
        self.assertIn('Review existing markup before adding', candidate.recommendation)
        self.assertIn('supported subset', candidate.detail)

    def test_standalone_ecommerce_audit_also_checks_actual_jsonld_errors(self):
        doc = htmlx._parse_stdlib(MERCHANT + '<script type="application/ld+json">{bad</script>', URL)
        report = Report(URL)
        meta = ecommerce.audit(doc, report)
        self.assertTrue(meta['is_product'])
        self.assertNotIn('schema.ecommerce.product.missing', {f.rule_id for f in report.findings})

    def test_observed_product_invalid_values_remain_checked_with_other_jsonld_errors(self):
        report = page('<script type="application/ld+json">{"@type":"Product","name":"Shoe","url":"not-a-url"}</script>'
                      '<script type="application/ld+json">{bad</script>')
        self.assertIn('schema.ecommerce.product.invalid.url', {f.rule_id for f in report.findings})
        self.assertTrue(report.meta['ecommerce']['is_product'])

    def test_optional_parser_path_preserves_the_guard(self):
        for parser in (htmlx._parse_stdlib, htmlx.parse):
            with mock.patch.object(microdata, 'MAX_ITEMS', 2):
                report = page(THING * 2 + HIDDEN_TYPES, parser=parser)
            self.assertFalse(ABSENCE & {f.rule_id for f in report.findings})

    def test_metadata_survives_ignored_findings_and_produces_manual_plan_task(self):
        report = partial(ignore=lambda *args: True)
        self.assertEqual([], report.findings)
        result = plan.build_plan(payload(report), str(FIXTURE))
        action, = result['actions']
        self.assertEqual('schema.extraction.unverified', action['rule_id'])
        self.assertEqual('manual_external', action['safety'])
        self.assertTrue(action['manual_action'])
        self.assertEqual([], action['likely_files'])
        self.assertFalse(action['requires_deploy'])
        self.assertIn('Do not add or duplicate markup', action['proposed_change'])

    def test_legacy_known_warning_with_stale_absence_advice_cannot_authorize_generation(self):
        for warning in ('microdata_warnings', 'rdfa_warnings'):
            value = {'url': URL, 'findings': [finding(rule) for rule in ABSENCE],
                     'meta': {'structured_data': {warning: ['budget reached']}}}
            result = plan.build_plan(value, str(FIXTURE))
            self.assertFalse(ABSENCE & {a['rule_id'] for a in result['actions']})
            self.assertNotIn('LEGACY_ADD_DUPLICATE_MARKUP', plan.render_markdown(result))

    def test_explicit_old_jsonld_error_is_enough_to_withhold_stale_absence_advice(self):
        value = {'url': URL, 'findings': [finding('schema.invalid.json.ld'), finding('schema.no.structured.data')]}
        result = plan.build_plan(value, str(FIXTURE))
        actions = {a['rule_id']: a for a in result['actions']}
        self.assertNotIn('schema.no.structured.data', actions)
        self.assertEqual('review_required', actions['schema.invalid.json.ld']['safety'])
        self.assertTrue(actions['schema.invalid.json.ld']['likely_files'])
        self.assertEqual('manual_external', actions['schema.extraction.unverified']['safety'])

    def test_extraction_warnings_are_verification_only_not_grouped_template_edits(self):
        value = {'url': URL, 'findings': [finding(rule) for rule in (
            'schema.microdata.extraction', 'schema.rdfa.extraction', 'schema.ecommerce.source.extraction')]}
        result = plan.build_plan(value, str(FIXTURE))
        self.assertTrue(all(a['safety'] == 'manual_external' and not a['likely_files'] for a in result['actions']))
        self.assertEqual([], result['groups'])
        self.assertIn('not assigned (verification only)', plan.render_markdown(result))
        self.assertEqual(3, len(result['actions']))
        self.assertNotIn('schema.extraction.unverified', {a['rule_id'] for a in result['actions']})

    def test_actual_observed_property_repairs_remain_reviewable_with_uncertainty(self):
        report = page('<script type="application/ld+json">{"@type":"Recipe"}</script>'
                      '<script type="application/ld+json">{bad</script>')
        result = plan.build_plan(payload(report), str(FIXTURE))
        repairs = [a for a in result['actions'] if a['rule_id'].startswith('schema.recipe.missing.required.')]
        self.assertEqual(2, len(repairs))
        self.assertTrue(all(a['safety'] == 'review_required' and a['likely_files'] for a in repairs))

    def test_audit_uncertain_leaf_suppresses_only_unlocatable_rollup_absence_not_clean_homepage_candidate(self):
        hp = payload(page(THING))
        value = {'homepage': hp, 'site': URL, 'crawl': {
            'pages': [{'url': URL + '/leaf', 'schema_extraction_unverified': True}],
            'recurring': [finding('schema.no.structured.data')]}, 'sitemap': {}}
        result = plan.build_plan(value, str(FIXTURE))
        rules = {a['rule_id'] for a in result['actions']}
        self.assertNotIn('schema.no.structured.data', rules)
        self.assertIn('schema.no.organization.website.entity', rules)
        self.assertIn('schema.extraction.unverified', rules)

    def test_old_audit_rollup_error_alone_does_not_become_an_absence_fix(self):
        value = {'homepage': payload(page(THING)), 'site': URL,
                 'crawl': {'recurring': [finding('schema.rdfa.extraction'), finding('schema.no.structured.data')]},
                 'sitemap': {}}
        result = plan.build_plan(value, str(FIXTURE))
        self.assertNotIn('schema.no.structured.data', {a['rule_id'] for a in result['actions']})

    def test_homepage_warning_does_not_hide_metadata_only_uncertain_leaf(self):
        value = {'homepage': payload(partial()), 'site': URL,
                 'crawl': {'pages': [{'schema_extraction_unverified': True}], 'recurring': []}, 'sitemap': {}}
        result = plan.build_plan(value, str(FIXTURE))
        actions = {a['rule_id']: a for a in result['actions']}
        self.assertEqual('page', actions['schema.microdata.extraction']['scope'])
        self.assertEqual('site', actions['schema.extraction.unverified']['scope'])
        self.assertIn('crawl sample/rollup', actions['schema.extraction.unverified']['evidence'])
        text = plan.render_markdown(result)
        self.assertIn('Verification scope:** Page report', text)
        self.assertIn('Verification scope:** Site sample/rollup', text)

    def test_rollup_warning_does_not_hide_metadata_only_uncertain_homepage(self):
        value = {'homepage': payload(partial(ignore=lambda *args: True)), 'site': URL,
                 'crawl': {'recurring': [finding('schema.rdfa.extraction')]}, 'sitemap': {}}
        result = plan.build_plan(value, str(FIXTURE))
        actions = {a['rule_id']: a for a in result['actions']}
        self.assertEqual('site', actions['schema.rdfa.extraction']['scope'])
        self.assertEqual('page', actions['schema.extraction.unverified']['scope'])
        self.assertIn('page report', actions['schema.extraction.unverified']['evidence'])

    def test_same_explicit_warning_in_both_scopes_coalesces_to_one_site_task(self):
        warning = finding('schema.microdata.extraction')
        warning['count'] = 3
        value = {'homepage': payload(partial()), 'site': URL,
                 'crawl': {'recurring': [warning]}, 'sitemap': {}}
        result = plan.build_plan(value, str(FIXTURE))
        action, = result['actions']
        self.assertEqual('schema.microdata.extraction', action['rule_id'])
        self.assertEqual(('site', 3), (action['scope'], action['occurrences']))

    def test_metadata_only_uncertainty_in_both_scopes_needs_one_task_covering_both(self):
        value = {'homepage': payload(partial(ignore=lambda *args: True)), 'site': URL,
                 'crawl': {'pages': [{'schema_extraction_unverified': True}]}, 'sitemap': {}}
        result = plan.build_plan(value, str(FIXTURE))
        action, = result['actions']
        self.assertEqual(('schema.extraction.unverified', 'site'), (action['rule_id'], action['scope']))
        self.assertIn('page report and crawl sample/rollup', action['evidence'])

    def test_unsupported_supplied_verification_scope_is_not_rendered_or_coerced(self):
        item = finding('schema.rdfa.extraction')
        item['scope'] = ['<img src="https://evil.test/pixel">']
        result = plan.build_plan({'url': URL, 'findings': [item]}, str(FIXTURE))
        text = plan.render_markdown(result)
        self.assertIn('Verification scope:** Unrecorded scope', text)
        self.assertNotIn('evil.test', text)

    def test_clean_homepage_unknown_crawl_flags_do_not_invent_extraction_failures(self):
        for flag in (None, False, 0, 1, 'true'):
            value = {'homepage': payload(page(THING)), 'site': URL,
                     'crawl': {'pages': [{'schema_extraction_unverified': flag}]}, 'sitemap': {}}
            result = plan.build_plan(value, str(FIXTURE))
            self.assertNotIn('schema.extraction.unverified', {a['rule_id'] for a in result['actions']})

    def test_absent_legacy_metadata_is_not_certified_or_fabricated_as_an_extraction_error(self):
        value = {'url': URL, 'findings': [finding('schema.no.structured.data')]}
        result = plan.build_plan(value, str(FIXTURE))
        action, = result['actions']
        self.assertEqual('review_required', action['safety'])
        self.assertIn('Non-observation does not prove', action['proposed_change'])

    def test_documented_legacy_jsonld_absence_id_is_withheld_on_known_extraction_warning(self):
        value = {'url': URL, 'findings': [finding('schema.no.structured.data.json.ld')],
                 'meta': {'structured_data': {'rdfa_warnings': ['unsupported relation']}}}
        result = plan.build_plan(value, str(FIXTURE))
        self.assertNotIn('schema.no.structured.data.json.ld', {a['rule_id'] for a in result['actions']})
        self.assertTrue(all(a['manual_action'] for a in result['actions']))

    def test_documented_legacy_absence_without_coverage_remains_conditional_review(self):
        value = {'url': URL, 'findings': [finding('schema.no.structured.data.json.ld')]}
        result = plan.build_plan(value, str(FIXTURE))
        action, = result['actions']
        self.assertEqual('review_required', action['safety'])
        self.assertIn('Non-observation does not prove', action['proposed_change'])

    def test_unsupported_supplied_receipt_does_not_authorize_absence_remediation(self):
        value = {'url': URL, 'findings': [finding('schema.no.structured.data')],
                 'meta': {'structured_data': {'extraction_coverage': None}}}
        result = plan.build_plan(value, str(FIXTURE))
        self.assertNotIn('schema.no.structured.data', {a['rule_id'] for a in result['actions']})
        self.assertIn('schema.extraction.unverified', {a['rule_id'] for a in result['actions']})

    def test_focused_non_schema_scope_does_not_get_a_false_task_from_unrelated_metadata(self):
        value = {'url': URL, 'findings': [], 'meta': {'scan_scope': {
            'requested': ['content'], 'completed': ['content']},
            'structured_data': {'extraction_coverage': None}}}
        result = plan.build_plan(value, str(FIXTURE))
        self.assertNotIn('schema.extraction.unverified', {a['rule_id'] for a in result['actions']})

    def test_plan_is_offline_readonly_and_repeatable(self):
        value = payload(partial())
        before = copy.deepcopy(value)
        files = {p: p.read_bytes() for p in FIXTURE.rglob('*') if p.is_file()}
        with mock.patch('socket.socket', side_effect=AssertionError('No network')):
            first = plan.build_plan(value, str(FIXTURE))
            second = plan.build_plan(value, str(FIXTURE))
            plan.render_markdown(first)
        self.assertEqual(first, second)
        self.assertEqual(before, value)
        self.assertEqual(files, {p: p.read_bytes() for p in files})


if __name__ == '__main__':
    unittest.main()
