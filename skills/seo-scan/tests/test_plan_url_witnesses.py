"""Planner-generated URL witnesses share the conservative marker omission rule."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan
try:
    from .test_plan_crawl_links import checked, data, FAIL, GAP
    from .test_plan_sitemap_verification import report, SOURCE, SAMPLE
except ImportError:
    from test_plan_crawl_links import checked, data, FAIL, GAP
    from test_plan_sitemap_verification import report, SOURCE, SAMPLE

REPO = Path(__file__).parent / 'fixtures/planner/plain_html'
BASE = 'https://example.test/'
MARKERS = ['https://fixture:canary_password@example.test/',
           'https://fixture%40canary_password/',
           'https://fixture＠canary_password/',
           'https://fixture％４０canary_password/']


def actions(payload):
    return {a['rule_id']: a for a in plan.build_plan(payload, str(REPO))['actions']}


def witnesses(action):
    return json.loads(action['evidence'].split('explicitly omitted):\n', 1)[1])


class TestPlanUrlWitnesses(unittest.TestCase):
    def test_literal_safe_labels_and_unsupported_values_keep_prior_shape(self):
        for value in (BASE, '', BASE + 'literal`|\\path\nnext', BASE + 'caf\u00e9/\u202e'):
            self.assertEqual({'url': value}, plan._url_witness(value))
        for value in (None, True, 1, {}, []):
            self.assertEqual({'url': None}, plan._url_witness(value))
        for value in MARKERS:
            self.assertEqual({'url': None, 'url_omitted': 'credential_like_marker'}, plan._url_witness(value))

    def test_failed_and_unverified_link_targets_and_sources_omit_markers(self):
        for marker in MARKERS:
            with self.subTest(marker=marker):
                info = checked([(404, None), (403, None)])
                for row in info['broken'] + info['unverified']:
                    row.update(url=marker, sources=[marker, BASE + 'safe', marker,
                                                   BASE + 'outside-cap', marker])
                built = actions(data(info))
                self.assertEqual({FAIL, GAP}, set(built))
                self.assertNotIn('canary_password', json.dumps(built))
                for action in built.values():
                    row = witnesses(action)[0]
                    self.assertIsNone(row['url'])
                    self.assertEqual('credential_like_marker', row['url_omitted'])
                    self.assertEqual([None, BASE + 'safe', None], row['sources'])
                    self.assertEqual(5, row['source_count'])
                    self.assertEqual([{'position': 1, 'reason': 'credential_like_marker'},
                                      {'position': 3, 'reason': 'credential_like_marker'}], row['source_url_omissions'])
                    self.assertEqual(1, action['occurrences'])
                    self.assertEqual('manual_external', action['safety'])
                    self.assertEqual([], action['likely_files'])
                self.assertEqual(404, witnesses(built[FAIL])[0]['status'])
                self.assertEqual(403, witnesses(built[GAP])[0]['status'])

    def test_omitted_targets_keep_their_slots_and_full_occurrence_counts(self):
        info = checked([(404, None)] * 7)
        for index, row in enumerate(info['broken']):
            row['url'] = MARKERS[0] if index in (0, 4) else BASE + str(index)
        action = actions(data(info))[FAIL]
        rows = witnesses(action)
        self.assertEqual(7, action['occurrences'])
        self.assertIn('first 5 of 7', action['evidence'])
        self.assertEqual([None, BASE + '1', BASE + '2', BASE + '3', None], [r['url'] for r in rows])
        self.assertNotIn(BASE + '5', action['evidence'])
        self.assertNotIn('canary_password', action['evidence'])

    def test_sitemap_failure_and_uncertainty_keep_classification_counts_and_safe_labels(self):
        for marker in MARKERS:
            for status, error, rule in ((404, None, SOURCE), (403, None, SAMPLE),
                                        (404, 'timeout', SAMPLE)):
                with self.subTest(marker=marker, status=status, error=error):
                    samples = [{'url': marker, 'status': status, 'error': error},
                               {'url': BASE + 'safe', 'status': status, 'error': error}]
                    payload = report(errors=[], fetch_failures=0, sitemaps_attempted=1,
                                     sitemaps_fetched=1, sample=samples, broken_sample=samples)
                    built = actions(payload)
                    self.assertEqual({rule}, set(built))
                    self.assertNotIn('canary_password', json.dumps(built))
                    self.assertEqual([{'status': status, 'url': None, 'url_omitted': 'credential_like_marker'},
                                      {'status': status, 'url': BASE + 'safe'}], witnesses(built[rule]))
                    self.assertIn('first 2 of 2', built[rule]['evidence'])
                    if rule == SAMPLE:
                        self.assertEqual(2, built[rule]['occurrences'])
                        self.assertEqual('manual_external', built[rule]['safety'])
                    else:
                        self.assertEqual('deploy_verification', built[rule]['safety'])

    def test_missing_source_lists_and_unsupported_sample_records_keep_prior_nulls(self):
        info = {'broken': [{'status': 404}]}
        row = witnesses(actions(data(info))[FAIL])[0]
        self.assertEqual({'status': 404, 'url': None, 'internal': None,
                          'sources': None, 'source_count': None}, row)
        info['broken'][0]['sources'] = []
        self.assertEqual([], witnesses(actions(data(info))[FAIL])[0]['sources'])
        payload = report(errors=[], fetch_failures=0, sitemaps_attempted=1,
                         sitemaps_fetched=1, sample=[None])
        self.assertEqual([{'status': None, 'url': None}], witnesses(actions(payload)[SAMPLE]))

    def test_mcp_and_markdown_remain_deterministic_offline_and_read_only(self):
        info = checked([(404, None)])
        info['broken'][0].update(url=MARKERS[0], sources=[MARKERS[1], BASE])
        payload = data(info)
        sample = {'url': MARKERS[2], 'status': 403, 'error': None}
        payload['sitemap'].update(sample=[sample], broken_sample=[sample])
        original = copy.deepcopy(payload)
        owner = REPO / 'index.html'; before = owner.read_bytes()
        relative = str(REPO.resolve().relative_to(Path.cwd().resolve()))
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            first = mcp_server._plan(payload, relative)
            self.assertEqual(first, mcp_server._plan(payload, relative))
        self.assertNotIn('canary_password', json.dumps(first))
        self.assertNotIn('canary_password', plan.render_markdown(first))
        self.assertIn('credential_like_marker', plan.render_markdown(first))
        self.assertEqual(original, payload)
        self.assertEqual(before, owner.read_bytes())


if __name__ == '__main__':
    unittest.main()
