"""Compared pages are not ranking winners, even with own-page GSC data."""

import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import brief
import compare
from lib import htmlx
from lib.report import Report

BASE = 'https://example.test/guide'
RIVAL = 'https://rival.test/guide'
OWN_HTML = '<title>A brief guide</title><h1>Guide</h1><p>A brief guide.</p>'
RIVAL_HTML = ('<title>Widget calibration guide</title><h1>Widget calibration</h1>'
              '<h2>How should widgets be calibrated?</h2>'
              '<h2>Torque tolerances and test methodology</h2>'
              '<p>According to a 2026 study, 45% of widgets drift. Detailed calibration guidance.</p>')


def page(url, body):
    doc = htmlx.parse(body, base_url=url)
    return {'url': url, 'facts': compare.facts(Report(url, fetched_status=200), doc),
            'headings': list(doc.headings), 'text': doc.body_text or ''}


class TestBriefGrounding(unittest.TestCase):
    def data(self, topic=False, gsc=None):
        return brief.synthesize(None if topic else page(BASE, OWN_HTML),
                                [page(RIVAL, RIVAL_HTML)], gsc,
                                topic='Widget calibration' if topic else None)

    def assert_no_winners(self, output):
        self.assertNotIn('pages that win', output)
        self.assertNotIn('winning pages', output)
        self.assertIn('not proof of why anyone ranks', output)

    def test_own_page_headings_and_structure_describe_compared_pages(self):
        output = brief.render_markdown(self.data())
        self.assertIn('## Gaps vs compared pages', output)
        self.assertIn('**Question-shaped H2/H3s:** the compared pages', output)
        self.assert_no_winners(output)

    def test_topic_subtopics_describe_compared_pages_not_ranking_winners(self):
        output = brief.render_markdown(self.data(topic=True))
        self.assertIn('## Subtopics the compared pages cover', output)
        self.assertIn('Structure-only brief', output)
        self.assert_no_winners(output)

    def test_own_query_data_does_not_prove_competitor_rankings(self):
        # Synthetic unit input, not a real Search Console measurement.
        gsc = {'found': True, 'property': 'sc-domain:example.test',
               'window': {'start': '2026-01-01', 'end': '2026-01-28'},
               'striking': [{'page': BASE, 'query': 'how to calibrate widgets',
                             'position': 9.2, 'impressions': 800, 'clicks': 12}]}
        for topic in (False, True):
            with self.subTest(topic=topic):
                output = brief.render_markdown(self.data(topic=topic, gsc=gsc))
                self.assert_no_winners(output)
                self.assertIn('your real Search Console queries', output)

    def test_rendering_does_not_mutate_scores_facts_or_json(self):
        data = self.data()
        before = brief.render_json(data)
        scores = [data['you']['score'], data['competitors'][0]['score']]
        brief.render_markdown(data)
        self.assertEqual(before, brief.render_json(data))
        self.assertEqual(scores, [data['you']['score'], data['competitors'][0]['score']])

    def test_cli_help_does_not_describe_unmeasured_winners(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            brief.main(['--help'])
        self.assertEqual(0, raised.exception.code)
        self.assertIn('compared pages', output.getvalue())
        self.assertNotIn('pages that win', output.getvalue())

    def test_plugin_brief_guidance_does_not_assume_competitor_rankings(self):
        command = (Path(__file__).resolve().parents[3] / 'commands' / 'narwhal.md').read_text()
        section = command.split('## If `$1` is `brief`', 1)[1].split('\n## ', 1)[0]
        self.assertNotIn('pages that currently win', section)
        self.assertNotIn('pages currently win', section)
        self.assertIn('competitor/reference pages', section)
        self.assertIn('Never invent search volumes or rankings', ' '.join(section.split()))


if __name__ == '__main__':
    unittest.main()
