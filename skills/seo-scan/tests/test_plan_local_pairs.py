"""Planner commands separate paired local proof from original baseline checks."""
import shlex
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan


class TestPlanLocalPairs(unittest.TestCase):
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
