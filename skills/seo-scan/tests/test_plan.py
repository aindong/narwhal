"""Remediation planner contract, framework, security, and CLI tests."""

import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import mcp_server  # noqa: E402
import plan  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "planner"


def load_report():
    return json.loads((FIXTURES / "input-report.fixture.json").read_text(encoding="utf-8"))


class TestFrameworkDetection(unittest.TestCase):
    EXPECTED = {
        "nextjs": "nextjs", "astro": "astro", "nuxt": "nuxt",
        "hugo": "hugo", "jekyll": "jekyll", "plain_html": "plain_html",
    }

    def test_all_documented_framework_fixtures_are_detected(self):
        for fixture, expected in self.EXPECTED.items():
            with self.subTest(fixture=fixture):
                root = (FIXTURES / fixture).resolve()
                inv = plan.inventory(root)
                result = plan.detect_framework(root, inv["files"])
                self.assertEqual(expected, result["name"])
                self.assertGreaterEqual(result["confidence"], 0.7)
                self.assertTrue(result["evidence"])

    def test_route_and_shared_owners_are_real_for_every_framework(self):
        expected_route = {
            "nextjs": "app/guides/widget/page.tsx",
            "astro": "src/pages/guides/widget.astro",
            "nuxt": "pages/guides/widget.vue",
            "hugo": "content/guides/widget.md",
            "jekyll": "guides/widget.md",
            "plain_html": "guides/widget/index.html",
        }
        for fixture, route in expected_route.items():
            with self.subTest(fixture=fixture):
                built = plan.build_plan(load_report(), str(FIXTURES / fixture))
                alt = next(a for a in built["actions"] if a["artifact"] == "image_alt")
                self.assertIn(route, {f["path"] for f in alt["likely_files"] if f["exists"]})
                title = next(a for a in built["actions"] if a["artifact"] == "title")
                self.assertTrue(any(f["exists"] for f in title["likely_files"]))


class TestPlanContract(unittest.TestCase):
    def test_complete_contract_and_named_mapping_coverage(self):
        built = plan.build_plan(load_report(), str(FIXTURES / "nextjs"),
                                report_source="fixture-report.json")
        self.assertEqual("1.0", built["schema_version"])
        self.assertEqual("narwhal_remediation_plan", built["kind"])
        self.assertEqual(9, len(built["actions"]))
        self.assertEqual(1.0, built["coverage"]["mapping_ratio"])
        self.assertTrue(built["groups"])
        self.assertEqual([], built["conflicts"])
        self.assertEqual("fixture-report.json", built["provenance"]["report"])
        required = {"action_id", "rule_id", "likely_files", "proposed_change",
                    "safety", "verification", "requires_deploy", "manual_action",
                    "confidence", "provenance"}
        for action in built["actions"]:
            self.assertTrue(required.issubset(action))

    def test_published_json_schema_matches_contract_version_and_required_fields(self):
        schema_path = SCRIPTS.parent / "references" / "remediation-plan.schema.json"
        schema = json.loads(schema_path.read_text())
        self.assertEqual(plan.PLAN_SCHEMA_VERSION,
                         schema["properties"]["schema_version"]["const"])
        action_required = set(schema["properties"]["actions"]["items"]["required"])
        built = plan.build_plan(load_report(), str(FIXTURES / "nextjs"))
        self.assertTrue(action_required.issubset(built["actions"][0]))

    def test_ecommerce_findings_map_to_product_schema_owner_and_guidance(self):
        report = {"schema_version": "2.0", "url": "https://example.test/guides/widget",
                  "findings": [{"category": "schema", "severity": "high",
                                "title": "Visible and schema price do not match",
                                "rule_id": "schema.ecommerce.price.mismatch"}]}
        built = plan.build_plan(report, str(FIXTURES / "nextjs"))
        action = built["actions"][0]
        self.assertEqual("product_schema", action["artifact"])
        self.assertEqual("review_required", action["safety"])
        self.assertIn("same current product data", action["proposed_change"])
        self.assertIn("app/guides/widget/page.tsx",
                      {f["path"] for f in action["likely_files"] if f["exists"]})

    def test_every_promised_finding_family_has_a_named_mapping(self):
        cases = {
            "technical.missing.title": "title",
            "technical.missing.meta.description": "meta_description",
            "technical.no.canonical.url": "canonical",
            "content.incomplete.open.graph.tags": "open_graph",
            "content.no.twitter.x.card.type": "open_graph",
            "schema.invalid.json.ld": "json_ld",
            "technical.no.robots.txt.found": "robots_txt",
            "technical.no.xml.sitemap.found": "sitemap",
            "geo.no.llms.txt": "llms_txt",
            "technical.no.h1.heading": "headings",
            "technical.images.missing.alt.text": "image_alt",
        }
        for rule_id, expected in cases.items():
            with self.subTest(rule_id=rule_id):
                self.assertEqual(expected, plan.classify_artifact(
                    {"rule_id": rule_id, "title": "", "category": rule_id.split(".")[0]}))

    def test_safety_classes_are_semantically_distinct(self):
        report = load_report()
        report["findings"] += [
            {"category": "technical", "severity": "high", "title": "Page not served over HTTPS",
             "rule_id": "technical.page.not.served.over.https"},
            {"category": "technical", "severity": "high", "title": "No responsive viewport tag",
             "rule_id": "technical.no.responsive.viewport.tag"},
        ]
        built = plan.build_plan(report, str(FIXTURES / "nextjs"))
        safety = {a["rule_id"]: a["safety"] for a in built["actions"]}
        self.assertEqual("manual_external", safety["technical.page.not.served.over.https"])
        self.assertEqual("safely_automatable", safety["technical.no.responsive.viewport.tag"])
        self.assertEqual("review_required", safety["technical.missing.title"])
        self.assertEqual("deploy_verification", safety["technical.no.robots.txt.found"])
        manual = next(a for a in built["actions"]
                      if a["rule_id"] == "technical.page.not.served.over.https")
        self.assertEqual([], manual["likely_files"])
        local = next(a for a in built["actions"]
                     if a["rule_id"] == "technical.missing.title")
        self.assertIn("<local-preview-url>", next(step for step in local["verification"] if step.startswith('narwhal ')))
        deployed = next(a for a in built["actions"]
                        if a["rule_id"] == "technical.no.robots.txt.found")
        self.assertIn("run after deploy", next(step for step in deployed["verification"] if step.startswith('narwhal ')))

    def test_legacy_report_gets_compatible_rule_id_and_warning(self):
        report = {"url": "https://example.test", "score": 80, "findings": [
            {"category": "technical", "severity": "high", "title": "Missing <title>"}]}
        built = plan.build_plan(report, str(FIXTURES / "plain_html"))
        self.assertEqual("technical.missing.title", built["actions"][0]["rule_id"])
        self.assertTrue(any("Legacy report" in warning for warning in built["warnings"]))

    def test_audit_includes_site_recurring_and_sitemap_actions(self):
        page = load_report()
        audit = {
            "schema_version": "2.0", "tool_version": "1.26.0",
            "site": page["url"], "overall_score": 55, "homepage": page,
            "crawl": {"recurring": [
                {"category": "technical", "severity": "high",
                 "title": "Missing meta description", "count": 7},
                {"category": "technical", "severity": "low",
                 "title": "No responsive viewport tag", "count": 3}]},
            "sitemap": {"errors": ["No sitemap found"], "problems": {},
                        "broken_sample": [], "invalid_lastmod": 0},
        }
        built = plan.build_plan(audit, str(FIXTURES / "nextjs"))
        actions = {action["rule_id"]: action for action in built["actions"]}
        self.assertEqual(7, actions["technical.missing.meta.description"]["occurrences"])
        self.assertEqual("site", actions["technical.no.responsive.viewport.tag"]["scope"])
        self.assertEqual("sitemap", actions["technical.sitemap.validation.unverified"]["artifact"])
        self.assertTrue(actions["technical.sitemap.validation.unverified"]["manual_action"])

    def test_deterministic_output(self):
        first = plan.build_plan(load_report(), str(FIXTURES / "astro"))
        second = plan.build_plan(load_report(), str(FIXTURES / "astro"))
        self.assertEqual(first, second)

    def test_duplicate_rule_ids_coalesce_to_one_stable_action(self):
        report = {"url": "https://example.test", "findings": [
            {"category": "technical", "severity": "low", "title": "Missing <title>",
             "rule_id": "technical.missing.title"},
            {"category": "technical", "severity": "high", "title": "Missing <title>",
             "rule_id": "technical.missing.title"}]}
        built = plan.build_plan(report, str(FIXTURES / "plain_html"))
        self.assertEqual(1, len(built["actions"]))
        self.assertEqual("high", built["actions"][0]["severity"])

    def test_action_generation_is_bounded_and_reports_partial_coverage(self):
        findings = [
            {"category": "content", "severity": "low", "title": f"Issue {n}",
             "rule_id": f"content.issue.{n}"}
            for n in range(plan.MAX_FINDINGS + 2)
        ]
        findings[-1]["severity"] = "critical"
        findings[-1]["rule_id"] = "content.zzz.urgent"
        built = plan.build_plan({"url": "https://example.test", "findings": findings},
                                str(FIXTURES / "plain_html"))
        self.assertEqual(plan.MAX_FINDINGS, len(built["actions"]))
        self.assertTrue(built["coverage"]["action_generation_capped"])
        self.assertEqual(plan.MAX_FINDINGS + 2,
                         built["coverage"]["actionable_findings"])
        self.assertEqual("content.zzz.urgent", built["actions"][0]["rule_id"])
        self.assertEqual("critical", built["actions"][0]["severity"])
        self.assertTrue(any("severity-first" in warning for warning in built["warnings"]))

    def test_action_limit_counts_unique_nonpassing_rules_and_only_reports_real_omissions(self):
        for total in (plan.MAX_FINDINGS - 1, plan.MAX_FINDINGS, plan.MAX_FINDINGS + 1):
            with self.subTest(total=total):
                findings = [
                    {'category': 'content', 'severity': 'low', 'title': f'Issue {n}',
                     'rule_id': f'content.limit.{n:04d}'}
                    for n in range(total - 1)]
                findings += [dict(findings[0], count=7),
                             {'category': 'content', 'severity': 'good', 'title': 'Passed check',
                              'rule_id': 'content.limit.passed'},
                             {'category': 'content', 'severity': 'critical', 'title': 'Urgent issue',
                              'rule_id': 'content.zzz.urgent'}]
                report = {'url': 'https://example.test/', 'findings': findings}
                original = copy.deepcopy(report)
                built = plan.build_plan(report, str(FIXTURES / 'plain_html'), report_source='<mcp-object>')
                expected_ids = (['content.zzz.urgent']
                                + [f'content.limit.{n:04d}' for n in range(min(total, plan.MAX_FINDINGS) - 1)])
                self.assertEqual(expected_ids, [a['rule_id'] for a in built['actions']])
                self.assertEqual(total, built['coverage']['actionable_findings'])
                self.assertEqual(min(total, plan.MAX_FINDINGS), built['coverage']['actions_emitted'])
                self.assertIs(total > plan.MAX_FINDINGS, built['coverage']['action_generation_capped'])
                selected = next(a for a in built['actions'] if a['rule_id'] == 'content.limit.0000')
                self.assertEqual(7, selected['occurrences'])
                self.assertEqual(2, selected['observation_selection']['normalized_observations'])
                warnings = [w for w in built['warnings'] if w.startswith('Action generation capped')]
                expected_warning = (f'Action generation capped at {plan.MAX_FINDINGS} of '
                                    f'{total} actionable findings (severity-first).')
                self.assertEqual([expected_warning] if total > plan.MAX_FINDINGS else [], warnings)
                self.assertEqual(total > plan.MAX_FINDINGS,
                                 expected_warning in plan.render_markdown(built))
                self.assertEqual(built, mcp_server._plan(report, 'skills/seo-scan/tests/fixtures/planner/plain_html'))
                self.assertEqual(original, report)

    def test_intent_conflicts_are_emitted(self):
        report = {"url": "https://example.test", "findings": [
            {"category": "technical", "severity": "critical", "title": "Page is set to noindex",
             "rule_id": "technical.page.is.set.to.noindex"},
            {"category": "technical", "severity": "medium", "title": "Page-level nofollow",
             "rule_id": "technical.page.level.nofollow"}]}
        built = plan.build_plan(report, str(FIXTURES / "plain_html"))
        self.assertEqual("conflict:robots_meta", built["conflicts"][0]["conflict_id"])

    def test_markdown_matches_golden(self):
        built = plan.build_plan(load_report(), str(FIXTURES / "nextjs"))
        actual = plan.render_markdown(built)
        expected = (FIXTURES / "golden-nextjs.md").read_text(encoding="utf-8")
        self.assertIn("**Target:** `https://example.test", actual)
        self.assertEqual(expected, actual)


class TestPathSafety(unittest.TestCase):
    def test_url_paths_cannot_emit_traversal_or_windows_source_candidates(self):
        for target in ('https://example.test/a/../../../sibling',
                       'https://example.test/a/../page',
                       'https://example.test/a/..\\outside',
                       'https://example.test/a/C:stream',
                       'https://example.test/..', 'https://example.test/a/.',
                       'https://example.test/a/\tpage'):
            with self.subTest(target=target):
                report = load_report()
                report['url'] = report['final_url'] = target
                built = plan.build_plan(report, str(FIXTURES / 'plain_html'))
                paths = {item['path'] for action in built['actions'] for item in action['likely_files']}
                self.assertTrue(paths)
                self.assertTrue(all('..' not in path.split('/') and '\\' not in path and ':' not in path
                                    for path in paths), paths)
                self.assertTrue(any('source candidates omitted' in warning for warning in built['warnings']))

    def test_convention_candidates_do_not_follow_symlinked_owners(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as outside:
            root = Path(repo).resolve()
            Path(repo, 'package.json').write_text('{"dependencies":{"next":"1"}}', encoding='utf-8')
            try:
                Path(repo, 'public').symlink_to(outside, target_is_directory=True)
                Path(repo, 'app').symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest('symlinks unavailable')
            report = load_report()
            built = plan.build_plan(report, repo)
            paths = {item['path'] for action in built['actions'] for item in action['likely_files']}
            self.assertTrue(all(not path.startswith(('public/', 'app/')) for path in paths), paths)
            for path in paths:
                (root / path).resolve().relative_to(root)
            self.assertTrue(any('source candidates omitted' in warning for warning in built['warnings']))

    def test_file_and_internal_symlinks_are_not_suggested_as_literal_owners(self):
        with tempfile.TemporaryDirectory() as repo:
            root = Path(repo).resolve()
            (root / 'real.html').write_text('real source', encoding='utf-8')
            (root / 'assets').mkdir()
            try:
                (root / 'index.html').symlink_to(root / 'real.html')
                (root / 'public').symlink_to(root / 'assets', target_is_directory=True)
            except OSError:
                self.skipTest('symlinks unavailable')
            warnings = []
            self.assertEqual([], plan.likely_files(root, ['real.html'], 'plain_html', 'title',
                                                  'https://example.test/', warnings))
            self.assertEqual([], plan.likely_files(root, ['real.html'], 'nextjs', 'llms_txt',
                                                  'https://example.test/', warnings))
            self.assertTrue(warnings)

    def test_unparseable_target_retains_safe_shared_candidates_with_warning(self):
        report = load_report()
        report['url'] = report['final_url'] = 'https://[invalid'
        built = plan.build_plan(report, str(FIXTURES / 'plain_html'))
        title = next(action for action in built['actions'] if action['artifact'] == 'title')
        self.assertIn('index.html', {item['path'] for item in title['likely_files']})
        self.assertTrue(any('source candidates omitted' in warning for warning in built['warnings']))

    def test_non_directory_and_uninspectable_components_are_not_source_owners(self):
        with tempfile.TemporaryDirectory() as repo:
            root = Path(repo).resolve()
            (root / 'index.html').write_text('home', encoding='utf-8')
            (root / 'a').write_text('not a directory', encoding='utf-8')
            warnings = []
            owners = plan.likely_files(root, ['index.html', 'a'], 'plain_html', 'title',
                                       'https://example.test/a/page', warnings)
            self.assertEqual(['index.html'], [item['path'] for item in owners])
            self.assertTrue(warnings)
            with mock.patch.object(Path, 'lstat', side_effect=PermissionError('not inspectable')):
                owners = plan.likely_files(root, ['index.html'], 'plain_html', 'title',
                                           'https://example.test/', warnings)
            self.assertEqual([], owners)
            (root / 'index.html').unlink()
            (root / 'index.html').mkdir()
            self.assertEqual([], plan.likely_files(root, [], 'plain_html', 'title',
                                                  'https://example.test/', warnings))

    def test_missing_source_owner_never_authorizes_structural_automation(self):
        with tempfile.TemporaryDirectory() as repo:
            report = {'url': 'https://example.test/', 'findings': [
                {'category': 'technical', 'severity': 'medium', 'title': 'Missing viewport',
                 'rule_id': 'technical.missing.viewport'}]}
            built = plan.build_plan(report, repo)
            action = built['actions'][0]
            self.assertEqual([], action['likely_files'])
            self.assertEqual('manual_external', action['safety'])
            self.assertTrue(action['manual_action'])

    def test_hidden_route_names_are_preserved_in_source_candidates(self):
        with tempfile.TemporaryDirectory() as repo:
            root = Path(repo)
            Path(repo, 'index.html').write_text('home', encoding='utf-8')
            Path(repo, '.well-known').mkdir()
            Path(repo, '.well-known', 'info.html').write_text('info', encoding='utf-8')
            report = load_report()
            report['url'] = report['final_url'] = 'https://example.test/.well-known/info'
            built = plan.build_plan(report, repo)
            title = next(action for action in built['actions'] if action['artifact'] == 'title')
            self.assertIn('.well-known/info.html', {item['path'] for item in title['likely_files'] if item['exists']})

    def test_missing_and_non_directory_repo_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            plan.safe_repo_root(str(FIXTURES / "absent"))
        with self.assertRaisesRegex(ValueError, "not a directory"):
            plan.safe_repo_root(str(FIXTURES / "input-report.fixture.json"))

    def test_inventory_skips_symlink_outside_repo(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as outside:
            Path(outside, "secret.txt").write_text("secret", encoding="utf-8")
            try:
                Path(repo, "escape").symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("symlinks unavailable")
            inv = plan.inventory(Path(repo).resolve())
            self.assertNotIn("escape/secret.txt", inv["files"])

    def test_inventory_cap_is_reported(self):
        with tempfile.TemporaryDirectory() as repo:
            for n in range(3):
                Path(repo, f"{n}.html").write_text("x", encoding="utf-8")
            inv = plan.inventory(Path(repo).resolve(), max_files=2)
            self.assertTrue(inv["capped"])
            self.assertEqual(2, len(inv["files"]))


class TestCliAndMcp(unittest.TestCase):
    def test_cli_json_and_helpful_bad_input(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = plan.main([str(FIXTURES / "input-report.fixture.json"), "--repo",
                            str(FIXTURES / "astro"), "--format", "json"])
        self.assertEqual(0, rc)
        self.assertEqual("astro", json.loads(stdout.getvalue())["framework"]["name"])
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = plan.main([str(FIXTURES / "missing.json")])
        self.assertEqual(2, rc)
        self.assertIn("Report file not found", stderr.getvalue())

    def test_mcp_plan_rejects_absolute_and_parent_paths(self):
        with self.assertRaisesRegex(ValueError, "relative"):
            mcp_server._plan(load_report(), str(FIXTURES.resolve()))
        with self.assertRaisesRegex(ValueError, "escape"):
            mcp_server._plan(load_report(), "../outside")

    def test_mcp_plan_is_bounded_and_read_only(self):
        workspace = FIXTURES.resolve()
        with mock.patch("pathlib.Path.cwd", return_value=workspace):
            result = mcp_server._plan(load_report(), "nextjs", max_files=999999)
        self.assertEqual("nextjs", result["framework"]["name"])
        self.assertLessEqual(result["coverage"]["files_scanned"], plan.MAX_REPO_FILES)
        self.assertEqual("<mcp-object>", result["provenance"]["report"])
        with mock.patch("pathlib.Path.cwd", return_value=workspace / "nextjs"):
            for limit in (0, 1):
                limited = mcp_server._plan(load_report(), max_files=limit)
                self.assertEqual(1, limited["coverage"]["files_scanned"])
                self.assertTrue(limited["coverage"]["file_inventory_capped"])

    def test_mcp_tool_is_registered_and_documented(self):
        tools = {name: fn for fn, name in mcp_server._TOOLS}
        self.assertIn("plan_remediation", tools)
        self.assertIn("never edits", tools["plan_remediation"].__doc__)


if __name__ == "__main__":
    unittest.main()
