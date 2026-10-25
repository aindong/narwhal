"""Malformed href syntax supplies source witnesses without inventing HTTP failures."""
import copy
import html
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan
import render_report
from lib import htmlx, http, links
from test_anchor_source_handoff import measure, URL, REPO
from test_malformed_anchor_links import BAD, source

RULE = 'technical.links.invalid.url'
LEGACY = 'technical.malformed.http.link.urls'


class TestMalformedLinkHandoff(unittest.TestCase):
    def test_bounded_source_witnesses_retain_order_occurrences_and_duplicate_values(self):
        hrefs = list(BAD) + [BAD[0], BAD[0]]
        _, data = measure(source(*hrefs))
        finding = next(f for f in data['findings'] if f['rule_id'] == RULE)
        evidence = json.loads(finding['evidence'])
        self.assertEqual(7, evidence['observed_count'])
        self.assertEqual(list(BAD), [row['href'] for row in evidence['witnesses']])
        self.assertEqual('low', finding['severity'])
        self.assertIn('destinations not checked', evidence['scope'])
        _, repeated = measure(source(BAD[0], BAD[0]))
        evidence = json.loads(repeated['findings'][0]['evidence'])
        self.assertEqual([BAD[0], BAD[0]], [row['href'] for row in evidence['witnesses']])

    def test_literal_malformed_values_roundtrip_and_remain_safe_in_report_views(self):
        href = 'https://example.test:nope/path?value=`<script>bad()</script>'
        native, data = measure('<a href="' + html.escape(href, quote=True) + '">Destination</a>')
        finding = next(f for f in data['findings'] if f['rule_id'] == RULE)
        self.assertNotIn('`', finding['evidence'])
        self.assertEqual(href, json.loads(finding['evidence'])['witnesses'][0]['href'])
        self.assertNotIn('<script>', render_report.render(native.to_markdown()))
        self.assertNotIn('<script>', render_report.render(plan.render_markdown(plan.build_plan(data, REPO))))

    def test_native_and_legacy_rules_get_source_review_without_reconstructing_old_witnesses(self):
        _, data = measure(source(*BAD))
        for legacy in (False, True):
            report = copy.deepcopy(data)
            if legacy:
                report.pop('schema_version')
                report['findings'][0].pop('rule_id')
                report['findings'][0].pop('evidence')
            built = plan.build_plan(report, REPO)
            action = built['actions'][0]
            self.assertEqual(LEGACY if legacy else RULE, action['rule_id'])
            self.assertEqual('content', action['artifact'])
            self.assertEqual('review_required', action['safety'])
            self.assertEqual('guides/widget/index.html', action['likely_files'][0]['path'])
            self.assertIn('without guessing a new destination', action['proposed_change'])
            self.assertNotIn('automation_eligibility', action)
            self.assertEqual(not legacy, 'witnesses' in action['evidence'])

    def test_valid_non_http_and_unassessed_base_references_do_not_create_malformed_witnesses(self):
        for body in (source('/valid', 'mailto:a@example.test', '#section', 'tel:+123'),
                     '<base href="http://["><a href="/relative">Destination</a>'):
            _, data = measure(body)
            self.assertNotIn(RULE, {f['rule_id'] for f in data['findings']})

    def test_collector_omissions_remain_syntax_only_without_destination_requests_or_statuses(self):
        body = source(*BAD, '/valid'); doc = htmlx._parse_stdlib(body, URL); diagnostics = {}
        with mock.patch.object(http, 'head', side_effect=AssertionError('No HTTP checks')), \
                mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            targets = links.extract_links(doc, URL, diagnostics=diagnostics)
            _, data = measure(body)
        self.assertEqual([{'url': 'https://example.test/valid', 'internal': True}], targets)
        self.assertEqual(len(BAD), diagnostics['invalid_url_occurrences'])
        evidence = json.loads(next(f for f in data['findings'] if f['rule_id'] == RULE)['evidence'])
        self.assertTrue(all(set(row) == {'href'} for row in evidence['witnesses']))

    def test_credential_like_values_are_omitted_across_all_source_witness_categories(self):
        values = ('http://secret:password@[broken', 'http://secret:password%40[broken',
                  'http://secret:password＠[broken',
                  'https://example.test:nope/path?address=person@example.test',
                  'https://example.test:nope/path?address=person%40example.test')
        for href in values:
            for label in ('', 'Read more', 'Destination'):
                with self.subTest(href=href, label=label):
                    _, data = measure('<a href="' + html.escape(href, quote=True) + '">' + label + '</a>')
                    payload = json.dumps(data)
                    self.assertNotIn('password', payload)
                    self.assertNotIn('secret:', payload)
                    for finding in data['findings']:
                        evidence = json.loads(finding['evidence'])
                        self.assertEqual(1, evidence['observed_count'])
                        self.assertIsNone(evidence['witnesses'][0]['href'])
                        self.assertEqual('credential_like_marker', evidence['witnesses'][0]['href_omitted'])

    def test_offline_mcp_keeps_contextual_guidance_evidence_and_input_bytes(self):
        _, data = measure(source(*BAD))
        data['findings'][0]['recommendation'] = 'UNSUPPORTED_DELETE_DESTINATIONS'
        original = copy.deepcopy(data)
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            built = mcp_server._plan(data, REPO)
        self.assertEqual(plan.build_plan(data, REPO, report_source='<mcp-object>'), built)
        self.assertEqual(original, data)
        self.assertEqual('review_required', built['actions'][0]['safety'])
        self.assertIn('witnesses', built['actions'][0]['evidence'])
        self.assertNotIn('UNSUPPORTED_DELETE_DESTINATIONS', plan.render_markdown(built))
        self.assertEqual('UNSUPPORTED_DELETE_DESTINATIONS', built['actions'][0]['source_recommendation'])


if __name__ == '__main__':
    unittest.main()
