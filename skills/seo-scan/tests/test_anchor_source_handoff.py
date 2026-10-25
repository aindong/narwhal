"""Native anchor-text observations retain witnesses and source-review handoffs."""
import copy
import html
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_technical
import mcp_server
import plan
import render_report
from lib import htmlx, http
from lib.report import Report

URL = 'https://example.test/guides/widget'
REPO = 'skills/seo-scan/tests/fixtures/planner/plain_html'
EMPTY = 'technical.links.with.no.anchor.text'
GENERIC = 'technical.generic.anchor.text'


def measure(source, parser=htmlx._parse_stdlib):
    result = Report(URL, final_url=URL, fetched_status=200)
    doc = parser(source, URL)
    with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
        audit_technical._links(doc, http.Response(URL, URL, 200, {}, source, 0), result)
    return result, json.loads(result.to_json())


class TestAnchorSourceHandoff(unittest.TestCase):
    def test_bounded_source_order_and_totals_do_not_become_unique_destination_counts(self):
        source = ''.join('<a href="/empty-' + str(i) + '"></a>' for i in range(8))
        source += ''.join('<a href="/same">Read more</a>' for _ in range(7))
        _, data = measure(source)
        rows = {f['rule_id']: f for f in data['findings']}
        for rule, count in ((EMPTY, 8), (GENERIC, 7)):
            witness = json.loads(rows[rule]['evidence'])
            self.assertEqual(count, witness['observed_count'])
            self.assertEqual(5, len(witness['witnesses']))
            self.assertIn('destinations not checked', witness['scope'])
        self.assertEqual(['/empty-' + str(i) for i in range(5)],
                         [r['href'] for r in json.loads(rows[EMPTY]['evidence'])['witnesses']])
        self.assertEqual(['/same'] * 5, [r['href'] for r in json.loads(rows[GENERIC]['evidence'])['witnesses']])

    def test_existing_image_title_and_visible_label_fallbacks_keep_their_counts(self):
        source = ('<a href="/visible">Read more</a><a href="/image"><img alt="Click here"></a>'
                  '<a href="/title" title=" Here "></a><a href="/empty"></a>'
                  '<a href="/descriptive"><img alt="Install the widget"></a>')
        for parser in (htmlx._parse_stdlib, htmlx.parse):
            _, data = measure(source, parser)
            rows = {f['rule_id']: json.loads(f['evidence']) for f in data['findings']}
            self.assertEqual({EMPTY, GENERIC}, set(rows))
            self.assertEqual(1, rows[EMPTY]['observed_count'])
            self.assertEqual(3, rows[GENERIC]['observed_count'])
            self.assertEqual(['Read more', 'Click here', 'Here'], [r['label'] for r in rows[GENERIC]['witnesses']])

    def test_source_witnesses_roundtrip_literal_backticks_without_breaking_rendering(self):
        href = '/target?value=`<script>bad()</script>'
        native, data = measure('<a href="' + html.escape(href, quote=True) + '"></a>')
        row = next(f for f in data['findings'] if f['rule_id'] == EMPTY)
        self.assertNotIn('`', row['evidence'])
        self.assertEqual(href, json.loads(row['evidence'])['witnesses'][0]['href'])
        self.assertNotIn('<script>', render_report.render(native.to_markdown()))
        built = plan.build_plan(data, REPO)
        self.assertNotIn('<script>', render_report.render(plan.render_markdown(built)))

    def test_native_and_legacy_rules_map_to_route_source_review_without_automatic_edits(self):
        _, data = measure('<a href="/empty"></a><a href="/generic">Click here</a>')
        for legacy in (False, True):
            report = copy.deepcopy(data)
            if legacy:
                report.pop('schema_version')
                for row in report['findings']: row.pop('rule_id')
            built = plan.build_plan(report, REPO)
            self.assertEqual({EMPTY, GENERIC}, {a['rule_id'] for a in built['actions']})
            for action in built['actions']:
                self.assertEqual('content', action['artifact'])
                self.assertEqual('review_required', action['safety'])
                self.assertEqual('guides/widget/index.html', action['likely_files'][0]['path'])
                self.assertNotIn('automation_eligibility', action)
                self.assertIn('witnesses', action['evidence'])
            generic = next(a for a in built['actions'] if a['rule_id'] == GENERIC)
            self.assertIn('Do not insert keywords', generic['proposed_change'])

    def test_legacy_keyword_advice_is_retained_as_data_without_overriding_contextual_review(self):
        _, data = measure('<a href="/generic">Click here</a>')
        data['findings'][0]['recommendation'] = 'UNSUPPORTED_KEYWORD_PROMISE'
        built = plan.build_plan(data, REPO)
        self.assertEqual('UNSUPPORTED_KEYWORD_PROMISE', built['actions'][0]['source_recommendation'])
        self.assertNotIn('UNSUPPORTED_KEYWORD_PROMISE', plan.render_markdown(built))
        self.assertIn('Do not insert keywords', plan.render_markdown(built))

    def test_offline_mcp_has_same_evidence_and_input_is_unchanged(self):
        _, data = measure('<a href="/empty"></a><a href="/generic">Click here</a>')
        original = copy.deepcopy(data)
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            built = mcp_server._plan(data, REPO)
        expected = plan.build_plan(data, REPO, report_source='<mcp-object>')
        self.assertEqual(expected, built)
        self.assertTrue(all(a['safety'] == 'review_required' for a in built['actions']))
        self.assertEqual(original, data)


if __name__ == '__main__':
    unittest.main()
