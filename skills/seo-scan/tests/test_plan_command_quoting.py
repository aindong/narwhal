"""Planner command data must stay literal when used in a POSIX shell."""

import contextlib
import copy
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diff_scan
import mcp_server
import plan

VALUES = ["ordinary", "space and café", "an'apostrophe", 'a"quote',
          '$NARWHAL_LITERAL_PROBE', '$(printf substitution)', '`printf substitution`',
          'semi;colon & pipe|operator', 'line\nbreak', '--format']
REPO = 'skills/seo-scan/tests/fixtures/planner/plain_html'


class TestPlanCommandQuoting(unittest.TestCase):
    def test_command_tokens_preserve_urls_and_paths_for_scan_and_audit(self):
        for kind in ('scan', 'audit'):
            for value in VALUES:
                with self.subTest(kind=kind, value=value):
                    target, source = 'https://example.test/' + value, 'reports/' + value + '.json'
                    commands = plan.verification_for('sitemap', target, source, kind)
                    fetch = shlex.split(commands[-2], comments=True)
                    diff = shlex.split(commands[-1])
                    self.assertEqual(['narwhal', kind, '--format', 'json', '-o', 'after.json', '--', target], fetch)
                    self.assertEqual(['narwhal', 'diff', '--fail-on-regression', '--', source, 'after.json'], diff)

    @unittest.skipUnless(os.name == 'posix' and shutil.which('sh'), 'POSIX shell probe')
    def test_actual_shell_does_not_expand_controlled_variables_or_substitutions(self):
        for value in VALUES:
            target, source = 'https://example.test/' + value, 'reports/' + value + '.json'
            commands = plan.verification_for('sitemap', target, source, 'audit')
            for command, literal in ((commands[-2], target), (commands[-1], source)):
                # Fixed fake command prints NUL-delimited arguments only. No
                # URL requests or real commands derived from source data run.
                script = 'narwhal() { printf "%s\\0" "$@"; }; ' + command
                result = subprocess.run([shutil.which('sh'), '-c', script],
                                        env=dict(os.environ, NARWHAL_LITERAL_PROBE='expanded'),
                                        capture_output=True, check=True, timeout=5)
                argv = result.stdout.decode().split('\0')[:-1]
                self.assertIn(literal, argv)
                self.assertEqual(shlex.split(command, comments=True)[1:], argv)

    def test_leading_dash_data_is_after_option_separator(self):
        for kind in ('scan', 'audit'):
            commands = plan.verification_for('sitemap', '--help', '--format', kind)
            self.assertEqual(['--', '--help'], shlex.split(commands[-2], comments=True)[-2:])
            self.assertEqual(['narwhal', 'diff', '--fail-on-regression', '--', '--format', 'after.json'],
                             shlex.split(commands[-1]))

    def test_local_placeholder_and_memory_baseline_remain_explicit(self):
        for kind, output in (('scan', 'after.json'), ('audit', 'page-after.json')):
            commands = plan.verification_for('title', 'https://example.test', '<memory>', kind)
            self.assertEqual(plan.MEMORY_BASELINE_INSTRUCTION, commands[0])
            self.assertEqual(['narwhal', 'scan', '--allow-private', '--format', 'json',
                              '-o', output, '--', '<local-preview-url>'], shlex.split(next(step for step in commands if step.startswith('narwhal scan '))))
            self.assertEqual('narwhal diff --fail-on-regression -- before.json after.json', commands[-1])

    def test_actual_diff_parser_accepts_leading_dash_filename_after_separator(self):
        report = {'url': 'https://example.test', 'score': 100, 'findings': [],
                  'meta': {'scan_scope': {'requested': ['schema'], 'completed': ['schema']}}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('--before.json', 'after.json'):
                (root / name).write_text(json.dumps(report))
            previous = Path.cwd()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(io.StringIO()):
                    rc = diff_scan.main(['--fail-on-regression', '--', '--before.json', 'after.json'])
            finally:
                os.chdir(previous)
        self.assertEqual(0, rc)

    def test_mcp_and_markdown_use_same_templates_without_mutating_report(self):
        report = {'url': 'https://example.test/$(printf literal)', 'findings': [
            {'category': 'technical', 'severity': 'high', 'rule_id': 'technical.no.robots.txt.found',
             'title': 'No robots.txt found'}]}
        original = copy.deepcopy(report)
        built = mcp_server._plan(report, REPO)
        command = next(step for step in built['actions'][0]['verification'] if step.startswith('narwhal '))
        self.assertEqual(report['url'], shlex.split(command, comments=True)[-1])
        markdown = plan.render_markdown(built)
        self.assertIn('POSIX shell quoting', markdown)
        self.assertIn('PowerShell/cmd', markdown)
        self.assertEqual(original, report)


if __name__ == '__main__':
    unittest.main()
