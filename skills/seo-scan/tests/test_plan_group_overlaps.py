"""Related actions must distinguish candidate unions from actual list overlaps."""
import copy
import itertools
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan
from test_plan_group_safety import report, TITLE, DESCRIPTION


def candidate(path, exists=True):
    return {'path': path, 'exists': exists}


def action(rule, *files, safety='review_required'):
    return {'rule_id': rule, 'artifact': 'title', 'safety': safety, 'likely_files': list(files)}


class TestGroupOverlaps(unittest.TestCase):
    def test_disjoint_candidates_keep_legacy_union_without_claiming_shared_ownership(self):
        rows = [action('a', candidate('a.html')), action('b', candidate('b.html'))]
        group = plan._groups(rows)[0]
        self.assertEqual(['a.html', 'b.html'], group['likely_shared_files'])
        self.assertEqual([], group['candidate_file_overlaps'])
        self.assertIn('union of existing candidates', group['candidate_file_basis'])
        self.assertIn('not proven shared ownership', group['candidate_file_basis'])
        self.assertIn('confirm source owners', group['reason'])

    def test_partial_overlap_records_only_rules_that_name_each_existing_candidate(self):
        rows = [action('a', candidate('common.html'), candidate('a.html')),
                action('b', candidate('common.html'), candidate('b.html')),
                action('c', candidate('c.html'))]
        original = copy.deepcopy(rows)
        expected = plan._groups(rows)
        self.assertEqual([{'path': 'common.html', 'rule_ids': ['a', 'b']}], expected[0]['candidate_file_overlaps'])
        for permutation in itertools.permutations(rows):
            self.assertEqual(expected, plan._groups(list(permutation)))
        self.assertEqual(original, rows)

    def test_duplicate_entries_and_missing_proposals_cannot_invent_existing_overlap(self):
        rows = [action('a', candidate('a.html'), candidate('a.html'), candidate('future.html', False)),
                action('b', candidate('b.html'), candidate('future.html', False))]
        group = plan._groups(rows)[0]
        self.assertEqual([], group['candidate_file_overlaps'])
        self.assertNotIn('future.html', group['likely_shared_files'])

    def test_manual_members_do_not_enter_overlap_receipts(self):
        rows = [action('a', candidate('common.html')), action('b', candidate('common.html'))]
        expected = plan._groups(rows)
        manual = action('manual', candidate('common.html'), candidate('external.html'), safety='manual_external')
        self.assertEqual(expected, plan._groups(rows + [manual]))
        self.assertEqual(['a', 'b'], expected[0]['candidate_file_overlaps'][0]['rule_ids'])

    def test_markdown_labels_union_and_legacy_unknown_overlap_without_owner_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'index.html').write_text('fixture', encoding='utf-8')
            built = plan.build_plan(report(TITLE, DESCRIPTION), tmp)
        text = plan.render_markdown(built)
        self.assertIn('Related actions to review', text)
        self.assertIn('existing candidate union: index.html', text)
        self.assertIn('candidates in multiple actions: index.html', text)
        self.assertNotIn('owners: index.html', text)
        for group in built['groups']: group.pop('candidate_file_overlaps')
        self.assertIn('candidates in multiple actions: unrecorded', plan.render_markdown(built))

    def test_offline_mcp_disjoint_discovery_group_preserves_input_and_source(self):
        data = report('technical.no.robots.txt.found', 'technical.xml.sitemap.not.found')
        original = copy.deepcopy(data)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); repo = root / 'source'; repo.mkdir()
            owners = [repo / name for name in ('index.html', 'robots.txt', 'sitemap.xml')]
            for owner in owners: owner.write_text('fixture', encoding='utf-8')
            snapshots = [owner.read_bytes() for owner in owners]
            with mock.patch.object(Path, 'cwd', return_value=root), \
                    mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
                built = mcp_server._plan(data, 'source')
            self.assertEqual(snapshots, [owner.read_bytes() for owner in owners])
        group = built['groups'][0]
        self.assertEqual('public_discovery_files', group['artifact'])
        self.assertEqual(['robots.txt', 'sitemap.xml'], group['likely_shared_files'])
        self.assertEqual([], group['candidate_file_overlaps'])
        self.assertEqual(original, data)


if __name__ == '__main__':
    unittest.main()
