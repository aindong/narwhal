"""Ranked graph observations must not depend on set/hash iteration order."""

import copy
import json
import os
import random
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from lib import sitegraph

BASE = 'https://example.test/'


def links(*urls):
    return [{'url': url, 'internal': True} for url in urls]


def star():
    pages = [BASE] + [BASE + letter for letter in 'abcdefgh']
    return {'base': BASE, 'crawled': pages, 'pages_links': {BASE: links(*pages[1:])},
            'sitemap_urls': pages + [BASE + 'orphan'], 'sitemap_found': True}


class TestGraphRankings(unittest.TestCase):
    def test_equal_inbound_ties_are_sorted_before_top_five_cutoff(self):
        graph = sitegraph.analyze(**star())
        self.assertEqual([{'url': BASE + letter, 'inbound': 1} for letter in 'abcde'], graph['top_linked'])

    def test_larger_inbound_count_still_precedes_lexical_url_order(self):
        data = star()
        data['pages_links'][BASE + 'a'] = links(BASE + 'h')
        graph = sitegraph.analyze(**data)
        self.assertEqual([BASE + letter for letter in 'habcd'], [item['url'] for item in graph['top_linked']])
        self.assertEqual([2, 1, 1, 1, 1], [item['inbound'] for item in graph['top_linked']])

    def test_deep_pages_use_depth_first_then_url_not_bfs_parent_order(self):
        pages = [BASE] + [BASE + suffix for suffix in ('1', '2', '3', 'parent-a', 'parent-z', 'leaf-a', 'leaf-z')]
        edges = {BASE: links(BASE + '1'), BASE + '1': links(BASE + '2'), BASE + '2': links(BASE + '3'),
                 BASE + '3': links(BASE + 'parent-a', BASE + 'parent-z'),
                 BASE + 'parent-a': links(BASE + 'leaf-z'), BASE + 'parent-z': links(BASE + 'leaf-a')}
        graph = sitegraph.analyze(BASE, pages, edges, [], False)
        self.assertEqual([{'url': BASE + 'leaf-a', 'depth': 5}, {'url': BASE + 'leaf-z', 'depth': 5},
                          {'url': BASE + 'parent-a', 'depth': 4}, {'url': BASE + 'parent-z', 'depth': 4}], graph['deep_pages'])
        self.assertEqual(5, graph['max_depth'])
        self.assertEqual(7, graph['internal_edges'])

    def test_input_permutations_keep_same_ranked_graph_without_mutation(self):
        data = star()
        expected = sitegraph.analyze(**data)
        for seed in range(8):
            shuffled = copy.deepcopy(data)
            rng = random.Random(seed)
            rng.shuffle(shuffled['crawled'])
            rng.shuffle(shuffled['pages_links'][BASE])
            before = copy.deepcopy(shuffled)
            self.assertEqual(expected, sitegraph.analyze(**shuffled))
            self.assertEqual(before, shuffled)

    def test_process_hash_seeds_keep_json_and_markdown_rankings_identical(self):
        program = ('import json, sys; from lib import sitegraph; '
                   'graph = sitegraph.analyze(**json.load(sys.stdin)); '
                   'print(json.dumps({"graph": graph, "markdown": sitegraph.render_markdown(graph)}, sort_keys=True))')
        outputs = []
        for seed in ('0', '1', '2', '42'):
            outputs.append(subprocess.check_output(
                [sys.executable, '-c', program], input=json.dumps(star()), text=True,
                env=dict(os.environ, PYTHONPATH=str(SCRIPTS), PYTHONHASHSEED=seed), timeout=20))
        self.assertEqual(1, len(set(outputs)))

    def test_metrics_and_scoped_top_three_markdown_are_preserved(self):
        graph = sitegraph.analyze(**star())
        self.assertEqual((9, 8, 1), (graph['pages_in_graph'], graph['internal_edges'], graph['max_depth']))
        self.assertEqual([], graph['unreachable_from_start'])
        self.assertEqual([], graph['zero_inbound'])
        self.assertEqual({'checked': True, 'candidates': [BASE + 'orphan'], 'total': 1}, graph['orphans'])
        text = '\n'.join(sitegraph.render_markdown(graph))
        self.assertIn('Most-linked pages:** ' + ', '.join(BASE + letter + ' (1)' for letter in 'abc'), text)
        self.assertIn('9-page crawl sample', text)


if __name__ == '__main__':
    unittest.main()
