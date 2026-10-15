"""Training choices are not search blocks; robots directives are not live probes."""

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_geo
import plan
from dataclasses import asdict
from lib import http
from lib.report import Report


def check(robots, **kwargs):
    report = Report('https://example.test/private/page', **kwargs)
    audit_geo._ai_crawler_access({'robots_txt': robots}, report)
    return report


def block(agent):
    return 'User-agent: ' + agent + '\nDisallow: /'


class TestAiCrawlerRoles(unittest.TestCase):
    def test_training_and_data_policy_choices_do_not_receive_visibility_penalties(self):
        for agent in ('GPTBot', 'ClaudeBot', 'Google-Extended', 'CCBot'):
            with self.subTest(agent=agent):
                report = check(block(agent))
                self.assertEqual(100, report.score())
                self.assertFalse(any(f.severity != 'good' for f in report.findings))
                self.assertIn(agent, report.to_markdown())
                self.assertIn('Crawler policy notes (not scored)', report.to_markdown())
                self.assertIn(agent, report.to_html())

    def test_nonbinding_user_fetch_directives_are_not_proven_access_blocks(self):
        for agent in ('ChatGPT-User', 'Perplexity-User'):
            with self.subTest(agent=agent):
                report = check(block(agent))
                self.assertEqual(100, report.score())
                self.assertIn('user-triggered', report.to_markdown())
                self.assertIn('not prove', report.to_markdown())

    def test_unverified_or_legacy_roles_do_not_invent_search_impact(self):
        for agent in ('Claude-Web', 'Bytespider'):
            with self.subTest(agent=agent):
                report = check(block(agent))
                self.assertEqual(100, report.score())
                self.assertIn('unverified', report.to_markdown())
                row = next(r for r in report.meta['ai_crawler_access']['agents'] if r['agent'] == agent)
                self.assertEqual('unverified', row['role'])
                self.assertIsNone(row['source'])

    def test_documented_search_and_retrieval_restrictions_remain_high_findings(self):
        for agent in ('OAI-SearchBot', 'Claude-SearchBot', 'Claude-User', 'PerplexityBot', 'Googlebot'):
            with self.subTest(agent=agent):
                report = check(block(agent))
                finding, = report.findings
                self.assertEqual('high', finding.severity)
                self.assertEqual('geo.ai.crawlers.are.blocked.in.robots.txt', finding.rule_id)
                self.assertEqual('site', finding.scope)
                self.assertEqual('robots_txt', plan.classify_artifact(asdict(finding)))
                self.assertIn(agent, finding.evidence)
                self.assertIn('your goals', finding.recommendation)
                self.assertNotIn('GPTBot', finding.recommendation)

    def test_mixed_roles_separate_scored_evidence_and_non_scoring_notes(self):
        report = check(block('GPTBot') + '\n\n' + block('OAI-SearchBot'))
        finding, = report.findings
        self.assertEqual(94, report.score())
        self.assertIn('OAI-SearchBot', finding.evidence)
        self.assertNotIn('GPTBot', finding.evidence)
        self.assertIn('GPTBot', report.to_markdown())

    def test_specific_search_allow_does_not_make_training_blocks_visibility_failures(self):
        agents = ('OAI-SearchBot', 'Claude-SearchBot', 'Claude-User', 'PerplexityBot', 'Googlebot')
        robots = 'User-agent: *\nDisallow: /\n\n' + '\n\n'.join(
            'User-agent: ' + agent + '\nAllow: /' for agent in agents)
        report = check(robots)
        self.assertEqual(100, report.score())
        self.assertTrue(report.meta['ai_crawler_access']['notes'])

    def test_shared_groups_and_equal_length_allow_precedence_are_preserved(self):
        report = check('User-agent: OAI-SearchBot\nUser-agent: Claude-SearchBot\n'
                       'Disallow: /\nAllow: /')
        self.assertEqual(100, report.score())
        self.assertEqual([], report.meta['ai_crawler_access']['notes'])

    def test_receipt_is_dated_sourced_and_root_only_without_network_probes(self):
        with mock.patch.object(http, 'fetch') as fetch:
            report = check(block('GPTBot'))
            fetch.assert_not_called()
        receipt = report.meta['ai_crawler_access']
        self.assertEqual('/', receipt['checked_path'])
        self.assertEqual('robots_txt_only', receipt['basis'])
        self.assertEqual('2026-10-15', receipt['policy_checked'])
        rows = receipt['agents']
        self.assertEqual(13, len(rows))
        self.assertEqual(13, len({r['agent'] for r in rows}))
        for row in rows:
            self.assertIs(type(row['disallowed']), bool)
            if row['role'] != 'unverified':
                self.assertTrue(row['source'].startswith('https://'))

    def test_missing_robots_is_unmeasured_not_an_allow_verdict(self):
        report = check(None)
        self.assertEqual([], report.findings)
        self.assertNotIn('ai_crawler_access', report.meta)
        self.assertNotIn('Crawler policy notes', report.to_html())

    def test_empty_and_path_specific_robots_do_not_certify_whole_site_access(self):
        for robots in ('', 'User-agent: OAI-SearchBot\nDisallow: /private'):
            with self.subTest(robots=robots):
                report = check(robots)
                self.assertEqual(100, report.score())
                self.assertIn('site root', report.findings[0].title)
                self.assertIn('not verified', report.findings[0].detail)

    def test_google_extended_note_distinguishes_gemini_grounding_from_search(self):
        output = check(block('Google-Extended')).to_markdown()
        self.assertIn('Gemini', output)
        self.assertIn('grounding', output)
        self.assertIn('not Google Search or AI Overviews', output)

    def test_rendering_policy_notes_does_not_change_scoring_counts_or_json(self):
        report = check(block('GPTBot'))
        before = report.to_json(), copy.deepcopy(report.counts()), report.score()
        report.to_markdown()
        report.to_html()
        self.assertEqual(before, (report.to_json(), report.counts(), report.score()))
        weighted = check(block('GPTBot'), weights={'good': 3})
        allowed = check('', weights={'good': 3})
        self.assertEqual(allowed.score(), weighted.score())

    def test_legacy_high_title_ignore_still_suppresses_only_the_finding(self):
        report = check(block('OAI-SearchBot'),
                       ignore=lambda cat, title: title == 'AI crawlers are blocked in robots.txt')
        self.assertEqual([], report.findings)
        row = next(r for r in report.meta['ai_crawler_access']['agents'] if r['agent'] == 'OAI-SearchBot')
        self.assertTrue(row['disallowed'])

    def test_missing_or_malformed_note_metadata_does_not_create_policy_claims(self):
        for value in (None, [], '', {}, {'notes': None}, {'notes': [None, 'text', {}]}):
            with self.subTest(value=value):
                report = Report('https://example.test/')
                report.meta['ai_crawler_access'] = value
                self.assertNotIn('Crawler policy notes', report.to_markdown())
                self.assertNotIn('Crawler policy notes', report.to_html())
        for changed in ({'version': True}, {'version': 2}, {'checked_path': '/private'},
                        {'basis': 'unknown'}):
            report = check(block('GPTBot'))
            report.meta['ai_crawler_access'].update(changed)
            self.assertNotIn('Crawler policy notes', report.to_markdown())
            self.assertNotIn('Crawler policy notes', report.to_html())

    def test_html_escapes_note_text_and_never_links_an_unsafe_source(self):
        report = check(block('GPTBot'))
        note = report.meta['ai_crawler_access']['notes'][0]
        note['text'] = '<script>unsafe</script>'
        note['source'] = 'javascript:alert(1)'
        html = report.to_html()
        self.assertIn('&lt;script&gt;unsafe&lt;/script&gt;', html)
        self.assertNotIn('<script>', html)
        self.assertNotIn('href="javascript:', html)
        json.loads(report.to_json())


if __name__ == '__main__':
    unittest.main()
