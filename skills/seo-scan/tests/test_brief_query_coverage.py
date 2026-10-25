"""Brief query observations retain the collector's row-limit evidence."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import brief
from test_brief_grounding import page, BASE, OWN_HTML, RIVAL


class TestBriefQueryCoverage(unittest.TestCase):
    def data(self, capped, *, topic=False, queries=True):
        query = {'query': 'Why do widgets wobble?', 'page': BASE,
                 'position': 9, 'impressions': 120}
        measured = {'found': True, 'property': 'fixture', 'capped': capped,
                    'striking': [query] if queries else []}
        return brief.synthesize(None if topic else page(BASE, OWN_HTML),
                                [page(RIVAL, OWN_HTML)], measured, topic='widgets')

    def test_synthesis_keeps_boolean_or_unknown_row_limit_status(self):
        for topic in (False, True):
            for value in (True, False, None, 'false', 0, 1):
                with self.subTest(topic=topic, value=value):
                    data = self.data(value, topic=topic)
                    self.assertIn('capped', data['gsc'])
                    self.assertIs(value if type(value) is bool else None, data['gsc']['capped'])
                    self.assertEqual('queries+pages', data['grounding'])
                    self.assertEqual(1, len(data['gsc']['striking']))

    def test_capped_and_legacy_briefs_warn_without_inventing_absence(self):
        for topic in (False, True):
            for queries in (False, True):
                data = self.data(True, topic=topic, queries=queries)
                before = copy.deepcopy(data)
                output = brief.render_markdown(data)
                self.assertIn('row limit', output)
                self.assertIn('either query window', output)
                self.assertIn('may be incomplete', output)
                if not queries:
                    self.assertIn('no matching striking-distance queries were observed in the retrieved rows', output)
                    self.assertNotIn('has no striking-distance queries for this page', output)
                self.assertEqual(before, data)
        data = self.data(None)
        del data['gsc']['capped']
        output = brief.render_markdown(data)
        self.assertIn('row-limit status was not recorded', output)
        self.assertTrue(output.startswith('# Content brief'))
        for value in ('false', 0, 1):
            data['gsc']['capped'] = value
            self.assertIn('row-limit status was not recorded', brief.render_markdown(data))
        data['gsc'] = {'found': False, 'note': 'GSC skipped', 'capped': True}
        self.assertNotIn('row limit', brief.render_markdown(data))
        output = brief.render_markdown(self.data(False))
        self.assertNotIn('may be incomplete', output)
        self.assertNotIn('row-limit status was not recorded', output)


if __name__ == '__main__':
    unittest.main()
