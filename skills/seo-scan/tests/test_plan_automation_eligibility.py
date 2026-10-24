"""Structural automation needs an explicit rule, observed candidate and usable evidence."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_technical
import plan
from lib import htmlx, http
from lib.report import Report

RULE = 'technical.no.responsive.viewport.tag'
URL = 'https://example.test/'


def baseline():
    report = Report(URL, fetched_status=200)
    report.meta['scan_scope'] = {'requested': ['technical'], 'completed': ['technical']}
    audit_technical._viewport_lang(htmlx._parse_stdlib('<html lang="en"><head></head></html>', URL), report)
    return json.loads(report.to_json())


class TestAutomationEligibility(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.repo = Path(self.folder.name)
        (self.repo / 'index.html').write_text('<html lang="en"></html>', encoding='utf-8')

    def action(self, report):
        return next(item for item in plan.build_plan(report, str(self.repo))['actions'] if item['artifact'] == 'viewport')

    def test_actual_missing_viewport_rule_with_existing_candidate_remains_eligible(self):
        data = baseline()
        original = copy.deepcopy(data)
        action = self.action(data)
        self.assertEqual(RULE, action['rule_id'])
        self.assertEqual('safely_automatable', action['safety'])
        self.assertTrue(action['automation_eligibility']['eligible'])
        self.assertEqual([], action['automation_eligibility']['blockers'])
        self.assertIn('only if', action['proposed_change'])
        self.assertEqual(original, data)
        schema = json.loads((Path(plan.__file__).parent.parent / 'references' /
                             'remediation-plan.schema.json').read_text(encoding='utf-8'))
        properties = schema['properties']['actions']['items']['properties']
        self.assertTrue(set(action).issubset(properties))
        receipt_schema = properties['automation_eligibility']
        self.assertEqual(set(action['automation_eligibility']), set(receipt_schema['required']))
        self.assertEqual(action['automation_eligibility']['basis'],
                         receipt_schema['properties']['basis']['const'])

    def test_unknown_viewport_rules_never_inherit_automatic_insertion(self):
        for title in ('Review custom viewport policy', 'No responsive viewport tag'):
            data = baseline()
            data['findings'][0].update(rule_id='technical.viewport.policy.review', title=title)
            action = self.action(data)
            self.assertEqual('review_required', action['safety'])
            self.assertFalse(action['automation_eligibility']['eligible'])
            self.assertIn('unrecognized_structural_rule', action['automation_eligibility']['blockers'])
            self.assertIn('only if confirmed absent', action['proposed_change'])
            self.assertIn('avoid duplicate', action['proposed_change'])
            text = plan.render_markdown(plan.build_plan(data, str(self.repo)))
            self.assertNotIn('## Safe candidates for automation', text)
            self.assertIn('Automation eligibility', text)

    def test_convention_only_owners_need_review_while_no_owners_stay_manual(self):
        (self.repo / 'index.html').unlink()
        (self.repo / 'package.json').write_text('{"dependencies":{"next":"^15"}}', encoding='utf-8')
        action = self.action(baseline())
        self.assertTrue(action['likely_files'])
        self.assertTrue(all(not item['exists'] for item in action['likely_files']))
        self.assertEqual('review_required', action['safety'])
        self.assertIn('no_existing_owner_candidate', action['automation_eligibility']['blockers'])
        (self.repo / 'package.json').unlink()
        self.assertEqual('manual_external', self.action(baseline())['safety'])

    def test_known_partial_truncated_failed_or_unexecuted_source_withholds_automation(self):
        for change in (
            {'status': 206}, {'status': 503}, {'hard_fail': True},
            {'meta': {'coverage': {'server_range': {'basis': http.SERVER_RANGE_BASIS, 'observed': True}}}},
            {'meta': {'response_truncated': True}},
            {'meta': {'scan_scope': {'requested': ['technical'], 'completed': []}}},
            {'meta': {'scan_scope': {'requested': ['content'], 'completed': ['content']}}},
        ):
            with self.subTest(change=change):
                data = baseline()
                data.update(change)
                action = self.action(data)
                self.assertEqual('review_required', action['safety'])
                self.assertIn('known_incomplete_source_evidence', action['automation_eligibility']['blockers'])
                self.assertTrue(action['likely_files'])  # retain review candidates, not an automatic edit

    def test_uncertain_crawl_rollups_withhold_only_their_own_automation(self):
        page = baseline()
        data = {'site': URL, 'homepage': page, 'crawl': {'pages': [{'hard_fail': True}], 'recurring': []}}
        self.assertEqual('safely_automatable', self.action(data)['safety'])
        data['crawl']['recurring'] = [dict(page['findings'][0], count=3)]
        action = self.action(data)
        self.assertEqual('review_required', action['safety'])
        self.assertEqual(3, action['occurrences'])
        self.assertIn('known_incomplete_source_evidence', action['automation_eligibility']['blockers'])
        data['homepage']['findings'] = []
        self.assertEqual('review_required', self.action(data)['safety'])

    def test_completed_technical_check_does_not_require_unrelated_auditors(self):
        data = baseline()
        data['meta']['scan_scope'] = {'requested': ['technical', 'content'], 'completed': ['technical']}
        self.assertEqual('safely_automatable', self.action(data)['safety'])

    def test_recurring_only_rule_does_not_inherit_unrelated_homepage_failure(self):
        page = baseline()
        finding = page['findings'].pop()
        page['hard_fail'] = True
        data = {'site': URL, 'homepage': page,
                'crawl': {'pages': [{'hard_fail': False}], 'recurring': [dict(finding, count=2)]}}
        self.assertEqual('safely_automatable', self.action(data)['safety'])

    def test_legacy_title_ids_remain_candidates_without_certifying_missing_metadata(self):
        data = baseline()
        data.pop('meta')
        data.pop('status')
        del data['findings'][0]['rule_id']
        action = self.action(data)
        self.assertEqual(RULE, action['rule_id'])
        self.assertEqual('safely_automatable', action['safety'])
        self.assertIn('not', action['automation_eligibility']['scope'])

    def test_safety_defaults_never_promote_a_new_artifact_to_automation(self):
        self.assertEqual(('manual_external', False), plan.safety_for('future_unrecognized_artifact'))


if __name__ == '__main__':
    unittest.main()
