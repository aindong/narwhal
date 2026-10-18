"""Explicit review recording cannot overwrite evidence or invent adjudication."""
import copy
from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

import test_review_corpus as fixture

review = fixture.review


class TestReviewRecording(unittest.TestCase):
    setUp = fixture.TestReviewCorpus.setUp
    save = fixture.TestReviewCorpus.save
    evidence = fixture.TestReviewCorpus.evidence

    def decisions(self, verdict='uncertain'):
        return {**dict.fromkeys(review.DIMENSIONS, verdict), 'reviewer': 'Fixture operator, not independent',
                'reviewed_at': '2026-10-19T05:00:00+08:00', 'rationale': 'Synthetic workflow test only.',
                'evidence': ['page'] if self.manifest['cases'][0].get('evidence') else []}

    def args(self, packet, output, verdict='uncertain'):
        args = ['record', str(self.path), str(packet), '--finding-id', 'fixture:0',
                '--reviewer', 'Fixture operator, not independent', '--reviewed-at', '2026-10-19T05:00:00+08:00',
                '--rationale', 'Synthetic workflow test only.', '-o', str(output)]
        for key in review.DIMENSIONS:
            args.extend(['--' + key, verdict])
        if self.manifest['cases'][0].get('evidence'):
            args.extend(['--evidence', 'page'])
        return args

    def packet_file(self):
        path = self.root / 'pending.json'
        path.write_text(json.dumps(review.prepare(self.path)), encoding='utf-8')
        return path

    def test_only_target_review_changes_and_original_object_is_preserved(self):
        self.evidence()
        self.report['findings'].append({'category': 'content', 'severity': 'low', 'title': 'Other observation'})
        self.save()
        packet = review.prepare(self.path)
        original = copy.deepcopy(packet)
        result = review.record_review(self.path, packet, 'fixture:0', self.decisions('supported'))
        expected = copy.deepcopy(packet)
        expected['cases'][0]['findings'][0]['review'] = self.decisions('supported')
        self.assertEqual(expected, result)
        self.assertEqual(original, packet)
        summary = review.summarize(self.path, result)
        self.assertEqual((2, 1, 'partial'), (summary['finding_count'], summary['fully_labelled_findings'], summary['review_status']))

    def test_recorded_labels_do_not_establish_accuracy_recall_or_independence(self):
        self.evidence()
        result = review.record_review(self.path, review.prepare(self.path), 'fixture:0', self.decisions('supported'))
        summary = review.summarize(self.path, result)
        self.assertEqual('fully_labelled', summary['review_status'])
        self.assertIsNone(summary['accuracy_metrics'])
        self.assertIsNone(summary['recall_metrics'])
        self.assertEqual(['Fixture operator, not independent'], summary['self_reported_reviewer_labels'])

    def test_other_case_and_responsible_reviewers_decisions_are_preserved(self):
        self.evidence()
        second = copy.deepcopy(self.report)
        second['url'] = 'https://example.test/second'
        (self.root / 'second.json').write_text(json.dumps(second), encoding='utf-8')
        self.manifest['cases'].append({'id': 'second', 'report': 'second.json',
                                      'evidence': self.manifest['cases'][0]['evidence']})
        self.save()
        packet = review.prepare(self.path)
        other = self.decisions()
        other['reviewer'] = 'Other synthetic operator'
        packet = review.record_review(self.path, packet, 'second:0', other)
        result = review.record_review(self.path, packet, 'fixture:0', self.decisions('supported'))
        self.assertEqual(packet['cases'][1], result['cases'][1])
        self.assertEqual(other, result['cases'][1]['findings'][0]['review'])

    def test_report_only_cannot_receive_supported_or_unsupported_decisions(self):
        packet = review.prepare(self.path)
        for verdict in ('supported', 'unsupported'):
            with self.assertRaisesRegex(ValueError, 'attached evidence'):
                review.record_review(self.path, packet, 'fixture:0', self.decisions(verdict))
        self.assertEqual('pending', review.summarize(self.path, packet)['review_status'])

    def test_uncertainty_without_evidence_is_allowed_without_claiming_accuracy(self):
        packet = review.record_review(self.path, review.prepare(self.path), 'fixture:0', self.decisions())
        self.assertEqual(1, review.summarize(self.path, packet)['verdict_counts']['observation']['uncertain'])

    def test_unknown_or_excluded_good_finding_ids_are_not_retargeted(self):
        for finding in ('fixture:1', 'fixture:999', 'other:0', '', None):
            with self.subTest(finding=finding), self.assertRaises(ValueError):
                review.record_review(self.path, review.prepare(self.path), finding, self.decisions())

    def test_partial_existing_review_requires_explicit_replacement_not_merging(self):
        packet = review.prepare(self.path)
        first = self.decisions()
        first['priority'] = first['recommendation'] = 'pending'
        packet = review.record_review(self.path, packet, 'fixture:0', first)
        replacement = self.decisions('not_applicable')
        for flag in (False, None, 1, 'true'):
            with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, 'replace-review'):
                review.record_review(self.path, packet, 'fixture:0', replacement, replace=flag)
        result = review.record_review(self.path, packet, 'fixture:0', replacement, replace=True)
        self.assertEqual(replacement, result['cases'][0]['findings'][0]['review'])
        self.assertEqual(first, packet['cases'][0]['findings'][0]['review'])

    def test_explicit_reset_keeps_inventory_and_original_decisions(self):
        packet = review.record_review(self.path, review.prepare(self.path), 'fixture:0', self.decisions())
        pending = {**dict.fromkeys(review.DIMENSIONS, 'pending'), 'reviewer': '', 'reviewed_at': '',
                   'rationale': '', 'evidence': []}
        result = review.record_review(self.path, packet, 'fixture:0', pending, replace=True)
        self.assertEqual('pending', review.summarize(self.path, result)['review_status'])
        self.assertEqual('fully_labelled', review.summarize(self.path, packet)['review_status'])
        self.assertEqual(1, len(result['cases'][0]['findings']))

    def test_no_reviewer_timestamp_rationale_or_witness_is_invented(self):
        self.evidence()
        for key, value in [('reviewer', ''), ('reviewed_at', ''), ('reviewed_at', '2026-10-19'),
                           ('rationale', ''), ('evidence', []), ('evidence', ['invented'])]:
            decisions = self.decisions('supported')
            decisions[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                review.record_review(self.path, review.prepare(self.path), 'fixture:0', decisions)

    def test_invalid_review_schema_or_verdict_is_rejected(self):
        for key, value in [('observation', 'correct'), ('priority', True), ('recommendation', []),
                           ('evidence', 'page')]:
            decisions = self.decisions()
            decisions[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                review.record_review(self.path, review.prepare(self.path), 'fixture:0', decisions)
        for decisions in ({}, None, {**self.decisions(), 'extra': True}):
            with self.assertRaises(ValueError):
                review.record_review(self.path, review.prepare(self.path), 'fixture:0', decisions)

    def test_invalid_input_packet_cannot_be_repaired_by_overwriting_its_review(self):
        packet = review.prepare(self.path)
        packet['cases'][0]['findings'][0]['review']['priority'] = 'invented'
        with self.assertRaises(ValueError):
            review.record_review(self.path, packet, 'fixture:0', self.decisions(), replace=True)

    def test_changed_source_or_immutable_packet_data_is_refused(self):
        packet = review.prepare(self.path)
        packet['cases'][0]['findings'][0]['finding']['title'] = 'Changed claim'
        with self.assertRaisesRegex(ValueError, 'Finding data changed'):
            review.record_review(self.path, packet, 'fixture:0', self.decisions())
        packet = review.prepare(self.path)
        self.report['status'] = 404
        self.save()
        with self.assertRaisesRegex(ValueError, 'source or provenance changed'):
            review.record_review(self.path, packet, 'fixture:0', self.decisions())

    def test_changed_attached_evidence_is_refused_before_recording(self):
        self.evidence()
        packet = review.prepare(self.path)
        (self.root / 'page.html').write_text('Changed capture', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'source or provenance changed'):
            review.record_review(self.path, packet, 'fixture:0', self.decisions('supported'))

    def test_recording_is_offline_and_all_sources_remain_identical(self):
        self.evidence()
        before = {p: p.read_bytes() for p in self.root.iterdir()}
        with mock.patch('socket.socket', side_effect=AssertionError('No network')):
            packet = review.prepare(self.path)
            result = review.record_review(self.path, packet, 'fixture:0', self.decisions('supported'))
            review.markdown(review.summarize(self.path, result))
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.iterdir()})

    def test_cli_round_trip_preserves_original_packet_and_requires_fresh_output(self):
        self.evidence()
        packet = self.packet_file()
        original = packet.read_bytes()
        output = self.root / 'recorded.json'
        args = self.args(packet, output, 'supported')
        result = subprocess.run([sys.executable, str(fixture.SCRIPT)] + args, capture_output=True, text=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('fully_labelled', review.summarize(self.path, json.loads(output.read_text()))['review_status'])
        self.assertEqual(original, packet.read_bytes())
        with redirect_stderr(io.StringIO()):
            self.assertEqual(2, review.main(args))
            self.assertEqual(2, review.main(self.args(packet, packet, 'supported') + ['--replace-review']))
        self.assertEqual(original, packet.read_bytes())

    def test_existing_output_aliases_are_never_overwritten(self):
        packet = self.packet_file()
        original = packet.read_bytes()
        for kind in ('symlink', 'hardlink'):
            alias = self.root / (kind + '.json')
            try:
                if kind == 'symlink':
                    alias.symlink_to(packet)
                else:
                    os.link(str(packet), str(alias))
            except OSError as exc:
                self.skipTest('Filesystem link unavailable: ' + str(exc))
            with redirect_stderr(io.StringIO()):
                self.assertEqual(2, review.main(self.args(packet, alias)))
            self.assertEqual(original, packet.read_bytes())

    def test_cli_replacement_is_explicit_and_preserves_the_old_recorded_packet(self):
        packet = self.packet_file()
        first = self.root / 'first-review.json'
        replacement = self.root / 'replacement.json'
        self.assertEqual(0, review.main(self.args(packet, first)))
        original = first.read_bytes()
        with redirect_stderr(io.StringIO()):
            self.assertEqual(2, review.main(self.args(first, replacement, 'not_applicable')))
        self.assertFalse(replacement.exists())
        self.assertEqual(0, review.main(self.args(first, replacement, 'not_applicable') + ['--replace-review']))
        self.assertEqual(original, first.read_bytes())
        recorded = json.loads(replacement.read_text())['cases'][0]['findings'][0]['review']
        self.assertTrue(all(recorded[key] == 'not_applicable' for key in review.DIMENSIONS))

    def test_invalid_cli_decisions_create_no_output(self):
        packet = self.packet_file()
        output = self.root / 'invalid.json'
        with redirect_stderr(io.StringIO()):
            self.assertEqual(2, review.main(self.args(packet, output, 'supported')))
        self.assertFalse(output.exists())

    def test_output_cap_fails_instead_of_clipping_or_creating_a_packet(self):
        packet = self.packet_file()
        output = self.root / 'too-large.json'
        with mock.patch.object(review, 'MAX_PACKET_BYTES', len(packet.read_bytes()) + 1), redirect_stderr(io.StringIO()):
            self.assertEqual(2, review.main(self.args(packet, output)))
        self.assertFalse(output.exists())

    def test_file_outputs_request_owner_only_permissions(self):
        if os.name != 'posix':
            self.skipTest('POSIX mode-bit check')
        original_umask = os.umask(0)
        try:
            packet = self.root / 'private-pending.json'
            output = self.root / 'private-recorded.json'
            self.assertEqual(0, review.main(['prepare', str(self.path), '-o', str(packet)]))
            self.assertEqual(0, review.main(self.args(packet, output)))
            for path in (packet, output):
                self.assertEqual(0o600, path.stat().st_mode & 0o777)
        finally:
            os.umask(original_umask)

    def test_reviewer_text_is_data_not_executed_or_treated_as_independent_authority(self):
        decisions = self.decisions()
        decisions['reviewer'] = '<script>ATTACK</script>'
        decisions['rationale'] = '$(never execute)\n[remote](https://invalid.test)'
        with mock.patch('socket.socket', side_effect=AssertionError('No network')):
            result = review.record_review(self.path, review.prepare(self.path), 'fixture:0', decisions)
            summary = review.summarize(self.path, result)
        self.assertEqual(decisions, result['cases'][0]['findings'][0]['review'])
        self.assertNotIn('<script>', review.markdown(summary))
        self.assertIsNone(summary['accuracy_metrics'])


if __name__ == '__main__':
    unittest.main()
