"""Server range evidence cannot establish full-page absence or health."""
from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import scan
import audit
import brief
import compare
import crawl_site
import diff_scan
import plan
from lib import http, hreflang
from lib.report import Report
from lib import report as reportlib

URL='https://example.test/page/'
BODY='<h1>Fragment fixture</h1><p>Only part of the response is supplied.</p>'
FULL='<html lang="en"><head><title>Complete controlled fixture</title></head><body>'+BODY+'</body></html>'


def response(status=200, *, ranged=False, body=BODY, rendered=False, truncated=False):
    headers={'content-type':'text/html'}
    if ranged: headers['content-range']='bytes secret:password@untrusted/9000'
    if truncated: headers['x-narwhal-truncated']='true'
    return http.Response(URL, URL, status, headers, body, 1, rendered=rendered)


def scanned(resp, **kwargs):
    with mock.patch.object(http,'fetch',return_value=resp):
        return scan.scan(URL,ctx={},check_images=False,**kwargs)


class TestServerPartialResponse(unittest.TestCase):
    def test_empty_range_snapshot_retains_range_evidence_not_just_empty_text(self):
        for resp in (response(206,body=''),response(ranged=True,body='')):
            self.assertEqual('partial',hreflang.source_observation(resp,URL)['status'])
        self.assertEqual('empty',hreflang.source_observation(response(body=''),URL)['status'])

    def test_range_body_is_not_a_complete_page_and_cannot_assert_missing_metadata(self):
        for resp in (response(206),response(ranged=True),response(206,body=''),response(ranged=True,truncated=True)):
            with mock.patch.object(scan,'gather_context',side_effect=AssertionError('No context request')), \
                    mock.patch.object(scan.htmlx,'parse',side_effect=AssertionError('No page extraction')):
                report=scanned(resp,collect_links=True,collect_fingerprint=True)
            self.assertTrue(report.hard_fail)
            self.assertEqual(0,report.score())
            self.assertEqual('Score unavailable',report.score_label())
            self.assertEqual([],report.meta['scan_scope']['completed'])
            self.assertEqual(['technical.response.partial'],[f.rule_id for f in report.findings])
            self.assertNotIn('links',report.meta);self.assertNotIn('fingerprint',report.meta)
            self.assertNotIn('password',report.to_json())

    def test_complete_and_intentional_byte_limit_controls_keep_their_existing_paths(self):
        complete=scanned(response(body=FULL))
        limited=scanned(response(body=FULL,truncated=True))
        for report in (complete,limited):
            self.assertFalse(report.hard_fail)
            self.assertEqual(['technical','content','schema','geo'],report.meta['scan_scope']['completed'])
            self.assertNotIn('technical.response.partial',[f.rule_id for f in report.findings])
        self.assertIn('technical.response.truncated',[f.rule_id for f in limited.findings])

    def test_partial_rendered_primary_cannot_start_a_served_pair(self):
        with mock.patch.object(http,'fetch',return_value=response(206,rendered=True)) as fetch:
            report=scan.scan(URL,render=True,ctx={},check_images=False)
        self.assertTrue(report.hard_fail);self.assertEqual(1,fetch.call_count)
        self.assertNotIn('js_dependence',report.meta)

    def test_partial_served_baseline_is_not_a_measured_text_comparison(self):
        for baseline in (response(206),response(ranged=True)):
            with mock.patch.object(http,'fetch',side_effect=[response(body=FULL,rendered=True),baseline]):
                report=scan.scan(URL,render=True,ctx={'jsdep':{'stale':True}},check_images=False)
            self.assertFalse(report.hard_fail)
            self.assertEqual('served_html_partial',report.meta['coverage']['js_comparison']['reason'])
            self.assertNotIn('js_dependence',report.meta)
            self.assertIn('partial',report._scope_note())

    def test_page_output_explains_unassessed_source_not_a_measured_seo_failure(self):
        report=scanned(response(ranged=True))
        for text in (report.to_markdown(),report.to_html()):
            self.assertIn('Score unavailable',text)
            self.assertIn('fail-safe',text)
            self.assertIn('full-page',text)
            self.assertNotIn('Missing &lt;title&gt;',text)

    def test_real_compare_and_brief_explain_range_uncertainty_even_with_http_200(self):
        for resp in (response(206),response(ranged=True)):
            with mock.patch.object(scan,'gather_context',return_value={}),mock.patch.object(http,'fetch',return_value=resp):
                result=compare.run([URL,URL+'other/'])
                self.assertNotIn('you',result)
                self.assertTrue(all('partial' in item.get('error','') for item in result['failed']))
                with self.assertRaisesRegex(RuntimeError,'partial'):brief._page(URL)

    def test_current_and_historical_known_partial_page_diffs_are_not_comparable(self):
        current=json.loads(scanned(response(ranged=True)).to_json())
        old=json.loads(scanned(response(body=FULL)).to_json())
        old['meta']['hreflang_source_observation']=hreflang.source_observation(response(ranged=True),URL)
        for value in (current,old):
            self.assertEqual('incomparable',diff_scan.diff_reports(value,copy.deepcopy(value))['comparison']['status'])

    def test_legacy_explicit_http_206_without_a_receipt_is_not_complete_coverage(self):
        old=json.loads(scanned(response(body=FULL)).to_json());old['status']=206
        old['meta'].pop('hreflang_source_observation')
        self.assertEqual('incomparable',diff_scan.diff_reports(old,copy.deepcopy(old))['comparison']['status'])

    def test_historical_crawl_partial_observation_blocks_whole_audit_comparison(self):
        page=json.loads(scanned(response(body=FULL)).to_json())
        value={'site':URL,'overall_score':min(page['score'],70),'homepage':page,'crawl':{'pages':[{
            'url':URL,'score':70,'hard_fail':False,
            'hreflang_source_observation':hreflang.source_observation(response(ranged=True),URL)}]}}
        self.assertEqual('incomparable',diff_scan.diff_reports(value,copy.deepcopy(value))['comparison']['status'])

    def test_live_partial_crawl_has_no_fingerprint_duplicate_or_relationship_claim(self):
        with mock.patch.object(scan,'gather_context',return_value={}), \
                mock.patch.object(crawl_site,'discover',return_value=[URL]), \
                mock.patch.object(http,'fetch',return_value=response(ranged=True)):
            result=crawl_site.crawl(URL,max_pages=1,concurrency=1)
        self.assertTrue(result['pages'][0]['hard_fail'])
        self.assertEqual(0,result['duplicate_coverage']['eligible_pages'])
        self.assertEqual(0,result['avg_score'])
        self.assertNotIn('hreflang',result)

    def test_ranged_response_planning_stays_manual_without_guessed_metadata_owners(self):
        report=scanned(response(ranged=True))
        with tempfile.TemporaryDirectory() as root:
            action=plan.build_plan(json.loads(report.to_json()),root)['actions'][0]
        self.assertEqual('manual_external',action['safety'])
        self.assertEqual([],action['likely_files'])
        self.assertIn('full',action['proposed_change'])

    def test_partial_source_affects_all_selected_groups_not_only_technical(self):
        report=scanned(response(ranged=True),only=['content'])
        self.assertTrue(report.hard_fail)
        self.assertEqual(['content'],report.meta['scan_scope']['requested'])
        self.assertEqual([],report.meta['scan_scope']['completed'])

    def test_range_marker_is_positive_bounded_and_never_echoes_the_raw_header(self):
        for header in ('','bytes 0-90/91','bytes */900','secret:password@untrusted'):
            resp=response(body=FULL);resp.headers['content-range']=header
            report=scanned(resp)
            self.assertTrue(report.hard_fail)
            self.assertEqual({'basis':http.SERVER_RANGE_BASIS,'observed':True},report.meta['coverage']['server_range'])
            self.assertNotIn('password',report.to_json())
        resp=response(206);resp.headers['content-type']='application/octet-stream'
        self.assertEqual('technical.response.partial',scanned(resp).findings[0].rule_id)

    def test_coverage_receipts_do_not_infer_unknown_or_malformed_range_observations(self):
        for receipt in (None,{},[],{'basis':'future','observed':True},
                        {'basis':http.SERVER_RANGE_BASIS,'observed':1},
                        {'basis':http.SERVER_RANGE_BASIS,'observed':'true'}):
            self.assertFalse(reportlib.recorded_response_partial({'coverage':{'server_range':receipt}}))
        self.assertFalse(reportlib.recorded_response_partial({}))
        self.assertTrue(reportlib.recorded_response_partial({'coverage':{'server_range':{
            'basis':http.SERVER_RANGE_BASIS,'observed':True}}}))
        contradictory={'basis':hreflang.SNAPSHOT_BASIS,'http_status':206,
                       'status':'source_observed','acquisition':'guarded_http'}
        self.assertIsNone(hreflang.recorded_observation({'hreflang_source_observation':contradictory}))
        self.assertTrue(reportlib.recorded_response_partial({'hreflang_source_observation':contradictory}))

    def test_historical_partial_report_is_not_labeled_overall_page_health(self):
        report=scanned(response(body=FULL))
        report.meta['hreflang_source_observation']=hreflang.source_observation(response(ranged=True),URL)
        self.assertEqual('Reported-findings score',report.score_label())
        self.assertIn('full-page',report._scope_note())

    def test_clearing_findings_cannot_hide_unassessed_execution_or_scope(self):
        report=scanned(response(ranged=True));report.findings.clear()
        self.assertEqual('Score unavailable',report.score_label())
        self.assertEqual(0,report.score())
        self.assertIn('partial/ranged',report._scope_note())
        reconstructed=Report(URL,meta=copy.deepcopy(report.meta))
        self.assertEqual('Score unavailable',reconstructed.score_label())

    def test_partial_baseline_does_not_invalidate_unselected_render_comparisons(self):
        with mock.patch.object(http,'fetch',side_effect=[response(body=FULL,rendered=True),response(ranged=True)]):
            report=scan.scan(URL,render=True,ctx={},only=['content'],check_images=False)
        self.assertIsNone(reportlib.recorded_js_comparison_problem(report.meta,for_score=True))
        value=json.loads(report.to_json())
        self.assertEqual('comparable',diff_scan.diff_reports(value,copy.deepcopy(value))['comparison']['status'])

    def test_mixed_audit_and_crawl_headlines_keep_partial_page_scope_visible(self):
        with mock.patch.object(scan,'gather_context',return_value={}), \
                mock.patch.object(crawl_site,'discover',return_value=[URL]), \
                mock.patch.object(http,'fetch',return_value=response(ranged=True)):
            site=crawl_site.crawl(URL,max_pages=1,concurrency=1)
        data={'site':URL,'page':scanned(response(body=FULL)),'site_result':site,'sitemap':{'start':URL,'seeds':[]}}
        for output in (crawl_site.render_markdown(site),audit.render_markdown(data),audit.render_html(data)):
            self.assertIn('1 sampled page(s) have partial/ranged HTML coverage',output)
            self.assertIn('not a comparable site-health measurement',output)

    def test_fallback_discovery_does_not_resolve_links_from_an_unassessed_range(self):
        fragment='<base href="https://example.test/wrong/"><a href="child/">Candidate</a>'
        for resp in (response(206,body=fragment),response(ranged=True,body=fragment)):
            with mock.patch.object(crawl_site.Discovery,'read',return_value=None), \
                    mock.patch.object(http,'fetch',return_value=resp):
                found=crawl_site.discover(URL,allow_private=False,timeout=1,limit=5,robots_txt='')
            self.assertEqual([URL],found)
        with mock.patch.object(crawl_site.Discovery,'read',return_value=None), \
                mock.patch.object(http,'fetch',return_value=response(body=fragment)):
            found=crawl_site.discover(URL,allow_private=False,timeout=1,limit=5,robots_txt='')
        self.assertEqual([URL,'https://example.test/wrong/child/'],found)


if __name__=='__main__':unittest.main()
