"""A repeated-rule action must disclose its bounded representative selection."""
import copy
import itertools
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan
from test_plan_repeated_evidence import finding, report, build, REPO


class TestPlanObservationSelection(unittest.TestCase):
    def test_repeated_selection_counts_normalized_observations_not_occurrences(self):
        rows = [finding('high', 'strong', 20), finding('low', 'weak', 7), finding('high', 'other', 3)]
        expected = build(report(rows))
        action = expected['actions'][0]
        receipt = action['observation_selection']
        self.assertEqual('worst_severity_then_sorted_json_v1', receipt['basis'])
        self.assertEqual(3, receipt['normalized_observations'])
        self.assertEqual('maximum_recorded_count', receipt['occurrences_basis'])
        self.assertEqual(20, action['occurrences'])
        self.assertIn('not matched or distinct page instances', receipt['scope'])
        for permutation in itertools.permutations(rows):
            self.assertEqual(expected, build(report(list(permutation))))
        text = plan.render_markdown(expected)
        self.assertIn('3 normalized observations', text)
        self.assertIn('Consult the original report for other observations', text)

    def test_singletons_cannot_supply_their_own_selection_receipt(self):
        row = finding('high', 'single')
        row['observation_selection'] = {'normalized_observations': 999, 'basis': 'untrusted'}
        built = build(report([row]))
        self.assertNotIn('observation_selection', built['actions'][0])
        self.assertNotIn('Observation selection', plan.render_markdown(built))
        repeated = build(report([row, dict(row, title='another')]))
        self.assertEqual(2, repeated['actions'][0]['observation_selection']['normalized_observations'])
        self.assertNotEqual('untrusted', repeated['actions'][0]['observation_selection']['basis'])

    def test_audit_rollups_and_manual_schema_actions_keep_receipt_in_markdown(self):
        rows = [dict(finding('low', 'page', 5), rule_id='schema.microdata.extraction', category='schema'),
                dict(finding('medium', 'rollup'), rule_id='schema.microdata.extraction', category='schema', count=9)]
        data = {'site': 'https://example.test/', 'homepage': report([rows[0]]),
                'crawl': {'recurring': [rows[1]]}, 'sitemap': {}}
        built = build(data); action = built['actions'][0]
        self.assertEqual(2, action['observation_selection']['normalized_observations'])
        self.assertEqual(9, action['occurrences'])
        self.assertTrue(action['manual_action'])
        self.assertEqual([], action['likely_files'])
        text = plan.render_markdown(built)
        self.assertIn('Verification scope', text)
        self.assertIn('2 normalized observations', text)

    def test_mcp_parity_without_network_or_input_mutation(self):
        data = report([finding('high', 'strong'), finding('low', 'weak')])
        original = copy.deepcopy(data)
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            built = mcp_server._plan(data, REPO)
        self.assertEqual(build(data), built)
        self.assertEqual(2, built['actions'][0]['observation_selection']['normalized_observations'])
        self.assertEqual(original, data)


if __name__ == '__main__':
    unittest.main()
