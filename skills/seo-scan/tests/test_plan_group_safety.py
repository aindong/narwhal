"""Manual actions must remain outside source-edit coordination groups."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan


def report(*rules):
    return {'schema_version': '2.0', 'url': 'https://example.test/', 'findings': [
        {'rule_id': rule, 'title': rule, 'category': 'technical', 'severity': 'medium'}
        for rule in rules]}


TITLE = 'technical.missing.title'
VIEWPORT = 'technical.missing.viewport'
DESCRIPTION = 'technical.missing.meta.description'


class TestManualGroupBoundary(unittest.TestCase):
    def test_rejected_framework_owners_cannot_reappear_through_grouping(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as outside:
            root = Path(repo)
            (root / 'package.json').write_text('{"dependencies":{"next":"^15"}}', encoding='utf-8')
            sentinel = Path(outside, 'layout.tsx')
            sentinel.write_text('outside source', encoding='utf-8')
            try:
                for name in ('src', 'app', 'pages'):
                    (root / name).symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest('symlinks unavailable')
            result = plan.build_plan(report(TITLE, VIEWPORT), repo)
            self.assertEqual('nextjs', result['framework']['name'])
            self.assertTrue(all(not action['likely_files'] and action['manual_action']
                                for action in result['actions']))
            self.assertEqual([], result['groups'])
            self.assertEqual('outside source', sentinel.read_text(encoding='utf-8'))

    def test_ownerless_actions_remain_manual_without_a_template_fix_group(self):
        with tempfile.TemporaryDirectory() as repo:
            result = plan.build_plan(report(TITLE, VIEWPORT), repo)
        self.assertEqual({TITLE, VIEWPORT}, {action['rule_id'] for action in result['actions']})
        self.assertTrue(all(action['manual_action'] for action in result['actions']))
        self.assertEqual([], result['groups'])
        text = plan.render_markdown(result)
        self.assertIn('Manual / external', text)
        self.assertNotIn('Grouped template fixes', text)
        self.assertIn(TITLE, text)
        self.assertIn(VIEWPORT, text)

    def test_external_hosting_actions_are_not_shared_source_edits(self):
        rules = ('technical.https', 'technical.compression.header')
        with tempfile.TemporaryDirectory() as repo:
            result = plan.build_plan(report(*rules), repo)
        self.assertTrue(all(action['artifact'] == 'server_config' for action in result['actions']))
        self.assertTrue(all(action['safety'] == 'manual_external' for action in result['actions']))
        self.assertEqual(set(rules), {action['rule_id'] for action in result['actions']})
        self.assertEqual([], result['groups'])

    def test_manual_member_cannot_expand_an_otherwise_valid_source_group(self):
        with tempfile.TemporaryDirectory() as known, tempfile.TemporaryDirectory() as unknown:
            Path(known, 'index.html').write_text('source', encoding='utf-8')
            source = plan.build_plan(report(TITLE, DESCRIPTION), known)
            manual = plan.build_plan(report(VIEWPORT), unknown)['actions'][0]
            expected = source['groups']
            self.assertTrue(expected)
            self.assertEqual(expected, plan._groups(source['actions'] + [manual]))

    def test_a_manual_member_cannot_create_a_two_action_source_group(self):
        with tempfile.TemporaryDirectory() as known, tempfile.TemporaryDirectory() as unknown:
            Path(known, 'index.html').write_text('source', encoding='utf-8')
            source = plan.build_plan(report(TITLE), known)
            manual = plan.build_plan(report(VIEWPORT), unknown)['actions'][0]
            self.assertEqual([], plan._groups(source['actions'] + [manual]))


if __name__ == '__main__':
    unittest.main()
