"""Verification output templates must not reuse known baseline filenames."""

import copy
import shlex
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan

REPO = str(Path(__file__).parent / 'fixtures' / 'planner' / 'plain_html')
TARGET = 'https://example.test/'


def commands_only(steps):
    return [shlex.split(step, comments=True) for step in steps if step.startswith('narwhal ')]


class TestPlanBaselinePreservation(unittest.TestCase):
    def test_after_baseline_uses_same_distinct_output_in_command_and_diff(self):
        sources = ['after.json', './after.json', '/repo/reports/after.json',
                   '/repo/AFTER.JSON', r'C:\reports\After.Json']
        for kind in ('scan', 'audit'):
            for artifact in ('title', 'json_ld', 'sitemap', 'server_config'):
                for source in sources:
                    with self.subTest(kind=kind, artifact=artifact, source=source):
                        commands = commands_only(plan.verification_for(artifact, TARGET, source, kind))
                        fetch, diff = commands[-2:]
                        self.assertEqual('after-2.json', fetch[fetch.index('-o') + 1])
                        self.assertEqual(['narwhal', 'diff', '--fail-on-regression', '--', source, 'after-2.json'], diff)

    def test_page_after_baseline_is_not_reused_by_local_audit_scan(self):
        for source in ('page-after.json', '/reports/PAGE-AFTER.JSON', r'C:\repo\page-after.json'):
            for artifact in ('title', 'product_schema'):
                with self.subTest(source=source, artifact=artifact):
                    steps = plan.verification_for(artifact, TARGET, source, 'audit')
                    local, audit, diff = commands_only(steps)
                    self.assertEqual('page-after-2.json', local[local.index('-o') + 1])
                    self.assertEqual('after.json', audit[audit.index('-o') + 1])
                    self.assertEqual('after.json', diff[-1])
                    self.assertTrue(any('do not compare page-after-2.json' in step for step in steps))

    def test_alternate_baselines_do_not_trigger_unrelated_renames(self):
        for source in ('before.json', 'after-2.json', 'page-after-2.json', '<memory>'):
            with self.subTest(source=source):
                self.assertEqual(('page-after.json', 'after.json'), plan._verification_outputs(source))

    def test_markdown_and_json_agree_on_alternate_audit_output_names(self):
        report = {'site': TARGET, 'homepage': {'findings': [
            {'category': 'technical', 'severity': 'high', 'title': 'Missing title',
             'rule_id': 'technical.missing.title'}]}, 'crawl': {}, 'sitemap': {}}
        for source, expected in (('after.json', 'after-2.json'), ('page-after.json', 'page-after-2.json')):
            built = plan.build_plan(report, REPO, report_source=source)
            markdown = plan.render_markdown(built)
            action = built['actions'][0]
            self.assertIn(expected, markdown)
            self.assertTrue(any(expected in step for step in action['verification']))
            if source == 'page-after.json':
                self.assertIn('Keep its `page-after-2.json` separate', markdown)
            else:
                self.assertIn('narwhal audit --format json -o after-2.json', markdown)

    def test_planning_keeps_report_and_source_provenance_unchanged(self):
        report = {'url': TARGET, 'findings': [{'category': 'technical', 'severity': 'high',
                   'rule_id': 'technical.missing.title', 'title': 'Missing title'}]}
        original = copy.deepcopy(report)
        built = plan.build_plan(report, REPO, report_source='/reports/after.json')
        self.assertEqual(original, report)
        self.assertEqual('/reports/after.json', built['provenance']['report'])
        self.assertEqual('after-2.json', commands_only(built['actions'][0]['verification'])[-1][-1])

    def test_output_selection_does_not_read_or_resolve_paths(self):
        with mock.patch('builtins.open', side_effect=AssertionError('No I/O')), \
                mock.patch.object(Path, 'resolve', side_effect=AssertionError('No path resolution')), \
                mock.patch.object(Path, 'stat', side_effect=AssertionError('No metadata read')):
            self.assertEqual(('page-after.json', 'after-2.json'), plan._verification_outputs('/private/after.json'))
            self.assertEqual(('page-after-2.json', 'after.json'), plan._verification_outputs('/private/page-after.json'))


if __name__ == '__main__':
    unittest.main()
