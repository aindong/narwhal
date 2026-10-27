"""Unsupported sample containers require verification, never invented probe rows."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan
from test_plan_sitemap_verification import report, FETCH, CAP, NOTES, SOURCE, SAMPLE

BAD = (None, False, 0, '', {}, True, 1, 'secret-token',
       {'status': 404, 'url': 'https://example.test/secret-token'})


def clean():
    return report(errors=[], fetch_failures=0, sitemaps_attempted=1, sitemaps_fetched=1,
                  sample=[], broken_sample=[])


class TestSitemapSampleContainers(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.workspace = Path(folder.name).resolve()
        self.repo = self.workspace / 'site'
        self.repo.mkdir()
        (self.repo / 'index.html').write_text('<html></html>', encoding='utf-8')
        (self.repo / 'sitemap.xml').write_text('<urlset/>', encoding='utf-8')

    def actions(self, data):
        built = plan.build_plan(data, str(self.repo), report_source='<mcp-object>')
        return built, {a['rule_id']: a for a in built['actions']}

    def assert_gap(self, action):
        self.assertEqual(('manual_external', True, False, []),
                         tuple(action[k] for k in ('safety', 'manual_action', 'requires_deploy', 'likely_files')))
        self.assertIn('sample', action['evidence'].lower())
        self.assertIn('container', action['evidence'].lower())
        self.assertIn('verify', action['source_recommendation'].lower())
        self.assertIn('before making source changes', action['source_recommendation'].lower())
        self.assertNotIn('secret-token', json.dumps(action))

    def test_explicit_unsupported_containers_cannot_be_clean_or_source_defects(self):
        for field in ('sample', 'broken_sample'):
            for value in BAD:
                with self.subTest(field=field, value=value):
                    data = clean()
                    data['sitemap'][field] = value
                    original = copy.deepcopy(data)
                    built, actions = self.actions(data)
                    self.assertEqual({NOTES}, set(actions))
                    self.assert_gap(actions[NOTES])
                    self.assertEqual(1, actions[NOTES]['occurrences'])
                    self.assertEqual([], built['groups'])
                    self.assertEqual(([], []), plan._sitemap_sample_evidence(data['sitemap']))
                    self.assertEqual(original, data)

    def test_absent_legacy_keys_empty_lists_and_successful_rows_keep_their_behavior(self):
        for legacy in (False, True):
            for rows in ([], [{'url': 'https://example.test/ok', 'status': 200, 'error': None}]):
                data = clean()
                data['sitemap']['sample'] = rows
                if legacy:
                    data.pop('schema_version')
                    data['sitemap'].pop('broken_sample')
                self.assertEqual({}, self.actions(data)[1])
        data = clean()
        data['sitemap'].pop('sample')
        data['sitemap'].pop('broken_sample')
        self.assertEqual({}, self.actions(data)[1])

    def test_valid_companion_failures_are_preserved_without_using_the_bad_container(self):
        valid = {'url': 'https://example.test/observed', 'status': 404, 'error': None}
        bad = {'url': 'https://example.test/secret-token', 'status': 500, 'error': None}
        for field, companion in (('sample', 'broken_sample'), ('broken_sample', 'sample')):
            data = clean()
            data['sitemap'].update({field: bad, companion: [valid]})
            _, actions = self.actions(data)
            self.assertEqual({NOTES, SOURCE}, set(actions))
            self.assert_gap(actions[NOTES])
            self.assertEqual('deploy_verification', actions[SOURCE]['safety'])
            self.assertIn('https://example.test/observed', actions[SOURCE]['evidence'])
            self.assertNotIn('secret-token', json.dumps(actions))
            self.assertEqual(1, actions[SOURCE]['occurrences'])
            self.assertEqual(([valid], []), plan._sitemap_sample_evidence(data['sitemap']))

    def test_gated_companion_rows_remain_unverified_without_invented_failures(self):
        data = clean()
        data['sitemap'].update(sample=[{'url': 'https://example.test/gated', 'status': 403, 'error': None}],
                               broken_sample={'url': 'https://example.test/secret-token', 'status': 404})
        _, actions = self.actions(data)
        self.assertEqual({NOTES, SAMPLE}, set(actions))
        self.assert_gap(actions[NOTES])
        self.assertIn('https://example.test/gated', actions[SAMPLE]['evidence'])
        self.assertNotIn('secret-token', json.dumps(actions))
        self.assertEqual(1, actions[SAMPLE]['occurrences'])

    def test_independent_fetch_cap_and_source_counts_remain_actionable(self):
        data = clean()
        data['sitemap'].update(errors=['fetch note', 'cap note'], fetch_failures=1,
                               sitemaps_attempted=2, sitemaps_fetched=1, truncated=2, sample=None)
        _, actions = self.actions(data)
        self.assertEqual({FETCH, CAP, NOTES}, set(actions))
        self.assertEqual((1, 2), (actions[FETCH]['occurrences'], actions[CAP]['occurrences']))
        self.assert_gap(actions[NOTES])
        data = clean()
        data['sitemap'].update(problems={'not-absolute': 1}, broken_sample=False)
        _, actions = self.actions(data)
        self.assertEqual({SOURCE, NOTES}, set(actions))
        self.assertEqual('deploy_verification', actions[SOURCE]['safety'])

    def test_counter_and_container_explanations_are_both_retained(self):
        data = clean()
        data['sitemap'].update(fetch_failures=False, sample=None)
        _, actions = self.actions(data)
        self.assertEqual({NOTES}, set(actions))
        self.assert_gap(actions[NOTES])
        self.assertIn('execution counters', actions[NOTES]['evidence'].lower())
        self.assertIn('sample containers', actions[NOTES]['evidence'].lower())

    def test_malformed_counts_cannot_replace_container_and_counter_explanations(self):
        for counts, expected in (({'invalid_lastmod': '0'}, {NOTES}),
                                 ({'problems': {'future': 'secret-token'}}, {NOTES}),
                                 ({'problems': []}, {NOTES}),
                                 ({'problems': {'not-absolute': 1, 'future': 'secret-token'}}, {NOTES, SOURCE})):
            for counter_gap in (False, True):
                with self.subTest(counts=counts, counter_gap=counter_gap):
                    data = clean()
                    data['sitemap'].update(sample=None, **counts)
                    if counter_gap:
                        data['sitemap']['fetch_failures'] = False
                    original = copy.deepcopy(data)
                    built, actions = self.actions(data)
                    self.assertEqual(expected, set(actions))
                    self.assert_gap(actions[NOTES])
                    self.assertIn('problem/invalid-lastmod counts', actions[NOTES]['evidence'].lower())
                    self.assertEqual(counter_gap, 'execution counters' in actions[NOTES]['evidence'].lower())
                    self.assertEqual(1, actions[NOTES]['occurrences'])
                    self.assertFalse(any(NOTES in group['rule_ids'] for group in built['groups']))
                    if SOURCE in actions:
                        self.assertEqual('deploy_verification', actions[SOURCE]['safety'])
                        self.assertTrue(actions[SOURCE]['requires_deploy'])
                        self.assertIn('invalid sitemap entries or lastmod values',
                                      actions[SOURCE]['evidence'].lower())
                        self.assertTrue(any(owner['path'] == 'sitemap.xml'
                                            for owner in actions[SOURCE]['likely_files']))
                    self.assertEqual(original, data)

    def test_successful_prefix_cannot_hide_later_failures_or_gated_records(self):
        ok = {'url': 'https://example.test/ok', 'status': 200, 'error': None}
        failure = {'url': 'https://example.test/gone', 'status': 404, 'error': None}
        gated = {'url': 'https://example.test/gated', 'status': 403, 'error': None}
        for samples, broken in (([ok, failure, gated], [failure]), ([ok], [failure, gated])):
            with self.subTest(samples=samples):
                data = clean()
                data['sitemap'].update(sample=samples, broken_sample=broken)
                original = copy.deepcopy(data)
                _, actions = self.actions(data)
                self.assertEqual({SOURCE, SAMPLE}, set(actions))
                self.assertEqual((1, 1), (actions[SOURCE]['occurrences'], actions[SAMPLE]['occurrences']))
                self.assertEqual(([failure], [gated]), plan._sitemap_sample_evidence(data['sitemap']))
                self.assertEqual(original, data)

    def test_cli_and_offline_mcp_keep_manual_scope_without_changing_inputs(self):
        data = clean()
        data['sitemap']['broken_sample'] = {'url': 'https://example.test/secret-token', 'status': 404}
        original = copy.deepcopy(data)
        baseline = self.workspace / 'before.json'
        baseline.write_text(json.dumps(data), encoding='utf-8')
        saved = baseline.read_bytes()
        sources = {p: p.read_bytes() for p in self.repo.iterdir()}
        output = self.workspace / 'plan.json'
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = plan.main([str(baseline), '--repo', str(self.repo), '--format', 'json', '-o', str(output)])
        self.assertEqual(0, code)
        action = json.loads(output.read_text())['actions'][0]
        self.assertEqual(NOTES, action['rule_id'])
        self.assert_gap(action)
        with mock.patch.object(Path, 'cwd', return_value=self.workspace), \
                mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            received = mcp_server._plan(data, 'site')
        self.assertEqual([NOTES], [a['rule_id'] for a in received['actions']])
        self.assert_gap(received['actions'][0])
        self.assertEqual(original, data)
        self.assertEqual(saved, baseline.read_bytes())
        self.assertEqual(sources, {p: p.read_bytes() for p in self.repo.iterdir()})


if __name__ == '__main__':
    unittest.main()
