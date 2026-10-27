"""Repeated rules retain coherent deterministic evidence without inventing counts."""
import copy
import itertools
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan

REPO = 'skills/seo-scan/tests/fixtures/planner/plain_html'
RULE = 'technical.no.title.tag'


def finding(severity, marker, count=1):
    return {'rule_id': RULE, 'category': 'technical', 'severity': severity,
            'title': marker, 'detail': marker + ' detail', 'evidence': marker + ' evidence',
            'recommendation': marker + ' advice', 'confidence': 0.4 if severity == 'high' else 0.9,
            'occurrences': count}


def report(rows):
    return {'url': 'https://example.test/', 'score': 80, 'findings': rows}


def build(data):
    return plan.build_plan(data, REPO, report_source='<mcp-object>')


class TestRepeatedPlanEvidence(unittest.TestCase):
    def test_missing_severity_uses_low_priority_for_complete_observation_selection(self):
        legacy, explicit = finding('low', 'alpha', 8), finding('low', 'zeta', 3)
        legacy.pop('severity')
        for kind in ('scan', 'audit'):
            for rows in ([legacy, explicit], [explicit, legacy]):
                for severity in ('low', 'medium'):
                    with self.subTest(kind=kind, first=rows[0]['title'], severity=severity):
                        selected_rows = copy.deepcopy(rows)
                        for row in selected_rows:
                            if 'severity' in row:
                                row['severity'] = severity
                        data = (report(selected_rows) if kind == 'scan' else
                                {'site': 'https://example.test/', 'homepage': report(selected_rows[:1]),
                                 'crawl': {'recurring': selected_rows[1:]}, 'sitemap': {}})
                        original = copy.deepcopy(data)
                        built = build(data)
                        action = built['actions'][0]
                        expected = legacy if severity == 'low' else explicit
                        self.assertEqual((severity, expected['title'], expected['evidence'],
                                          expected['recommendation'], expected['confidence']),
                                         tuple(action[k] for k in ('severity', 'title', 'evidence',
                                                                  'source_recommendation', 'confidence')))
                        self.assertEqual(8, action['occurrences'])
                        self.assertEqual('site' if kind == 'audit' else 'page', action['scope'])
                        self.assertEqual(2, action['observation_selection']['normalized_observations'])
                        self.assertEqual(built, mcp_server._plan(data, REPO))
                        self.assertEqual(original, data)

    def test_missing_low_severity_does_not_lose_its_place_at_the_action_limit(self):
        for kind in ('scan', 'audit'):
            with self.subTest(kind=kind):
                rows = [{'category': 'content', 'severity': 'low', 'title': f'Issue {n}',
                         'rule_id': f'content.zzz.{n:04d}'} for n in range(1000)]
                legacy = {'category': 'content', 'rule_id': 'content.incomplete.open.graph.tags',
                          'title': 'Legacy Open Graph observation', 'evidence': 'Recorded legacy evidence.'}
                data = (report(rows + [legacy]) if kind == 'scan' else
                        {'site': 'https://example.test/', 'homepage': report(rows),
                         'crawl': {'recurring': [legacy]}, 'sitemap': {}})
                original = copy.deepcopy(data)
                built = build(data)
                self.assertEqual([legacy['rule_id']] + [f'content.zzz.{n:04d}' for n in range(999)],
                                 [a['rule_id'] for a in built['actions']])
                self.assertEqual((1001, 1000, True), tuple(built['coverage'][k] for k in
                                 ('actionable_findings', 'actions_emitted', 'action_generation_capped')))
                self.assertEqual('low', built['actions'][0]['severity'])
                self.assertEqual('open_graph', built['actions'][0]['artifact'])
                explicit = copy.deepcopy(data)
                selected = explicit['findings'][-1] if kind == 'scan' else explicit['crawl']['recurring'][0]
                selected['severity'] = 'low'
                self.assertEqual(build(explicit), built)
                self.assertEqual(built, mcp_server._plan(data, REPO))
                self.assertEqual(original, data)

    def test_worst_observation_retains_its_own_title_evidence_recommendation_and_confidence(self):
        low, high = finding('low', 'weak', 8), finding('high', 'strong', 2)
        for rows in ([low, high], [high, low]):
            data = report(rows); original = copy.deepcopy(data)
            actions = build(data)['actions']
            self.assertEqual(1, len(actions))
            action = actions[0]
            self.assertEqual(('high', 'strong', 'strong evidence', 'strong advice', 0.4),
                             tuple(action[k] for k in ('severity', 'title', 'evidence', 'source_recommendation', 'confidence')))
            self.assertEqual(8, action['occurrences'])  # maximum, not sum or instance matching
            self.assertEqual('action:' + RULE, action['action_id'])
            self.assertEqual(original, data)

    def test_equal_severity_representative_is_stable_across_every_input_order(self):
        rows = [finding('high', 'alpha', 2), finding('high', 'beta', 9), finding('low', 'weak', 20)]
        expected = build(report(rows))
        for permutation in itertools.permutations(rows):
            self.assertEqual(expected, build(report(list(permutation))))
        self.assertEqual('alpha', expected['actions'][0]['title'])
        self.assertEqual(20, expected['actions'][0]['occurrences'])

    def test_recurring_worst_evidence_is_not_discarded_by_homepage_merge(self):
        page, recurring = finding('low', 'homepage'), finding('critical', 'crawl', 5)
        recurring['count'] = 7
        data = {'site': 'https://example.test/', 'homepage': report([page]),
                'crawl': {'recurring': [recurring]}, 'sitemap': {}}
        original = copy.deepcopy(data)
        action = build(data)['actions'][0]
        self.assertEqual(('critical', 'crawl', 'crawl evidence', 'site', 7),
                         tuple(action[k] for k in ('severity', 'title', 'evidence', 'scope', 'occurrences')))
        self.assertEqual(original, data)

    def test_recurring_occurrences_are_retained_when_legacy_count_is_absent(self):
        data = {'site': 'https://example.test/', 'homepage': report([]),
                'crawl': {'recurring': [finding('high', 'crawl', 6)]}, 'sitemap': {}}
        self.assertEqual(6, build(data)['actions'][0]['occurrences'])

    def test_site_scope_and_maximum_count_remain_when_homepage_is_worst(self):
        data = {'site': 'https://example.test/', 'homepage': report([finding('critical', 'homepage', 10)]),
                'crawl': {'recurring': [dict(finding('low', 'crawl'), count=3)]}, 'sitemap': {}}
        action = build(data)['actions'][0]
        self.assertEqual('homepage evidence', action['evidence'])
        self.assertEqual('site', action['scope'])
        self.assertEqual(10, action['occurrences'])

    def test_offline_mcp_and_legacy_ids_keep_same_complete_observation(self):
        rows = [finding('low', 'Thin content (10 words)'), finding('high', 'Thin content (2 words)')]
        for row in rows:
            row.pop('rule_id')
        data = report(rows); original = copy.deepcopy(data)
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            actual = mcp_server._plan(data, REPO)
        self.assertEqual(build(data), actual)
        self.assertEqual('technical.thin.content', actual['actions'][0]['rule_id'])
        self.assertIn('2 words', actual['actions'][0]['evidence'])
        self.assertEqual(original, data)


if __name__ == '__main__':
    unittest.main()
