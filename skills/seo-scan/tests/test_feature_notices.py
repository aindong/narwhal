"""Google appearance retirement is not schema.org invalidity or ranking proof."""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_schema
import brief
import generate_schema
import scan
from lib import config, htmlx, http
from lib.report import Report

URL = 'https://example.test/faq'


def report(html, ignore=None):
    doc = htmlx.parse(html, URL)
    response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, html, 1)
    result = Report(URL, ignore=ignore)
    audit_schema.audit(doc, response, result, {})
    return result


def page(types):
    return '<script type="application/ld+json">' + json.dumps([{'@type': typ} for typ in types]) + '</script>'


def notices(result):
    return result.meta['structured_data'].get('google_rich_result_notices', [])


class TestFeatureNotices(unittest.TestCase):
    def test_faq_notice_uses_current_retirement_date_not_old_restriction(self):
        result = report(page(['FAQPage']))
        finding = next(f for f in result.findings if f.rule_id == 'schema.deprecated.rich.result.type.faqpage')
        self.assertEqual('low', finding.severity)
        self.assertIn('Google', finding.title)
        self.assertIn('May 7, 2026', finding.detail)
        self.assertNotIn('limited to authoritative', finding.detail)
        self.assertIn('does not invalidate schema.org', finding.recommendation)
        self.assertIn('ranking penalty', finding.recommendation)

    def test_claimreview_preserves_other_consumer_support_with_its_source(self):
        result = report(page(['ClaimReview']))
        finding = next(f for f in result.findings if f.rule_id.endswith('.claimreview'))
        self.assertIn('Fact Check Explorer', finding.detail)
        self.assertIn('2025', finding.detail)
        self.assertIn('/structured-data/factcheck', finding.recommendation)
        self.assertEqual(['https://developers.google.com/search/docs/appearance/structured-data/factcheck'], notices(result)[0]['additional_sources'])

    def test_four_known_features_have_dated_narrow_primary_provenance(self):
        result = report(page(list(audit_schema.DEPRECATED)))
        self.assertEqual(set(audit_schema.DEPRECATED), {n['type'] for n in notices(result)})
        for notice in notices(result):
            self.assertEqual('retired', notice['status'])
            self.assertEqual('2026-10-12', notice['checked_on'])
            self.assertIn('not schema.org validity or ranking', notice['scope'])
            self.assertTrue(notice['source'].startswith('https://developers.google.com/search/'))
            self.assertEqual(audit_schema.DEPRECATED_SOURCES[notice['type']], notice['source'])

    def test_distinct_same_type_nodes_have_one_notice_and_one_scoring_finding(self):
        html = '<script type="application/ld+json">[{"@type":"FAQPage","name":"First"},{"@type":"FAQPage","name":"Second"}]</script>'
        result = report(html)
        self.assertEqual(1, len(notices(result)))
        self.assertEqual(1, len([f for f in result.findings if f.rule_id.endswith('.faqpage')]))

    def test_legacy_and_new_title_ignore_rules_are_honored(self):
        for title in ('Deprecated rich-result type: FAQPage', 'Retired Google rich-result feature: FAQPage'):
            cfg = config.Config({'ignore': {'titles': [title]}})
            result = report(page(['FAQPage']), ignore=cfg.is_ignored)
            self.assertFalse(any(f.rule_id.endswith('.faqpage') for f in result.findings))
            self.assertEqual(1, len(notices(result)))

    def test_feature_sources_are_not_fetched_during_an_audit(self):
        with mock.patch.object(http, 'fetch', side_effect=AssertionError('no feature source fetch allowed')):
            result = report(page(['FAQPage', 'ClaimReview']))
        self.assertEqual(2, len(notices(result)))

    def test_feature_specific_retirement_does_not_retire_shared_schema_types(self):
        result = report(page(['Course', 'Car', 'Book', 'VideoObject', 'Product']))
        self.assertEqual([], notices(result))
        self.assertFalse(any(f.rule_id.startswith('schema.deprecated.rich.result.type.') for f in result.findings))

    def test_all_formats_and_backends_receive_same_google_note(self):
        pages = (page(['FAQPage']), '<div itemscope itemtype="https://schema.org/FAQPage"></div>', '<div vocab="https://schema.org/" typeof="FAQPage"></div>')
        for html in pages:
            outputs = []
            for parser in (htmlx._parse_stdlib, htmlx.parse):
                doc = parser(html, URL)
                result = Report(URL)
                audit_schema.audit(doc, None, result, {})
                outputs.append(notices(result))
                self.assertEqual('FAQPage', notices(result)[0]['type'])
            self.assertEqual(outputs[0], outputs[1])

    def test_html_recommendation_exposes_source_and_scope(self):
        text = report(page(['FAQPage'])).to_html()
        for expected in ('Retired Google rich-result feature: FAQPage', 'Google sources (checked 2026-10-12)', 'https://developers.google.com/search/updates', 'does not invalidate schema.org'):
            self.assertIn(expected, text)
        claim_text = report(page(['ClaimReview'])).to_html()
        self.assertIn('ClaimReview remains supported by Fact Check Explorer', claim_text)

    def test_valid_semantic_faq_generation_and_brief_suggestions_remain_available(self):
        data = generate_schema.build('FAQPage', {'mainEntity': json.dumps([{'@type': 'Question', 'name': 'What is Narwhal?', 'acceptedAnswer': {'@type': 'Answer', 'text': 'A local-first audit toolkit.'}}])})
        self.assertEqual('FAQPage', data['@type'])
        self.assertEqual('Question', data['mainEntity'][0]['@type'])
        suggestions = brief.schema_suggestions(None, [], ['What is Narwhal?'])
        self.assertTrue(any(s['type'] == 'FAQPage' for s in suggestions))

    def test_scan_json_keeps_stable_rule_identity_and_status_metadata(self):
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, page(['FAQPage']), 1)
        with mock.patch.object(scan.http, 'fetch', return_value=response):
            payload = json.loads(scan.scan(URL, only=['schema'], ctx={}, check_images=False).to_json())
        self.assertEqual('retired', payload['meta']['structured_data']['google_rich_result_notices'][0]['status'])
        self.assertTrue(any(f['rule_id'] == 'schema.deprecated.rich.result.type.faqpage' for f in payload['findings']))


if __name__ == '__main__':
    unittest.main()
