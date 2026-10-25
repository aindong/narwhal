"""Skipped source directories must not disappear from planning coverage."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan

RULE = 'technical.no.responsive.viewport.tag'
REPO = 'skills/seo-scan/tests/fixtures/planner/plain_html'


def report():
    return {'url': 'https://example.test/', 'findings': [
        {'rule_id': RULE, 'category': 'technical', 'severity': 'medium', 'title': 'No responsive viewport tag'}]}


def failing_walk(original):
    def walk(root, *, followlinks, onerror):
        onerror(PermissionError(13, 'denied', str(Path(root) / 'unreadable')))
        return original(root, followlinks=followlinks, onerror=onerror)
    return walk


class TestPlanInventoryErrors(unittest.TestCase):
    def test_walk_failure_is_counted_even_when_known_owner_was_found(self):
        original_walk = plan.os.walk
        with mock.patch.object(plan.os, 'walk', side_effect=failing_walk(original_walk)):
            built = plan.build_plan(report(), REPO)
        self.assertEqual(1, built['coverage']['file_inventory_walk_errors'])
        self.assertFalse(built['coverage']['file_inventory_capped'])
        self.assertTrue(any('could not traverse 1' in item for item in built['warnings']))
        action = built['actions'][0]
        self.assertTrue(any(owner['exists'] for owner in action['likely_files']))
        self.assertEqual('review_required', action['safety'])
        self.assertFalse(action['automation_eligibility']['eligible'])
        self.assertIn('incomplete_repository_inventory', action['automation_eligibility']['blockers'])
        self.assertIn('source coverage is incomplete', plan.render_markdown(built))

    def test_file_cap_also_withholds_automatic_candidate_despite_existing_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('a.txt', 'index.html', 'z.txt'):
                (root / name).write_text('<html></html>', encoding='utf-8')
            built = plan.build_plan(report(), str(root), max_files=2)
        self.assertTrue(built['coverage']['file_inventory_capped'])
        self.assertEqual(0, built['coverage']['file_inventory_walk_errors'])
        action = built['actions'][0]
        self.assertTrue(any(owner['exists'] for owner in action['likely_files']))
        self.assertFalse(action['automation_eligibility']['eligible'])
        self.assertEqual('review_required', action['safety'])

    def test_clean_inventory_retains_existing_candidate_behavior(self):
        built = plan.build_plan(report(), REPO)
        self.assertEqual(0, built['coverage']['file_inventory_walk_errors'])
        self.assertFalse(built['coverage']['file_inventory_capped'])
        self.assertEqual('safely_automatable', built['actions'][0]['safety'])
        self.assertTrue(built['actions'][0]['automation_eligibility']['eligible'])

    def test_root_traversal_failure_is_not_reported_as_a_complete_empty_repo(self):
        def denied(root, *, followlinks, onerror):
            onerror(OSError('root unavailable'))
            return iter(())
        with mock.patch.object(plan.os, 'walk', side_effect=denied):
            built = plan.build_plan(report(), REPO)
        self.assertEqual(0, built['coverage']['files_scanned'])
        self.assertEqual(1, built['coverage']['file_inventory_walk_errors'])
        self.assertFalse(built['actions'][0]['automation_eligibility']['eligible'])
        self.assertTrue(built['warnings'])

    def test_diagnostics_bound_directory_witnesses_without_losing_total(self):
        def denied(root, *, followlinks, onerror):
            for i in range(7):
                onerror(PermissionError(13, 'denied', str(Path(root) / f'unreadable-{i}')))
            return iter(())
        with mock.patch.object(plan.os, 'walk', side_effect=denied):
            built = plan.build_plan(report(), REPO)
        self.assertEqual(7, built['coverage']['file_inventory_walk_errors'])
        warnings = '\n'.join(built['warnings'])
        self.assertIn('unreadable-4', warnings)
        self.assertNotIn('unreadable-5', warnings)
        self.assertIn('could not traverse 7', warnings)

    def test_mcp_preserves_error_receipt_and_read_only_plan(self):
        data = report(); original = copy.deepcopy(data); original_walk = plan.os.walk
        with mock.patch.object(plan.os, 'walk', side_effect=failing_walk(original_walk)), \
                mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            built = mcp_server._plan(data, REPO)
        self.assertEqual(1, built['coverage']['file_inventory_walk_errors'])
        self.assertFalse(built['actions'][0]['automation_eligibility']['eligible'])
        self.assertEqual(original, data)


if __name__ == '__main__':
    unittest.main()
