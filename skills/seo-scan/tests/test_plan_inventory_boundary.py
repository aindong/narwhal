"""Reaching the file budget is not evidence that eligible source files were omitted."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan
from test_plan_inventory_errors import report


def source(root, rel='index.html'):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<html><head></head><body>Fixture</body></html>', encoding='utf-8')
    return path


class TestInventoryBoundary(unittest.TestCase):
    def test_exact_budget_does_not_withhold_otherwise_eligible_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); source(root)
            built = plan.build_plan(report(), str(root), max_files=1)
        self.assertEqual(1, built['coverage']['files_scanned'])
        self.assertFalse(built['coverage']['file_inventory_capped'])
        self.assertTrue(built['actions'][0]['automation_eligibility']['eligible'])
        self.assertFalse(any('inventory capped' in warning for warning in built['warnings']))

    def test_exact_budget_in_nested_directory_is_not_capped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); source(root, 'pages/index.html'); source(root, 'pages/nested/page.html')
            inv = plan.inventory(root, max_files=2)
        self.assertEqual(['pages/index.html', 'pages/nested/page.html'], inv['files'])
        self.assertFalse(inv['capped'])

    def test_one_more_eligible_file_sets_cap_without_exceeding_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); source(root); source(root, 'nested/other.html')
            built = plan.build_plan(report(), str(root), max_files=1)
        self.assertEqual(1, built['coverage']['files_scanned'])
        self.assertTrue(built['coverage']['file_inventory_capped'])
        self.assertIn('incomplete_repository_inventory', built['actions'][0]['automation_eligibility']['blockers'])

    def test_ignored_files_and_empty_directories_do_not_invent_omitted_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); source(root); source(root, 'node_modules/dependency.html'); (root / 'empty').mkdir()
            inv = plan.inventory(root, max_files=1)
        self.assertEqual(['index.html'], inv['files'])
        self.assertFalse(inv['capped'])

    def test_traversal_error_after_budget_is_still_recorded_and_blocks_candidate(self):
        def walk(root, *, followlinks, onerror):
            yield root, [], ['index.html']
            onerror(PermissionError(13, 'denied', str(Path(root) / 'blocked')))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); source(root)
            with mock.patch.object(plan.os, 'walk', side_effect=walk):
                built = plan.build_plan(report(), str(root), max_files=1)
        self.assertFalse(built['coverage']['file_inventory_capped'])
        self.assertEqual(1, built['coverage']['file_inventory_walk_errors'])
        self.assertFalse(built['actions'][0]['automation_eligibility']['eligible'])

    def test_mcp_exact_budget_coverage_is_read_only_and_offline(self):
        data = report(); original = copy.deepcopy(data)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); owner = source(root / 'source'); owner_bytes = owner.read_bytes()
            with mock.patch.object(Path, 'cwd', return_value=root), \
                    mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
                built = mcp_server._plan(data, 'source', max_files=1)
            self.assertEqual(owner_bytes, owner.read_bytes())
        self.assertFalse(built['coverage']['file_inventory_capped'])
        self.assertTrue(built['actions'][0]['automation_eligibility']['eligible'])
        self.assertEqual(original, data)


if __name__ == '__main__':
    unittest.main()
