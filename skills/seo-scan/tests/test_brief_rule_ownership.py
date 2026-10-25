"""Own one built-in scoring/suppression policy for an entire content brief."""

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import brief
import gsc
from lib import config, http

BASE = 'https://example.test/page-a'
RIVAL = 'https://example.test/page-b'
HTML = '<html lang="en"><title>A detailed guide</title><h1>Guide</h1><p>A brief guide.</p></html>'


def response(url, status=200):
    return http.Response(url, url, status, {'content-type': 'text/html'}, HTML, 1)


def run(cfg, your_url=BASE, rivals=None, fetch=None, gather=None, topic=None):
    reports, inputs = [], []
    original = brief.scanner.scan
    def scan(url, **kwargs):
        inputs.append(kwargs['config'])
        rep = original(url, **kwargs)
        reports.append(rep)
        return rep
    with mock.patch.object(brief.scanner, 'scan', side_effect=scan), \
            mock.patch.object(gsc, 'gather', side_effect=AssertionError('Rule-policy fixture queried account')), \
            mock.patch.object(brief.scanner, 'gather_context', side_effect=gather or (lambda *a, **k: {})), \
            mock.patch.object(http, 'fetch', side_effect=fetch or (lambda url, **k: response(url))):
        data = brief.run(your_url, rivals if rivals is not None else [RIVAL],
                         config=cfg, use_gsc=False, topic=topic)
    return data, reports, inputs


class TestBriefRuleOwnership(unittest.TestCase):
    def assert_one_policy(self, data, reports):
        self.assertNotIn('error', data)
        pages = ([data['you']] if 'you' in data else []) + data.get('competitors', [])
        self.assertGreaterEqual(len(pages), 2)
        self.assertEqual(1, len({page['score'] for page in pages}))
        fingerprints = {rep.meta['scan_settings']['rule_config'] for rep in reports
                        if rep.fetched_status == 200}
        self.assertEqual(1, len(fingerprints))
        return next(iter(fingerprints))

    def test_first_fetch_cannot_change_later_page_scoring_and_suppression(self):
        cfg = config.Config()
        def fetch(url, **kwargs):
            if url == BASE:
                cfg.weights['high'] = 0
                cfg.thresholds['thin_content'] = 1
                cfg._ignore_categories.add('content')
                cfg._ignore_titles.append('viewport')
            return response(url)
        data, reports, inputs = run(cfg, fetch=fetch)
        fp = self.assert_one_policy(data, reports)
        defaults = config.Config()
        self.assertEqual(config.comparison_fingerprint(defaults, defaults.thresholds), fp)
        self.assertIsNot(cfg, inputs[0])
        self.assertIs(inputs[0], inputs[1])

    def test_capture_precedes_first_context_gathering(self):
        cfg = config.Config()
        def gather(*args, **kwargs):
            cfg._ignore_categories.add('content')
            return {}
        data, reports, _ = run(cfg, gather=gather)
        fp = self.assert_one_policy(data, reports)
        defaults = config.Config()
        self.assertEqual(config.comparison_fingerprint(defaults, defaults.thresholds), fp)

    def test_failed_rival_cannot_switch_rules_for_remaining_rivals(self):
        cfg = config.Config()
        missing = 'https://example.test/missing'
        def fetch(url, **kwargs):
            if url == missing:
                cfg._ignore_categories.add('content')
                return response(url, status=404)
            return response(url)
        data, reports, _ = run(cfg, rivals=[missing, RIVAL], fetch=fetch)
        self.assert_one_policy(data, reports)
        self.assertEqual([{'url': missing, 'error': 'HTTP 404'}], data['failed'])

    def test_topic_mode_owns_rules_before_first_competitor_scan(self):
        cfg = config.Config()
        def fetch(url, **kwargs):
            if url == BASE:
                cfg._ignore_categories.add('content')
            return response(url)
        data, reports, _ = run(cfg, your_url=None, rivals=[BASE, RIVAL],
                               fetch=fetch, topic='Guide')
        self.assert_one_policy(data, reports)
        self.assertNotIn('you', data)
        self.assertEqual('Guide', data['topic'])
        self.assertEqual('pages-only', data['grounding'])
        self.assertFalse(data['gsc']['found'])

    def test_later_brief_uses_caller_updates_without_changing_completed_output(self):
        cfg = config.Config()
        first, reports, _ = run(cfg)
        fp = self.assert_one_policy(first, reports)
        score = first['you']['score']
        cfg._ignore_categories.add('content')
        second, second_reports, _ = run(cfg)
        self.assertNotEqual(fp, self.assert_one_policy(second, second_reports))
        self.assertNotEqual(score, second['you']['score'])
        self.assertEqual(score, first['you']['score'])
        self.assertEqual(score, reports[0].score())

    def test_custom_callbacks_are_preserved_and_unverified(self):
        cfg = config.Config()
        cfg.is_ignored = lambda category, title: True
        data, reports, inputs = run(cfg)
        self.assertEqual(100, data['you']['score'])
        self.assertEqual(100, data['competitors'][0]['score'])
        self.assertTrue(all(item is cfg for item in inputs))
        self.assertTrue(all('rule_config' not in rep.meta['scan_settings'] for rep in reports))

    def test_source_package_config_alias_is_captured_too(self):
        spec = importlib.util.spec_from_file_location('brief_config_alias', config.__file__)
        alias = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(alias)
        cfg = alias.Config()
        def fetch(url, **kwargs):
            cfg._ignore_categories.add('content')
            return response(url)
        data, reports, inputs = run(cfg, fetch=fetch)
        self.assert_one_policy(data, reports)
        self.assertIsNot(cfg, inputs[0])

    def test_failed_own_page_still_errors_without_scanning_rivals(self):
        data, reports, _ = run(config.Config(), fetch=lambda url, **k: response(url, status=404))
        self.assertIn('could not scan your page', data['error'])
        self.assertNotIn('you', data)
        self.assertNotIn('competitors', data)
        self.assertEqual(1, len(reports))


if __name__ == '__main__':
    unittest.main()
