"""Malformed local manifests must not stop read-only remediation planning."""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mcp_server
import plan


REPORT = {'schema_version': '2.0', 'url': 'https://example.test/', 'findings': [
    {'category': 'technical', 'severity': 'high', 'title': 'Missing title',
     'rule_id': 'technical.missing.title'}]}


class TestManifestEvidence(unittest.TestCase):
    def build(self, root, manifest):
        """Write one controlled manifest; planning itself must leave it intact."""
        package = root / 'package.json'
        package.write_text(manifest, encoding='utf-8')
        before = package.read_bytes()
        result = plan.build_plan(REPORT, str(root))
        self.assertEqual(before, package.read_bytes())
        return result

    def test_non_object_json_keeps_plan_and_independent_config_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'astro.config.mjs').write_text('export default {}', encoding='utf-8')
            for value in (None, [], 'secret-token', 42, False):
                with self.subTest(value_type=type(value).__name__):
                    result = self.build(root, json.dumps(value))
                    self.assertEqual('astro', result['framework']['name'])
                    self.assertEqual(['astro.config.* present'], result['framework']['evidence'])
                    self.assertEqual(1, len(result['actions']))
                    self.assertTrue(any('package.json' in item for item in result['warnings']))
                    self.assertNotIn('secret-token', json.dumps(result))

    def test_malformed_section_does_not_discard_valid_sibling_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for field, sibling in (('dependencies', 'devDependencies'), ('devDependencies', 'dependencies')):
                for value in (None, [], 'next', 5, True):
                    with self.subTest(field=field, value_type=type(value).__name__):
                        result = self.build(root, json.dumps({field: value, sibling: {'next': '^15'}}))
                        self.assertEqual('nextjs', result['framework']['name'])
                        self.assertTrue(any(field in item for item in result['warnings']))

    def test_invalid_version_values_do_not_claim_framework_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for value in (None, {}, [], 7, False, '', '   '):
                with self.subTest(value_type=type(value).__name__, value=value):
                    result = self.build(root, json.dumps({'dependencies': {'next': value}}))
                    self.assertEqual('unknown', result['framework']['name'])
                    self.assertEqual([], result['framework']['evidence'])
                    self.assertTrue(any('dependencies' in item for item in result['warnings']))

    def test_parse_and_read_limits_are_disclosed_without_echoing_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for manifest in ('{"secret-token":', '[' * 2000 + ']' * 2000, '9' * 10000):
                with self.subTest(prefix=manifest[:10]):
                    result = self.build(root, manifest)
                    self.assertEqual('unknown', result['framework']['name'])
                    self.assertTrue(any('package.json' in item for item in result['warnings']))
                    self.assertNotIn('secret-token', json.dumps(result))
            with mock.patch.object(plan, 'MAX_FILE_BYTES', 8):
                result = self.build(root, '{"dependencies":{"next":"^15"}}')
            self.assertEqual('unknown', result['framework']['name'])
            self.assertTrue(any('package.json' in item for item in result['warnings']))

    def test_valid_and_missing_manifests_do_not_add_manifest_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = plan.build_plan(REPORT, tmp)
            self.assertFalse(any('package.json' in item for item in result['warnings']))
            for package, framework in (({}, 'unknown'), ({'dependencies': {'astro': '^5'}}, 'astro'),
                                       ({'devDependencies': {'nuxt': 'latest'}}, 'nuxt')):
                with self.subTest(framework=framework):
                    result = self.build(root, json.dumps(package))
                    self.assertEqual(framework, result['framework']['name'])
                    self.assertFalse(any('package.json' in item for item in result['warnings']))

    def test_mixed_entries_and_unreadable_manifest_keep_precise_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self.build(root, '{"dependencies":{"next":null,"astro":"workspace:*"}}')
            self.assertEqual('astro', result['framework']['name'])
            self.assertEqual(['package.json depends on astro'], result['framework']['evidence'])
            self.assertTrue(any('dependencies' in item for item in result['warnings']))
            self.assertIn('package.json dependencies', plan.render_markdown(result))
            with mock.patch.object(Path, 'read_text', side_effect=PermissionError('secret-token')):
                result = self.build(root, '{"dependencies":{"next":"latest"}}')
            self.assertEqual('unknown', result['framework']['name'])
            self.assertEqual([], result['framework']['evidence'])
            self.assertTrue(any('package.json' in item for item in result['warnings']))
            self.assertNotIn('secret-token', json.dumps(result))

    def test_cli_and_mcp_return_usable_plans_for_a_malformed_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.build(root, 'null')
            report = root / 'report.json'
            report.write_text(json.dumps(REPORT), encoding='utf-8')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = plan.main([str(report), '--repo', tmp, '--format', 'json'])
            self.assertEqual(0, code)
            cli = json.loads(output.getvalue())
            with mock.patch.object(Path, 'cwd', return_value=root):
                mcp = mcp_server._plan(REPORT, '.')
            for result in (cli, mcp):
                self.assertEqual('unknown', result['framework']['name'])
                self.assertEqual(1, len(result['actions']))
                self.assertTrue(any('package.json' in item for item in result['warnings']))


if __name__ == '__main__':
    unittest.main()
