"""Audit rollups locate witnessed pages instead of unrelated home fallbacks."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit
import mcp_server
import plan
from lib.report import Report
from test_crawl_rule_handoff import crawl_reports

BASE = 'https://example.test/'
RULE = 'technical.no.h1.heading'


def audit_data(urls):
    home = Report(BASE, final_url=BASE, fetched_status=200)
    pages = [home]
    for url in urls:
        page = Report(url, final_url=url, fetched_status=200)
        page.add('technical', 'high', 'No H1 heading', rule_id=RULE)
        pages.append(page)
    crawled = crawl_reports(pages)
    return json.loads(audit.render_json({'site': BASE, 'page': home, 'site_result': crawled,
                                        'sitemap': {'start': BASE, 'seeds': []}}))


class TestCrawlPageOwners(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.workspace = Path(folder.name).resolve()
        self.repo = self.workspace / 'site'
        for rel in ('index.html', 'pricing/index.html', 'docs/index.html'):
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('Fixture source', encoding='utf-8')
        self.data = audit_data([BASE + 'pricing/', BASE + 'docs/'])

    def action(self, data=None):
        built = plan.build_plan(data or self.data, str(self.repo), report_source='<mcp-object>')
        return next(a for a in built['actions'] if a['rule_id'] == RULE)

    def test_witnessed_inner_pages_displace_unaffected_home_without_mutation_or_network(self):
        original = copy.deepcopy(self.data)
        sources = {str(p.relative_to(self.repo)): p.read_bytes() for p in self.repo.rglob('*.html')}
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            action = self.action()
            with mock.patch.object(Path, 'cwd', return_value=self.workspace):
                received = mcp_server._plan(self.data, 'site')
        self.assertEqual({'docs/index.html', 'pricing/index.html'}, {o['path'] for o in action['likely_files']})
        self.assertTrue(all(o['exists'] for o in action['likely_files']))
        self.assertEqual('review_required', action['safety'])
        self.assertEqual(2, action['occurrences'])
        self.assertIn(BASE + 'pricing/', action['evidence'])
        self.assertIn('not a complete affected-page list', action['evidence'])
        self.assertEqual(action, next(a for a in received['actions'] if a['rule_id'] == RULE))
        self.assertEqual(original, self.data)
        self.assertEqual(sources, {str(p.relative_to(self.repo)): p.read_bytes() for p in self.repo.rglob('*.html')})

    def test_bare_host_context_uses_cli_scheme_without_normalizing_witnesses(self):
        data = copy.deepcopy(self.data)
        data['site'] = 'example.test'
        with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
            self.assertEqual({'docs/index.html', 'pricing/index.html'},
                             {o['path'] for o in self.action(data)['likely_files']})
            row = next(row for row in data['crawl']['recurring'] if row['rule_id'] == RULE)
            row['url_sample']['urls'] = ['example.test/pricing/']
            self.assertEqual([], self.action(data)['likely_files'])
            self.assertEqual({}, plan._rule_page_witnesses(data, 'https://[invalid'))

    def test_home_observations_need_matching_rule_complete_source_and_same_origin(self):
        row = {'rule_id': RULE, 'category': 'technical', 'severity': 'high', 'title': 'No H1 heading'}
        for page, expected in (
            ({'final_url': BASE + 'docs/', 'url': BASE + 'old/', 'findings': [row]}, BASE + 'docs/'),
            ({'url': BASE + 'pricing/', 'findings': [row]}, BASE + 'pricing/'),
            ({'findings': [row]}, BASE),
            ({'url': 'https://foreign.test/', 'findings': [row]}, None),
            ({'url': BASE, 'status': 206, 'findings': [row]}, None),
            ({'url': BASE, 'hard_fail': True, 'findings': [row]}, None),
            ({'url': BASE, 'findings': [dict(row, severity='good')]}, None),
            ({'url': BASE, 'findings': [dict(row, rule_id='technical.other')]}, None),
        ):
            data = {'crawl': {'recurring': [row]}, 'homepage': page}
            with self.subTest(page=page):
                self.assertEqual({RULE: [expected]} if expected else {},
                                 plan._rule_page_witnesses(data, BASE))
        for data in ({}, {'crawl': {}}, {'crawl': {'recurring': [row]}}):
            self.assertEqual({}, plan._rule_page_witnesses(data, BASE))

    def test_legacy_unknown_foreign_and_unlocatable_sources_do_not_guess_home(self):
        for change in ('legacy', 'basis', 'foreign', 'unlocatable', 'ambiguous_root'):
            data = copy.deepcopy(self.data)
            row = next(row for row in data['crawl']['recurring'] if row['rule_id'] == RULE)
            if change == 'legacy':
                row.pop('url_sample')
            elif change == 'basis':
                row['url_sample']['basis'] = 'future'
            elif change == 'foreign':
                row['url_sample']['urls'] = ['https://foreign.test/pricing/']
            elif change == 'unlocatable':
                row['url_sample']['urls'] = [BASE + 'dynamic/']
            else:
                row['url_sample']['urls'] = [BASE + '//']
            with self.subTest(change=change):
                action = self.action(data)
                self.assertEqual([], action['likely_files'])
                self.assertTrue(action['manual_action'])
                self.assertEqual('manual_external', action['safety'])
                self.assertNotIn('automation_eligibility', action)

    def test_sample_cap_preserves_count_without_inventing_unsampled_owners(self):
        urls = [BASE + 'page-{}'.format(i) for i in range(7)]
        for i in range(7):
            (self.repo / 'page-{}.html'.format(i)).write_text('Fixture', encoding='utf-8')
        data = audit_data(urls)
        row = next(row for row in data['crawl']['recurring'] if row['rule_id'] == RULE)
        self.assertTrue(row['url_sample']['truncated'])
        action = self.action(data)
        self.assertEqual(7, action['occurrences'])
        self.assertEqual({'page-{}.html'.format(i) for i in range(5)}, {o['path'] for o in action['likely_files']})
        self.assertIn('not a complete affected-page list', action['evidence'])

    def test_partly_unlocated_witnesses_preserve_known_candidates_and_manual_warning(self):
        (self.repo / 'pricing/index.html').unlink()
        built = plan.build_plan(self.data, str(self.repo))
        action = next(a for a in built['actions'] if a['rule_id'] == RULE)
        self.assertEqual(['docs/index.html'], [o['path'] for o in action['likely_files']])
        self.assertIn(BASE + 'pricing/', action['evidence'])
        self.assertTrue(any('locate it manually' in warning for warning in built['warnings']))

    def test_witness_owner_cap_and_root_content_conventions(self):
        (self.repo / 'index.md').write_text('Home', encoding='utf-8')
        warnings = []
        for target in (BASE, BASE.rstrip('/')):
            with self.subTest(target=target):
                owners = plan._witness_owners(self.repo, ['index.md'], 'jekyll', 'headings', [target], warnings)
                self.assertEqual(['index.md'], [o['path'] for o in owners])
                self.assertEqual([], warnings)
        files, targets = [], []
        for i in range(5):
            targets.append(BASE + 'page-{}/'.format(i))
            for rel in ('page-{}.html'.format(i), 'page-{}/index.html'.format(i)):
                path = self.repo / rel
                path.parent.mkdir(exist_ok=True)
                path.write_text('Page', encoding='utf-8')
                files.append(rel)
        owners = plan._witness_owners(self.repo, files, 'plain_html', 'headings', targets, warnings)
        self.assertEqual(8, len(owners))
        self.assertEqual(8, len({o['path'] for o in owners}))
        self.assertEqual([], warnings)

    def test_shared_candidate_retains_strongest_observation_in_either_url_order(self):
        files = ['src/pages/head.astro', 'src/pages/pricing.astro']
        for rel in files:
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('Fixture source', encoding='utf-8')
        targets = [BASE + 'head/', BASE + 'pricing/']
        snapshots = {rel: (self.repo / rel).read_bytes() for rel in files}
        results = []
        for ordered in (targets, list(reversed(targets))):
            warnings = []
            owners = plan._witness_owners(self.repo, files, 'astro', 'title', ordered, warnings)
            self.assertEqual(set(files), {o['path'] for o in owners})
            head = next(o for o in owners if o['path'] == files[0])
            self.assertEqual(0.9, head['confidence'])
            self.assertIn('route convention', head['reason'])
            self.assertEqual([], warnings)
            results.append(owners)
        self.assertEqual(results[0], results[1])
        self.assertEqual(snapshots, {rel: (self.repo / rel).read_bytes() for rel in files})

    def test_unknown_framework_root_witness_remains_an_ownerless_manual_action(self):
        row = {'rule_id': RULE, 'category': 'technical', 'severity': 'high', 'title': 'No H1 heading'}
        data = {'site': BASE, 'homepage': {'url': BASE, 'findings': [row]},
                'crawl': {'recurring': [dict(row, count=1)]}}
        original = copy.deepcopy(data)
        with tempfile.TemporaryDirectory() as tmp:
            built = plan.build_plan(data, tmp)
        self.assertEqual('unknown', built['framework']['name'])
        action = next(a for a in built['actions'] if a['rule_id'] == RULE)
        self.assertEqual([], action['likely_files'])
        self.assertTrue(action['manual_action'])
        self.assertEqual('manual_external', action['safety'])
        self.assertEqual(original, data)

    def test_symlinked_witness_owner_keeps_known_page_and_unsafe_source_warning(self):
        original = copy.deepcopy(self.data)
        docs = self.repo / 'docs/index.html'
        snapshot = docs.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp) / 'outside.html'
            outside.write_text('Outside source', encoding='utf-8')
            pricing = self.repo / 'pricing/index.html'
            pricing.unlink()
            try:
                pricing.symlink_to(outside)
            except OSError:
                self.skipTest('symlinks unavailable')
            with mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')):
                built = plan.build_plan(self.data, str(self.repo))
            action = next(a for a in built['actions'] if a['rule_id'] == RULE)
            self.assertEqual(['docs/index.html'], [o['path'] for o in action['likely_files']])
            self.assertIn(plan.SOURCE_CANDIDATE_WARNING, built['warnings'])
            self.assertTrue(any('locate it manually' in warning for warning in built['warnings']))
            self.assertEqual('Outside source', outside.read_text(encoding='utf-8'))
        self.assertEqual(snapshot, docs.read_bytes())
        self.assertEqual(original, self.data)

    def test_framework_routes_and_shared_head_priority_are_preserved(self):
        cases = (
            ('next', 'src/app/pricing/page.jsx', 'src/app/docs/page.jsx', 'app/layout.tsx'),
            ('astro', 'src/pages/pricing.mdx', 'src/pages/docs/index.astro', 'src/layouts/Layout.astro'),
            ('nuxt', 'app/pages/pricing.vue', 'app/pages/docs/index.vue', 'nuxt.config.ts'),
        )
        for dependency, pricing, docs, head in cases:
            with self.subTest(framework=dependency), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                (root / 'package.json').write_text(json.dumps({'dependencies': {dependency: '*'}}), encoding='utf-8')
                for rel in (pricing, docs, head):
                    path = root / rel
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text('Fixture', encoding='utf-8')
                built = plan.build_plan(self.data, str(root))
                action = next(a for a in built['actions'] if a['rule_id'] == RULE)
                self.assertEqual({pricing, docs}, {o['path'] for o in action['likely_files']})
                framework = built['framework']['name']
                added_homes = []
                for rel in plan.FRAMEWORK_CANDIDATES[framework]['content']:
                    path = root / rel
                    if path.exists():
                        continue
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text('Healthy home', encoding='utf-8')
                    added_homes.append(path)
                files = [p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()]
                for artifact in ('content', 'image_alt'):
                    owners = plan._witness_owners(root, files, framework, artifact,
                                                  [BASE + 'pricing/', BASE + 'docs/'], [])
                    self.assertEqual({pricing, docs}, {o['path'] for o in owners})
                for path in added_homes:
                    path.unlink()
                metadata = copy.deepcopy(self.data)
                row = next(r for r in metadata['crawl']['recurring'] if r['rule_id'] == RULE)
                row.update(rule_id='technical.missing.title', title='Missing <title>')
                built = plan.build_plan(metadata, str(root))
                action = next(a for a in built['actions'] if a['rule_id'] == 'technical.missing.title')
                self.assertEqual(head, action['likely_files'][0]['path'])
                self.assertTrue({pricing, docs}.issubset({o['path'] for o in action['likely_files']}))

    def test_unlocated_structural_rollup_cannot_use_healthy_home_to_become_eligible(self):
        data = copy.deepcopy(self.data)
        row = next(r for r in data['crawl']['recurring'] if r['rule_id'] == RULE)
        row.update(rule_id='technical.no.responsive.viewport.tag', title='No responsive viewport tag')
        row.pop('url_sample')
        built = plan.build_plan(data, str(self.repo))
        action = next(a for a in built['actions'] if a['artifact'] == 'viewport')
        self.assertEqual([], action['likely_files'])
        self.assertTrue(action['manual_action'])
        self.assertFalse(action['automation_eligibility']['eligible'])
        self.assertIn('no_existing_owner_candidate', action['automation_eligibility']['blockers'])

    def test_partly_unlocated_viewport_withholds_automation_until_all_witnesses_located(self):
        data = copy.deepcopy(self.data)
        row = next(r for r in data['crawl']['recurring'] if r['rule_id'] == RULE)
        row.update(rule_id='technical.no.responsive.viewport.tag', title='No responsive viewport tag')
        (self.repo / 'pricing/index.html').unlink()
        action = next(a for a in plan.build_plan(data, str(self.repo))['actions'] if a['artifact'] == 'viewport')
        self.assertEqual(['docs/index.html'], [o['path'] for o in action['likely_files']])
        self.assertEqual(['unlocated_page_witness'], action['automation_eligibility']['blockers'])
        self.assertFalse(action['automation_eligibility']['eligible'])
        self.assertEqual('review_required', action['safety'])
        (self.repo / 'pricing/index.html').write_text('Located source', encoding='utf-8')
        action = next(a for a in plan.build_plan(data, str(self.repo))['actions'] if a['artifact'] == 'viewport')
        self.assertTrue(action['automation_eligibility']['eligible'])
        self.assertEqual([], action['automation_eligibility']['blockers'])


if __name__ == '__main__':
    unittest.main()
