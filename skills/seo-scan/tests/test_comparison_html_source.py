"""Comparison provenance follows measured snapshots, not rendering requests."""

import copy
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import brief
import compare
from lib import htmlx
from lib.report import Report
from lib.report import md_to_html

URLS = ['https://example.test/guide', 'https://rival.test/guide']
HTML = '<title>Guide</title><h1>Guide</h1><p>A detailed guide.</p>'


def report(url, rendered):
    result = Report(url, fetched_status=200, rendered=rendered)
    result._doc = htmlx.parse(HTML, base_url=url)
    return result


class TestComparisonHtmlSource(unittest.TestCase):
    def run_tools(self, modes):
        def scan(url, **kwargs):
            return report(url, modes[URLS.index(url)])
        with mock.patch.object(compare.scanner, 'scan', side_effect=scan):
            return (compare.run(URLS, render=True),
                    brief.run(URLS[0], URLS[1:], render=True, use_gsc=False))

    def test_facts_retain_actual_boolean_rendering_mode(self):
        for rendered in (False, True):
            item = report(URLS[0], rendered)
            self.assertIs(rendered, compare.facts(item, item._doc)['rendered'])

    def test_mixed_modes_are_retained_and_labeled_per_page(self):
        comparison, content_brief = self.run_tools([True, False])
        for data, renderer in ((comparison, compare.render_markdown),
                               (content_brief, brief.render_markdown)):
            with self.subTest(renderer=renderer.__module__):
                self.assertIs(True, data['you']['rendered'])
                self.assertIs(False, data['competitors'][0]['rendered'])
                before = copy.deepcopy(data)
                output = renderer(data)
                self.assertIn('JavaScript-rendered DOM', output)
                self.assertIn('Served HTML', output)
                self.assertNotIn("pages' own served HTML", output)
                self.assertNotIn('differences from served HTML', output)
                self.assertEqual(before, data)

    def test_requested_rendering_does_not_relabel_raw_fallback(self):
        for data, renderer in zip(self.run_tools([False, False]),
                                  (compare.render_markdown, brief.render_markdown)):
            output = renderer(data)
            self.assertIn('Served HTML', output)
            self.assertNotIn('JavaScript-rendered DOM', output)

    def test_legacy_missing_and_malformed_mode_are_unknown_not_served(self):
        for value in (None, 'false', 0, 1, [], {}):
            with self.subTest(value=value):
                self.assertEqual('Unknown (not recorded)', compare.html_source({'rendered': value}))
        self.assertEqual('Unknown (not recorded)', compare.html_source({}))
        comparison, content_brief = self.run_tools([True, True])
        for data, renderer in ((comparison, compare.render_markdown),
                               (content_brief, brief.render_markdown)):
            data['you'].pop('rendered')
            self.assertIn('Unknown (not recorded)', renderer(data))

    def test_topic_and_own_page_only_briefs_show_the_available_sources(self):
        for own, rivals in ((None, [URLS[1]]), (URLS[0], [])):
            with mock.patch.object(brief.scanner, 'scan', side_effect=lambda u, **k: report(u, True)):
                data = brief.run(own, rivals, topic='Guide' if own is None else None,
                                 render=True, use_gsc=False)
            output = brief.render_markdown(data)
            self.assertIn('## Page snapshots', output)
            self.assertIn('JavaScript-rendered DOM', output)
            self.assertNotIn('Served HTML', output)

    def test_connected_gsc_wording_does_not_relabel_rendered_snapshots(self):
        _, data = self.run_tools([True, True])
        for striking in ([], [{'query': 'widget guide', 'position': 9,
                               'impressions': 100}]):
            data['gsc'] = {'found': True, 'property': 'sc-domain:example.test',
                           'striking': striking}
            output = brief.render_markdown(data)
            self.assertIn('JavaScript-rendered DOM', output)
            self.assertNotIn('served HTML', output)
            self.assertNotIn("pages' served", output)

    def test_new_snapshot_table_keeps_literal_url_pipes_in_one_cell(self):
        _, data = self.run_tools([True, True])
        data['you']['url'] = 'https://example.test/guide|appendix'
        before = copy.deepcopy(data)
        markdown = brief.render_markdown(data)
        self.assertIn('guide%7Cappendix | JavaScript-rendered DOM |', markdown)
        html = md_to_html(markdown)
        self.assertIn('<td>https://example.test/guide%7Cappendix</td>'
                      '<td>JavaScript-rendered DOM</td>', html)
        self.assertEqual(before, data)


if __name__ == '__main__':
    unittest.main()
