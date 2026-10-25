"""The development gate fails closed without adding runtime dependencies."""
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[3] / 'scripts/mutation_test.py'
spec = importlib.util.spec_from_file_location('mutation_gate', SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class TestMutationGate(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
