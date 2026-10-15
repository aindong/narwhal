"""Prospective selection is a frozen acquisition plan, not ground truth."""

from collections import Counter, defaultdict
import json
from pathlib import Path
import unittest
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / 'docs/tuning/prospective-cases.json'


class TestProspectiveCohort(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads(PLAN.read_text(encoding='utf-8'))

    def test_fifty_unique_candidate_urls_and_ids_have_no_truth_labels(self):
        self.assertEqual('purposeful_capture_sample_not_validated_benchmark', self.plan['interpretation'])
        cases = self.plan['cases']
        self.assertEqual(50, len(cases))
        self.assertEqual(50, len({case['id'] for case in cases}))
        self.assertEqual(50, len({case['url'] for case in cases}))
        expected = {'id', 'url', 'site_group', 'intended_role', 'intended_language', 'split', 'render'}
        for case in cases:
            self.assertEqual(expected, set(case))
            self.assertRegex(case['id'], r'^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$')
            parsed = urlparse(case['url'])
            self.assertEqual('https', parsed.scheme)
            self.assertTrue(parsed.hostname)
            self.assertIsNone(parsed.username)
            self.assertIsNone(parsed.password)
            self.assertFalse(parsed.fragment)
            self.assertIs(type(case['render']), bool)

    def test_operational_site_groups_do_not_cross_the_reserved_split(self):
        groups = defaultdict(set)
        for case in self.plan['cases']:
            groups[case['site_group']].add(case['split'])
        self.assertEqual(25, len(groups))
        self.assertTrue(all(len(splits) == 1 for splits in groups.values()))
        self.assertEqual(Counter(development=30, reserved=20), Counter(case['split'] for case in self.plan['cases']))
        self.assertEqual(5, sum(case['render'] for case in self.plan['cases']))
        self.assertIn('not proof of independence', self.plan['split_basis'])

    def test_declared_diversity_does_not_certify_actual_page_role_or_language(self):
        roles = {case['intended_role'] for case in self.plan['cases']}
        self.assertTrue({'product', 'recipe', 'reference', 'article', 'homepage', 'venue', 'listing'}.issubset(roles))
        self.assertTrue({'en', 'fr', 'nl'}.issubset({case['intended_language'] for case in self.plan['cases']}))
        self.assertIn('unverified declarations', self.plan['selection_basis'])
        self.assertIn('Do not replace failed URLs', self.plan['review_policy']['failures'])
        self.assertIn('Do not inspect finding rows', self.plan['review_policy']['reserved'])
        self.assertIn('No precision, recall', self.plan['review_policy']['metrics'])
        self.assertFalse(self.plan['capture_defaults']['allow_private'])
        self.assertFalse(self.plan['capture_defaults']['check_images'])

    def test_reserved_urls_are_not_reused_from_the_historical_report_inventory(self):
        historical = json.loads((ROOT / 'docs/tuning/review-corpus.json').read_text())
        historical_urls = {json.loads((ROOT / 'docs/tuning' / case['report']).read_text())['url']
                           for case in historical['cases']}
        reserved = {case['url'] for case in self.plan['cases'] if case['split'] == 'reserved'}
        self.assertFalse(reserved & historical_urls)

    def test_preacquisition_amendment_preserves_explicit_limits_and_unknowns(self):
        self.assertEqual('prospective-inputs-2026-10-v2', self.plan['cohort_id'])
        self.assertEqual('prospective-inputs-2026-10-v1', self.plan['supersedes_uncaptured_cohort'])
        policy = self.plan['acquisition_policy']
        self.assertEqual(0.5, policy['delay_between_cases_seconds'])
        self.assertEqual(180, policy['case_execution_deadline_seconds'])
        self.assertIn('unverified preflight skips', policy['robots_preflight'])
        self.assertIn('not an effective-policy or site-quality verdict', policy['robots_preflight'])


if __name__ == '__main__':
    unittest.main()
