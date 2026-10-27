"""Successful observations cannot become work or inflate a remaining action."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan
from lib.report import Report
from test_plan_automation_eligibility import baseline, RULE, URL
from test_plan_repeated_evidence import build, REPO


def successes():
    report = Report(URL, fetched_status=200)
    report.ok('technical', 'Responsive viewport declared')
    report.ok('schema', 'Structured data present', 'WebSite')
    return json.loads(report.to_json())


class TestPlanSuccessObservations(unittest.TestCase):
    def compare(self, data):
        original = copy.deepcopy(data)
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')), \
                mock.patch('socket.socket.connect', side_effect=AssertionError('No network')):
            expected = build(data)
            self.assertEqual(expected, mcp_server._plan(data, REPO))
        self.assertEqual(original, data)
        return expected

    def test_native_successes_and_imported_good_rollups_emit_no_remediation(self):
        page = successes()
        rollups = [dict(row, count=5) for row in page['findings']]
        for kind, data in (
                ('scan', page),
                ('audit-page', {'site': URL, 'homepage': page, 'crawl': {}}),
                ('audit-crawl', {'site': URL, 'homepage': dict(page, findings=[]),
                                 'crawl': {'recurring': rollups}})):
            with self.subTest(kind=kind):
                built = self.compare(data)
                self.assertEqual([], built['actions'])
                self.assertEqual([], built['groups'])
                self.assertEqual([], built['conflicts'])
                self.assertEqual(0, built['coverage']['actionable_findings'])
                self.assertEqual(0, built['coverage']['actions_emitted'])
                self.assertEqual(0, built['coverage']['named_mappings'])
                self.assertFalse(built['coverage']['action_generation_capped'])
                self.assertNotIn('## Safe candidates for automation', plan.render_markdown(built))

    def test_successes_do_not_change_page_count_scope_or_observation_selection(self):
        page = baseline()
        remaining = page['findings'][0]
        remaining.pop('scope', None)  # legacy page default
        remaining['occurrences'] = 2
        good = dict(remaining, severity='good', scope='site', occurrences=999,
                    count=999, evidence='Successful observation, not remaining work')
        for kind in ('scan', 'audit-page', 'audit-crawl'):
            for rows in ([remaining, good], [good, remaining]):
                with self.subTest(kind=kind, success_first=rows[0] is good):
                    supplied = dict(page, findings=rows + successes()['findings'])
                    if kind != 'scan':
                        supplied = {'site': URL, 'homepage': supplied, 'crawl': {
                            'recurring': [good] if kind == 'audit-crawl' else []}}
                    built = self.compare(supplied)
                    self.assertEqual([RULE], [a['rule_id'] for a in built['actions']])
                    action = built['actions'][0]
                    self.assertEqual(2, action['occurrences'])
                    self.assertEqual('page', action['scope'])
                    self.assertEqual(remaining['detail'], action['evidence'])
                    self.assertNotIn('observation_selection', action)
                    self.assertTrue(action['automation_eligibility']['eligible'])
                    self.assertEqual(1, built['coverage']['actionable_findings'])
                    self.assertEqual(1, built['coverage']['actions_emitted'])
                    self.assertFalse(built['coverage']['action_generation_capped'])


if __name__ == '__main__':
    unittest.main()
