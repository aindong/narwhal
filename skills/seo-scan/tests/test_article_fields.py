"""Article-family recommendations are not mandatory eligibility properties."""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_schema
import generate_schema
import scan
from lib import config, htmlx, http
from lib.report import Report

URL = 'https://example.test/article'
TYPES = ('Article', 'NewsArticle', 'BlogPosting')


def node(typ='Article'):
    return {'@type': typ, 'headline': 'Actual article', 'author': {'@type': 'Person', 'name': 'Writer'},
            'datePublished': '2026-10-12', 'image': 'https://example.test/image.jpg'}


def page(data):
    org = {'@type': 'Organization', 'name': 'Example', 'url': 'https://example.test', 'logo': 'https://example.test/logo.png'}
    return '<article><h1>Actual article</h1></article><script type="application/ld+json">' + json.dumps([data, org]) + '</script>'


def inspect(html, parser=htmlx.parse, ignore=None):
    doc = parser(html, URL)
    result = Report(URL, ignore=ignore)
    audit_schema.audit(doc, None, result, {})
    return result


class TestArticleFields(unittest.TestCase):
    def test_absent_headline_is_recommended_not_a_high_required_error(self):
        for typ in TYPES:
            data = node(typ); del data['headline']
            result = inspect(page(data))
            self.assertFalse(any(f.severity == 'high' for f in result.findings))
            finding = next(f for f in result.findings if f.rule_id == 'schema.' + typ.lower() + '.missing.recommended.properties')
            self.assertEqual('low', finding.severity)
            self.assertIn('headline', finding.detail)
            self.assertIn('no required properties', finding.recommendation)
            self.assertIn('do not invent authors or dates', finding.recommendation)
            self.assertEqual(99, result.score())

    def test_empty_headlines_get_one_conditional_recommendation(self):
        for value in ('', '  ', None, [], {}, [None, ' '], {'@value': ' ', '@language': 'en'}):
            data = node(); data['headline'] = value
            result = inspect(page(data))
            self.assertEqual(99, result.score())
            self.assertFalse(any(f.severity in ('high', 'critical') for f in result.findings))
            self.assertIn('headline', next(f for f in result.findings if f.severity == 'low').detail)

    def test_all_three_article_types_receive_the_same_applicable_field_checks(self):
        for typ in TYPES:
            result = inspect(page({'@type': typ}))
            self.assertEqual(99, result.score())
            finding = next(f for f in result.findings if f.severity == 'low')
            for field in ('headline', 'author', 'datePublished', 'image'):
                self.assertIn(field, finding.detail)

    def test_complete_article_family_controls_keep_full_score(self):
        for typ in TYPES:
            result = inspect(page(node(typ)))
            self.assertEqual(100, result.score())
            self.assertFalse(any(f.severity != 'good' for f in result.findings))

    def test_article_policy_has_narrow_dated_source_provenance(self):
        result = inspect(page(node('NewsArticle')))
        policy = result.meta['structured_data']['article_field_policy']
        self.assertEqual([], policy['required_properties'])
        self.assertEqual(['NewsArticle'], policy['observed_types'])
        self.assertEqual('2026-10-12', policy['checked_on'])
        self.assertEqual(audit_schema.ARTICLE_SOURCE, policy['source'])
        self.assertIn('not full eligibility or schema.org validity', policy['scope'])

    def test_blank_dates_or_authors_are_not_disguised_as_complete_recommendations(self):
        data = node(); data.update(author=None, datePublished='')
        result = inspect(page(data))
        finding = next(f for f in result.findings if f.severity == 'low')
        self.assertIn('author, datePublished', finding.detail)
        self.assertNotIn('headline', finding.detail)

    def test_nonempty_inline_literals_and_references_are_not_proven_absent(self):
        data = node(); data.update(headline={'@value': 'Article', '@language': 'en'}, author={'@id': '#writer'})
        result = inspect(page(data))
        self.assertEqual(100, result.score())  # not a full reference/type validator
        self.assertTrue(audit_schema._article_value_present(0))
        self.assertTrue(audit_schema._article_value_present(False))
        value = 'unknown'
        for _ in range(20): value = [value]
        self.assertTrue(audit_schema._article_value_present(value))

    def test_legacy_headline_optout_does_not_hide_unrelated_recommendations(self):
        cfg = config.Config({'ignore': {'titles': ["Article missing required 'headline'"]}})
        data = node(); del data['headline']
        result = inspect(page(data), ignore=cfg.is_ignored)
        self.assertFalse(any(f.severity != 'good' for f in result.findings))
        del data['author']
        result = inspect(page(data), ignore=cfg.is_ignored)
        finding = next(f for f in result.findings if f.severity == 'low')
        self.assertIn('author', finding.detail)
        self.assertNotIn('headline', finding.detail)

    def test_other_types_still_keep_their_existing_required_checks(self):
        result = inspect(page({'@type': 'Event', 'name': 'Meetup'}))
        self.assertTrue(any(f.rule_id == 'schema.event.missing.required.startdate' and f.severity == 'high' for f in result.findings))
        self.assertNotIn('article_field_policy', result.meta['structured_data'])

    def test_default_generators_label_headline_recommended_not_required(self):
        for typ in TYPES:
            data = generate_schema.build(typ, {})
            self.assertIn('(recommended)', data['headline'])
            self.assertNotIn('(required)', data['headline'])
            minimal = generate_schema.build(typ, {}, include_recommended=False)
            self.assertEqual({'@context': 'https://schema.org', '@type': typ}, minimal)
            explicit = generate_schema.build(typ, {'headline': 'Known title'}, include_recommended=False)
            self.assertEqual('Known title', explicit['headline'])

    def test_jsonld_microdata_rdfa_and_backends_share_recommended_scope(self):
        pages = ('<script type="application/ld+json">{"@type":"Article"}</script>', '<article itemscope itemtype="https://schema.org/Article"></article>', '<article vocab="https://schema.org/" typeof="Article"></article>')
        for html in pages:
            results = [inspect(html, parser) for parser in (htmlx._parse_stdlib, htmlx.parse)]
            self.assertEqual([(f.rule_id, f.severity) for f in results[0].findings], [(f.rule_id, f.severity) for f in results[1].findings])
            self.assertEqual(results[0].meta, results[1].meta)
            self.assertFalse(any(f.severity == 'high' for f in results[0].findings))

    def test_html_and_scan_json_expose_optional_scope_without_source_fetch(self):
        html = page({'@type': 'Article'})
        text = inspect(html).to_html()
        self.assertIn('Google Article markup has no required properties', text)
        self.assertIn(audit_schema.ARTICLE_SOURCE, text)
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, html, 1)
        with mock.patch.object(scan.http, 'fetch', return_value=response) as fetch:
            payload = json.loads(scan.scan(URL, only=['schema'], ctx={}, check_images=False).to_json())
        self.assertEqual(1, fetch.call_count)
        self.assertEqual([], payload['meta']['structured_data']['article_field_policy']['required_properties'])


if __name__ == '__main__':
    unittest.main()
