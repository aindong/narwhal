"""Structural automation needs an explicit rule, observed candidate and usable evidence."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_technical
import plan
import mcp_server
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
            {'status': 1}, {'status': 199}, {'status': 206}, {'status': 300}, {'status': 503}, {'hard_fail': True},
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

    def test_explicit_invalid_scope_blocks_page_and_crawl_without_repairing_legacy(self):
        invalid = (None, [], {}, {'requested': 'technical', 'completed': []},
                   {'requested': ['technical'], 'completed': ['technical', 'technical']},
                   {'requested': ['technical'], 'completed': ['schema']},
                   {'requested': ['future'], 'completed': ['future']})
        for scope in invalid:
            for kind in ('scan', 'audit'):
                page = baseline()
                if kind == 'scan':
                    page['meta']['scan_scope'] = scope
                    data = page
                else:
                    finding = page['findings'].pop()
                    recurring = dict(finding, count=1, url_sample={
                        'basis': 'recorded_crawl_rule_url_labels_v1', 'urls': [URL],
                        'truncated': False, 'omitted': 0})
                    data = {'site': URL, 'homepage': page, 'crawl': {
                        'pages': [{'url': URL, 'scan_scope': scope}], 'recurring': [recurring]}}
                original = copy.deepcopy(data)
                with self.subTest(scope=scope, kind=kind):
                    action = next(a for a in plan.build_plan(data, str(self.repo),
                                  report_source='<mcp-object>')['actions'] if a['rule_id'] == RULE)
                    self.assertFalse(action['automation_eligibility']['eligible'])
                    self.assertEqual('review_required', action['safety'])
                    self.assertIn('known_incomplete_source_evidence', action['automation_eligibility']['blockers'])
                    self.assertEqual(['index.html'], [owner['path'] for owner in action['likely_files']])
                    with mock.patch.object(Path, 'cwd', return_value=self.repo.parent), \
                            mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
                        received = mcp_server._plan(data, self.repo.name)
                    self.assertEqual(action, next(a for a in received['actions'] if a['rule_id'] == RULE))
                    self.assertEqual(original, data)
        legacy = baseline()
        legacy['meta'].pop('scan_scope')
        self.assertTrue(self.action(legacy)['automation_eligibility']['eligible'])
        for metadata in (None, [], 'unrecorded'):
            legacy['meta'] = metadata
            self.assertTrue(self.action(legacy)['automation_eligibility']['eligible'])

    def test_uncertain_crawl_rollups_withhold_only_their_own_automation(self):
        page = baseline()
        data = {'site': URL, 'homepage': page, 'crawl': {'pages': [{'hard_fail': True}], 'recurring': []}}
        self.assertEqual('safely_automatable', self.action(data)['safety'])
        data['crawl']['recurring'] = [dict(page['findings'][0], count=3)]
        data['crawl']['recurring'][0]['url_sample'] = {
            'basis': 'recorded_crawl_rule_url_labels_v1', 'urls': [URL], 'truncated': False, 'omitted': 0}
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
        data['crawl']['recurring'][0]['url_sample'] = {
            'basis': 'recorded_crawl_rule_url_labels_v1', 'urls': [URL], 'truncated': False, 'omitted': 0}
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

    def test_markdown_receipts_expose_classification_blockers_and_authority_limits(self):
        for name in ('a.txt', 'z.txt'):
            (self.repo / name).write_text('Fixture', encoding='utf-8')
        cases = (
            ('eligible', None, False, []),
            ('unknown_rule', None, False, ['unrecognized_structural_rule']),
            ('partial', 206, False, ['known_incomplete_source_evidence']),
            ('capped', None, True, ['incomplete_repository_inventory']),
            ('combined', 206, True, ['unrecognized_structural_rule', 'incomplete_repository_inventory',
                                    'known_incomplete_source_evidence']),
        )
        for name, status, capped, blockers in cases:
            with self.subTest(case=name):
                data = baseline()
                if name in ('unknown_rule', 'combined'):
                    data['findings'][0]['rule_id'] = 'technical.viewport.policy.review'
                if status is not None:
                    data['status'] = status
                built = plan.build_plan(data, str(self.repo), max_files=2 if capped else 5000)
                original = copy.deepcopy(built)
                action = next(item for item in built['actions'] if item['artifact'] == 'viewport')
                self.assertEqual(blockers, action['automation_eligibility']['blockers'])
                text = plan.render_markdown(built)
                line = next(line for line in text.splitlines() if line.startswith('- **Automation eligibility:**'))
                self.assertIn('not edit authorization', line)
                self.assertIn('inspect current source before editing', line)
                if blockers:
                    self.assertIn('withheld: ' + ', '.join(blockers), line)
                    self.assertNotIn('## Safe candidates for automation', text)
                    self.assertFalse(action['automation_eligibility']['eligible'])
                else:
                    self.assertIn('candidate.', line)
                    self.assertNotIn('withheld:', line)
                    self.assertIn('## Safe candidates for automation', text)
                    self.assertTrue(action['automation_eligibility']['eligible'])
                self.assertEqual(original, built)

    def test_markdown_without_observed_owners_withholds_convention_and_ownerless_actions(self):
        (self.repo / 'index.html').unlink()
        package = self.repo / 'package.json'
        package.write_text('{"dependencies":{"next":"*"}}', encoding='utf-8')
        for layout, expected in (('convention_only', 'review_required'), ('ownerless', 'manual_external')):
            if layout == 'ownerless':
                package.unlink()
            with self.subTest(layout=layout):
                built = plan.build_plan(baseline(), str(self.repo))
                action = next(item for item in built['actions'] if item['artifact'] == 'viewport')
                self.assertEqual(expected, action['safety'])
                self.assertFalse(action['automation_eligibility']['eligible'])
                text = plan.render_markdown(built)
                line = next(line for line in text.splitlines() if line.startswith('- **Automation eligibility:**'))
                self.assertIn('withheld: no_existing_owner_candidate', line)
                self.assertIn('not edit authorization', line)
                self.assertNotIn('## Safe candidates for automation', text)


if __name__ == '__main__':
    unittest.main()
