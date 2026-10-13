"""One crawl/audit uses one captured built-in rule policy across its pages."""

import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit
import crawl_site
from lib import config, http

BASE = 'https://example.test/page-a'
CHILD = 'https://example.test/page-b'
HTML = '<html lang="en"><title>A detailed guide</title><h1>Guide</h1><p>A brief guide.</p></html>'


def response(url):
    return http.Response(url, url, 200, {'content-type': 'text/html'}, HTML, 1)


def crawl(cfg, context=None, fetch=None, discover=None, concurrency=1):
    with mock.patch.object(crawl_site.scanner, 'gather_context', return_value=context or {}), \
            mock.patch.object(crawl_site, 'discover', side_effect=discover or (lambda *a, **k: [BASE, CHILD])), \
            mock.patch.object(http, 'fetch', side_effect=fetch or (lambda url, **kwargs: response(url))):
        return crawl_site.crawl(BASE, config=cfg, max_pages=2, concurrency=concurrency,
                                detect_dupes=False, obey_robots=False)


class TestSiteRuleOwnership(unittest.TestCase):
    def assert_one_policy(self, data):
        fingerprints = {page['scan_settings']['rule_config'] for page in data['pages']}
        self.assertEqual(1, len(fingerprints))
        self.assertEqual(data['pages'][0]['score'], data['pages'][1]['score'])
        return next(iter(fingerprints))

    def test_serial_crawl_does_not_mix_policies_after_first_page_changes_caller(self):
        cfg = config.Config()
        def fetch(url, **kwargs):
            if url == BASE:
                cfg._ignore_categories.add('content'); cfg.weights['high'] = 0
                cfg.thresholds['thin_content'] = 1
            return response(url)
        data = crawl(cfg, fetch=fetch)
        fp = self.assert_one_policy(data)
        defaults = config.Config()
        self.assertEqual(config.comparison_fingerprint(defaults, defaults.thresholds), fp)

    def test_parallel_crawl_owns_rules_before_worker_io(self):
        cfg = config.Config(); changed = threading.Event()
        def fetch(url, **kwargs):
            if url == BASE:
                cfg._ignore_categories.add('content'); cfg.weights['high'] = 0
                changed.set()
            else:
                self.assertTrue(changed.wait(timeout=3))
            return response(url)
        self.assert_one_policy(crawl(cfg, fetch=fetch, concurrency=2))

    def test_capture_precedes_site_context_gathering(self):
        cfg = config.Config()
        def gather(*args, **kwargs):
            cfg._ignore_categories.add('content'); return {}
        with mock.patch.object(crawl_site.scanner, 'gather_context', side_effect=gather), \
                mock.patch.object(crawl_site, 'discover', return_value=[BASE, CHILD]), \
                mock.patch.object(http, 'fetch', side_effect=lambda url, **k: response(url)):
            data = crawl_site.crawl(BASE, config=cfg, max_pages=2, concurrency=1, detect_dupes=False)
        fp = self.assert_one_policy(data); defaults = config.Config()
        self.assertEqual(config.comparison_fingerprint(defaults, defaults.thresholds), fp)

    def test_gathered_threshold_overrides_are_owned_before_discovery(self):
        cfg = config.Config(); th = {'thin_content': 100, 'nested': {'limits': [1, 2]}}
        def discover(*args, **kwargs):
            th['thin_content'] = 1; th['nested']['limits'][0] = 999
            return [BASE, CHILD]
        data = crawl(cfg, context={'thresholds': th}, discover=discover)
        fp = self.assert_one_policy(data)
        expected = {'thin_content': 100, 'nested': {'limits': [1, 2]}}
        self.assertEqual(config.comparison_fingerprint(cfg, expected), fp)

    def test_gathered_threshold_mutation_between_pages_does_not_mix_context_policies(self):
        cfg = config.Config(); th = {'thin_content': 100}
        def fetch(url, **kwargs):
            if url == BASE:
                th['thin_content'] = 0
            return response(url)
        data = crawl(cfg, context={'thresholds': th}, fetch=fetch)
        fp = self.assert_one_policy(data)
        self.assertEqual(config.comparison_fingerprint(cfg, {'thin_content': 100}), fp)

    def test_later_crawl_sees_updates_while_current_crawl_stays_consistent(self):
        cfg = config.Config()
        first = crawl(cfg)
        cfg._ignore_categories.add('content')
        second = crawl(cfg)
        self.assertNotEqual(self.assert_one_policy(first), self.assert_one_policy(second))
        self.assertNotEqual(first['avg_score'], second['avg_score'])

    def test_audit_shares_rules_across_homepage_and_crawl_and_captures_sample_budget(self):
        cfg = config.Config()
        def fetch(url, **kwargs):
            cfg._ignore_categories.add('content'); cfg.thresholds['thin_content'] = 1
            cfg.defaults['sample'] = 1
            return response(url)
        with mock.patch.object(audit.scanner, 'gather_context', return_value={}), \
                mock.patch.object(crawl_site, 'discover', return_value=[BASE, CHILD]), \
                mock.patch.object(http, 'fetch', side_effect=fetch), \
                mock.patch.object(audit.validate_sitemap, 'analyze', return_value={}) as sitemap:
            data = audit.run(BASE, config=cfg, max_pages=2, concurrency=1)
        fp = self.assert_one_policy(data['site_result'])
        self.assertEqual(data['page'].meta['scan_settings']['rule_config'], fp)
        self.assertEqual(10, sitemap.call_args.kwargs['sample'])
        self.assertEqual(1, cfg.defaults['sample'])

    def test_audit_resolves_custom_sample_callback_without_replacing_it(self):
        cfg = config.Config(); calls = []
        def default(name, fallback=None):
            calls.append(name); return 7 if name == 'sample' else fallback
        cfg.default = default
        with mock.patch.object(audit.scanner, 'gather_context', return_value={}), \
                mock.patch.object(crawl_site, 'discover', return_value=[BASE, CHILD]), \
                mock.patch.object(http, 'fetch', side_effect=lambda url, **k: response(url)), \
                mock.patch.object(audit.validate_sitemap, 'analyze', return_value={}) as sitemap:
            audit.run(BASE, config=cfg, max_pages=2, concurrency=1)
        self.assertEqual(['sample'], calls)
        self.assertEqual(7, sitemap.call_args.kwargs['sample'])

    def test_custom_crawl_policy_remains_live_and_unverified(self):
        class Custom(config.Config):
            def is_ignored(self, category, title):
                return True
        data = crawl(Custom())
        for page in data['pages']:
            self.assertNotIn('rule_config', page['scan_settings'])
            self.assertEqual(100, page['score'])


if __name__ == '__main__':
    unittest.main()
