"""Only measured image responses support weight findings or passing claims."""
from pathlib import Path
import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import scan
import audit as site_audit
import brief
import compare
import diff_scan
import plan
from lib import htmlx, http, images
from lib.report import Report, recorded_image_weight_problem, UNVERIFIED_IMAGE_WEIGHT_ERROR

BASE = 'https://example.test/'
HEADERS = {'content-type': 'image/png', 'content-length': str(600 * 1024)}


def audit(outcomes):
    doc = htmlx.parse(''.join('<img src="/' + str(i) + '.png" width="1" height="1">'
                             for i in range(len(outcomes))), base_url=BASE)
    def head(url, **kwargs):
        return outcomes[int(url.rsplit('/', 1)[-1].split('.')[0])]
    facts = images.audit_images(doc, BASE, head_info=head)
    report = Report(BASE)
    images.findings(facts, report)
    return facts, report


class TestImageWeightEvidence(unittest.TestCase):
    def test_failed_partial_and_nonimage_heads_cannot_supply_weight(self):
        cases = [(status, HEADERS, None) for status in (0, 204, 206, 301, 401, 403, 404, 429, 500)]
        cases += [(200, HEADERS, 'timeout'), (200, HEADERS, False),
                  (200, {'content-length': '614400'}, None),
                  (200, dict(HEADERS, **{'content-type': None}), None),
                  (200, dict(HEADERS, **{'content-type': ''}), None),
                  (200, dict(HEADERS, **{'content-type': 'text/html'}), None),
                  (200, dict(HEADERS, **{'content-range': 'bytes 0-99/614400'}), None),
                  (200, dict(HEADERS, **{'transfer-encoding': 'chunked'}), None)]
        for outcome in cases:
            with self.subTest(status=outcome[0], headers=outcome[1], error=outcome[2]):
                facts, report = audit([outcome])
                self.assertEqual([], facts['heavy'])
                self.assertEqual([], facts['legacy'])
                self.assertNotIn('No heavy images detected', {f.title for f in report.findings})
                self.assertEqual(0, facts['weight_verified'])
                self.assertEqual(1, facts['weight_unverified'])

    def test_missing_or_invalid_length_is_unknown_and_never_crashes(self):
        for size in (None, '', '12A', '-1', '1.5', '²', '６１４４００', '9' * 21,
                     '9' * 10000, 0, False, 1.5, [], '\u00a040960', 'X40960X'):
            with self.subTest(size=str(size)[:20]):
                facts, report = audit([(200, dict(HEADERS, **{'content-length': size}), None)])
                self.assertEqual([], facts['heavy'])
                self.assertEqual([], facts['legacy'])
                self.assertNotIn('No heavy images detected', {f.title for f in report.findings})
                self.assertEqual(0, facts['weight_verified'])

    def test_valid_ascii_lengths_include_zero_padding_and_rounding_boundaries(self):
        for size, expected in (('0', 0), ('512', 0), ('1536', 2), ('204800', 200),
                               ('614400', 600), ('0' * 10000 + '40960', 40), (' \t40960\t ', 40)):
            with self.subTest(size=size[:20]):
                self.assertEqual(expected, images._weight_kb(200, dict(HEADERS, **{'content-length': size}), None))
        self.assertGreater(images._weight_kb(200, dict(HEADERS, **{'content-length': '9' * 20}), None), 500)
        self.assertEqual(600, images._weight_kb(200, HEADERS, ''))
        facts, _ = audit([(200, {'content-type': ' IMAGE/PNG; charset=binary ', 'content-length': '614400'}, None)])
        self.assertEqual([600], [item['kb'] for item in facts['legacy']])

    def test_scan_records_verified_and_unknown_weights_without_an_all_clear(self):
        html = '<img src="/small.webp"><img src="/blocked.png">'
        response = http.Response(BASE, BASE, 200, {'content-type': 'text/html'}, html, 0)
        def head(url, **kwargs):
            return ((200, {'content-type': 'image/webp', 'content-length': '40960'}, None)
                    if url.endswith('small.webp') else (403, HEADERS, None))
        with mock.patch.object(scan.http, 'fetch', return_value=response), \
                mock.patch.object(images.http, 'head_info', side_effect=head), \
                mock.patch('socket.getaddrinfo', side_effect=AssertionError('Unexpected DNS lookup')) as dns:
            report = scan.scan(BASE, only=['technical'], ctx={})
        dns.assert_not_called()
        self.assertEqual({'checked': 2, 'unchecked': 0, 'missing_dims': 2,
                          'weight_verified': 1, 'weight_unverified': 1}, report.meta['images'])
        self.assertNotIn('No heavy images detected', {f.title for f in report.findings})
        self.assertEqual(report.meta['images'], json.loads(report.to_json())['meta']['images'])
        for rendered in (report.to_markdown(), report.to_html()):
            self.assertIn(UNVERIFIED_IMAGE_WEIGHT_ERROR, rendered)

    def test_receipts_do_not_guess_legacy_data_or_accept_invalid_counts(self):
        for images_meta in ({}, {'checked': 1}, {'checked': 1, 'weight_verified': 1, 'weight_unverified': 0}):
            self.assertIsNone(recorded_image_weight_problem({'images': images_meta}))
        for receipt in ({'checked': 1, 'weight_verified': 1}, {'checked': 1, 'weight_unverified': 1}):
            self.assertEqual(UNVERIFIED_IMAGE_WEIGHT_ERROR, recorded_image_weight_problem({'images': receipt}))
        pending = {'images': {'checked': 1, 'weight_verified': 0, 'weight_unverified': 1},
                   'scan_scope': {'requested': ['technical', 'schema'], 'completed': ['schema']}}
        self.assertEqual(UNVERIFIED_IMAGE_WEIGHT_ERROR, recorded_image_weight_problem(pending, for_score=True))
        for changes in ({'weight_unverified': 1}, {'weight_verified': False},
                        {'weight_verified': -1}, {'weight_verified': '1'}, {'checked': None}):
            receipt = {'checked': 1, 'weight_verified': 1, 'weight_unverified': 0}
            receipt.update(changes)
            meta = {'images': receipt}
            self.assertEqual(UNVERIFIED_IMAGE_WEIGHT_ERROR, recorded_image_weight_problem(meta))
            meta['scan_scope'] = {'requested': ['schema'], 'completed': ['schema'], 'not_selected': ['technical', 'content', 'geo']}
            self.assertIsNone(recorded_image_weight_problem(meta, for_score=True))
            self.assertEqual(UNVERIFIED_IMAGE_WEIGHT_ERROR, recorded_image_weight_problem(meta))

    def test_uncertainty_blocks_fix_claims_briefs_comparisons_and_source_actions(self):
        report = Report(BASE, fetched_status=200, meta={
            'images': {'checked': 1, 'weight_verified': 0, 'weight_unverified': 1},
            'scan_scope': {'requested': ['technical'], 'completed': ['technical']}})
        report._doc = htmlx.parse('<title>Page</title><h1>Page</h1>', base_url=BASE)
        after = json.loads(report.to_json())
        before = copy.deepcopy(after)
        before['meta']['images'] = {'checked': 1, 'weight_verified': 1, 'weight_unverified': 0}
        before['findings'] = [{'category': 'technical', 'severity': 'medium', 'title': 'Heavy images', 'rule_id': 'technical.heavy.images'}]
        self.assertEqual('comparable', diff_scan.diff_reports(before, before)['comparison']['status'])
        before_audit = {'site': BASE, 'overall_score': 100, 'homepage': before, 'crawl': {'pages': []}}
        after_audit = {'site': BASE, 'overall_score': 100, 'homepage': after, 'crawl': {'pages': []}}
        for old, new in ((before, after), (after, before), (before_audit, after_audit), (after_audit, before_audit)):
            result = diff_scan.diff_reports(old, new)
            self.assertEqual('incomparable', result['comparison']['status'])
            self.assertIsNone(result['score_delta'])
            self.assertEqual([], result['resolved'])
            self.assertTrue(any(UNVERIFIED_IMAGE_WEIGHT_ERROR in reason for reason in result['comparison']['reasons']))
        with tempfile.TemporaryDirectory() as directory:
            old_path, new_path = Path(directory) / 'old.json', Path(directory) / 'new.json'
            old_path.write_text(json.dumps(before)); new_path.write_text(json.dumps(after))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(2, diff_scan.main([str(old_path), str(new_path), '--fail-on-regression']))
            actions = plan.build_plan(after, directory)['actions']
        self.assertEqual(1, len(actions))
        self.assertEqual('technical.images.weight.unverified', actions[0]['rule_id'])
        self.assertTrue(actions[0]['manual_action'])
        self.assertEqual([], actions[0]['likely_files'])
        self.assertFalse(actions[0]['requires_deploy'])
        with mock.patch.object(compare.scanner, 'scan', return_value=report):
            result = compare.run([BASE])
            self.assertTrue(result['failed'][0]['image_weight_unverified'])
            with self.assertRaisesRegex(RuntimeError, 'Image weights need verification'):
                brief._page(BASE)
        self.assertIn(UNVERIFIED_IMAGE_WEIGHT_ERROR,
                      site_audit._schema_score_note({'page': report, 'site_result': {'pages': []}}))

    def test_valid_lengths_keep_real_findings_and_count_mixed_coverage(self):
        facts, report = audit([(200, HEADERS, None), (404, HEADERS, None),
                               (200, {'content-type': 'image/webp'}, None)])
        self.assertEqual(3, facts['checked'])
        self.assertEqual(1, facts['weight_verified'])
        self.assertEqual(2, facts['weight_unverified'])
        self.assertEqual([600], [item['kb'] for item in facts['heavy']])
        self.assertEqual([600], [item['kb'] for item in facts['legacy']])
        heavy = next(f for f in report.findings if f.title.startswith('Heavy images'))
        self.assertIn('Measured weights for 1 of 3 images', heavy.detail)

    def test_small_weights_pass_only_when_all_attempted_weights_are_measured(self):
        small = (200, {'content-type': 'image/webp', 'content-length': '40960'}, None)
        facts, report = audit([small])
        self.assertEqual(1, facts['weight_verified'])
        self.assertIn('No heavy images detected', {f.title for f in report.findings})
        facts, report = audit([small, (200, {'content-type': 'image/webp'}, None)])
        self.assertEqual(1, facts['weight_unverified'])
        self.assertNotIn('No heavy images detected', {f.title for f in report.findings})


if __name__ == '__main__':
    unittest.main()
