"""Review coverage must never masquerade as measured scanner accuracy."""

import copy
from contextlib import redirect_stderr
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'scripts/review_corpus.py'
SPEC = importlib.util.spec_from_file_location('review_corpus', SCRIPT)
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


class TestReviewCorpus(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.report = {'url': 'https://example.test/', 'status': 200, 'rendered': False,
                       'findings': [{'category': 'technical', 'severity': 'high',
                                     'title': 'Missing title', 'detail': 'No title observed',
                                     'recommendation': 'Add a descriptive title.'},
                                    {'category': 'technical', 'severity': 'good', 'title': 'One H1'}]}
        self.manifest = {'schema_version': 1, 'name': 'Fixture review',
                         'cases': [{'id': 'fixture', 'report': 'report.json'}]}
        self.path = self.root / 'manifest.json'
        self.save()

    def save(self):
        (self.root / 'report.json').write_text(json.dumps(self.report), encoding='utf-8')
        self.path.write_text(json.dumps(self.manifest), encoding='utf-8')

    def evidence(self):
        (self.root / 'page.html').write_text('<html><h1>Fixture</h1></html>', encoding='utf-8')
        self.manifest['cases'][0]['evidence'] = [{'id': 'page', 'path': 'page.html',
                                                'kind': 'declared_page_html', 'captured_at': '2026-10-15T10:00:00Z'}]
        self.save()

    def label(self, packet, verdict='supported'):
        packet['cases'][0]['findings'][0]['review'] = {
            **{key: verdict for key in review.DIMENSIONS}, 'reviewer': 'Self-reported reviewer',
            'reviewed_at': '2026-10-15T11:00:00+00:00', 'rationale': 'Fixture review, not independent validation.',
            'evidence': ['page'] if packet['cases'][0]['evidence'] else []}

    def test_preparation_is_deterministic_pending_and_does_not_invent_legacy_provenance(self):
        packet = review.prepare(self.path)
        self.assertEqual(packet, review.prepare(self.path))
        case = packet['cases'][0]
        self.assertIsNone(case['provenance']['schema_version'])
        self.assertIsNone(case['provenance']['tool_version'])
        self.assertEqual('report_only', case['evidence_status'])
        self.assertEqual(1, case['excluded_good_findings'])
        self.assertEqual('fixture:0', case['findings'][0]['id'])
        summary = review.summarize(self.path, packet)
        self.assertEqual('pending', summary['review_status'])
        self.assertEqual(1, summary['verdict_counts']['observation']['pending'])
        self.assertIsNone(summary['accuracy_metrics'])
        self.assertIsNone(summary['recall_metrics'])

    def test_labelled_reviews_still_cannot_establish_accuracy_recall_or_independence(self):
        self.evidence()
        packet = review.prepare(self.path)
        self.label(packet)
        summary = review.summarize(self.path, packet)
        self.assertEqual('fully_labelled', summary['review_status'])
        self.assertEqual(1, summary['fully_labelled_findings'])
        self.assertEqual(1, summary['cases_with_attached_files'])
        self.assertEqual(['Self-reported reviewer'], summary['self_reported_reviewer_labels'])
        self.assertIsNone(summary['accuracy_metrics'])
        self.assertIsNone(summary['recall_metrics'])
        self.assertIn('reviewer independence are not measured', summary['basis'])

    def test_report_only_cannot_support_a_confident_verdict_without_frozen_evidence(self):
        packet = review.prepare(self.path)
        self.label(packet)
        with self.assertRaisesRegex(ValueError, 'attached evidence'):
            review.summarize(self.path, packet)
        self.label(packet, 'uncertain')
        summary = review.summarize(self.path, packet)
        self.assertEqual(1, summary['report_only_cases'])
        self.assertIsNone(summary['accuracy_metrics'])

    def test_partial_reviews_count_each_dimension_without_filling_pending_labels(self):
        self.evidence()
        packet = review.prepare(self.path)
        self.label(packet)
        packet['cases'][0]['findings'][0]['review']['priority'] = 'pending'
        summary = review.summarize(self.path, packet)
        self.assertEqual('partial', summary['review_status'])
        self.assertEqual(0, summary['fully_labelled_findings'])
        self.assertEqual(1, summary['verdict_counts']['priority']['pending'])
        self.assertEqual(1, summary['verdict_counts']['observation']['supported'])

    def test_missing_reviewer_rationale_timestamp_or_known_evidence_is_rejected(self):
        self.evidence()
        source = review.prepare(self.path)
        self.label(source)
        for key, value in (('reviewer', ''), ('rationale', ''), ('reviewed_at', '2026-10-15'),
                           ('evidence', ['unknown']), ('observation', 'correct'), ('priority', [])):
            with self.subTest(key=key):
                packet = copy.deepcopy(source)
                packet['cases'][0]['findings'][0]['review'][key] = value
                with self.assertRaises(ValueError):
                    review.summarize(self.path, packet)

    def test_source_report_changed_after_packet_creation_is_rejected(self):
        packet = review.prepare(self.path)
        self.report['status'] = 404
        self.save()
        with self.assertRaisesRegex(ValueError, 'source or provenance changed'):
            review.summarize(self.path, packet)

    def test_manifest_change_or_byte_change_is_not_silently_reused(self):
        packet = review.prepare(self.path)
        self.path.write_text(self.path.read_text() + '\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'stale or changed'):
            review.summarize(self.path, packet)

    def test_changed_attached_evidence_is_rejected(self):
        self.evidence()
        packet = review.prepare(self.path)
        (self.root / 'page.html').write_text('<title>Changed</title>', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'source or provenance changed'):
            review.summarize(self.path, packet)

    def test_report_cannot_be_its_own_corroborating_attachment(self):
        self.evidence()
        self.manifest['cases'][0]['evidence'][0]['path'] = 'report.json'
        self.save()
        with self.assertRaisesRegex(ValueError, 'cannot corroborate itself'):
            review.prepare(self.path)

    def test_dropped_cases_findings_and_changed_data_cannot_inflate_review_coverage(self):
        source = review.prepare(self.path)
        variants = []
        packet = copy.deepcopy(source)
        packet['cases'] = []
        variants.append(packet)
        packet = copy.deepcopy(source)
        packet['cases'][0]['findings'] = []
        variants.append(packet)
        packet = copy.deepcopy(source)
        packet['cases'][0]['findings'][0]['finding']['title'] = 'Changed claim'
        variants.append(packet)
        packet = copy.deepcopy(source)
        packet['cases'][0]['provenance']['rendered'] = 0
        variants.append(packet)
        packet = copy.deepcopy(source)
        packet['schema_version'] = True
        variants.append(packet)
        for packet in variants:
            with self.assertRaises(ValueError):
                review.summarize(self.path, packet)

    def test_duplicate_cases_or_copied_report_bytes_are_not_extra_cases(self):
        entry = self.manifest['cases'][0]
        for second in (dict(entry), {**entry, 'id': 'copy'}):
            self.manifest['cases'] = [entry, second]
            self.save()
            with self.assertRaises(ValueError):
                review.prepare(self.path)

    def test_relative_path_boundary_and_absolute_paths_are_enforced(self):
        for path in ('../outside.json', str(self.root / 'report.json')):
            self.manifest['cases'][0]['report'] = path
            self.save()
            with self.assertRaises(ValueError):
                review.prepare(self.path)

    def test_symlink_outside_manifest_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / 'outside.json'
            target.write_text(json.dumps(self.report), encoding='utf-8')
            link = self.root / 'link.json'
            try:
                link.symlink_to(target)
            except OSError as exc:
                self.skipTest('Symlink permission unavailable: ' + str(exc))
            self.manifest['cases'][0]['report'] = 'link.json'
            self.save()
            with self.assertRaisesRegex(ValueError, 'escapes'):
                review.prepare(self.path)

    def test_count_and_byte_caps_fail_explicitly_without_partial_packets(self):
        for name, limit in (('MAX_CASES', 0), ('MAX_FINDINGS', 0), ('MAX_REPORT_BYTES', 8), ('MAX_INPUT_BYTES', 1)):
            with self.subTest(name=name), mock.patch.object(review, name, limit):
                with self.assertRaises(ValueError):
                    review.prepare(self.path)
        self.evidence()
        with mock.patch.object(review, 'MAX_EVIDENCE_BYTES', 8):
            with self.assertRaises(ValueError):
                review.prepare(self.path)

    def test_malformed_json_protocols_nonfinite_numbers_and_severity_are_rejected(self):
        for raw in ('{"schema_version":1,"schema_version":1}', '{broken', '{"value": NaN}'):
            self.path.write_text(raw, encoding='utf-8')
            with self.assertRaises(ValueError):
                review.prepare(self.path)
        self.save()
        self.report['findings'][0]['severity'] = 'urgent'
        self.save()
        with self.assertRaisesRegex(ValueError, 'severity'):
            review.prepare(self.path)

    def test_empty_corpus_or_no_actionable_findings_is_not_an_accuracy_pass(self):
        self.manifest['cases'] = []
        self.save()
        with self.assertRaises(ValueError):
            review.prepare(self.path)
        self.manifest['cases'] = [{'id': 'fixture', 'report': 'report.json'}]
        self.report['findings'] = [self.report['findings'][1]]
        self.save()
        summary = review.summarize(self.path, review.prepare(self.path))
        self.assertEqual('no_actionable_findings', summary['review_status'])
        self.assertIsNone(summary['accuracy_metrics'])

    def test_source_text_is_data_not_executed_or_rendered_as_markdown(self):
        self.report['findings'][0]['title'] = '<script>untrusted()</script> [remote](https://invalid.test)'
        self.save()
        with mock.patch('socket.socket', side_effect=AssertionError('No network')):
            packet = review.prepare(self.path)
            text = review.markdown(review.summarize(self.path, packet))
        self.assertNotIn('<script>', text)
        self.assertNotIn('invalid.test', text)
        self.assertIn('Accuracy and recall: not measured', text)

    def test_cli_round_trip_is_offline_and_existing_outputs_are_never_overwritten(self):
        packet = self.root / 'packet.json'
        result = subprocess.run([sys.executable, str(SCRIPT), 'prepare', str(self.path), '-o', str(packet)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr)
        raw = packet.read_bytes()
        stream = io.StringIO()
        with redirect_stderr(stream):
            self.assertEqual(2, review.main(['prepare', str(self.path), '-o', str(packet)]))
            self.assertEqual(2, review.main(['prepare', str(self.path), '-o', str(self.path)]))
        self.assertEqual(raw, packet.read_bytes())
        result = subprocess.run([sys.executable, str(SCRIPT), 'summarize', str(self.path), str(packet)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('pending', json.loads(result.stdout)['review_status'])

    def test_historical_manifest_is_only_an_unreviewed_report_inventory(self):
        path = ROOT / 'docs/tuning/review-corpus.json'
        packet = review.prepare(path)
        summary = review.summarize(path, packet)
        self.assertEqual(15, summary['case_count'])
        self.assertEqual(15, summary['report_only_cases'])
        self.assertGreater(summary['finding_count'], 0)
        self.assertEqual('pending', summary['review_status'])
        self.assertIsNone(summary['accuracy_metrics'])


if __name__ == '__main__':
    unittest.main()
