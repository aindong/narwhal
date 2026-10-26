"""The development gate fails closed without adding runtime dependencies."""
import importlib.util
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[3] / 'scripts/mutation_test.py'
spec = importlib.util.spec_from_file_location('mutation_gate', SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class TestMutationGate(unittest.TestCase):
    def test_selected_profile_is_staged_without_changing_configuration_or_targets(self):
        for custom in (False, True):
            with self.subTest(custom=custom), tempfile.TemporaryDirectory(prefix='mutation profile ') as tmp:
                root = Path(tmp)
                for rel in ('skills/seo-scan/scripts', 'skills/seo-scan/tests', 'scripts/mutation', 'bin'):
                    (root / rel).mkdir(parents=True)
                (root / 'skills/seo-scan/scripts/fixture.py').write_text('pass\n', encoding='utf-8')
                default = root / 'scripts/mutation/pyproject.toml'
                default.write_text('# Default profile\n', encoding='utf-8')
                alternate = root / 'focused profile.toml'
                alternate.write_text('# Focused profile\n', encoding='utf-8')
                selected = alternate if custom else default
                executable = root / 'bin/mutmut'
                executable.touch()

                def run(command, *, cwd, check):
                    self.assertEqual([str(executable), 'run', '--max-children', '4', 'target_*'], command)
                    self.assertTrue(check)
                    self.assertEqual(selected.read_bytes(), (cwd / 'pyproject.toml').read_bytes())
                    self.assertEqual('pass\n', (cwd / 'src/fixture.py').read_text(encoding='utf-8'))
                    self.assertNotEqual(root, cwd)
                    metadata = cwd / 'mutants/src/fixture.py.meta'
                    metadata.parent.mkdir(parents=True)
                    metadata.write_text(json.dumps({'exit_code_by_key': {'target_1': 1}}), encoding='utf-8')

                args = ['mutation_test.py', 'target_*']
                if custom:
                    args += ['--config', str(alternate)]
                report = root / 'results.json'
                if custom:
                    args += ['--report', str(report)]
                with mock.patch.object(gate, 'ROOT', root), \
                        mock.patch.object(gate.sys, 'argv', args), \
                        mock.patch.object(gate.sys, 'executable', str(root / 'bin/python')), \
                        mock.patch.object(gate, 'version', return_value='3.7.0'), \
                        mock.patch.object(gate.subprocess, 'run', side_effect=run) as invoked, \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(0, gate.main())
                invoked.assert_called_once()
                if custom:
                    receipt = json.loads(report.read_text(encoding='utf-8'))
                    self.assertEqual('passed', receipt['status'])
                    self.assertEqual((1, 1), (receipt['killed'], receipt['total']))
                    self.assertEqual({'target_1': 1}, receipt['results'])
                self.assertEqual('# Default profile\n', default.read_text(encoding='utf-8'))
                self.assertEqual('# Focused profile\n', alternate.read_text(encoding='utf-8'))

    def test_report_preserves_survivors_and_errors_without_weakening_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in ('skills/seo-scan/scripts', 'skills/seo-scan/tests', 'bin'):
                (root / rel).mkdir(parents=True)
            config = root / 'profile.toml'
            config.write_text('# Fixture', encoding='utf-8')
            (root / 'bin/mutmut').touch()
            report = root / 'results.json'
            results = {'target_killed': 1, 'target_survived': 0, 'target_error': 3,
                       'target_incomplete': None, 'target_boolean': True}
            def run(command, *, cwd, check):
                if command[1] == 'run':
                    meta = cwd / 'mutants/src/fixture.py.meta'
                    meta.parent.mkdir(parents=True)
                    meta.write_text(json.dumps({'exit_code_by_key': {**results, 'other': 1}}), encoding='utf-8')
                else:
                    self.assertEqual('show', command[1])
            with mock.patch.object(gate, 'ROOT', root), \
                    mock.patch.object(gate.sys, 'argv', ['mutation_test.py', '--config', str(config),
                        '--report', str(report), 'target_*']), \
                    mock.patch.object(gate.sys, 'executable', str(root / 'bin/python')), \
                    mock.patch.object(gate, 'version', return_value='3.7.0'), \
                    mock.patch.object(gate.subprocess, 'run', side_effect=run), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(1, gate.main())
            receipt = json.loads(report.read_text(encoding='utf-8'))
            self.assertEqual({'schema_version': 1, 'mutmut_version': '3.7.0', 'targets': ['target_*'],
                              'status': 'failed', 'killed': 1, 'total': 5, 'results': results}, receipt)

    def test_failed_baseline_replaces_old_pass_with_incomplete_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in ('skills/seo-scan/scripts', 'skills/seo-scan/tests', 'bin'):
                (root / rel).mkdir(parents=True)
            config = root / 'profile.toml'
            config.write_text('# Fixture', encoding='utf-8')
            (root / 'bin/mutmut').touch()
            report = root / 'results.json'
            report.write_text(json.dumps({'status': 'passed', 'killed': 999}), encoding='utf-8')
            with mock.patch.object(gate, 'ROOT', root), \
                    mock.patch.object(gate.sys, 'argv', ['mutation_test.py', '--config', str(config),
                        '--report', str(report), 'target_*']), \
                    mock.patch.object(gate.sys, 'executable', str(root / 'bin/python')), \
                    mock.patch.object(gate, 'version', return_value='3.7.0'), \
                    mock.patch.object(gate.subprocess, 'run', side_effect=gate.subprocess.CalledProcessError(1, ['mutmut'])), \
                    self.assertRaises(gate.subprocess.CalledProcessError):
                gate.main()
            self.assertEqual({'schema_version': 1, 'status': 'not_completed', 'targets': ['target_*']},
                             json.loads(report.read_text(encoding='utf-8')))

    def test_missing_or_directory_profile_fails_before_mutation_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            for config in (Path(tmp), Path(tmp) / 'missing.toml'):
                with self.subTest(config=config), \
                        mock.patch.object(gate.sys, 'argv', ['mutation_test.py', '--config', str(config)]), \
                        mock.patch.object(gate.subprocess, 'run') as invoked, \
                        contextlib.redirect_stderr(io.StringIO()) as errors, \
                        self.assertRaises(SystemExit) as stopped:
                    gate.main()
                self.assertEqual(2, stopped.exception.code)
                self.assertIn('Mutation configuration must be a file', errors.getvalue())
                invoked.assert_not_called()

    def test_only_test_failure_exits_pass_and_unselected_results_do_not_count(self):
        results, failures = gate.check_results(
            [{'exit_code_by_key': {'target_1': 1, 'other': 0}}], 'target_*')
        self.assertEqual({'target_1': 1}, results)
        self.assertEqual({}, failures)

    def test_survivors_internal_errors_and_every_incomplete_exit_fail(self):
        for code in (0, 2, 3, 5, None, 33, 34, 35, 36, 37,
                     -24, 24, 152, 255, -11, -9, 999, True, '1'):
            with self.subTest(code=code):
                _, failures = gate.check_results([{'exit_code_by_key': {'target': code}}], 'target')
                self.assertEqual({'target': code}, failures)

    def test_empty_or_nonmatching_results_cannot_pass(self):
        for records in ([], [{'exit_code_by_key': {}}], [{'exit_code_by_key': {'other': 1}}]):
            with self.subTest(records=records), self.assertRaises(ValueError):
                gate.check_results(records, 'target')

    def test_duplicate_results_cannot_hide_a_failure(self):
        with self.assertRaises(ValueError):
            gate.check_results([{'exit_code_by_key': {'target': 0}},
                                {'exit_code_by_key': {'target': 1}}], 'target')

    def test_unsupported_metadata_cannot_pass(self):
        with self.assertRaises(KeyError):
            gate.check_results([{'renamed_result_field': {'target': 1}}], 'target')

    def test_every_requested_target_must_match_even_when_another_is_killed(self):
        records = [{'exit_code_by_key': {'first_1': 1}}]
        with self.assertRaisesRegex(ValueError, 'second'):
            gate.check_results(records, ['first_*', 'second_*'])
        with self.assertRaises(ValueError):
            gate.check_results(records, [])

    def test_multiple_and_overlapping_targets_count_unique_mutants_and_preserve_failures(self):
        records = [{'exit_code_by_key': {'first_1': 1, 'second_1': 0, 'other': 1}}]
        results, failures = gate.check_results(records, ['first_*', '*_1', 'second_*'])
        self.assertEqual({'first_1': 1, 'second_1': 0}, results)
        self.assertEqual({'second_1': 0}, failures)

    def test_duplicate_records_are_not_hidden_by_overlapping_patterns(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            gate.check_results([{'exit_code_by_key': {'first_1': 0}},
                                {'exit_code_by_key': {'first_1': 1}}], ['first_*', '*_1'])


if __name__ == '__main__':
    unittest.main()
