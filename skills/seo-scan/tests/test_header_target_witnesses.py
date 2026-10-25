"""Header handoffs retain bounded recorded labels without guessing ownership."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan
from lib import indexing, links
try:
    from .test_crawl_rule_handoff import audit_report, BASE, LEAF, HEADER_RULES
except ImportError:
    from test_crawl_rule_handoff import audit_report, BASE, LEAF, HEADER_RULES

REPO = Path(__file__).parent / 'fixtures/planner/plain_html'
NOINDEX = 'technical.http.robots.noindex'
NOFOLLOW = 'technical.http.robots.nofollow'


def page(url=LEAF, fields=('none',), basis='response_header_fields'):
    receipt, _ = indexing.http_robots(list(fields), basis)
    return {'url': url, 'http_robots': receipt}


def evidence(pages, rule=NOINDEX):
    return plan._header_target_evidence({'pages': pages}, rule)


def rows(text):
    return json.loads(text.split('not re-fetched):\n', 1)[1])


class TestHeaderTargetWitnesses(unittest.TestCase):
    def test_native_audit_and_legacy_titles_keep_leaf_labels_and_manual_ownership(self):
        data = audit_report()
        for legacy in (False, True):
            supplied = copy.deepcopy(data)
            if legacy:
                for item in supplied['crawl']['recurring']:
                    item.pop('rule_id')
            built = plan.build_plan(supplied, str(REPO))
            self.assertEqual(2, len(built['actions']))
            for action in built['actions']:
                self.assertEqual([{'crawl_target_label': LEAF, 'header_basis': 'merged_or_unknown'}],
                                 rows(action['evidence']))
                self.assertEqual('manual_external', action['safety'])
                self.assertEqual('server_config', action['artifact'])
                self.assertEqual([], action['likely_files'])
                self.assertTrue(action['requires_deploy'])
            self.assertEqual([], built['groups'])

    def test_each_directive_matches_only_its_supported_unprefixed_receipts(self):
        pages = [page(BASE + 'index', ('noindex',)), page(BASE + 'follow', ('nofollow',)),
                 page(BASE + 'named', ('googlebot: none',)), page(BASE + 'clear', ('index,follow',))]
        self.assertEqual([BASE + 'index'], [r['crawl_target_label'] for r in rows(evidence(pages))])
        self.assertEqual([BASE + 'follow'], [r['crawl_target_label'] for r in rows(evidence(pages, NOFOLLOW))])
        for basis in ('response_header_fields', 'browser_reported_fields', 'merged_or_unknown'):
            self.assertEqual(basis, rows(evidence([page(basis=basis)]))[0]['header_basis'])

    def test_unsupported_incomplete_and_failed_receipts_cannot_name_targets(self):
        variants = [dict(page(), hard_fail=True), {'url': LEAF}, {'url': LEAF, 'http_robots': []}]
        for key, values in {'version': (None, True, 0, 2), 'basis': ('unknown', None),
                            'notes': (None, 'text'), 'field_count': (None, True, 0, -1, 1.0),
                            'generic': (None, 'noindex', ['noindex', 'unsupported'], [])}.items():
            for value in values:
                item = page(); item['http_robots'][key] = value; variants.append(item)
        for item in variants:
            with self.subTest(item=item):
                self.assertEqual('', evidence([item]))
        self.assertEqual('', evidence([]))
        self.assertEqual('', plan._header_target_evidence({}, NOINDEX))

    def test_bounds_witnesses_but_counts_receipts_including_duplicate_labels(self):
        pages = [page(BASE + str(n)) for n in range(7)] + [page(BASE)] * 2
        text = evidence(pages)
        self.assertIn('first 5 of 9', text)
        self.assertIn('not verified response destinations or distinct pages', text)
        self.assertEqual([BASE + str(n) for n in range(5)], [r['crawl_target_label'] for r in rows(text)])
        self.assertEqual(2, len(rows(evidence([page(), page()]))))

    def test_missing_and_credential_like_labels_are_omitted_without_losing_receipt_count(self):
        secret_labels = ['https://user:secret@example.test/', 'https://user%40secret/',
                         'https://user＠secret/', 'https://user％４０secret/']
        for value in secret_labels:
            with self.subTest(value=value):
                self.assertTrue(links.has_credential_like_marker(value))
                text = evidence([page(value)])
                self.assertNotIn('secret', text)
                self.assertEqual([{'crawl_target_label': None, 'header_basis': 'response_header_fields',
                                   'url_omitted': 'credential_like_marker'}], rows(text))
        for value in (None, '', 1, False, {}):
            with self.subTest(value=value):
                self.assertEqual('unrecorded_or_unsupported', rows(evidence([page(value)]))[0]['url_omitted'])
        self.assertFalse(links.has_credential_like_marker(BASE))
        label = BASE + 'literal`|\\path\nnext'
        self.assertEqual(label, rows(evidence([page(label)]))[0]['crawl_target_label'])
        label = BASE + 'caf\u00e9/\u202e'
        text = evidence([page(label)])
        self.assertTrue(text.isascii())
        self.assertEqual(label, rows(text)[0]['crawl_target_label'])

    def test_homepage_evidence_is_preserved_and_no_labels_are_guessed_from_recurring_counts(self):
        data = audit_report()
        observation = copy.deepcopy(data['crawl']['recurring'][0])
        observation.update(rule_id=NOINDEX, evidence='Original homepage header evidence.')
        data['homepage']['findings'] = [observation]
        built = plan.build_plan(data, str(REPO))
        action = next(a for a in built['actions'] if a['rule_id'] == NOINDEX)
        self.assertTrue(action['evidence'].startswith('Original homepage header evidence.\n\n'))
        data['crawl']['pages'] = []
        for action in plan.build_plan(data, str(REPO))['actions']:
            self.assertNotIn('crawl_target_label', action['evidence'])
        scan = copy.deepcopy(data['homepage'])
        self.assertNotIn('crawl_target_label', plan.build_plan(scan, str(REPO))['actions'][0]['evidence'])

    def test_mcp_planning_is_deterministic_offline_and_read_only(self):
        data = audit_report(); original = copy.deepcopy(data)
        owner = REPO / 'index.html'; before = owner.read_bytes()
        relative_repo = str(REPO.resolve().relative_to(Path.cwd().resolve()))
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            first = mcp_server._plan(data, relative_repo)
            second = mcp_server._plan(data, relative_repo)
        self.assertEqual(first, second)
        self.assertEqual(HEADER_RULES, {a['rule_id'] for a in first['actions']})
        self.assertTrue(all(rows(a['evidence'])[0]['crawl_target_label'] == LEAF for a in first['actions']))
        self.assertEqual(original, data)
        self.assertEqual(before, owner.read_bytes())


if __name__ == '__main__':
    unittest.main()
