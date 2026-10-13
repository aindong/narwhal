"""A scan uses owned rule inputs, not caller mutations during its I/O."""

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import scan
from lib import config, http

URL = 'https://example.test/guide'
HTML = '<h1>Guide</h1>'


def response(rendered=False):
    return http.Response(URL, URL, 200, {'content-type': 'text/html'}, HTML, 1, rendered=rendered)


def sentinel(doc, resp, report, ctx):
    if ctx['thresholds']['thin_content'] >= 100:
        report.add('content', 'high', 'sentinel')


class TestRuleOwnership(unittest.TestCase):
    def test_plain_rules_are_detached_without_changing_fingerprint(self):
        original = config.Config({'ignore': {'categories': ['geo'], 'titles': ['one']}})
        cloned, owned = config.snapshot_rules(original)
        self.assertTrue(owned)
        self.assertEqual(config.comparison_fingerprint(original, original.thresholds),
                         config.comparison_fingerprint(cloned, cloned.thresholds))
        original.weights['high'] = 0; original.thresholds['thin_content'] = 1
        original._ignore_categories.add('content'); original._ignore_titles.append('sentinel')
        self.assertEqual(6, cloned.weights['high']); self.assertEqual(300, cloned.thresholds['thin_content'])
        self.assertFalse(cloned.is_ignored('content', 'sentinel'))
        self.assertTrue(cloned.is_ignored('geo', 'anything'))

    def test_original_config_mutations_during_fetch_do_not_change_current_scan(self):
        cfg = config.Config()
        def fetch(*args, **kwargs):
            cfg.weights['high'] = 0; cfg.thresholds['thin_content'] = 1
            cfg._ignore_categories.add('content'); cfg._ignore_titles.append('sentinel')
            return response()
        with mock.patch.object(http, 'fetch', side_effect=fetch), \
                mock.patch.dict(scan.AUDITORS, {'content': sentinel}):
            rep = scan.scan(URL, only=['content'], config=cfg, ctx={}, check_images=False)
        self.assertEqual(['sentinel'], [f.title for f in rep.findings])
        self.assertEqual(94, rep.score())
        defaults = config.Config()
        self.assertEqual(config.comparison_fingerprint(defaults, defaults.thresholds), rep.meta['scan_settings']['rule_config'])

    def test_between_auditor_mutations_do_not_change_later_checks(self):
        cfg = config.Config()
        def mutate(doc, resp, report, ctx):
            cfg.thresholds['thin_content'] = 1; cfg._ignore_titles.append('sentinel')
        with mock.patch.object(http, 'fetch', return_value=response()), \
                mock.patch.dict(scan.AUDITORS, {'technical': mutate, 'content': sentinel}):
            rep = scan.scan(URL, only=['technical', 'content'], config=cfg, ctx={}, check_images=False)
        self.assertEqual(['sentinel'], [f.title for f in rep.findings])
        self.assertEqual(['technical', 'content'], rep.meta['scan_scope']['completed'])

    def test_supplied_context_thresholds_are_owned_before_fetch(self):
        cfg = config.Config()
        thresholds = {'thin_content': 100, 'nested': {'limits': [40, 120]}}
        ctx = {'thresholds': thresholds}; seen = {}
        def fetch(*args, **kwargs):
            thresholds['thin_content'] = 1; thresholds['nested']['limits'][0] = 999
            ctx['thresholds'] = {'thin_content': 0}
            return response()
        def observe(doc, resp, report, context):
            seen.update(context['thresholds']); sentinel(doc, resp, report, context)
        with mock.patch.object(http, 'fetch', side_effect=fetch), \
                mock.patch.dict(scan.AUDITORS, {'content': observe}):
            rep = scan.scan(URL, only=['content'], config=cfg, ctx=ctx, check_images=False)
        self.assertEqual({'thin_content': 100, 'nested': {'limits': [40, 120]}}, seen)
        self.assertEqual(config.comparison_fingerprint(cfg, seen), rep.meta['scan_settings']['rule_config'])
        self.assertEqual(['sentinel'], [f.title for f in rep.findings])

    def test_gathered_thresholds_are_owned_before_render_dependence_fetch(self):
        thresholds = {'thin_content': 100}
        responses = [response(True), response()]
        def fetch_response(*args, **kwargs):
            result = responses.pop(0)
            if not result.rendered:
                thresholds['thin_content'] = 0
            return result
        with mock.patch.object(http, 'fetch', side_effect=fetch_response) as fetch, \
                mock.patch.object(scan, 'gather_context', return_value={'thresholds': thresholds}), \
                mock.patch.object(scan.jsdiff, 'analyze', return_value=
                                  {'words_raw': 1, 'words_rendered': 1, 'js_only_pct': 0}), \
                mock.patch.dict(scan.AUDITORS, {'content': sentinel}):
            rep = scan.scan(URL, only=['content'], check_images=False, render=True)
        self.assertEqual(2, fetch.call_count)
        self.assertEqual(['sentinel'], [f.title for f in rep.findings])

    def test_future_scans_use_new_config_but_completed_report_keeps_old_policy(self):
        cfg = config.Config()
        with mock.patch.object(http, 'fetch', return_value=response()), \
                mock.patch.dict(scan.AUDITORS, {'content': sentinel}):
            before = scan.scan(URL, only=['content'], config=cfg, ctx={}, check_images=False)
            saved = before.to_json()
            cfg._ignore_titles.append('sentinel')
            after = scan.scan(URL, only=['content'], config=cfg, ctx={}, check_images=False)
        self.assertEqual(saved, before.to_json()); self.assertEqual([], after.findings)
        self.assertNotEqual(before.meta['scan_settings']['rule_config'], after.meta['scan_settings']['rule_config'])
        before.add('content', 'low', 'sentinel extra')
        self.assertTrue(any(f.title == 'sentinel extra' for f in before.findings))

    def test_snapshot_and_scan_accept_packaged_import_aliases(self):
        spec = importlib.util.spec_from_file_location('config_owned_alias', config.__file__)
        alias = importlib.util.module_from_spec(spec); spec.loader.exec_module(alias)
        cfg = alias.Config(); cloned, owned = config.snapshot_rules(cfg)
        self.assertTrue(owned); self.assertFalse(cloned is cfg)
        with mock.patch.object(http, 'fetch', return_value=response()):
            rep = scan.scan(URL, only=['schema'], config=cfg, ctx={}, check_images=False)
        self.assertIn('rule_config', rep.meta['scan_settings'])

    def test_custom_subclasses_and_instance_callbacks_keep_behavior_unverified(self):
        class Custom(config.Config):
            def is_ignored(self, category, title):
                return True
        for cfg in (Custom(), config.Config()):
            if type(cfg) is config.Config:
                cfg.is_ignored = lambda category, title: True
            original, owned = config.snapshot_rules(cfg)
            self.assertIs(cfg, original); self.assertFalse(owned)
            with mock.patch.object(http, 'fetch', return_value=response()), \
                    mock.patch.dict(scan.AUDITORS, {'content': sentinel}):
                rep = scan.scan(URL, only=['content'], config=cfg, ctx={}, check_images=False)
            self.assertEqual([], rep.findings); self.assertNotIn('rule_config', rep.meta['scan_settings'])

    def test_class_level_custom_policy_with_marker_is_not_rewritten(self):
        class Custom(config.Config):
            _comparison_protocol = config.Config._comparison_protocol
            def is_ignored(self, category, title):
                return False
        cfg = Custom({'ignore': {'categories': ['content']}})
        self.assertIsNone(config.comparison_fingerprint(cfg, cfg.thresholds))
        with mock.patch.object(http, 'fetch', return_value=response()), \
                mock.patch.dict(scan.AUDITORS, {'content': sentinel}):
            rep = scan.scan(URL, only=['content'], config=cfg, ctx={}, check_images=False)
        self.assertEqual(['sentinel'], [f.title for f in rep.findings])
        self.assertNotIn('rule_config', rep.meta['scan_settings'])

    def test_replaced_builtin_class_callback_is_never_certified(self):
        for callback in (lambda self, category, title: True,
                         lambda self, category, title: False):
            cfg = config.Config()
            with mock.patch.object(config.Config, 'is_ignored', callback):
                same, owned = config.snapshot_rules(cfg)
                self.assertIs(cfg, same); self.assertFalse(owned)
                self.assertIsNone(config.comparison_fingerprint(cfg, cfg.thresholds))
                with mock.patch.object(http, 'fetch', return_value=response()), \
                        mock.patch.dict(scan.AUDITORS, {'content': sentinel}):
                    rep = scan.scan(URL, only=['content'], config=cfg, ctx={}, check_images=False)
                self.assertNotIn('rule_config', rep.meta['scan_settings'])
                self.assertEqual(bool(rep.findings), not callback(cfg, 'content', 'sentinel'))

    def test_later_class_callback_replacement_cannot_change_captured_scan(self):
        cfg = config.Config()
        original = config.Config.is_ignored
        def fetch(*args, **kwargs):
            config.Config.is_ignored = lambda self, category, title: True
            return response()
        try:
            with mock.patch.object(http, 'fetch', side_effect=fetch), \
                    mock.patch.dict(scan.AUDITORS, {'content': sentinel}):
                rep = scan.scan(URL, only=['content'], config=cfg, ctx={}, check_images=False)
            self.assertEqual(['sentinel'], [f.title for f in rep.findings])
            self.assertIn('rule_config', rep.meta['scan_settings'])
        finally:
            config.Config.is_ignored = original

    def test_bound_policy_for_a_different_config_is_not_certified(self):
        first, second = config.Config(), config.Config({'ignore': {'categories': ['content']}})
        first.is_ignored = second.is_ignored
        self.assertIsNone(config.comparison_fingerprint(first, first.thresholds))

    def test_custom_values_are_not_copied_or_certified(self):
        class NoCopy:
            def __deepcopy__(self, memo):
                raise AssertionError('custom copying must not run')
        obj = NoCopy(); ctx = {'thresholds': {'thin_content': 100, 'unused': obj}}
        value, owned = config.owned_value(ctx['thresholds'])
        self.assertIs(value, ctx['thresholds']); self.assertFalse(owned)
        with mock.patch.object(http, 'fetch', return_value=response()), \
                mock.patch.dict(scan.AUDITORS, {'content': sentinel}):
            rep = scan.scan(URL, only=['content'], ctx=ctx, check_images=False)
        self.assertNotIn('rule_config', rep.meta['scan_settings']); json.loads(rep.to_json())

    def test_nested_plain_shapes_shared_references_and_cycles_are_preserved(self):
        shared = {'limits': [1, 2]}; original = {'one': shared, 'two': shared, 'tuple': (1, 2)}
        copied, owned = config.owned_value(original)
        self.assertTrue(owned); self.assertIs(copied['one'], copied['two'])
        self.assertIsNot(shared, copied['one']); self.assertEqual((1, 2), copied['tuple'])
        cyclic = []; cyclic.append(cyclic)
        copied, owned = config.owned_value(cyclic)
        self.assertTrue(owned); self.assertIs(copied, copied[0]); self.assertIsNot(copied, cyclic)

    def test_deep_unsupported_threshold_shapes_remain_unverified(self):
        nested = 1
        for _ in range(70):
            nested = [nested]
        value, owned = config.owned_value(nested)
        self.assertFalse(owned); self.assertIs(value, nested)
        with mock.patch.object(http, 'fetch', return_value=response()):
            rep = scan.scan(URL, only=['schema'], ctx={'thresholds': {'unused': nested}}, check_images=False)
        self.assertNotIn('rule_config', rep.meta['scan_settings']); json.loads(rep.to_json())


if __name__ == '__main__':
    unittest.main()
