"""Planner commands separate paired local proof from original baseline checks."""
import shlex
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan


class TestPlanLocalPairs(unittest.TestCase):
    def test_recorded_byte_budget_is_preserved_only_for_valid_scan_evidence(self):
        for value in (64_000, 6_000_000, 20_000_000, None, True, '6000000', 6_000_000.0,
                      63_999, 20_000_001, 0, -1):
            with self.subTest(value=value):
                page = {'meta': {'coverage': {'response_byte_limit': value}}}
                before = repr(page)
                options = plan._recorded_scan_options(page)
                valid = type(value) is int and 64_000 <= value <= 20_000_000
                self.assertEqual(('--max-bytes', str(value)) if valid else (), options)
                steps = plan.verification_for('title', 'https://example.test', 'before.json',
                                               scan_options=options)
                scans = [shlex.split(step, comments=True) for step in steps if step.startswith('narwhal scan ')]
                self.assertEqual(3, len(scans))
                for command in scans:
                    self.assertEqual(valid, '--max-bytes' in command)
                    if valid:
                        self.assertEqual(str(value), command[command.index('--max-bytes') + 1])
                self.assertEqual(before, repr(page))
        for coverage in (None, [], True, '6000000', {}):
            self.assertEqual((), plan._recorded_scan_options({'meta': {'coverage': coverage}}))
        page = {'meta': {'scan_scope': {'requested': ['technical'], 'completed': ['technical']},
                         'scan_settings': {'render_requested': True, 'image_checks': False},
                         'coverage': {'response_byte_limit': 6_000_000}}}
        self.assertEqual(('--only', 'technical', '--render', '--no-image-checks', '--max-bytes', '6000000'),
                         plan._recorded_scan_options(page))

    def test_scan_settings_prerequisite_is_present_once_before_local_or_deployed_scans(self):
        for artifact in ('title', 'json_ld', 'sitemap', 'server_config'):
            steps = plan.verification_for(artifact, 'https://example.test', 'before.json')
            self.assertEqual(1, steps.count(plan.SCAN_SETTINGS_INSTRUCTION))
            scan = next(i for i, step in enumerate(steps) if step.startswith('narwhal scan '))
            self.assertLess(steps.index(plan.SCAN_SETTINGS_INSTRUCTION), scan)

    def test_local_scans_pair_before_edits_and_original_target_waits_for_deploy(self):
        for kind in ('scan', 'audit'):
            steps = plan.verification_for('title', 'https://example.test/page', 'original.json', kind)
            commands = [shlex.split(s, comments=True) for s in steps if s.startswith('narwhal ')]
            self.assertEqual(['scan', 'scan', 'diff', kind, 'diff'], [c[1] for c in commands])
            self.assertEqual(['page-before.json', 'page-after.json'],
                             [c[c.index('-o') + 1] for c in commands[:2]])
            self.assertTrue(all(c[-1] == '<local-preview-url>' and '--allow-private' in c
                                for c in commands[:2]))
            self.assertEqual(['page-before.json', 'page-after.json'], commands[2][-2:])
            self.assertEqual('https://example.test/page', commands[3][-1])
            self.assertEqual(['original.json', 'after.json'], commands[4][-2:])
            self.assertTrue(all('--require-comparable' in c and '--fail-on-regression' in c
                                for c in (commands[2], commands[4])))
            self.assertIn('Before editing', '\n'.join(steps))
            self.assertIn('After applying', '\n'.join(steps))
            self.assertIn('run after deploy', '\n'.join(steps))

    def test_local_before_name_cannot_overwrite_original_baseline(self):
        for source in ('page-before.json', '/reports/PAGE-BEFORE.JSON', r'C:\reports\page-before.json'):
            steps = plan.verification_for('title', 'https://example.test', source)
            commands = [shlex.split(s, comments=True) for s in steps if s.startswith('narwhal ')]
            self.assertEqual('page-before-2.json', commands[0][commands[0].index('-o') + 1])
            self.assertEqual('page-before-2.json', commands[2][-2])
            self.assertEqual(source, commands[-1][-2])


if __name__ == '__main__':
    unittest.main()
