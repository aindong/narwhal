"""Known partial HTML is not complete-page comparison or brief evidence."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import brief
import compare
import scan
import mcp_server
from lib import config, htmlx, http, report as reportlib

TARGET = 'https://example.test/owner'
PARTIAL = 'https://example.test/partial'
COMPLETE = 'https://example.test/complete'
HTML = '<html lang="en"><title>A detailed guide</title><h1>Guide</h1><p>A complete guide.</p></html>'


@contextlib.contextmanager
def fixture(partial):
    def fetch(url, **kwargs):
        headers = {'content-type': 'text/html'}
        if url in partial:
            headers['x-narwhal-truncated'] = 'true'
        return http.Response(url, url, 200, headers, HTML, 1)
    with mock.patch.object(scan, 'gather_context', return_value={}), \
            mock.patch.object(http, 'fetch', side_effect=fetch):
        yield


class TestComparisonCoverage(unittest.TestCase):
    def test_compare_truncated_target_has_no_scoreboard_or_gap_verdict(self):
        with fixture({TARGET}):
            data = compare.run([TARGET, PARTIAL, COMPLETE])
        self.assertIn('error', data)
        for key in ('you', 'competitors', 'gaps', 'leads'):
            self.assertNotIn(key, data)
        self.assertEqual(200, data['failed'][0]['status'])
        self.assertTrue(data['failed'][0]['response_truncated'])
        output = compare.render_markdown(data)
        self.assertIn('truncated', output.lower())
        self.assertIn('complete HTML', output)
        self.assertNotIn('Scoreboard', output)

    def test_compare_skips_partial_rival_and_uses_complete_rival(self):
        with fixture({PARTIAL}):
            data = compare.run([TARGET, PARTIAL, COMPLETE])
        self.assertNotIn('error', data)
        self.assertEqual([COMPLETE], [item['url'] for item in data['competitors']])
        self.assertEqual([], data['gaps'])
        self.assertTrue(data['failed'][0]['response_truncated'])
        self.assertIn('truncated', compare.render_markdown(data).lower())

    def test_compare_with_no_complete_rivals_returns_error(self):
        with fixture({PARTIAL}):
            data = compare.run([TARGET, PARTIAL])
        self.assertIn('error', data)
        self.assertNotIn('gaps', data)
        self.assertIn('truncated', compare.render_markdown(data).lower())

    def test_brief_truncated_own_page_returns_error_without_recommendations(self):
        with fixture({TARGET}):
            data = brief.run(TARGET, [COMPLETE], use_gsc=False)
        self.assertIn('truncated', data['error'].lower())
        for key in ('you', 'gaps', 'schema', 'structure'):
            self.assertNotIn(key, data)
        self.assertIn('complete HTML', brief.render_markdown(data))

    def test_brief_skips_partial_rival_and_uses_complete_rival(self):
        with fixture({PARTIAL}):
            data = brief.run(TARGET, [PARTIAL, COMPLETE], use_gsc=False)
        self.assertNotIn('error', data)
        self.assertEqual([COMPLETE], [item['url'] for item in data['competitors']])
        self.assertIn('truncated', data['failed'][0]['error'].lower())
        self.assertIn('truncated', brief.render_markdown(data).lower())

    def test_topic_brief_uses_only_complete_rivals(self):
        with fixture({PARTIAL}):
            data = brief.run(competitor_urls=[PARTIAL, COMPLETE], topic='Guide', use_gsc=False)
        self.assertNotIn('error', data)
        self.assertNotIn('you', data)
        self.assertEqual([COMPLETE], [item['url'] for item in data['competitors']])
        self.assertIn('truncated', data['failed'][0]['error'].lower())

    def test_topic_without_any_eligible_pages_returns_error_and_diagnostics(self):
        with fixture({PARTIAL}):
            data = brief.run(competitor_urls=[PARTIAL], topic='Guide', use_gsc=False)
        self.assertIn('error', data)
        self.assertNotIn('grounding', data)
        self.assertNotIn('schema', data)
        self.assertIn('truncated', brief.render_markdown(data).lower())
        self.assertEqual(PARTIAL, data['failed'][0]['url'])

    def test_own_page_brief_remains_page_only_when_all_rivals_are_partial(self):
        with fixture({PARTIAL}):
            data = brief.run(TARGET, [PARTIAL], use_gsc=False)
        self.assertNotIn('error', data)
        self.assertEqual('page-only', data['grounding'])
        self.assertEqual(TARGET, data['you']['url'])
        self.assertNotIn('competitors', data)
        self.assertNotIn('gaps', data)
        self.assertIn('truncated', brief.render_markdown(data).lower())

    def test_empty_topic_api_request_cannot_claim_page_grounding(self):
        data = brief.run(topic='Guide', use_gsc=False)
        self.assertIn('error', data)
        self.assertNotIn('grounding', data)

    def test_mcp_adapters_preserve_truncated_input_errors(self):
        with fixture({TARGET}):
            compared = mcp_server._compare(TARGET, [COMPLETE])
            content = mcp_server._brief(TARGET, [COMPLETE], use_gsc=False)
        self.assertIn('error', compared)
        self.assertTrue(compared['failed'][0]['response_truncated'])
        self.assertIn('truncated', content['error'].lower())

    def test_topic_with_all_failed_fetches_is_not_a_measured_brief(self):
        with mock.patch.object(http, 'fetch', return_value=http.Response(
                PARTIAL, PARTIAL, 404, {'content-type': 'text/html'}, '', 1)):
            data = brief.run(competitor_urls=[PARTIAL], topic='Guide', use_gsc=False)
        self.assertIn('error', data)
        self.assertNotIn('grounding', data)
        self.assertIn('HTTP 404', brief.render_markdown(data))

    def test_canonical_nested_flag_is_checked_even_without_legacy_top_level_flag(self):
        rep = reportlib.Report(TARGET, fetched_status=200)
        rep._doc = htmlx.parse(HTML, base_url=TARGET)
        rep.meta['coverage'] = {'response_truncated': True}
        with mock.patch.object(scan, 'scan', return_value=rep):
            compared = compare.run([TARGET, COMPLETE])
            content = brief.run(TARGET, [COMPLETE], use_gsc=False)
        self.assertIn('error', compared)
        self.assertIn('truncated', content['error'].lower())

    def test_explicit_top_level_flag_is_checked_for_rendered_reports_too(self):
        rep = reportlib.Report(TARGET, fetched_status=200, rendered=True)
        rep._doc = htmlx.parse(HTML, base_url=TARGET)
        rep.meta['response_truncated'] = True
        with mock.patch.object(scan, 'scan', return_value=rep):
            compared = compare.run([TARGET, COMPLETE], render=True)
            content = brief.run(TARGET, [COMPLETE], render=True, use_gsc=False)
        self.assertIn('error', compared)
        self.assertIn('truncated', content['error'].lower())

    def test_legacy_missing_or_nonboolean_flags_do_not_invent_truncation(self):
        for value in (None, False, 0, 1, 'true'):
            with self.subTest(value=value):
                rep = reportlib.Report(TARGET, fetched_status=200)
                rep._doc = htmlx.parse(HTML, base_url=TARGET)
                rep.meta['coverage'] = {'response_truncated': value}
                rep.meta['response_truncated'] = value
                with mock.patch.object(scan, 'scan', return_value=rep):
                    compared = compare.run([TARGET, COMPLETE])
                    content = brief.run(TARGET, [COMPLETE], use_gsc=False)
                self.assertNotIn('error', compared)
                self.assertNotIn('error', content)

    def test_standalone_scan_keeps_partial_coverage_report_and_findings(self):
        with fixture({TARGET}):
            rep = scan.scan(TARGET)
        self.assertTrue(rep.meta['coverage']['response_truncated'])
        self.assertFalse(rep.hard_fail)
        self.assertIn('technical.response.truncated', [f.rule_id for f in rep.findings])

    def test_ignoring_truncation_finding_cannot_bypass_input_coverage_gate(self):
        cfg = config.Config({'ignore': {'titles': ['Response exceeded scan byte limit']}})
        with fixture({TARGET}):
            rep = scan.scan(TARGET, config=cfg)
            compared = compare.run([TARGET, COMPLETE], config=cfg)
            content = brief.run(TARGET, [COMPLETE], config=cfg, use_gsc=False)
        self.assertNotIn('technical.response.truncated', [f.rule_id for f in rep.findings])
        self.assertTrue(rep.meta['coverage']['response_truncated'])
        self.assertIn('error', compared)
        self.assertIn('truncated', content['error'].lower())

    def test_truncated_target_cli_outputs_diagnostics_and_exits_two(self):
        with tempfile.TemporaryDirectory() as folder:
            for module in (compare, brief):
                with self.subTest(tool=module.__name__):
                    path = Path(folder) / (module.__name__ + '.json')
                    argv = [TARGET, COMPLETE, '--no-config', '--format', 'json', '-o', str(path)]
                    if module is brief:
                        argv.append('--no-gsc')
                    with fixture({TARGET}), contextlib.redirect_stdout(io.StringIO()):
                        status = module.main(argv)
                    self.assertEqual(2, status)
                    data = json.loads(path.read_text(encoding='utf-8'))
                    self.assertIn('error', data)
                    self.assertNotIn('gaps', data)


if __name__ == '__main__':
    unittest.main()
