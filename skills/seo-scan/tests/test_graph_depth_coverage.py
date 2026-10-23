"""Graph observations survive empty-edge samples without invented coverage."""
import copy
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from lib import sitegraph

BASE = 'https://example.test/'


def links(*urls):
    return [{'url': url, 'internal': True} for url in urls]


def zero_graph(count=1, orphans=1):
    return sitegraph.analyze(BASE, [BASE] + [BASE + 'unlinked/' + str(i) for i in range(count)], {},
                             [BASE + 'outside/' + str(i) for i in range(orphans)], True)


def text(g, **kwargs):
    return '\n'.join(sitegraph.render_markdown(g, **kwargs))


class TestGraphDepthCoverage(unittest.TestCase):
    def test_zero_edges_keep_all_known_observations_and_scope(self):
        g = zero_graph()
        self.assertEqual(0, g['internal_edges'])
        self.assertEqual({'basis': sitegraph.DEPTH_BASIS, 'start_present': True,
                          'reachable_nodes': 1, 'unreachable_nodes': 1}, g['depth_coverage'])
        rendered = text(g, sitemap_total=3)
        for expected in ('zero recorded edges does not prove the site has no links',
                         'among 1 reachable of 2 supplied graph nodes',
                         'No inbound internal links observed in the sample (1)',
                         'Orphan candidates', BASE + 'outside/0', BASE + 'unlinked/0',
                         'against 3 discovered sitemap URLs', 'larger cap does not itself repair missing edges'):
            self.assertIn(expected, rendered)
        self.assertNotIn('🟢', rendered)
        self.assertNotIn('needs a larger crawl', rendered)

    def test_empty_graph_is_unassessed_not_measured_zero_depth(self):
        g = sitegraph.analyze(BASE, [], {}, [], False)
        self.assertEqual({'basis': sitegraph.DEPTH_BASIS, 'start_present': False,
                          'reachable_nodes': 0, 'unreachable_nodes': 0}, g['depth_coverage'])
        self.assertEqual(0, g['max_depth'])  # preserve historical JSON placeholder
        self.assertIn('Depth from the start URL is unassessed', text(g))
        self.assertIn('Orphan check skipped', text(g))
        self.assertNotIn('Max measured click depth', text(g))

    def test_start_only_is_a_measured_zero_with_one_node_not_site_health(self):
        g = sitegraph.analyze(BASE, [BASE], {}, [], False)
        self.assertIn('among 1 reachable of 1 supplied graph nodes', text(g))
        self.assertIn('not verified crawler access or ranking', text(g))
        self.assertNotIn('🟢', text(g))

    def test_self_links_do_not_create_interpage_edges(self):
        g = sitegraph.analyze(BASE, [BASE], {BASE: links(BASE, BASE + '#section')}, [], False)
        self.assertEqual(0, g['internal_edges'])
        self.assertEqual(1, g['depth_coverage']['reachable_nodes'])
        self.assertIn('No inter-page edges', text(g))

    def test_absent_start_with_edges_leaves_all_node_reachability_unassessed(self):
        a, b = BASE + 'a', BASE + 'b'
        g = sitegraph.analyze(BASE, [a, b], {a: links(b)}, [], False)
        self.assertEqual(1, g['internal_edges'])
        self.assertEqual(0, g['depth_coverage']['reachable_nodes'])
        rendered = text(g)
        self.assertIn('Raw `max_depth=0` is a placeholder', rendered)
        self.assertIn('Recorded URLs with unassessed start reachability (2)', rendered)
        self.assertNotIn('Crawled but not reachable', rendered)

    def test_absent_start_without_edges_still_shows_nodes(self):
        g = sitegraph.analyze(BASE, [BASE + 'a'], {}, [], False)
        self.assertIn('unassessed start reachability (1)', text(g))
        self.assertIn(BASE + 'a', text(g))

    def test_isolated_start_does_not_hide_other_component(self):
        a, b = BASE + 'a', BASE + 'b'
        g = sitegraph.analyze(BASE, [BASE, a, b], {a: links(b)}, [], False)
        self.assertEqual(0, g['max_depth'])
        self.assertEqual(1, g['internal_edges'])
        self.assertIn('among 1 reachable of 3 supplied graph nodes', text(g))
        self.assertIn('within the supplied graph (2)', text(g))
        self.assertNotIn('🟢', text(g))

    def test_connected_cycle_keeps_bfs_numbers(self):
        a, b = BASE + 'a', BASE + 'b'
        g = sitegraph.analyze(BASE, [BASE, a, b], {BASE: links(a), a: links(b), b: links(BASE)}, [], False)
        self.assertEqual(2, g['max_depth'])
        self.assertEqual(3, g['internal_edges'])
        self.assertEqual([], g['unreachable_from_start'])
        self.assertEqual(3, g['depth_coverage']['reachable_nodes'])
        self.assertIn('among 3 reachable of 3 supplied graph nodes', text(g))

    def test_fragment_alias_start_uses_same_identity(self):
        g = sitegraph.analyze(BASE + '#start', [BASE], {}, [], False)
        self.assertTrue(g['depth_coverage']['start_present'])
        self.assertIsNotNone(sitegraph.recorded_depth(g))

    def test_zero_edge_samples_keep_existing_display_caps_and_show_omissions(self):
        g = zero_graph(count=7, orphans=10)
        rendered = text(g)
        self.assertIn('sample (7)', rendered)
        self.assertEqual(3, rendered.count('… +2 more (see JSON)'))  # two lists plus orphan list
        self.assertIn(BASE + 'unlinked/4', rendered)
        self.assertNotIn(BASE + 'unlinked/5', rendered)
        self.assertIn(BASE + 'outside/7', rendered)
        self.assertNotIn(BASE + 'outside/8', rendered)
        self.assertEqual(7, len(g['unreachable_from_start']))
        self.assertEqual(10, len(g['orphans']['candidates']))

    def test_deep_list_keeps_five_items_and_explicit_omission(self):
        nodes = [BASE] + [BASE + 'n/' + str(i) for i in range(10)]
        g = sitegraph.analyze(BASE, nodes, {a: links(b) for a, b in zip(nodes, nodes[1:])}, [], False)
        self.assertEqual(10, g['max_depth'])
        self.assertEqual(7, len(g['deep_pages']))
        self.assertIn('deeper than 3 clicks (7)', text(g))
        self.assertEqual(5, text(g).count('  - depth '))
        self.assertIn('… +2 more (see JSON)', text(g))

    def test_legacy_keeps_evidence_without_inventing_bfs_receipt(self):
        g = zero_graph()
        del g['depth_coverage']
        rendered = text(g)
        self.assertIn('start/BFS coverage is unrecorded or unsupported', rendered)
        self.assertIn('listed as unreachable (start/BFS scope unverified)', rendered)
        self.assertIn(BASE + 'unlinked/0', rendered)
        self.assertIn(BASE + 'outside/0', rendered)
        self.assertNotIn('Max measured click depth', rendered)

    def test_unknown_and_malformed_receipts_are_not_certified(self):
        for value in (None, [], 'v1', {}, {'basis': 'future'},
                      {'basis': sitegraph.DEPTH_BASIS}):
            with self.subTest(value=value):
                g = zero_graph(); g['depth_coverage'] = value
                self.assertIsNone(sitegraph.recorded_depth(g))
                self.assertIn('unrecorded or unsupported', text(g))

    def test_invalid_count_types_ranges_and_contradictions_are_not_certified(self):
        cases = [('reachable_nodes', True), ('unreachable_nodes', -1), ('reachable_nodes', 1.0),
                 ('start_present', 1), ('start_present', False), ('reachable_nodes', 0),
                 ('unreachable_nodes', 0), ('reachable_nodes', 2)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                g = zero_graph(); g['depth_coverage'][field] = value
                self.assertIsNone(sitegraph.recorded_depth(g))
        for field, value in (('internal_edges', True), ('internal_edges', -1),
                             ('internal_edges', 3),
                             ('max_depth', 1), ('pages_in_graph', True), ('unreachable_from_start', [])):
            with self.subTest(field=field, value=value):
                g = zero_graph(); g[field] = value
                self.assertIsNone(sitegraph.recorded_depth(g))

    def test_two_reachable_nodes_need_positive_depth_and_enough_edges(self):
        g = sitegraph.analyze(BASE, [BASE, BASE + 'a'], {BASE: links(BASE + 'a')}, [], False)
        for field, value in (('max_depth', 0), ('internal_edges', 0)):
            candidate = copy.deepcopy(g); candidate[field] = value
            self.assertIsNone(sitegraph.recorded_depth(candidate))

    def test_no_orphans_does_not_become_inbound_link_pass(self):
        g = zero_graph(orphans=0)
        self.assertIn('this does not prove every sitemap URL is linked', text(g))
        self.assertIn('No inbound internal links observed', text(g))

    def test_missing_sitemap_is_not_a_clean_orphan_verdict(self):
        g = zero_graph(); g['orphans'] = {'checked': False, 'candidates': [], 'total': 0}
        self.assertIn('Orphan check skipped', text(g))
        self.assertNotIn('no additional candidates', text(g))

    def test_analysis_and_render_are_offline_deterministic_and_nonmutating(self):
        with mock.patch.object(socket, 'socket', side_effect=AssertionError('No network')):
            g = zero_graph(); before = json.dumps(g, sort_keys=True)
            first = text(g)
            self.assertEqual(first, text(g))
            self.assertEqual(before, json.dumps(g, sort_keys=True))


if __name__ == '__main__': unittest.main()
