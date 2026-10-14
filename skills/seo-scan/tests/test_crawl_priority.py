"""The bounded site rollup puts urgency before recurrence, without data loss."""

import json
import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit
import crawl_site
from lib.report import Report


def result(items):
    return {'base': 'https://example.test', 'pages_scanned': 30, 'avg_score': 80,
            'pages': [], 'recurring': Counter(dict(items))}


def rows(data):
    return [line for line in crawl_site.render_markdown(data).splitlines()
            if line.startswith('| ') and 'Severity' not in line and 'Score' not in line]


class TestCrawlPriority(unittest.TestCase):
    def test_rare_critical_is_not_hidden_by_twelve_common_medium_types(self):
        items = [(('content', 'medium', 'Common issue ' + str(i)), 30 - i)
                 for i in range(12)]
        items.append((('technical', 'critical', 'Rare critical issue'), 1))
        data = result(items)
        output = crawl_site.render_markdown(data)
        self.assertIn('Rare critical issue', rows(data)[0])
        self.assertEqual(12, len(rows(data)))
        self.assertIn('1 additional issue type(s) not shown', output)
        self.assertIn('JSON report retains the full rollup', output)

    def test_severity_precedes_frequency_and_frequency_breaks_severity_ties(self):
        data = result([(('content', 'medium', 'Common medium'), 30),
                       (('technical', 'high', 'Rare high'), 1),
                       (('schema', 'critical', 'Critical'), 1),
                       (('geo', 'high', 'Common high'), 20)])
        self.assertEqual(['Critical', 'Common high', 'Rare high', 'Common medium'],
                         [row.split(' | ')[-1].rstrip(' |') for row in rows(data)])

    def test_tied_priorities_are_deterministic_regardless_of_insertion_order(self):
        items = [(('technical', 'high', 'Zulu'), 2),
                 (('technical', 'high', 'Alpha'), 2),
                 (('content', 'high', 'Other'), 2)]
        self.assertEqual(rows(result(items)), rows(result(reversed(items))))

    def test_empty_and_uncapped_rollups_do_not_claim_omissions(self):
        self.assertNotIn('Priority issues', crawl_site.render_markdown(result([])))
        data = result([(('technical', 'high', 'One issue'), 1)])
        self.assertIn('Priority issues', crawl_site.render_markdown(data))
        self.assertNotIn('not shown', crawl_site.render_markdown(data))

    def test_rendering_preserves_full_json_counts_and_frequency_order(self):
        data = result([(('content', 'medium', 'Common'), 30),
                       (('technical', 'critical', 'Rare'), 1)])
        before = crawl_site.render_json(data)
        crawl_site.render_markdown(data)
        self.assertEqual(before, crawl_site.render_json(data))
        payload = json.loads(before)
        self.assertEqual([30, 1], [item['count'] for item in payload['recurring']])
        self.assertEqual([30, 1], list(data['recurring'].values()))

    def test_comprehensive_audit_html_inherits_priority_order(self):
        site = result([(('content', 'medium', 'Frequent medium issue'), 30),
                       (('technical', 'critical', 'Rare critical issue'), 1)])
        data = {'site': site['base'], 'site_result': site,
                'page': Report(site['base']), 'sitemap': {'start': site['base'], 'seeds': []}}
        output = audit.render_html(data)
        self.assertLess(output.index('Rare critical issue'), output.index('Frequent medium issue'))
        self.assertIn('severity first, then frequency', output)


if __name__ == '__main__':
    unittest.main()
