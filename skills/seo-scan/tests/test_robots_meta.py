"""Generic meta robots restrictions are exact tokens across all active tags."""

import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_technical
from lib import htmlx
from lib.report import Report

NOINDEX = 'technical.page.is.set.to.noindex'
NOFOLLOW = 'technical.page.level.nofollow'
META_PASS = 'technical.page.is.indexable'  # legacy identity retained, wording scoped


def audit_meta(markup, parser=htmlx._parse_stdlib):
    doc = parser('<html><head>' + markup + '</head><body><h1>Example</h1></body></html>', 'https://example.test/')
    report = Report('https://example.test/')
    audit_technical._robots_directives(doc, report)
    return report


class TestRobotsMeta(unittest.TestCase):
    def test_none_expands_to_both_restrictions(self):
        rep = audit_meta('<meta name="robots" content="none">')
        self.assertEqual({NOINDEX, NOFOLLOW}, {f.rule_id for f in rep.findings})
        self.assertEqual(['critical', 'medium'], [f.severity for f in rep.findings])
        self.assertTrue(all('none' in f.evidence for f in rep.findings))

    def test_later_tags_cannot_be_hidden_by_first_allowing_or_empty_tag(self):
        for first in ('index, follow', 'all', ''):
            with self.subTest(first=first):
                rep = audit_meta('<meta name="robots" content="' + first + '"><meta name="robots" content="noindex, nofollow">')
                self.assertEqual({NOINDEX, NOFOLLOW}, {f.rule_id for f in rep.findings})

    def test_repeated_restrictions_emit_one_finding_per_rule(self):
        rep = audit_meta('<meta name="robots" content="noindex">' * 12 + '<meta name="robots" content="nofollow">' * 12)
        self.assertEqual([NOINDEX, NOFOLLOW], [f.rule_id for f in rep.findings])

    def test_case_and_plain_whitespace_separated_names(self):
        rep = audit_meta('<meta name="RoBoTs" content="  NoInDeX \t NOFOLLOW  ">')
        self.assertEqual({NOINDEX, NOFOLLOW}, {f.rule_id for f in rep.findings})

    def test_substrings_and_parameter_values_are_not_standalone_rules(self):
        for content in ('x-noindex, x-nofollow', 'noindexable notnofollow',
                        'max-image-preview:none', 'max-image-preview: none',
                        'unavailable_after: noindex', 'noindex: nofollow'):
            with self.subTest(content=content):
                rep = audit_meta('<meta name="robots" content="' + content + '">')
                self.assertEqual([META_PASS], [f.rule_id for f in rep.findings])

    def test_parameter_values_do_not_hide_separate_comma_rule(self):
        rep = audit_meta('<meta name="robots" content="max-image-preview: none, noindex">')
        self.assertEqual([NOINDEX], [f.rule_id for f in rep.findings])

    def test_nofollow_does_not_imply_noindex(self):
        rep = audit_meta('<meta name="robots" content="index, nofollow">')
        self.assertEqual([NOFOLLOW, META_PASS], [f.rule_id for f in rep.findings])

    def test_pass_is_narrow_and_retains_existing_rule_identity(self):
        rep = audit_meta('<meta name="googlebot" content="noindex">')
        finding = rep.findings[0]
        self.assertEqual(META_PASS, finding.rule_id)
        self.assertEqual('good', finding.severity)
        self.assertNotIn('indexable', finding.title.lower())
        self.assertIn('generic', finding.title.lower())
        self.assertIn('HTTP', finding.detail)
        self.assertIn('crawler-specific', finding.detail)
        self.assertIn('not proof', finding.detail)

    def test_late_restriction_is_scanned_and_keeps_a_bounded_witness(self):
        rep = audit_meta('<meta name="robots" content="nofollow">' * 1500
                         + '<meta name="robots" content="noindex,' + 'x' * 10000 + '">')
        self.assertEqual([NOINDEX, NOFOLLOW], [f.rule_id for f in rep.findings])
        for finding in rep.findings:
            self.assertLess(len(finding.evidence), 200)
            self.assertIn('1501', finding.evidence)
            self.assertIn('noindex', finding.evidence)

    def test_inert_templates_cannot_supply_restrictions(self):
        rep = audit_meta('<template><meta name="robots" content="none"></template>')
        self.assertEqual([META_PASS], [f.rule_id for f in rep.findings])

    @unittest.skipUnless(importlib.util.find_spec('bs4'), 'optional BeautifulSoup backend absent')
    def test_optional_parser_agrees_on_duplicate_alias_and_inert_cases(self):
        for markup in ('<meta name="robots" content="index"><meta name="robots" content="NONE">',
                       '<meta name="robots" content="max-image-preview: none">',
                       '<template><meta name="robots" content="noindex"></template>',
                       '<meta name="robots" content="x-noindex">'):
            with self.subTest(markup=markup):
                std = audit_meta(markup)
                optional = audit_meta(markup, htmlx._parse_bs4)
                self.assertEqual([(f.rule_id, f.severity, f.evidence) for f in std.findings],
                                 [(f.rule_id, f.severity, f.evidence) for f in optional.findings])


if __name__ == '__main__':
    unittest.main()
