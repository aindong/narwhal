"""Crawled response evidence must not be assigned to an unobserved requested page."""
from pathlib import Path
import copy
import json
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import scan
import crawl_site
import diff_scan
from lib import http, hreflang

BASE = 'https://example.test/en/'
TARGET = 'https://example.test/fr/'
OTHER = 'https://example.test/other/'


def html(*urls):
    return '<html><head><title>Acquisition fixture</title>' + ''.join(
        '<link rel="alternate" hreflang="fr" href="' + url + '">' for url in urls
    ) + '</head><body><h1>Acquisition fixture</h1></body></html>'


def crawl(response):
    def fetch(url, **kwargs):
        if url == BASE:
            return http.Response(BASE, BASE, 200, {'content-type': 'text/html'}, html(BASE, TARGET), 1)
        if url == TARGET:
            return response
        raise AssertionError('Unobserved source must not generate another probe: ' + url)
    with mock.patch.object(scan, 'gather_context', return_value={}), \
            mock.patch.object(crawl_site, 'discover', return_value=[BASE, TARGET]), \
            mock.patch.object(http, 'fetch', side_effect=fetch) as fetched, \
            mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
        result = crawl_site.crawl(BASE, max_pages=2, concurrency=1, detect_dupes=False)
    return result, fetched


class TestCrawledHreflangAcquisition(unittest.TestCase):
    def test_changed_final_identity_is_unassessed_and_does_not_seed_other_probes(self):
        result, fetched = crawl(http.Response(TARGET, OTHER, 200, {'content-type': 'text/html'}, html(OTHER), 1))
        cluster = result['hreflang']
        self.assertEqual([], cluster['missing_return'])
        self.assertEqual([], cluster['missing_self'])
        self.assertEqual(1, cluster['unassessed_pairs'])
        self.assertEqual(0, cluster['probed'])
        self.assertEqual([BASE, TARGET], [call.args[0] for call in fetched.call_args_list])
        self.assertEqual('identity_changed', result['pages'][1]['hreflang_source_observation']['status'])

    def test_empty_bytes_do_not_establish_missing_return(self):
        result, _ = crawl(http.Response(TARGET, TARGET, 200, {'content-type': 'text/html'}, '', 1))
        self.assertEqual([], result['hreflang']['missing_return'])
        self.assertEqual(1, result['hreflang']['unassessed_pairs'])
        self.assertEqual('empty', result['pages'][1]['hreflang_source_observation']['status'])

    def test_unknown_html_media_type_does_not_establish_missing_return(self):
        result, _ = crawl(http.Response(TARGET, TARGET, 200, {}, html(), 1))
        self.assertEqual([], result['hreflang']['missing_return'])
        self.assertEqual(1, result['hreflang']['unassessed_pairs'])
        self.assertEqual('non_html', result['pages'][1]['hreflang_source_observation']['status'])

    def test_complete_empty_html_still_records_observed_missing_return(self):
        result, _ = crawl(http.Response(TARGET, TARGET, 200, {'content-type': 'text/html'}, html(), 1))
        self.assertEqual([{'page': BASE, 'target': TARGET, 'lang': 'fr'}], result['hreflang']['missing_return'])
        self.assertEqual(0, result['hreflang']['unassessed_pairs'])
        self.assertEqual('source_observed', result['pages'][1]['hreflang_source_observation']['status'])

    def test_complete_reciprocal_sample_remains_observed_without_reprobes(self):
        result, fetched = crawl(http.Response(TARGET, TARGET, 200, {'content-type': 'text/html; charset=utf-8'}, html(BASE, TARGET), 1))
        self.assertEqual([], result['hreflang']['missing_return'])
        self.assertEqual(2, result['hreflang']['checked_pairs'])
        self.assertEqual(2, fetched.call_count)
        self.assertEqual('source_observed', result['pages'][1]['hreflang_source_observation']['status'])

    def test_unsampled_probe_preserves_receipts_without_inventing_return_tags(self):
        cases = [('reciprocal', TARGET, 200, html(BASE, TARGET), 'source_observed', 2, 0),
                 ('missing_return', TARGET, 200, html(), 'source_observed', 1, 0),
                 ('partial', TARGET, 206, html(), 'partial', 0, 1),
                 ('redirected', OTHER, 200, html(OTHER), 'identity_changed', 0, 1)]
        for name, final, status, body, observation, checked, unverified in cases:
            def fetch(url, **kwargs):
                if url == BASE:
                    return http.Response(BASE, BASE, 200, {'content-type': 'text/html'}, html(BASE, TARGET), 1)
                self.assertEqual(TARGET, url)
                return http.Response(TARGET, final, status, {'content-type': 'text/html'}, body, 1)
            with self.subTest(case=name), \
                    mock.patch.object(scan, 'gather_context', return_value={}), \
                    mock.patch.object(crawl_site, 'discover', return_value=[BASE]), \
                    mock.patch.object(http, 'fetch', side_effect=fetch) as fetched, \
                    mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
                result = crawl_site.crawl(BASE, max_pages=1, concurrency=1, detect_dupes=False)
            self.assertEqual([BASE, TARGET], [call.args[0] for call in fetched.call_args_list])
            self.assertEqual([BASE], [page['url'] for page in result['pages']])
            self.assertEqual({'basis': hreflang.EXTRACTION_BASIS, 'declared': 2,
                              'accepted': 2, 'omitted': {}}, result['pages'][0]['hreflang_extraction'])
            cluster = result['hreflang']
            self.assertEqual(1 + int(observation == 'source_observed'),
                             cluster['source_coverage']['recorded_pages'])
            self.assertEqual(0, cluster['source_coverage']['unrecorded_pages'])
            self.assertEqual(checked, cluster['checked_pairs'])
            self.assertEqual(0, cluster['unassessed_pairs'])
            self.assertEqual(unverified, cluster['unverified_targets'])
            self.assertEqual(int(observation == 'source_observed'), cluster['probed'])
            self.assertEqual([{'page': BASE, 'target': TARGET, 'lang': 'fr'}]
                             if name == 'missing_return' else [], cluster['missing_return'])
            self.assertEqual([{'target': BASE, **result['pages'][0]['hreflang_source_observation']}],
                             cluster['sampled_source_observations'])
            self.assertEqual(1, len(cluster['probe_observations']))
            receipt = cluster['probe_observations'][0]
            self.assertEqual(TARGET, receipt['target'])
            self.assertEqual(observation, receipt['status'])
            self.assertEqual('guarded_http', receipt['acquisition'])
            self.assertEqual(status, receipt['http_status'])

    def test_crawl_forwards_preview_options_and_bounds_followup_timeouts(self):
        body = html(BASE, TARGET).replace('</body>', '<a href="' + TARGET + '">French</a></body>')
        for private, render, actual, timeout in ((False, False, False, 3), (True, True, True, 20),
                                                 (True, False, False, 3), (False, True, True, 20),
                                                 (True, True, False, 3)):
            options = {'timeout': timeout}
            if private:
                options['allow_private'] = True
            if render:
                options['render'] = True
            def fetch(url, **kwargs):
                self.assertIn(url, (BASE, TARGET))
                return http.Response(url, url, 200, {'content-type': 'text/html'},
                                     body if url == BASE else html(BASE, TARGET), 1,
                                     rendered=actual and kwargs.get('render', False))
            with self.subTest(private=private, render=render, actual=actual, timeout=timeout), \
                    mock.patch.object(scan, 'gather_context', return_value={}) as gather, \
                    mock.patch.object(crawl_site, 'discover', return_value=[BASE]) as discover, \
                    mock.patch.object(http, 'fetch', side_effect=fetch) as fetched, \
                    mock.patch.object(http, 'head', return_value=(200, None)) as head, \
                    mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
                result = crawl_site.crawl(BASE, max_pages=1, concurrency=1, check_links=True,
                                          detect_dupes=False, **options)
                for helper in (gather, discover):
                    self.assertIs(private, helper.call_args.kwargs.get('allow_private'))
                    self.assertEqual(timeout, helper.call_args.kwargs.get('timeout'))
                primary = [call for call in fetched.call_args_list if call.args[0] == BASE]
                probes = [call for call in fetched.call_args_list if call.args[0] == TARGET]
                self.assertEqual(2 if actual else 1, len(primary))
                self.assertIs(render, primary[0].kwargs.get('render'))
                self.assertIs(actual, result['pages'][0]['rendered'])
                self.assertEqual(1, len(probes))
                for call in fetched.call_args_list:
                    self.assertIs(private, call.kwargs.get('allow_private'))
                    self.assertEqual(timeout if call.args[0] == BASE else min(timeout, 8),
                                     call.kwargs.get('timeout'))
                head.assert_called_once_with(TARGET, timeout=min(timeout, 8), allow_private=private)
                self.assertEqual(1, result['links']['checked'])
                self.assertEqual(2, result['hreflang']['checked_pairs'])

    def test_page_scan_retains_final_page_facts_without_false_source_omission(self):
        response = http.Response(TARGET, OTHER, 200, {'content-type': 'text/html'}, html(OTHER), 1)
        with mock.patch.object(http, 'fetch', return_value=response):
            report = scan.scan(TARGET, ctx={}, check_images=False)
        self.assertEqual(OTHER, report.final_url)
        self.assertEqual(['technical', 'content', 'schema', 'geo'], report.meta['scan_scope']['completed'])
        self.assertEqual(1, report.meta['hreflang_extraction']['accepted'])
        self.assertFalse(hreflang.unverified(report.meta, for_score=True))
        self.assertEqual('identity_changed', report.meta['hreflang_source_observation']['status'])

    def test_acquisition_notes_remain_visible_without_mutating_sample_facts(self):
        result, _ = crawl(http.Response(TARGET, TARGET, 200, {}, html(), 1))
        before = copy.deepcopy(result)
        rendered = crawl_site.render_markdown(result)
        self.assertIn('Crawled source observations', rendered)
        self.assertIn('HTML media type unverified', rendered)
        self.assertNotIn('Missing return tags', rendered)
        self.assertEqual(before, result)
        self.assertNotIn('source_observed', json.dumps(result['hreflang']['missing_return']))

    def test_unavailable_partial_and_missing_identity_snapshots_stay_unassessed(self):
        responses = [http.Response(TARGET, TARGET, 404, {'content-type': 'text/html'}, html(OTHER), 1),
                     http.Response(TARGET, TARGET, 302, {'content-type': 'text/html'}, html(OTHER), 1),
                     http.Response(TARGET, '', 200, {'content-type': 'text/html'}, html(OTHER), 1),
                     http.Response(TARGET, TARGET, 200, {'content-type': 'text/html', 'x-narwhal-truncated': 'true'}, html(OTHER), 1)]
        for response in responses:
            result, fetched = crawl(response)
            self.assertEqual([], result['hreflang']['missing_return'])
            self.assertEqual(1, result['hreflang']['unassessed_pairs'])
            self.assertEqual(2, fetched.call_count)

    def test_rendered_snapshot_is_disclosed_not_mislabeled_as_served_html(self):
        response = http.Response(TARGET, TARGET, 200, {'content-type': 'text/html'}, html(BASE, TARGET), 1, rendered=True)
        result, _ = crawl(response)
        self.assertEqual('rendered_snapshot', result['pages'][1]['hreflang_source_observation']['acquisition'])
        self.assertEqual([], result['hreflang']['missing_return'])

    def test_server_range_response_does_not_establish_complete_html_coverage(self):
        for status, headers in [(206, {'content-type': 'text/html'}),
                                (200, {'content-type': 'text/html', 'content-range': 'bytes 0-80/900'})]:
            result, fetched = crawl(http.Response(TARGET, TARGET, status, headers, html(), 1))
            self.assertEqual([], result['hreflang']['missing_return'])
            self.assertEqual(1, result['hreflang']['unassessed_pairs'])
            self.assertEqual('partial', result['pages'][1]['hreflang_source_observation']['status'])
            self.assertEqual(2, fetched.call_count)

    def test_receipt_basis_types_and_status_consistency_are_not_inferred(self):
        good = hreflang.source_observation(http.Response(TARGET, TARGET, 200, {'content-type': 'text/html'}, html(), 1), TARGET)
        for key, value in [('basis', 'future'), ('status', 'future'), ('http_status', True),
                           ('http_status', 403), ('http_status', 206), ('http_status', -1), ('acquisition', 'future')]:
            broken = dict(good); broken[key] = value
            self.assertIsNone(hreflang.recorded_observation({'hreflang_source_observation': broken}))
        for meta in (None, {}, {'hreflang_source_observation': []}):
            self.assertIsNone(hreflang.recorded_observation(meta))
        self.assertEqual(good, hreflang.recorded_observation({'hreflang_source_observation': good}))

    def test_response_policy_change_is_not_mislabeled_as_website_improvement(self):
        response = http.Response(TARGET, TARGET, 200, {'content-type': 'text/html'}, html(BASE, TARGET), 1)
        site, _ = crawl(response)
        with mock.patch.object(http, 'fetch', return_value=response):
            page = json.loads(scan.scan(TARGET, ctx={}, check_images=False).to_json())
        current = {'site': BASE, 'overall_score': min(page['score'], site['avg_score']), 'homepage': page, 'crawl': site}
        legacy = copy.deepcopy(current); legacy['crawl'].pop('hreflang_acquisition_basis')
        self.assertEqual('incomparable', diff_scan.diff_reports(legacy, current)['comparison']['status'])
        self.assertEqual('comparable', diff_scan.diff_reports(current, copy.deepcopy(current))['comparison']['status'])

    def test_sampled_receipt_previews_are_bounded_literal_and_nonmutating(self):
        value = hreflang.analyze({BASE: [{'lang': 'fr', 'href': TARGET}]})
        value['sampled_source_observations'] = [{'target': TARGET + '?x=![](https://outside.test/track)' + 'x' * 500,
                                               'status': 'non_html', 'acquisition': 'guarded_http',
                                               'http_status': 200, 'basis': hreflang.SNAPSHOT_BASIS} for _ in range(8)]
        before = copy.deepcopy(value); text = '\n'.join(hreflang.render_markdown(value))
        self.assertIn('… +3 more (see JSON)', text)
        self.assertIn('[truncated; see JSON]', text)
        self.assertIn('0 of 8 supplied response(s)', text)
        self.assertEqual(before, value)


if __name__ == '__main__': unittest.main()
