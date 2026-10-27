"""One known row cannot certify settings omitted from another sampled row."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diff_scan
import mcp_server
from test_diff_crawl_sample import audit, URL
from test_diff_scope import invoke

SCOPE = {'requested': ['technical', 'schema'], 'completed': ['technical', 'schema']}
SETTINGS = {'render_requested': False, 'rendered': False, 'image_checks': False,
            'content_length_reviewed': True, 'readability_reviewed': True,
            'schema_extraction_reviewed': True, 'rule_config': 'a' * 64}


def recorded(urls=(URL, URL), score=60):
    data = audit(list(urls), score)
    data['crawl'].update(pages_scanned=len(urls), recurring=[])
    for row in data['crawl']['pages']:
        row.update(rendered=False, scan_scope=copy.deepcopy(SCOPE), scan_settings=dict(SETTINGS))
    return data


class TestCrawlSettingPresence(unittest.TestCase):
    def assert_withheld(self, old, new):
        before = copy.deepcopy((old, new))
        result = diff_scan.diff_reports(old, new)
        self.assertEqual('incomparable', result['comparison']['status'])
        self.assertIsNone(result['score_delta'])
        self.assertIsNone(result['regression'])
        self.assertEqual([], result['resolved'])
        self.assertTrue(any('crawl' in reason.lower() for reason in result['comparison']['reasons']))
        self.assertEqual(result, mcp_server._diff(json.dumps(old), json.dumps(new)))
        self.assertEqual(2, invoke(old, new, '--require-comparable', '--fail-on-regression')[0])
        self.assertEqual(before, (old, new))

    def test_missing_settings_in_duplicate_rows_cannot_hide_a_score_gain(self):
        for key in SETTINGS:
            with self.subTest(key=key):
                old, new = recorded(), recorded(score=99)
                new['crawl']['pages'][1]['scan_settings'].pop(key)
                if key == 'rendered':
                    new['crawl']['pages'][1].pop('rendered')
                self.assert_withheld(old, new)
                self.assert_withheld(new, old)
                self.assert_withheld(new, new)
                new['crawl']['pages'].reverse()
                self.assert_withheld(old, new)

    def test_one_recorded_scope_cannot_hide_an_unrecorded_duplicate(self):
        old, new = recorded(), recorded(score=99)
        new['crawl']['pages'][1].pop('scan_scope')
        self.assert_withheld(old, new)
        self.assert_withheld(new, old)
        self.assert_withheld(new, new)
        new['crawl']['pages'].reverse()
        self.assert_withheld(old, new)

    def test_single_known_settings_becoming_unrecorded_are_not_matching_checks(self):
        for key in SETTINGS:
            old, new = recorded((URL,)), recorded((URL,), score=99)
            new['crawl']['pages'][0]['scan_settings'].pop(key)
            if key == 'rendered':
                new['crawl']['pages'][0].pop('rendered')
            self.assert_withheld(old, new)
            self.assert_withheld(new, old)

    def test_untyped_values_cannot_substitute_for_known_settings(self):
        for key, value in SETTINGS.items():
            old, new = recorded(), recorded(score=99)
            new['crawl']['pages'][1]['scan_settings'][key] = str(value)
            if key == 'rule_config':
                new['crawl']['pages'][1]['scan_settings'][key] = 'not-a-fingerprint'
            if key == 'rendered':
                new['crawl']['pages'][1].pop('rendered')
            self.assert_withheld(old, new)

    def test_matching_settings_keep_real_fix_and_reverse_regression(self):
        old, new = recorded(score=94), recorded(score=100)
        finding = {'category': 'schema', 'severity': 'high', 'title': 'Controlled missing schema name',
                   'rule_id': 'schema.controlled.missing.name'}
        old['homepage']['findings'] = [finding]
        for row in new['crawl']['pages']:
            row['scan_scope']['requested'].reverse()
            row['scan_scope']['completed'].reverse()
            row['scan_settings']['rule_config'] = 'A' * 64
            row['scan_settings']['future_setting'] = True
        result = diff_scan.diff_reports(old, new)
        self.assertEqual('comparable', result['comparison']['status'])
        self.assertEqual(6, result['score_delta'])
        self.assertEqual([finding], result['resolved'])
        self.assertEqual(0, invoke(old, new, '--require-comparable', '--fail-on-regression')[0])
        self.assertEqual(1, invoke(new, old, '--require-comparable', '--fail-on-regression')[0])

    def test_actual_rendering_fallback_preserves_known_evidence(self):
        old, new = recorded(), recorded(score=99)
        new['crawl']['pages'][1]['scan_settings']['rendered'] = 'false'
        self.assertIs(new['crawl']['pages'][1]['rendered'], False)
        self.assertEqual('comparable', diff_scan.diff_reports(old, new)['comparison']['status'])

    def test_two_legacy_unknown_snapshots_retain_their_handling(self):
        old, new = recorded(), recorded(score=99)
        for data in (old, new):
            for row in data['crawl']['pages']:
                row.pop('scan_scope')
                row.pop('scan_settings')
                row.pop('rendered')
        result = diff_scan.diff_reports(old, new)
        self.assertEqual('comparable', result['comparison']['status'])
        self.assertIn('Missing settings are not inferred', result['comparison']['basis'])
        self.assertIn('missing legacy page scopes remain unverified', result['comparison']['basis'])
