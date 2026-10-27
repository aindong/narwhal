"""A source candidate cannot replace usable URL evidence for structural edits."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan
from test_plan_automation_eligibility import baseline, RULE, URL


INVALID = ('', '/', 'relative/path', 'example.test', '//example.test/', 'not a URL', '--help',
           'mailto:help@example.test', 'file:///tmp/index.html', 'https://example.test:bad/',
           'https://example.test:65536/', 'https://[broken/', 'https://user:pass@example.test/',
           'https://example.test/\npage', 'https://example.test/\x7fpage',
           'https://example.test/' + 'x' * 4096)


class TestUrlEligibility(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name).resolve()
        (self.root / 'index.html').write_text('<html lang="en"><head></head></html>', encoding='utf-8')

    def action(self, data, eligible):
        original = copy.deepcopy(data)
        built = plan.build_plan(data, str(self.root))
        self.assertEqual(data.get('schema_version', 'legacy'), built['provenance']['report_schema_version'])
        self.assertEqual(data.get('tool_version', 'unknown'), built['provenance']['report_tool_version'])
        score_field = 'overall_score' if 'homepage' in data else 'score'
        self.assertEqual(data.get(score_field), built['source_score'])
        action = next(action for action in built['actions'] if action['rule_id'] == RULE)
        self.assertEqual(eligible, action['automation_eligibility']['eligible'])
        self.assertEqual('safely_automatable' if eligible else 'review_required', action['safety'])
        self.assertTrue(any(owner['path'] == 'index.html' and owner['exists'] for owner in action['likely_files']))
        if not eligible:
            self.assertIn('known_incomplete_source_evidence', action['automation_eligibility']['blockers'])
            self.assertNotIn('## Safe candidates for automation', plan.render_markdown(built))
        self.assertEqual(original, data)
        return built, action

    def test_unusable_scan_labels_withhold_even_with_site_scope_and_an_owner(self):
        for label in INVALID:
            for scope in ('page', 'site'):
                with self.subTest(label=label[:80], scope=scope):
                    data = baseline()
                    data.update(url=label, final_url=label)
                    data['findings'][0]['scope'] = scope
                    built, _ = self.action(data, False)
                    self.assertEqual(label, built['target'])

    def test_scope_hint_cannot_hide_known_failed_page_execution(self):
        data = baseline()
        data['status'] = 206
        data['findings'][0]['scope'] = 'site'
        self.action(data, False)

    def test_audit_page_and_invocation_urls_preserve_bare_host_compatibility(self):
        for site in (URL, 'example.test', 'example.test:443/'):
            page = baseline()
            self.action({'site': site, 'homepage': page, 'crawl': {}}, True)
            legacy = copy.deepcopy(page)
            legacy.pop('url', None)
            legacy.pop('final_url', None)
            self.action({'site': site, 'homepage': legacy, 'crawl': {}}, True)
        for site, page_url in (('file:///tmp/index.html', URL), ('not a URL', URL),
                               ('https://example.test:bad/', URL), (URL, 'mailto:help@example.test'),
                               (URL, 'example.test'), (URL, '\ud800'), (URL, {'unsupported': 'label'})):
            with self.subTest(site=site, page_url=page_url):
                page = baseline()
                page.update(url=page_url, final_url=page_url)
                self.action({'site': site, 'homepage': page, 'crawl': {}}, False)

    def test_final_url_takes_precedence_over_the_original_invocation(self):
        for final_url, eligible in (('file:///tmp/index.html', False), (URL, True)):
            page = baseline()
            page.update(url='example.test', final_url=final_url)
            self.action({'site': URL, 'homepage': page, 'crawl': {}}, eligible)

    def test_falsy_malformed_final_labels_do_not_become_usable_fallbacks(self):
        for final_url in ({}, [], False, 0):
            with self.subTest(final_url=final_url):
                page = baseline()
                page['final_url'] = final_url
                self.action({'site': URL, 'homepage': page, 'crawl': {}}, False)
        page = baseline()
        page['final_url'] = ''
        self.action({'site': URL, 'homepage': page, 'crawl': {}}, True)

    def test_bad_crawl_labels_withhold_but_unrecorded_legacy_labels_remain_unknown(self):
        for label in ('missing', '', 'file:///tmp/index.html', 'https://example.test:bad/'):
            with self.subTest(label=label):
                page = baseline()
                finding = dict(page['findings'][0], count=1, url_sample={
                    'basis': 'recorded_crawl_rule_url_labels_v1', 'urls': [URL], 'truncated': False, 'omitted': 0})
                page['findings'] = []
                row = baseline()
                if label == 'missing':
                    row.pop('url', None)
                    row.pop('final_url', None)
                else:
                    row.update(url=label, final_url=label)
                data = {'site': URL, 'homepage': page, 'crawl': {'pages': [row], 'recurring': [finding]}}
                self.action(data, label == 'missing')

    def test_supported_labels_remain_offline_and_mcp_keeps_the_same_receipt(self):
        for label in (URL, 'HTTP://EXAMPLE.TEST/path?x=1#part', 'http://127.0.0.1:8000/',
                      'http://[::1]:8000/', 'https://例え.テスト/café',
                      URL + 'x' * (plan.finding_urls.MAX_URL_CHARS - len(URL)), 'https://example.test:bad/'):
            with self.subTest(label=label):
                data = baseline()
                data.update(url=label, final_url=label)
                original = copy.deepcopy(data)
                with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')), \
                        mock.patch('socket.socket.connect', side_effect=AssertionError('No network')):
                    built, action = self.action(data, not label.endswith(':bad/'))
                    with mock.patch.object(Path, 'cwd', return_value=self.root.parent):
                        received = mcp_server._plan(data, self.root.name)
                actual = next(item for item in received['actions'] if item['rule_id'] == RULE)
                self.assertEqual(action['automation_eligibility'], actual['automation_eligibility'])
                self.assertEqual(built['target'], received['target'])
                self.assertEqual(original, data)

    def test_crawl_witnesses_do_not_repair_bad_context_or_inherit_unrelated_home_failure(self):
        page = baseline()
        finding = dict(page['findings'].pop(), count=1, url_sample={
            'basis': 'recorded_crawl_rule_url_labels_v1', 'urls': [URL], 'truncated': False, 'omitted': 0})
        data = {'site': 'https://exa\nmple.test/', 'homepage': page,
                'crawl': {'pages': [baseline()], 'recurring': [finding]}}
        self.action(data, False)
        data['site'] = URL
        data['homepage']['status'] = 206
        self.action(data, True)


if __name__ == '__main__':
    unittest.main()
