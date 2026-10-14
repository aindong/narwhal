"""All pages in one comparison use the captured built-in rules."""

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import compare
from lib import config, http

BASE = 'https://example.test/page-a'
RIVAL = 'https://example.test/page-b'
HTML = '<html lang="en"><title>A detailed guide</title><h1>Guide</h1><p>A brief guide.</p></html>'


def response(url, status=200):
    return http.Response(url, url, status, {'content-type': 'text/html'}, HTML, 1)


def run(cfg, urls=None, fetch=None, gather=None):
    reports, inputs = [], []
    original = compare.scanner.scan
    def scan(url, **kwargs):
        inputs.append(kwargs['config'])
        rep = original(url, **kwargs)
        reports.append(rep)
        return rep
    with mock.patch.object(compare.scanner, 'scan', side_effect=scan), \
            mock.patch.object(compare.scanner, 'gather_context', side_effect=gather or (lambda *a, **k: {})), \
            mock.patch.object(http, 'fetch', side_effect=fetch or (lambda url, **k: response(url))):
        data = compare.run(urls or [BASE, RIVAL], config=cfg)
    return data, reports, inputs


class TestCompareRuleOwnership(unittest.TestCase):
    def assert_one_policy(self, data, reports):
        self.assertNotIn('error', data)
        self.assertEqual(data['you']['score'], data['competitors'][0]['score'])
        fingerprints = {rep.meta['scan_settings']['rule_config'] for rep in reports
                        if rep.fetched_status == 200}
        self.assertEqual(1, len(fingerprints))
        return next(iter(fingerprints))

    def test_mutation_during_first_fetch_cannot_switch_later_page_rules(self):
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

    def test_rules_are_captured_before_first_context_fetch(self):
        cfg = config.Config()
        def gather(*args, **kwargs):
            cfg._ignore_categories.add('content')
            return {}
        data, reports, _ = run(cfg, gather=gather)
        self.assert_one_policy(data, reports)
        defaults = config.Config()
        self.assertEqual(config.comparison_fingerprint(defaults, defaults.thresholds),
                         reports[0].meta['scan_settings']['rule_config'])

    def test_failed_competitor_does_not_switch_rules_for_remaining_pages(self):
        cfg = config.Config()
        failed = 'https://example.test/missing'
        def fetch(url, **kwargs):
            if url == failed:
                cfg._ignore_categories.add('content')
                return response(url, status=404)
            return response(url)
        data, reports, _ = run(cfg, urls=[BASE, failed, RIVAL], fetch=fetch)
        self.assert_one_policy(data, reports)
        self.assertEqual([{'url': failed, 'status': 404}], data['failed'])

    def test_future_comparison_uses_caller_changes_without_altering_completed_output(self):
        cfg = config.Config()
        first, reports, _ = run(cfg)
        first_score = first['you']['score']
        fp = self.assert_one_policy(first, reports)
        cfg._ignore_categories.add('content')
        second, second_reports, _ = run(cfg)
        self.assertNotEqual(fp, self.assert_one_policy(second, second_reports))
        self.assertNotEqual(first_score, second['you']['score'])
        self.assertEqual(first_score, first['you']['score'])
        self.assertEqual(first_score, reports[0].score())

    def test_custom_callback_is_preserved_and_not_certified(self):
        cfg = config.Config()
        cfg.is_ignored = lambda category, title: True
        data, reports, inputs = run(cfg)
        self.assertEqual(100, data['you']['score'])
        self.assertEqual(100, data['competitors'][0]['score'])
        self.assertTrue(all(item is cfg for item in inputs))
        self.assertTrue(all('rule_config' not in rep.meta['scan_settings'] for rep in reports))

    def test_source_package_config_alias_is_captured_too(self):
        spec = importlib.util.spec_from_file_location('comparison_config_alias', config.__file__)
        alias = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(alias)
        cfg = alias.Config()
        def fetch(url, **kwargs):
            cfg._ignore_categories.add('content')
            return response(url)
        data, reports, inputs = run(cfg, fetch=fetch)
        self.assert_one_policy(data, reports)
        self.assertIsNot(cfg, inputs[0])


if __name__ == '__main__':
    unittest.main()
