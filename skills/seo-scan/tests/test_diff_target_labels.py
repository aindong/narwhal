"""Diffs retain both target labels without claiming URL mapping or identity."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diff_scan
import mcp_server


def page(url='https://example.test/'):
    return {'url': url, 'score': 90, 'findings': [],
            'meta': {'scan_scope': {'requested': ['technical'], 'completed': ['technical']}}}


def audit(site):
    return {'site': site, 'overall_score': 90, 'homepage': page(), 'crawl': {}, 'sitemap': {}}


class TestDiffTargetLabels(unittest.TestCase):
    def test_scan_keeps_earlier_final_label_and_allows_intended_local_preview(self):
        before, after = page('https://example.test/requested'), page('http://localhost:3000/preview')
        before['final_url'] = 'https://example.test/final?x=1'
        original = copy.deepcopy((before, after))
        result = diff_scan.diff_reports(before, after)
        self.assertEqual(before['final_url'], result['old_url'])
        self.assertEqual(after['url'], result['url'])
        self.assertEqual('comparable', result['comparison']['status'])
        self.assertEqual(0, result['score_delta'])
        text = diff_scan.render_markdown(result)
        self.assertIn('Target labels differ', text)
        self.assertIn('Local preview mappings are not inferred', text)
        self.assertEqual(original, (before, after))

    def test_audit_and_incomparable_branches_retain_actual_labels(self):
        before, after = audit('https://old.test/'), audit('https://new.test/')
        after['homepage']['meta']['scan_scope']['completed'] = []
        result = diff_scan.diff_reports(before, after)
        self.assertEqual('incomparable', result['comparison']['status'])
        self.assertIsNone(result['regression'])
        self.assertEqual(before['site'], result['old_url'])
        self.assertEqual(after['site'], result['url'])
        self.assertIn('Target labels differ', diff_scan.render_markdown(result))

    def test_equal_labels_and_older_diff_objects_do_not_invent_a_mapping_warning(self):
        result = diff_scan.diff_reports(page(), page())
        self.assertEqual(result['old_url'], result['url'])
        self.assertNotIn('Target labels differ', diff_scan.render_markdown(result))
        result.pop('old_url')
        self.assertNotIn('Target labels differ', diff_scan.render_markdown(result))
        before = page(); before.pop('url')
        self.assertEqual('', diff_scan.diff_reports(before, page())['old_url'])

    def test_literal_target_block_roundtrips_without_closing_fence(self):
        old = 'https://example.test/```\n# instruction\n</pre><script>bad()</script>?q=café'
        result = diff_scan.diff_reports(page(old), page('http://localhost/'))
        text = diff_scan.render_markdown(result)
        block = text.split('```json\n', 1)[1].split('\n```', 1)[0]
        self.assertNotIn('`', block)
        self.assertEqual({'earlier': old, 'later': result['url']}, json.loads(block))
        self.assertEqual(result, json.loads(diff_scan.render_json(result)))

    def test_mcp_returns_identical_labels_offline_without_mutating_input(self):
        before, after = page('https://old.test/'), page('https://new.test/')
        original = copy.deepcopy((before, after))
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            result = mcp_server._diff(json.dumps(before), json.dumps(after))
        self.assertEqual(diff_scan.diff_reports(before, after), result)
        self.assertEqual(before['url'], result['old_url'])
        self.assertEqual(original, (before, after))


if __name__ == '__main__':
    unittest.main()
