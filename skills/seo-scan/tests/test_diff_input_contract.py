"""Invalid report evidence must never become a measured diff or a passing gate."""

import copy
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diff_scan
import mcp_server
from test_diff_scope import FINDING, invoke, report


def valid():
    return report(['technical'], findings=[dict(FINDING)], score=94)


class TestDiffInputContract(unittest.TestCase):
    def test_decoder_rejects_non_text_with_bounded_labeled_diagnostics(self):
        for value in (None, {}, [], 200, False, b'{"secret-token":200}'):
            with self.subTest(type=type(value).__name__):
                with self.assertRaises(ValueError) as stopped:
                    diff_scan._decode_report_json(value, 'Earlier report')
                message = str(stopped.exception)
                self.assertIn('Earlier report', message)
                self.assertIn('string', message.lower())
                self.assertNotIn('secret-token', message)
                self.assertLess(len(message), 300)

    def assert_rejected(self, bad):
        for old, new, label in ((bad, valid(), 'Earlier'), (valid(), bad, 'Later')):
            with self.subTest(label=label):
                with self.assertRaises(ValueError) as caught:
                    diff_scan.diff_reports(old, new)
                self.assertIn(label, str(caught.exception))
                self.assertLess(len(str(caught.exception)), 300)

    def test_non_object_and_ambiguous_report_shapes_are_rejected(self):
        for value in (None, [], 'findings', 7, False):
            with self.subTest(type=type(value).__name__):
                self.assert_rejected(value)
        self.assert_rejected(dict(valid(), homepage=valid()))
        for homepage in (None, [], 'secret-token'):
            self.assert_rejected({'overall_score': 80, 'homepage': homepage})

    def test_scan_score_is_explicit_finite_numeric_and_in_range(self):
        missing = valid()
        del missing['score']
        self.assert_rejected(missing)
        for value in (None, True, False, 'secret-token', [], {}, -1, 101,
                      float('nan'), float('inf'), float('-inf'), 10 ** 100):
            with self.subTest(type=type(value).__name__, value=repr(value)[:20]):
                self.assert_rejected(dict(valid(), score=value))

    def test_audit_requires_its_own_overall_score_without_homepage_substitution(self):
        self.assert_rejected({'site': 'https://example.test/', 'homepage': valid()})
        for value in (None, True, '80', float('nan'), float('inf'), -1, 101):
            self.assert_rejected({'site': 'https://example.test/', 'overall_score': value, 'homepage': valid()})
        audit = {'site': 'https://example.test/', 'overall_score': 83.5,
                 'homepage': {'url': 'https://example.test/', 'findings': []}}
        result = diff_scan.diff_reports(audit, copy.deepcopy(audit))
        self.assertEqual(83.5, result['old_score'])
        self.assertEqual(0, result['score_delta'])
        self.assertEqual('unknown', result['comparison']['status'])

    def test_missing_or_malformed_finding_lists_cannot_become_empty(self):
        for value in (None, {}, 'secret-token', True):
            self.assert_rejected(dict(valid(), findings=value))
        self.assert_rejected({'overall_score': 80, 'homepage': {'url': 'https://example.test/'}})
        for value in (None, [], 'secret-token', 4, False):
            self.assert_rejected(dict(valid(), findings=[value]))

    def test_consumed_finding_fields_have_supported_identity_and_severity_types(self):
        for field, values in (('category', (None, [], {}, '', '   ')),
                              ('severity', (None, [], {}, '', 'urgent')),
                              ('title', (None, [], {}, 7)),
                              ('rule_id', ([], {}, 7, True, '   '))):
            for value in values:
                with self.subTest(field=field, type=type(value).__name__):
                    finding = dict(FINDING, **{field: value})
                    self.assert_rejected(dict(valid(), findings=[finding]))
        for field in ('category', 'severity', 'title'):
            finding = dict(FINDING)
            del finding[field]
            self.assert_rejected(dict(valid(), findings=[finding]))
        self.assert_rejected(dict(valid(), url={'secret-token': 'not a URL label'}))
        self.assert_rejected(dict(valid(), findings=[dict(FINDING, title='', rule_id='')]))
        self.assert_rejected(dict(valid(), findings=[dict(FINDING, title=' (one)', rule_id=None)]))

    def test_legacy_ids_additive_fields_and_fractional_scores_remain_supported(self):
        for rule in (None, ''):
            before = valid()
            before['findings'][0]['rule_id'] = rule
            before['findings'][0]['future_field'] = {'kept': True}
            before['score'] = 93.5
            before['meta'] = {}
            original = copy.deepcopy(before)
            result = diff_scan.diff_reports(before, dict(before, score=94))
            self.assertEqual(0.5, result['score_delta'])
            self.assertEqual('unknown', result['comparison']['status'])
            self.assertEqual(1, result['unchanged'])
            self.assertEqual(original, before)
        result = diff_scan.diff_reports(dict(valid(), score=0), dict(valid(), score=100))
        self.assertEqual(100, result['score_delta'])
        blank_label = dict(valid(), findings=[dict(FINDING, title='')])
        self.assertEqual(1, diff_scan.diff_reports(blank_label, blank_label)['unchanged'])

    def test_invalid_inputs_fail_before_comparison_and_preserve_existing_outputs(self):
        bad = dict(valid(), score='secret-token' + 'x' * 5000)
        with mock.patch.object(diff_scan, '_comparison') as compare:
            self.assert_rejected(bad)
        compare.assert_not_called()
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp, 'diff.json')
            destination.write_bytes(b'original output')
            for flags in ([], ['--fail-on-regression']):
                code, out, err = invoke(valid(), bad, '--format', 'json', '-o', str(destination), *flags)
                self.assertEqual(2, code)
                self.assertEqual('', out)
                self.assertIn('Later', err)
                self.assertNotIn('secret-token', err)
                self.assertLess(len(err), 300)
                self.assertEqual(b'original output', destination.read_bytes())

    def test_mcp_rejects_invalid_evidence_instead_of_returning_a_diff(self):
        for bad in (None, dict(valid(), score=float('nan')), dict(valid(), findings=None)):
            with self.assertRaises(ValueError):
                mcp_server._diff(json.dumps(valid()), json.dumps(bad))

    def test_decoder_failures_are_labeled_and_do_not_write_cli_output(self):
        with mock.patch.object(diff_scan.json, 'loads', side_effect=RecursionError('secret-token')):
            with self.assertRaisesRegex(ValueError, 'Later report JSON') as caught:
                diff_scan._decode_report_json('{}', 'Later report')
        self.assertNotIn('secret-token', str(caught.exception))
        for text in ('{"secret-token":', '[' * 2000 + ']' * 2000, '9' * 10000):
            with self.subTest(prefix=text[:10]):
                with self.assertRaises(ValueError) as caught:
                    mcp_server._diff(json.dumps(valid()), text)
                self.assertIn('Later', str(caught.exception))
                self.assertNotIn('secret-token', str(caught.exception))
                self.assertLess(len(str(caught.exception)), 300)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before, after, output = root / 'old.json', root / 'new.json', root / 'diff.json'
            before.write_text(json.dumps(valid()), encoding='utf-8')
            output.write_bytes(b'original output')
            for raw in (('[' * 2000 + ']' * 2000).encode(), b'{"secret-token":"\xff"}'):
                after.write_bytes(raw)
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = diff_scan.main([str(before), str(after), '-o', str(output)])
                self.assertEqual(2, code)
                self.assertEqual('', out.getvalue())
                self.assertIn('Later', err.getvalue())
                self.assertNotIn('secret-token', err.getvalue())
                self.assertNotIn('Traceback', err.getvalue())
                self.assertEqual(b'original output', output.read_bytes())

    def test_validation_does_not_mask_unexpected_comparison_errors(self):
        with mock.patch.object(diff_scan, '_comparison', side_effect=RuntimeError('programming error')):
            with self.assertRaises(RuntimeError):
                diff_scan.diff_reports(valid(), valid())
        with mock.patch.object(diff_scan.json, 'loads', side_effect=RuntimeError('programming error')):
            with self.assertRaises(RuntimeError):
                diff_scan._decode_report_json('{}')


if __name__ == '__main__':
    unittest.main()
