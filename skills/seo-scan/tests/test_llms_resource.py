"""Root-file evidence does not confuse HTML/gates/failure with publication."""

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_geo
import brief
import compare
import crawl_site
import diff_scan
import plan
import scan
from lib import htmlx, http, llms_resource
from lib.report import Report, recorded_llms_problem

BASE = 'https://example.test/'
URL = BASE + 'llms.txt'


def response(status=200, body='# Project\n\n> A concise guide.', mime='text/plain', **kw):
    headers = {'content-type': mime}
    if kw.pop('truncated', False):
        headers['x-narwhal-truncated'] = 'true'
    return http.Response(URL, URL, status, headers, body, 0, **kw)


def report_for(resp, only='geo'):
    rep = Report(BASE, final_url=BASE, fetched_status=200)
    rep.meta['scan_scope'] = {'requested': [only], 'completed': [only]}
    rep._doc = htmlx.parse('<html><title>Fixture</title><h1>Fixture</h1></html>', BASE)
    audit_geo._llms_txt({'llms_txt_receipt': llms_resource.assess(resp)}, rep)
    return rep


class TestLlmsResponseEvidence(unittest.TestCase):
    def test_text_candidates_support_atx_setext_bom_and_media_types(self):
        for mime in ('text/plain', 'text/markdown; charset=utf-8', 'text/x-markdown', ''):
            for body in ('# Project', '\ufeff\n \t\n# Project', 'Project\n=======\n\nDetails'):
                with self.subTest(mime=mime, body=body):
                    receipt = llms_resource.assess(response(body=body, mime=mime))
                    self.assertEqual('observed', receipt['state'])
                    self.assertIsNotNone(llms_resource.recorded(receipt))
                    rep = report_for(response(body=body, mime=mime))
                    self.assertEqual(['geo.llms.txt.published'], [f.rule_id for f in rep.findings])
                    self.assertIn('candidate', rep.findings[0].title)
                    self.assertIn('not full proposal validation', rep.findings[0].detail)

    def test_html_fallback_is_not_published_or_missing(self):
        for mime, body in (('text/html', '# Project'), ('application/xhtml+xml', '# Project'),
                           ('text/plain', '<!DOCTYPE html><html><h1>App</h1></html>'),
                           ('', '\ufeff <HTML><h1>App</h1></HTML>')):
            with self.subTest(mime=mime):
                rep = report_for(response(body=body, mime=mime))
                self.assertFalse(rep.findings)
                self.assertEqual('html_response', rep.meta['llms_txt']['reason'])
                self.assertEqual(100, rep.score())
                self.assertIn('unverified', rep.to_markdown())

    def test_plain_soft_errors_empty_other_formats_and_indented_code_are_unverified(self):
        for body, mime in (('Not found', 'text/plain'), ('', 'text/plain'), ('\ufeff \n', 'text/plain'),
                           ('{"name":"Project"}', 'application/json'), ('<root/>', 'application/xml'),
                           ('# Project', 'application/octet-stream'), ('    # Code', 'text/plain'),
                           ('    Project\n===', 'text/plain')):
            with self.subTest(body=body, mime=mime):
                rep = report_for(response(body=body, mime=mime))
                self.assertFalse(rep.findings)
                self.assertEqual('unverified', rep.meta['llms_txt']['state'])

    def test_404_and_410_record_only_root_absence_with_stable_rule(self):
        for status in (404, 410):
            rep = report_for(response(status=status, body='<html>missing</html>', mime='text/html'))
            self.assertEqual('absent', rep.meta['llms_txt']['state'])
            self.assertEqual([('geo.no.llms.txt', 'low', 'site')], [(f.rule_id, f.severity, f.scope) for f in rep.findings])
            self.assertIn('Root', rep.findings[0].detail)
            self.assertIn('subpath files', rep.findings[0].detail)

    def test_gates_http_errors_and_no_response_are_not_absence(self):
        for status in (0, 101, 301, 304, 401, 403, 429, 500, 503, 999):
            with self.subTest(status=status):
                rep = report_for(response(status=status, error='secret-token' if status == 0 else None))
                self.assertFalse(rep.findings)
                self.assertEqual('unverified', rep.meta['llms_txt']['state'])
                self.assertEqual('root_http_response', rep.meta['llms_txt']['basis'])
                self.assertNotIn('secret-token', rep.to_json())

    def test_truncated_candidate_is_not_verified_and_body_is_not_retained(self):
        rep = report_for(response(body='# Project\nsecret-body-token', truncated=True))
        self.assertEqual('truncated', rep.meta['llms_txt']['reason'])
        self.assertFalse(rep.findings)
        self.assertNotIn('secret-body-token', rep.to_json())

    def test_partial_or_no_content_status_does_not_verify_a_complete_candidate(self):
        for status in (204, 205, 206):
            rep = report_for(response(status=status))
            self.assertFalse(rep.findings)
            self.assertEqual('unverified', rep.meta['llms_txt']['state'])
        resp = response()
        resp.headers['content-range'] = 'bytes 0-100/500'
        self.assertEqual('partial_response', llms_resource.assess(resp)['reason'])

    def test_probe_uses_one_existing_fetch_without_following_markdown_links(self):
        resp = response(body='# Project\n\n- [secret](http://127.0.0.1/private)')
        with mock.patch.object(http, 'fetch', return_value=resp) as fetch:
            receipt = llms_resource.probe(URL, allow_private=False, timeout=7)
        fetch.assert_called_once_with(URL, allow_private=False, timeout=7)
        self.assertEqual('observed', receipt['state'])
        self.assertNotIn('private', json.dumps(receipt))

    def test_probe_keeps_default_private_host_guard(self):
        with mock.patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 80))]):
            with self.assertRaises(http.SSRFError):
                llms_resource.probe('http://127.0.0.1/llms.txt', allow_private=False, timeout=1)

    def test_redirect_target_is_recorded_without_claiming_other_subpaths(self):
        resp = response()
        resp.final_url = BASE + 'docs/llms.txt'
        receipt = llms_resource.assess(resp)
        self.assertEqual(resp.final_url, receipt['final_url'])
        self.assertEqual('/llms.txt', receipt['checked_path'])

    def test_context_fetches_once_and_preserves_legacy_flags_without_making_them_authority(self):
        for resp, expected in ((response(), True), (response(mime='text/html'), False), (response(status=404), False)):
            with mock.patch.object(http, 'fetch_text', return_value=''), \
                    mock.patch.object(http, 'fetch_bytes', return_value=(None, 'HTTP 404')), \
                    mock.patch.object(http, 'fetch', return_value=resp) as fetch:
                ctx = scan.gather_context(BASE, allow_private=False, timeout=1)
            self.assertEqual(1, fetch.call_count)
            self.assertEqual(expected, ctx['llms_txt'])
            self.assertEqual(llms_resource.assess(resp), ctx['llms_txt_receipt'])

    def test_legacy_flags_and_missing_context_are_not_relabelled_as_http_measurements(self):
        for ctx in ({}, {'llms_txt': True}, {'llms_txt': False}):
            rep = Report(BASE)
            audit_geo._llms_txt(ctx, rep)
            self.assertEqual('unverified', rep.meta['llms_txt']['state'])
            self.assertIsNone(recorded_llms_problem(rep.meta, for_score=True))
            self.assertIn('no root http evidence', rep.to_markdown().lower())
            self.assertNotIn('llms.txt published', rep.to_markdown())

    def test_malformed_or_future_receipt_cannot_fall_back_to_a_true_flag(self):
        valid = llms_resource.assess(response())
        for bad in ({**valid, 'version': True}, {**valid, 'version': 99},
                    {**valid, 'state': 'absent'}, {**valid, 'http_status': 404},
                    {**valid, 'body_truncated': True}, {**valid, 'basis': 'unknown'},
                    {**valid, 'state': 'unverified', 'reason': []}):
            rep = Report(BASE)
            audit_geo._llms_txt({'llms_txt_receipt': bad, 'llms_txt': True}, rep)
            self.assertFalse(rep.findings)
            self.assertEqual('not_recorded', rep.meta['llms_txt']['basis'])

    def test_json_markdown_html_show_only_typed_non_scoring_receipt_notes(self):
        rep = report_for(response(mime='text/html', body='<script>secret-body</script>'))
        self.assertIn('llms_txt', json.loads(rep.to_json())['meta'])
        for output in (rep.to_markdown(), rep.to_html()):
            self.assertIn('Root llms.txt response evidence', output)
            self.assertIn('unverified', output)
            self.assertNotIn('secret-body', output)

    def test_only_geo_owns_the_observation(self):
        body = '<html><title>Fixture page</title><h1>Fixture</h1></html>'
        ctx = {'llms_txt_receipt': llms_resource.assess(response())}
        for group in ('technical', 'geo'):
            with mock.patch.object(http, 'fetch', return_value=http.Response(BASE, BASE, 200, {}, body, 0)):
                rep = scan.scan(BASE, ctx=ctx, only=[group], check_images=False)
            self.assertEqual(group == 'geo', 'llms_txt' in rep.meta)

    def test_unverified_http_evidence_blocks_relevant_diff_compare_and_brief(self):
        rep = report_for(response(mime='text/html'))
        data = json.loads(rep.to_json())
        self.assertEqual('incomparable', diff_scan.diff_reports(data, data)['comparison']['status'])
        with mock.patch.object(compare.scanner, 'scan', return_value=rep):
            result = compare.run([BASE, BASE + 'rival'])
        self.assertTrue(result['failed'][0]['llms_txt_unverified'])
        with mock.patch.object(brief.scanner, 'scan', return_value=rep):
            with self.assertRaisesRegex(RuntimeError, 'Root llms.txt availability'):
                brief._page(BASE)
        rep.meta['scan_scope'] = {'requested': ['technical'], 'completed': ['technical']}
        self.assertIsNone(recorded_llms_problem(rep.meta, for_score=True))
        built = plan.build_plan(json.loads(rep.to_json()), str(Path(__file__).parent / 'fixtures/planner/plain_html'))
        self.assertFalse(built['actions'])

    def test_observed_and_absent_receipts_do_not_block_score_comparison(self):
        for resp in (response(), response(status=404)):
            rep = report_for(resp)
            self.assertIsNone(recorded_llms_problem(rep.meta, for_score=True))
            data = json.loads(rep.to_json())
            self.assertNotEqual('incomparable', diff_scan.diff_reports(data, data)['comparison']['status'])

    def test_planner_emits_manual_verification_not_file_creation_for_unknown_response(self):
        rep = report_for(response(status=429))
        built = plan.build_plan(json.loads(rep.to_json()), str(Path(__file__).parent / 'fixtures/planner/plain_html'))
        action = next(action for action in built['actions'] if action['rule_id'] == 'geo.llms.txt.availability.unverified')
        self.assertTrue(action['manual_action'])
        self.assertFalse(action['requires_deploy'])
        self.assertFalse(action['likely_files'])
        self.assertIn('Do not create or rewrite', action['proposed_change'])
        self.assertFalse(built['groups'])

    def test_crawl_retains_shared_root_and_page_evidence_without_rescoring_uncertainty(self):
        receipt = llms_resource.assess(response(status=403))
        rep = report_for(response(status=403))
        before = copy.deepcopy(rep.meta)
        with mock.patch.object(crawl_site.scanner, 'gather_context', return_value={'llms_txt_receipt': receipt}), \
                mock.patch.object(crawl_site, 'discover', return_value=[BASE]), \
                mock.patch.object(crawl_site.scanner, 'scan', return_value=rep):
            result = crawl_site.crawl(BASE, max_pages=1)
        self.assertEqual(receipt, result['llms_txt'])
        self.assertEqual(receipt, result['pages'][0]['llms_txt'])
        self.assertTrue(result['pages'][0]['llms_txt_unverified'])
        self.assertEqual(100, result['avg_score'])
        self.assertIn('Root llms.txt unverified', crawl_site.render_markdown(result))
        self.assertEqual(before, rep.meta)

    def test_uncertain_audit_receipt_overrides_stale_missing_file_remediation(self):
        rep = report_for(response(status=429))
        rep.add('geo', 'low', 'No llms.txt', rule_id='geo.no.llms.txt')
        data = {'site': BASE, 'homepage': json.loads(rep.to_json()), 'sitemap': {},
                'crawl': {'llms_txt': rep.meta['llms_txt'], 'recurring': [
                    {'category': 'geo', 'severity': 'low', 'title': 'No llms.txt',
                     'rule_id': 'geo.no.llms.txt', 'count': 3}]}}
        built = plan.build_plan(data, str(Path(__file__).parent / 'fixtures/planner/plain_html'))
        self.assertNotIn('geo.no.llms.txt', [action['rule_id'] for action in built['actions']])
        self.assertTrue(all(action['manual_action'] for action in built['actions']))


if __name__ == '__main__':
    unittest.main()
