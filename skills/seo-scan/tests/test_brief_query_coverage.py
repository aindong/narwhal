"""Brief query observations retain the collector's row-limit evidence."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import brief
from test_brief_grounding import page, BASE, OWN_HTML, RIVAL


class TestBriefQueryCoverage(unittest.TestCase):
    def test_consistent_receipts_accept_one_row_limits_and_all_matching_inputs(self):
        for count, limit in ((0, 1), (1, 1), (2, 1), (2, 15)):
            with self.subTest(count=count, limit=limit):
                data = self.data(False, topic=True)
                row = data['gsc']['striking'][0]
                retained = min(count, limit)
                data['gsc']['striking'] = [dict(row) for _ in range(retained)]
                data['gsc']['topic_query_selection'] = {
                    'basis': 'topic_term_overlap', 'input_rows': count, 'matching_rows': count,
                    'retained_rows': retained, 'omitted_rows': count - retained, 'limit': limit}
                self.assertTrue(brief.recorded_topic_selection(data['gsc']))
                self.assertIn(f'{retained} of {count} matching retrieved rows retained',
                              brief.render_markdown(data))

    def test_invalid_selection_receipts_cannot_claim_coverage_or_crash_rendering(self):
        original = self.data(False, topic=True)
        receipt = original['gsc']['topic_query_selection']
        invalid = [None, [], {'basis': 'unsupported'}]
        for key in ('input_rows', 'matching_rows', 'retained_rows', 'omitted_rows', 'limit'):
            for value in (None, True, False, -1, '1', 1.0):
                invalid.append({**receipt, key: value})
            missing = dict(receipt)
            del missing[key]
            invalid.append(missing)
        invalid += [{**receipt, 'input_rows': 0}, {**receipt, 'matching_rows': 0},
                    {**receipt, 'retained_rows': 0}, {**receipt, 'omitted_rows': 1},
                    {**receipt, 'limit': 0},
                    {**receipt, 'input_rows': 2, 'matching_rows': 2, 'omitted_rows': 1}]
        for selection in invalid:
            with self.subTest(selection=selection):
                data = copy.deepcopy(original)
                data['gsc']['topic_query_selection'] = selection
                before = copy.deepcopy(data)
                output = brief.render_markdown(data)
                self.assertNotIn('Topic query selection:', output)
                self.assertIn('omitted matches are unverified', output)
                self.assertEqual(before, data)
        for rows in (None, (), tuple(original['gsc']['striking']), {}, []):
            data = copy.deepcopy(original['gsc'])
            data['striking'] = rows
            self.assertFalse(brief.recorded_topic_selection(data))
        self.assertFalse(brief.recorded_topic_selection({'striking': [], 'topic_query_selection': {
            'basis': 'topic_term_overlap', 'input_rows': 0, 'matching_rows': 0,
            'retained_rows': 0, 'omitted_rows': 0, 'limit': 0}}))

    def test_topic_selection_records_matching_retained_and_omitted_rows(self):
        for count in (0, 14, 15, 16, 20):
            with self.subTest(count=count):
                rows = [{'query': f'widgets guide {i}', 'page': BASE,
                         'position': 9, 'impressions': 120} for i in range(count)]
                measured = {'found': True, 'capped': False,
                            'striking': rows + [{'query': 'bicycle maintenance', 'page': BASE}]}
                data = brief.synthesize(None, [page(RIVAL, OWN_HTML)], measured, topic='widgets')
                self.assertEqual(rows[:15], data['gsc']['striking'])
                self.assertEqual({'basis': 'topic_term_overlap', 'input_rows': count + 1,
                                  'matching_rows': count, 'retained_rows': min(count, 15),
                                  'omitted_rows': max(0, count - 15), 'limit': 15},
                                 data['gsc']['topic_query_selection'])
                self.assertIs(False, data['gsc']['capped'])
                output = brief.render_markdown(data)
                self.assertIn(f'{min(count, 15)} of {count} matching retrieved rows retained', output)
                self.assertIn(f'{max(0, count - 15)} omitted', output)
                self.assertIn('lexical term overlap', output)
                self.assertIn('not verified semantic relevance', output)
                self.assertEqual(rows, brief.topic_queries(measured, 'widgets', top=None))
        self.assertNotIn('topic_query_selection', self.data(False)['gsc'])
        for selection in (None, {'basis': 'unsupported'}):
            data = self.data(False, topic=True)
            data['gsc']['topic_query_selection'] = selection
            self.assertIn('omitted matches are unverified', brief.render_markdown(data))

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
