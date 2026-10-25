"""Crawl serialization must not replace explicit rule identity with display text."""
import copy
import json
from collections import Counter
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit
import audit_technical
import crawl_site
import mcp_server
import plan
from lib import htmlx, http
from lib.report import Report

BASE = 'https://example.test/'
LEAF = BASE + 'leaf'
REPO = 'skills/seo-scan/tests/fixtures/planner/plain_html'
HEADER_RULES = {'technical.http.robots.noindex', 'technical.http.robots.nofollow'}


def header_page():
    report = Report(LEAF, final_url=LEAF, fetched_status=200)
    response = http.Response(LEAF, LEAF, 200, {'x-robots-tag': 'none'}, '<html></html>', 1)
    audit_technical._http_robots(response, report)
    return report


def crawl_reports(reports):
    with mock.patch.object(crawl_site.scanner, 'gather_context', return_value={}), \
            mock.patch.object(crawl_site, 'discover', return_value=[r.url for r in reports]), \
            mock.patch.object(crawl_site.scanner, 'scan', side_effect=reports), \
            mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
        return crawl_site.crawl(BASE, max_pages=len(reports), concurrency=1, detect_dupes=False)


def audit_report():
    homepage = Report(BASE, final_url=BASE, fetched_status=200)
    site = crawl_reports([homepage, header_page()])
    return json.loads(audit.render_json({'site': BASE, 'page': homepage, 'site_result': site,
                                        'sitemap': {'start': BASE, 'seeds': []}}))


class TestCrawlRuleHandoff(unittest.TestCase):
    def test_leaf_header_native_ids_survive_composite_audit_and_keep_external_ownership(self):
        data = audit_report()
        self.assertEqual(HEADER_RULES, {f['rule_id'] for f in data['crawl']['recurring']})
        self.assertEqual([1, 1], [f['count'] for f in data['crawl']['recurring']])
        built = plan.build_plan(data, REPO)
        self.assertEqual(HEADER_RULES, {a['rule_id'] for a in built['actions']})
        for action in built['actions']:
            self.assertEqual('server_config', action['artifact'])
            self.assertEqual('manual_external', action['safety'])
            self.assertEqual([], action['likely_files'])
            self.assertTrue(action['requires_deploy'])
            self.assertIn('only if confirmed unintended', action['proposed_change'])
            self.assertIn('HTML meta tags does not remove a response header', action['proposed_change'])
        self.assertEqual([], built['groups'])

    def test_same_display_title_does_not_merge_different_recorded_rules(self):
        page = Report(BASE)
        for rule in ('technical.custom.one', 'technical.custom.two'):
            page.add('technical', 'high', 'Same display title', rule_id=rule)
        data = crawl_reports([page])
        self.assertEqual(Counter({('technical', 'high', 'Same display title'): 2}), data['recurring'])
        payload = json.loads(crawl_site.render_json(data))
        self.assertNotIn('recurring_rule_counts', payload)
        self.assertEqual({'technical.custom.one', 'technical.custom.two'}, {r['rule_id'] for r in payload['recurring']})
        self.assertEqual([1, 1], [r['count'] for r in payload['recurring']])

    def test_rendering_is_read_only_and_keeps_legacy_counter_interface(self):
        data = crawl_reports([header_page()]); original = copy.deepcopy(data)
        first = crawl_site.render_json(data)
        self.assertEqual(first, crawl_site.render_json(data))
        self.assertEqual(original, data)
        self.assertTrue(all(len(key) == 3 for key in data['recurring']))
        self.assertEqual(2, sum(data['recurring'].values()))

    def test_stale_or_invalid_identity_counts_cannot_silently_relabel_a_changed_rollup(self):
        data = crawl_reports([header_page()])
        changed = copy.deepcopy(data)
        changed['recurring'][('technical', 'critical', 'Added later')] += 1
        with self.assertRaisesRegex(ValueError, 'disagree'):
            crawl_site.render_json(changed)
        key = next(iter(data['recurring_rule_counts']))
        for count in (0, -1, True):
            changed = copy.deepcopy(data); changed['recurring_rule_counts'][key] = count
            with self.assertRaisesRegex(ValueError, 'positive integers'):
                crawl_site.render_json(changed)

    def test_legacy_counter_rendering_keeps_counts_without_fabricating_ids(self):
        legacy = {'recurring': Counter({('technical', 'high', 'Legacy title'): 3})}
        payload = json.loads(crawl_site.render_json(legacy))
        self.assertEqual([{'category': 'technical', 'severity': 'high', 'title': 'Legacy title', 'count': 3}], payload['recurring'])

    def test_legacy_header_titles_remain_external_while_html_meta_stays_in_source(self):
        data = audit_report()
        for row in data['crawl']['recurring']: row.pop('rule_id')
        built = plan.build_plan(data, REPO)
        self.assertTrue(all(a['artifact'] == 'server_config' and a['manual_action'] for a in built['actions']))
        self.assertTrue(all('only if confirmed unintended' in a['proposed_change'] for a in built['actions']))
        page = Report(BASE)
        audit_technical._robots_directives(htmlx._parse_stdlib('<meta name="robots" content="noindex">', BASE), page)
        html_plan = plan.build_plan(json.loads(page.to_json()), REPO)
        self.assertEqual('robots_meta', html_plan['actions'][0]['artifact'])
        self.assertEqual('review_required', html_plan['actions'][0]['safety'])

    def test_offline_mcp_receives_native_header_ids_without_mutating_audit_or_source(self):
        data = audit_report(); original = copy.deepcopy(data)
        owner = Path(REPO) / 'index.html'; owner_bytes = owner.read_bytes()
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            built = mcp_server._plan(data, REPO)
        self.assertEqual(HEADER_RULES, {a['rule_id'] for a in built['actions']})
        self.assertTrue(all(a['manual_action'] and not a['likely_files'] for a in built['actions']))
        self.assertEqual(original, data)
        self.assertEqual(owner_bytes, owner.read_bytes())


if __name__ == '__main__':
    unittest.main()
