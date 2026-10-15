"""Opt-in review acquisition preserves scan inputs, not validated findings."""

from contextlib import redirect_stderr
from hashlib import sha256
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'skills/seo-scan/scripts'))
import scan
from lib import http


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


capture = load('capture_review_case', 'capture_review_case.py')
review = load('capture_review_corpus', 'review_corpus.py')
URL = 'https://example.test/guide'
HTML = '<html lang="en"><title>Captured guide</title><p>By Jane Doe</p><article><h1>Guide</h1><p>Stored evidence.</p></article></html>'
CONTEXT = {'robots_txt': 'User-agent: *\nDisallow:\n', 'sitemap_found': True, 'llms_txt': False}


def response(source=HTML, **kwargs):
    defaults = {'url': URL, 'final_url': URL, 'status': 200,
                'headers': {'content-type': 'text/html', 'set-cookie': 'private-test-cookie'},
                'text': source, 'elapsed_ms': 1, 'robots_header_fields': ['noindex', 'nofollow'],
                'robots_header_basis': 'response_header_fields'}
    defaults.update(kwargs)
    return http.Response(**defaults)


class TestReviewCapture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.target = self.root / 'case'

    def record(self, replies=None, **kwargs):
        with mock.patch.object(http, 'fetch', side_effect=replies or [response()]) as fetch, \
                mock.patch.object(scan, 'gather_context', return_value=dict(CONTEXT)) as context, \
                mock.patch('socket.socket', side_effect=AssertionError('No network')):
            result = capture.capture(URL, self.target, case_id='guide', check_images=False, **kwargs)
        return result, fetch, context

    def read(self, name):
        return json.loads((self.target / name).read_text(encoding='utf-8'))

    def test_same_response_and_context_are_preserved_without_a_refetch(self):
        manifest, fetch, context = self.record(source_revision='declared-test-revision')
        self.assertEqual(1, fetch.call_count)
        self.assertEqual(1, context.call_count)
        self.assertEqual(HTML, (self.target / 'page-source.txt').read_text(encoding='utf-8'))
        metadata = self.read('capture.json')
        self.assertEqual('captured_inputs_only_pending_review', metadata['interpretation'])
        self.assertEqual('private-test-cookie', metadata['primary_response']['headers']['set-cookie'])
        self.assertEqual(['noindex', 'nofollow'], metadata['primary_response']['robots_header_fields'])
        self.assertEqual('response_header_fields', metadata['primary_response']['robots_header_basis'])
        self.assertEqual('operator_supplied_unverified', metadata['revision_basis'])
        self.assertEqual('declared-test-revision', metadata['declared_source_revision'])
        self.assertEqual(sys.version, metadata['runtime']['python'])
        self.assertEqual('installed_version_inventory_not_backend_selection_proof', metadata['runtime']['basis'])
        self.assertEqual({'requests', 'beautifulsoup4', 'lxml', 'trafilatura', 'playwright'},
                         set(metadata['runtime']['optional_distributions']))
        self.assertEqual(CONTEXT['robots_txt'], self.read('site-context.json')['robots_txt'])
        self.assertEqual(manifest, self.read('manifest.json'))
        for name, witness in metadata['files'].items():
            raw = (self.target / name).read_bytes()
            self.assertEqual({'bytes': len(raw), 'sha256': sha256(raw).hexdigest()}, witness)
        self.assertNotIn('private-test-cookie', (self.target / 'report.json').read_text())
        self.assertEqual([], list(self.target.glob('*.html')))

    def test_output_is_compatible_with_pending_review_and_no_accuracy_claim(self):
        self.record()
        packet = review.prepare(self.target / 'manifest.json')
        summary = review.summarize(self.target / 'manifest.json', packet)
        self.assertEqual(1, summary['cases_with_attached_files'])
        self.assertEqual('pending', summary['review_status'])
        self.assertIsNone(summary['accuracy_metrics'])
        self.assertIsNone(summary['recall_metrics'])
        self.assertGreater(summary['finding_count'], 0)
        self.assertEqual(0, summary['fully_labelled_findings'])

    def test_normal_scans_do_not_retain_raw_inputs_or_change_json_when_opted_in(self):
        reports = []
        for retain in (False, True):
            with mock.patch.object(http, 'fetch', return_value=response()), \
                    mock.patch('socket.socket', side_effect=AssertionError('No network')):
                reports.append(scan.scan(URL, ctx=dict(CONTEXT), check_images=False, retain_evidence=retain))
        self.assertFalse(hasattr(reports[0], '_capture_inputs'))
        self.assertEqual(reports[0].to_json(), reports[1].to_json())
        self.assertEqual(reports[0].to_markdown(), reports[1].to_markdown())
        self.assertNotIn('_capture_inputs', reports[1].to_json())

    def test_rendered_primary_and_actual_paired_served_response_are_separate(self):
        rendered = response(HTML + '<p>Rendered marker</p>', rendered=True)
        served = response('<title>Raw input</title><p>Served marker</p>')
        manifest, fetch, _ = self.record(replies=[rendered, served], render=True)
        self.assertEqual(2, fetch.call_count)
        self.assertEqual(rendered.text, (self.target / 'page-source.txt').read_text())
        self.assertEqual(served.text, (self.target / 'served-source.txt').read_text())
        self.assertEqual(4, len(manifest['cases'][0]['evidence']))
        self.assertTrue(self.read('capture.json')['primary_response']['rendered'])
        self.assertFalse(self.read('capture.json')['served_comparison_response']['rendered'])
        self.assertEqual('measured', self.read('report.json')['meta']['coverage']['js_comparison']['status'])
        review.prepare(self.target / 'manifest.json')

    def test_render_request_fallback_is_not_called_a_rendered_dom(self):
        manifest, fetch, _ = self.record(render=True)
        self.assertEqual(1, fetch.call_count)
        self.assertEqual('declared_decoded_response_text', manifest['cases'][0]['evidence'][0]['kind'])
        self.assertTrue(self.read('capture.json')['settings']['render_requested'])
        self.assertFalse(self.read('capture.json')['primary_response']['rendered'])

    def test_failed_paired_fetch_is_unknown_not_invented_source(self):
        rendered = response(rendered=True)
        self.record(replies=[rendered, OSError('Unavailable')], render=True)
        self.assertFalse((self.target / 'served-source.txt').exists())
        self.assertIsNone(self.read('capture.json')['served_comparison_response'])
        self.assertEqual('served_html_unavailable', self.read('report.json')['meta']['coverage']['js_comparison']['reason'])

    def test_truncated_rendered_input_does_not_get_an_invented_served_comparison(self):
        partial = response(rendered=True, headers={'content-type': 'text/html', 'x-narwhal-truncated': 'true'})
        _, fetch, _ = self.record(replies=[partial], render=True)
        self.assertEqual(1, fetch.call_count)
        self.assertTrue(self.read('capture.json')['scan_coverage']['response_truncated'])
        self.assertIsNone(self.read('capture.json')['served_comparison_response'])

    def test_render_failure_does_not_claim_an_observed_dom(self):
        failed = response('', status=0, rendered=True, error='Document replacement rejected')
        manifest, fetch, context = self.record(replies=[failed], render=True)
        self.assertEqual(1, fetch.call_count)
        context.assert_not_called()
        self.assertEqual('declared_error_response_text', manifest['cases'][0]['evidence'][0]['kind'])
        self.assertEqual([], self.read('report.json')['meta']['scan_scope']['completed'])

    def test_http_errors_and_nonhtml_capture_observed_inputs_without_measurement_claims(self):
        for status, kind in ((404, 'text/html'), (200, 'application/json')):
            with self.subTest(status=status, kind=kind):
                self.target = self.root / ('case-' + str(status))
                failed = response('Observed error or non-HTML body', status=status, headers={'content-type': kind})
                _, fetch, context = self.record(replies=[failed])
                self.assertEqual(1, fetch.call_count)
                context.assert_not_called()
                self.assertIsNone(self.read('site-context.json'))
                self.assertEqual(status, self.read('capture.json')['primary_response']['status'])
                self.assertEqual([], self.read('report.json')['meta']['scan_scope']['completed'])
                review.prepare(self.target / 'manifest.json')

    def test_existing_directory_refuses_before_any_scan(self):
        self.target.mkdir()
        (self.target / 'sentinel').write_text('user data')
        with mock.patch.object(scan, 'scan') as scanner:
            with self.assertRaises(FileExistsError):
                capture.capture(URL, self.target, case_id='guide')
        scanner.assert_not_called()
        self.assertEqual('user data', (self.target / 'sentinel').read_text())

    def test_invalid_identifiers_settings_credentials_fail_before_directory_creation(self):
        variants = ({'case_id': '../escape'}, {'case_id': ''}, {'timeout': True},
                    {'timeout': 0}, {'max_bytes': 63_999}, {'max_bytes': 20_000_001},
                    {'only': ['not-an-auditor']}, {'source_revision': 'x' * 161},
                    {'allow_private': 'false'}, {'render': 1}, {'check_images': None})
        for variant in variants:
            with self.subTest(variant=variant), mock.patch.object(scan, 'scan') as scanner:
                kwargs = {'case_id': 'guide', **variant}
                with self.assertRaises(ValueError):
                    capture.capture(URL, self.target, **kwargs)
                scanner.assert_not_called()
                self.assertFalse(self.target.exists())
        with self.assertRaisesRegex(ValueError, 'credentials'):
            capture.capture('https://user:secret@example.test/', self.target, case_id='guide')
        self.assertFalse(self.target.exists())

    def test_private_hosts_still_rejected_without_explicit_optin(self):
        with mock.patch('socket.socket', side_effect=AssertionError('Must reject before HTTP')):
            with self.assertRaises(http.SSRFError):
                capture.capture('http://127.0.0.1/', self.target, case_id='private')
        self.assertFalse((self.target / 'manifest.json').exists())

    def test_artifact_limit_error_keeps_no_completion_manifest_or_truncated_evidence(self):
        with mock.patch.object(capture, 'MAX_EVIDENCE_BYTES', 20):
            with self.assertRaisesRegex(ValueError, 'byte limit'):
                self.record()
        self.assertEqual([], list(self.target.iterdir()))

    def test_interrupted_write_leaves_partial_files_but_no_manifest(self):
        original = os.open
        def interrupt(path, *args, **kwargs):
            if Path(path).name == 'site-context.json':
                raise OSError('Synthetic write failure')
            return original(path, *args, **kwargs)
        with mock.patch.object(os, 'open', interrupt):
            with self.assertRaisesRegex(OSError, 'Synthetic write failure'):
                self.record()
        self.assertTrue((self.target / 'report.json').is_file())
        self.assertTrue((self.target / 'page-source.txt').is_file())
        self.assertFalse((self.target / 'manifest.json').exists())

    @unittest.skipIf(os.name == 'nt', 'POSIX permission bits only')
    def test_local_capture_files_are_owner_only(self):
        self.record()
        self.assertEqual(0o700, self.target.stat().st_mode & 0o777)
        self.assertTrue(all(path.stat().st_mode & 0o077 == 0 for path in self.target.iterdir()))

    def test_cli_error_preserves_existing_data_and_reports_capture_not_validation(self):
        self.target.mkdir()
        errors = io.StringIO()
        with redirect_stderr(errors):
            result = capture.main([URL, '--output-dir', str(self.target), '--case-id', 'guide'])
        self.assertEqual(2, result)
        self.assertIn('not a completed capture', errors.getvalue())

    def test_partial_manifest_is_not_mistaken_for_a_completed_capture(self):
        original = capture._write_new
        def interrupt(path, raw):
            if path.name == 'manifest.json':
                original(path, raw[:10])
                raise OSError('Synthetic manifest interruption')
            return original(path, raw)
        with mock.patch.object(capture, '_write_new', side_effect=interrupt):
            with self.assertRaisesRegex(OSError, 'manifest interruption'):
                self.record()
        self.assertTrue((self.target / 'manifest.json').exists())
        with self.assertRaises(ValueError):
            review.prepare(self.target / 'manifest.json')

    def test_file_appearing_after_reservation_is_never_overwritten(self):
        original = capture._write_new
        def collision(path, raw):
            if path.name == 'page-source.txt':
                path.write_text('concurrent user data')
            return original(path, raw)
        with mock.patch.object(capture, '_write_new', side_effect=collision):
            with self.assertRaises(FileExistsError):
                self.record()
        self.assertEqual('concurrent user data', (self.target / 'page-source.txt').read_text())
        self.assertFalse((self.target / 'manifest.json').exists())


if __name__ == '__main__':
    unittest.main()
