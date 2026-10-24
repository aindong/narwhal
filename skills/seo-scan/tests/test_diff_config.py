"""Changed suppression/scoring/check rules are not page fixes."""

import json
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diff_scan
import scan
from lib import config, http
try:
    from .test_diff_settings import URL, HTML, configured
    from .test_diff_scope import invoke
except ImportError:
    from test_diff_settings import URL, HTML, configured
    from test_diff_scope import invoke


def fingerprint(data=None, thresholds=None):
    cfg = config.Config(data)
    return config.comparison_fingerprint(cfg, cfg.thresholds if thresholds is None else thresholds)


class TestRuleConfigCoverage(unittest.TestCase):
    def test_default_fingerprint_is_stable_and_opaque(self):
        value = fingerprint()
        self.assertEqual(64, len(value)); self.assertEqual(value, fingerprint({}))
        cfg = config.Config({'ignore': {'titles': ['PRIVATE_CONFIG_TOKEN']}})
        encoded = config.comparison_fingerprint(cfg, cfg.thresholds)
        self.assertNotIn('PRIVATE_CONFIG_TOKEN', encoded)
        self.assertNotEqual(value, encoded)

    def test_source_and_package_import_aliases_share_builtin_config_protocol(self):
        spec = importlib.util.spec_from_file_location('config_package_alias', config.__file__)
        alias = importlib.util.module_from_spec(spec); spec.loader.exec_module(alias)
        cfg = alias.Config()
        self.assertIsNot(type(cfg), config.Config)
        self.assertEqual(fingerprint(), config.comparison_fingerprint(cfg, cfg.thresholds))
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, HTML, 1)
        with mock.patch.object(http, 'fetch', return_value=response):
            rep = scan.scan(URL, only=['schema'], ctx={}, config=cfg, check_images=False)
        self.assertEqual(fingerprint(), rep.meta['scan_settings']['rule_config'])

    def test_dictionary_order_and_integral_float_weights_do_not_change_fingerprint(self):
        weights = {k: float(v) for k, v in reversed(list(config.DEFAULT_WEIGHTS.items()))}
        self.assertEqual(fingerprint(), fingerprint({'weights': weights}))

    def test_ignore_case_order_and_duplicates_do_not_change_behavior_signature(self):
        first = {'ignore': {'categories': ['GEO', 'schema'], 'titles': ['Heavy', 'Legacy']}}
        second = {'ignore': {'categories': ['schema', 'geo', 'GEO'], 'titles': ['legacy', 'HEAVY', 'legacy']}}
        self.assertEqual(fingerprint(first), fingerprint(second))

    def test_rule_inputs_change_signature_but_cli_budget_defaults_do_not(self):
        for data in ({'weights': {'high': 1}}, {'thresholds': {'title_min': 30}},
                     {'ignore': {'categories': ['technical']}}, {'ignore': {'titles': ['Heavy images']}}):
            self.assertNotEqual(fingerprint(), fingerprint(data))
        self.assertEqual(fingerprint(), fingerprint({'defaults': {'max_pages': 2, 'timeout': 1}}))

    def test_effective_context_thresholds_are_used_not_only_config_defaults(self):
        cfg = config.Config({'thresholds': {'title_min': 30}})
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, HTML, 1)
        with mock.patch.object(http, 'fetch', return_value=response):
            rep = scan.scan(URL, only=['schema'], ctx={'thresholds': {'title_min': 50}}, config=cfg)
        self.assertEqual(config.comparison_fingerprint(cfg, {'title_min': 50}), rep.meta['scan_settings']['rule_config'])
        self.assertNotEqual(config.comparison_fingerprint(cfg, cfg.thresholds), rep.meta['scan_settings']['rule_config'])

    def test_report_scoring_and_provenance_do_not_drift_when_original_config_mutates(self):
        cfg = config.Config()
        html = '<script type="application/ld+json">{"@type":"Product","name":""}</script>'
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, html, 1)
        with mock.patch.object(http, 'fetch', return_value=response):
            rep = scan.scan(URL, only=['schema'], ctx={}, config=cfg, check_images=False)
        before = json.loads(rep.to_json())
        cfg.weights['high'] = 0
        self.assertEqual(before, json.loads(rep.to_json()))
        self.assertIsNot(cfg.weights, rep.weights)
        self.assertEqual(config.comparison_fingerprint(cfg, cfg.thresholds, weights=rep.weights),
                         rep.meta['scan_settings']['rule_config'])

    def test_unserializable_nonfinite_and_custom_shapes_remain_unverified(self):
        cfg = config.Config()
        for thresholds in ({'unused': object()}, {'title_min': float('nan')}, {'title_min': float('inf')}):
            self.assertIsNone(config.comparison_fingerprint(cfg, thresholds))
        class Custom(config.Config):
            pass
        self.assertIsNone(config.comparison_fingerprint(Custom(), cfg.thresholds))
        custom_callback = config.Config(); custom_callback.is_ignored = lambda category, title: True
        self.assertIsNone(config.comparison_fingerprint(custom_callback, cfg.thresholds))
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, HTML, 1)
        with mock.patch.object(http, 'fetch', return_value=response):
            rep = scan.scan(URL, only=['schema'], ctx={'thresholds': {'unused': object()}})
        self.assertNotIn('rule_config', rep.meta['scan_settings'])
        json.loads(rep.to_json())

    def test_known_configuration_mismatch_blocks_gate_in_both_directions(self):
        before, after = configured(), configured()
        before['meta']['scan_settings']['rule_config'] = fingerprint()
        after['meta']['scan_settings']['rule_config'] = fingerprint({'weights': {'high': 1}})
        for old, new in ((before, after), (after, before)):
            result = diff_scan.diff_reports(old, new)
            self.assertEqual('incomparable', result['comparison']['status'])
            self.assertIsNone(result['score_delta']); self.assertEqual([], result['resolved'])
            self.assertEqual(2, invoke(old, new, '--fail-on-regression')[0])

    def test_legacy_malformed_digests_are_not_guessed_and_case_is_normalized(self):
        good = configured(); good['meta']['scan_settings']['rule_config'] = fingerprint()
        for value in (None, 42, [], 'bad', 'a' * 63, 'z' * 64):
            unknown = configured(); unknown['meta']['scan_settings']['rule_config'] = value
            result = diff_scan.diff_reports(unknown, good)
            self.assertNotIn('rule_config', result['comparison']['old_settings'])
            self.assertEqual('comparable', result['comparison']['status'])
        upper = configured(); upper['meta']['scan_settings']['rule_config'] = fingerprint().upper()
        self.assertEqual('comparable', diff_scan.diff_reports(upper, good)['comparison']['status'])

    def test_ignored_image_findings_are_not_reported_as_resolved_fixes(self):
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, HTML, 1)
        head = (200, {'content-type': 'image/png', 'content-length': '768000'}, '')
        cfg = config.Config({'ignore': {'titles': ['Heavy images', 'Legacy image formats']}})
        with mock.patch.object(http, 'fetch', return_value=response), mock.patch.object(http, 'head_info', return_value=head):
            before = scan.scan(URL, only=['technical'], ctx={}, check_images=True)
            after = scan.scan(URL, only=['technical'], ctx={}, check_images=True, config=cfg)
        self.assertGreater(after.score(), before.score())
        result = diff_scan.diff_reports(json.loads(before.to_json()), json.loads(after.to_json()))
        self.assertEqual('incomparable', result['comparison']['status'])
        self.assertIsNone(result['score_delta']); self.assertEqual([], result['resolved'])

    def test_changed_child_configuration_blocks_audit_even_with_matching_homepage(self):
        before = {'site': URL, 'overall_score': 100, 'homepage': configured(), 'crawl': {'pages': [
            {'url': URL, 'scan_settings': {'rule_config': fingerprint()}}]}}
        after = json.loads(json.dumps(before))
        after['crawl']['pages'][0]['scan_settings']['rule_config'] = fingerprint({'ignore': {'titles': ['image']}})
        result = diff_scan.diff_reports(before, after)
        self.assertEqual('incomparable', result['comparison']['status'])
        self.assertTrue(any('Crawl setting rule_config' in r for r in result['comparison']['reasons']))


if __name__ == '__main__':
    unittest.main()
