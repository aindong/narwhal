"""Reference links explain findings without changing measured report data."""

import ast
import json
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diff_scan
from lib.report import Finding, Report

BASE = 'https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/'


class TestFindingGuides(unittest.TestCase):
    def test_priority_and_quick_win_render_links_in_markdown_and_html(self):
        report = Report('https://example.test/')
        report.add('technical', 'high', 'Missing meta description')
        report.add('content', 'low', 'No visible date signal')
        for output in (report.to_markdown(), report.to_html()):
            with self.subTest(format='html' if output.startswith('<') else 'markdown'):
                self.assertIn(BASE + 'technical-seo.md#title--meta-description', output)
                self.assertIn(BASE + 'content-eeat.md#date-cues-not-freshness-verification', output)
                self.assertEqual(2, output.count('Learn more'))

    def test_json_links_are_additive_and_leave_score_and_identity_unchanged(self):
        report = Report('https://example.test/')
        report.add('content', 'high', 'Thin content (210 words)')
        data = json.loads(report.to_json())
        finding = data['findings'][0]
        self.assertEqual(BASE + 'content-eeat.md#content-depth-not-word-count-for-its-own-sake',
                         finding['reference_url'])
        self.assertEqual('content.thin.content', finding['rule_id'])
        self.assertEqual(94, data['score'])
        old = json.loads(report.to_json())
        del old['findings'][0]['reference_url']
        result = diff_scan.diff_reports(old, data)
        for key in ('added', 'resolved', 'worsened', 'improved'):
            self.assertFalse(result[key])

    def test_stable_id_not_presentation_title_selects_section(self):
        finding = Finding('technical', 'high', 'Custom wording',
                          rule_id='technical.missing.meta.description')
        self.assertEqual(BASE + 'technical-seo.md#title--meta-description', finding.reference_url)

    def test_all_four_categories_and_known_schema_families(self):
        cases = [
            ('technical', 'technical.no.canonical.url', 'technical-seo.md#canonicalization'),
            ('content', 'content.no.visible.author.byline', 'content-eeat.md#experience--expertise'),
            ('geo', 'geo.few.self.contained.citable.passages', 'geo-llmo.md#2-citable-self-contained-passages'),
            ('schema', 'schema.ecommerce.price.mismatch', 'schema.md#product-and-merchant-listing-checks'),
            ('schema', 'schema.deprecated.rich.result.type.faqpage', 'schema.md#retired-google-search-rich-result-features'),
        ]
        for category, rule, target in cases:
            with self.subTest(rule=rule):
                finding = Finding(category, 'medium', 'Test', rule_id=rule)
                self.assertEqual(BASE + target, finding.reference_url)

    def test_unmapped_rules_receive_only_general_category_context(self):
        finding = Finding('technical', 'medium', 'Future check', rule_id='custom.future')
        self.assertEqual(BASE + 'technical-seo.md', finding.reference_url)
        finding = Finding('content', 'low', 'Misleading title', rule_id='technical.no.canonical.url')
        self.assertEqual(BASE + 'content-eeat.md', finding.reference_url)

    def test_unknown_categories_and_passes_do_not_invent_references(self):
        report = Report('https://example.test/')
        report.add('custom', 'high', 'Unknown check')
        report.ok('technical', 'Title present')
        for item in json.loads(report.to_json())['findings']:
            self.assertNotIn('reference_url', item)
        self.assertNotIn('Learn more', report.to_markdown())
        self.assertNotIn('Learn more', report.to_html())

    def test_untrusted_ids_and_titles_cannot_supply_a_link_destination(self):
        report = Report('https://example.test/')
        report.add('technical', 'high', '<script>bad</script>',
                   rule_id='javascript:alert(1)')
        data = json.loads(report.to_json())
        self.assertEqual(BASE + 'technical-seo.md', data['findings'][0]['reference_url'])
        html = report.to_html()
        self.assertIn('&lt;script&gt;bad&lt;/script&gt;', html)
        self.assertNotIn('href="javascript:', html)

    def test_rendering_does_not_fetch_reference_content(self):
        report = Report('https://example.test/')
        report.add('geo', 'low', 'No llms.txt')
        with mock.patch('urllib.request.urlopen', side_effect=AssertionError('No network')), \
                mock.patch('socket.create_connection', side_effect=AssertionError('No network')):
            self.assertIn('reference_url', report.to_json())
            self.assertIn('Learn more', report.to_markdown())
            self.assertIn('Learn more', report.to_html())

    def test_registered_sections_exist_in_shipped_reference_guides(self):
        from lib.guides import _GUIDES, _SECTION_RULES, _PREFIX_SECTIONS
        root = Path(__file__).resolve().parents[1] / 'references'
        headings = {}
        for category, name in _GUIDES.items():
            text = (root / name).read_text(encoding='utf-8')
            headings[category] = {
                re.sub(r'[^\w\- ]', '', line.lstrip('#').strip().lower()).replace(' ', '-')
                for line in text.splitlines() if line.startswith('#')
            }
        for category, anchor, _ in _SECTION_RULES:
            self.assertIn(anchor, headings[category])
        for category, _, anchor in _PREFIX_SECTIONS:
            self.assertIn(anchor, headings[category])

    def test_exact_catalog_rules_are_still_emitted_by_builtin_auditors(self):
        from lib.guides import _SECTIONS
        root = Path(__file__).resolve().parents[1] / 'scripts'
        found = set()
        for category in ('technical', 'content', 'schema', 'geo'):
            source = ast.parse((root / ('audit_' + category + '.py')).read_text(encoding='utf-8'))
            for node in ast.walk(source):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == 'add' and len(node.args) > 2):
                    continue
                title = node.args[2]
                if isinstance(title, ast.Constant) and isinstance(title.value, str):
                    found.add((category, Finding(category, 'low', title.value).rule_id))
                for keyword in node.keywords:
                    if keyword.arg == 'rule_id' and isinstance(keyword.value, ast.Constant):
                        found.add((category, keyword.value.value))
        self.assertFalse(set(_SECTIONS) - found)


if __name__ == '__main__':
    unittest.main()
