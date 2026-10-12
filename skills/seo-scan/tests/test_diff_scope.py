"""Diffs must not turn omitted checks into evidence of a fix."""

import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diff_scan
from lib.report import Report, recorded_scan_scope

ALL = ['technical', 'content', 'schema', 'geo']
FINDING = {'category': 'technical', 'severity': 'high', 'title': 'Missing description',
           'rule_id': 'technical.description.missing'}


def report(groups=None, completed=None, findings=None, score=100):
    data = {'url': 'https://example.test/', 'score': score,
            'findings': findings or [], 'meta': {}}
    if groups is not None:
        data['meta']['scan_scope'] = {'requested': list(groups),
                                     'completed': list(groups if completed is None else completed)}
    return data


def invoke(old, new, *flags):
    with tempfile.TemporaryDirectory() as tmp:
        before, after = Path(tmp) / 'before.json', Path(tmp) / 'after.json'
        before.write_text(json.dumps(old)); after.write_text(json.dumps(new))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = diff_scan.main([str(before), str(after)] + list(flags))
        return rc, out.getvalue(), err.getvalue()


class TestDiffScope(unittest.TestCase):
    def assert_incomparable(self, old, new):
        result = diff_scan.diff_reports(old, new)
        self.assertEqual('incomparable', result['comparison']['status'])
        self.assertIsNone(result['score_delta']); self.assertIsNone(result['regression'])
        for key in ('added', 'resolved', 'worsened', 'improved', 'new_critical_high'):
            self.assertEqual([], result[key])
        self.assertEqual(0, result['unchanged'])
        self.assertNotIn('**Improved', diff_scan.render_markdown(result))
        self.assertNotIn('## ✅ Resolved', diff_scan.render_markdown(result))
        return result

    def test_full_to_focused_is_not_an_improvement_or_resolution(self):
        old = report(ALL, findings=[FINDING], score=94)
        new = report(['schema'])
        result = self.assert_incomparable(old, new)
        self.assertEqual({'old_findings': 1, 'new_findings': 0}, result['not_compared'])
        self.assertEqual(94, result['old_score']); self.assertEqual(100, result['new_score'])

    def test_expanding_or_switching_scope_does_not_invent_new_regressions(self):
        for old, new in ((report(['schema']), report(ALL, findings=[FINDING], score=94)),
                         (report(['schema']), report(['technical'], findings=[FINDING], score=94))):
            self.assert_incomparable(old, new)

    def test_order_does_not_change_auditor_scope(self):
        result = diff_scan.diff_reports(report(ALL), report(list(reversed(ALL))))
        self.assertEqual('comparable', result['comparison']['status'])
        self.assertEqual(0, result['score_delta'])

    def test_same_focused_scope_keeps_real_resolutions_and_score_delta(self):
        finding = dict(FINDING, category='schema', rule_id='schema.example')
        result = diff_scan.diff_reports(report(['schema'], findings=[finding], score=94), report(['schema']))
        self.assertEqual('comparable', result['comparison']['status'])
        self.assertEqual(6, result['score_delta']); self.assertEqual([finding], result['resolved'])
        self.assertFalse(result['regression'])
        self.assertNotIn('health is better', diff_scan.render_markdown(result))

    def test_same_full_scope_retains_regression_gate(self):
        rc, out, err = invoke(report(ALL), report(ALL, findings=[FINDING], score=94), '--fail-on-regression')
        self.assertEqual(1, rc); self.assertIn('Regressed', out)
        self.assertIn('regression detected', err)

    def test_failed_or_incomplete_execution_is_not_comparable_even_if_both_match(self):
        for groups, completed in ((ALL, []), (ALL, ['schema'])):
            failed = report(groups, completed=completed, score=0)
            self.assert_incomparable(failed, failed)
            self.assert_incomparable(report(groups), failed)
            self.assert_incomparable(failed, report(groups))

    def test_known_failed_execution_still_blocks_when_other_scope_unknown(self):
        self.assert_incomparable(report(), report(ALL, completed=[]))
        self.assert_incomparable(report(ALL, completed=[]), report())

    def test_truncated_response_coverage_is_not_fix_proof(self):
        for meta in ({'coverage': {'response_truncated': True}}, {'response_truncated': True}):
            truncated = report(ALL); truncated['meta'].update(meta)
            self.assert_incomparable(report(ALL), truncated)
            self.assert_incomparable(truncated, truncated)

    def test_untruncated_or_missing_coverage_flag_does_not_invent_failure(self):
        before, after = report(ALL), report(ALL)
        after['meta']['coverage'] = {'response_truncated': False}
        self.assertEqual('comparable', diff_scan.diff_reports(before, after)['comparison']['status'])

    def test_legacy_scope_is_unknown_not_inferred_from_categories(self):
        result = diff_scan.diff_reports(report(findings=[FINDING], score=94), report())
        self.assertEqual('unknown', result['comparison']['status'])
        self.assertEqual(6, result['score_delta']); self.assertEqual([FINDING], result['resolved'])
        self.assertIsNone(result['comparison']['old_scope'])
        self.assertIn('unverified', diff_scan.render_markdown(result))

    def test_one_known_one_unknown_scope_stays_explicitly_unknown(self):
        result = diff_scan.diff_reports(report(ALL), report())
        self.assertEqual('unknown', result['comparison']['status'])
        self.assertEqual(ALL, result['comparison']['old_scope']['completed'])
        self.assertIsNone(result['comparison']['new_scope'])

    def test_malformed_scope_is_unknown_with_shared_report_validation(self):
        for scope in (None, [], {}, {'requested': [], 'completed': []},
                      {'requested': ALL, 'completed': ['other']},
                      {'requested': ALL + ['schema'], 'completed': ALL},
                      {'requested': ALL, 'completed': ['schema', 'schema']},
                      {'requested': ALL, 'completed': 'schema'},
                      {'requested': [42], 'completed': []},
                      {'requested': ['schema'], 'completed': ['technical']}):
            with self.subTest(scope=scope):
                data = report(); data['meta']['scan_scope'] = scope
                self.assertIsNone(recorded_scan_scope(data['meta']))
                self.assertIsNone(Report('x', meta=data['meta'])._scope_info())
                self.assertEqual('unknown', diff_scan.diff_reports(data, report())['comparison']['status'])

    def test_non_dict_meta_is_unknown_without_crashing(self):
        for meta in (None, [], 'bad'):
            data = report(); data['meta'] = meta
            self.assertEqual('unknown', diff_scan.diff_reports(data, report())['comparison']['status'])

    def test_audit_uses_homepage_scope_and_keeps_overall_score(self):
        old = {'site': 'https://example.test', 'overall_score': 60, 'homepage': report(ALL)}
        new = {'site': 'https://example.test', 'overall_score': 70, 'homepage': report(ALL)}
        result = diff_scan.diff_reports(old, new)
        self.assertEqual('comparable', result['comparison']['status'])
        self.assertEqual(10, result['score_delta'])
        self.assertIn('site-wide samples', result['comparison']['basis'])
        new['homepage'] = report(['schema'])
        self.assert_incomparable(old, new)

    def test_page_and_audit_score_kinds_are_not_comparable_even_without_scope(self):
        self.assert_incomparable(report(), {'site': 'https://example.test', 'overall_score': 100,
                                           'homepage': report()})

    def test_cli_known_incomparability_blocks_gate_but_can_render_diagnostic(self):
        for flags, expected in ((['--fail-on-regression'], 2), ([], 0)):
            rc, out, err = invoke(report(ALL), report(['schema']), *flags)
            self.assertEqual(expected, rc); self.assertIn('Not comparable', out)
            self.assertIn('not compared', out)
            self.assertNotIn('(±0)', out)
            if flags:
                self.assertIn('FAIL: report coverage', err)

    def test_json_nulls_make_unmeasured_changes_explicit(self):
        rc, out, err = invoke(report(ALL), report(['schema']), '--format', 'json', '--fail-on-regression')
        data = json.loads(out)
        self.assertEqual(2, rc); self.assertIsNone(data['score_delta']); self.assertIsNone(data['regression'])
        self.assertIn('not comparable', err)

    def test_legacy_gate_compatibility_is_preserved_with_visible_warning(self):
        rc, out, err = invoke(report(), report(), '--fail-on-regression')
        self.assertEqual(0, rc); self.assertIn('unverified', out); self.assertIn('WARNING:', err)
        rc, _, _ = invoke(report(), report(findings=[FINDING], score=94), '--fail-on-regression')
        self.assertEqual(1, rc)

    def test_comparison_does_not_mutate_input_reports(self):
        old, new = report(ALL, findings=[FINDING]), report(['schema'])
        saved = copy.deepcopy((old, new))
        diff_scan.diff_reports(old, new)
        self.assertEqual(saved, (old, new))

    def test_mcp_diff_exposes_the_same_offline_scope_guard(self):
        import mcp_server
        result = mcp_server._diff(json.dumps(report(ALL)), json.dumps(report(['schema'])))
        self.assertEqual('incomparable', result['comparison']['status'])
        self.assertIsNone(result['regression']); self.assertEqual([], result['resolved'])


if __name__ == '__main__':
    unittest.main()
