"""Malformed local manifests must not stop read-only remediation planning."""

import contextlib
import copy
import io
import json
from pathlib import Path
from types import SimpleNamespace
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
    def test_invalid_utf8_cannot_supply_dependency_evidence_or_wrong_owners(self):
        for raw in (b'{"dependencies":{"next":"\xff"}}',
                    b'{"devDependencies":{"nuxt":"\xc0\xaf"}}',
                    b'{"dependencies":{"next":"latest"},"secret-token":"\xed\xa0\x80"}'):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                package = root / 'package.json'
                package.write_bytes(raw)
                owner = root / 'index.html'
                owner.write_text('<html><head></head><body>Fixture</body></html>', encoding='utf-8')
                source = owner.read_bytes()
                data = copy.deepcopy(REPORT)
                result = plan.build_plan(data, str(root))
                self.assertEqual('plain_html', result['framework']['name'])
                self.assertGreaterEqual(result['framework']['confidence'], 0)
                self.assertLessEqual(result['framework']['confidence'], 1)
                self.assertEqual('index.html', result['actions'][0]['likely_files'][0]['path'])
                self.assertIs(result['actions'][0]['likely_files'][0]['exists'], True)
                self.assertTrue(any('package.json' in item and 'unverified' in item for item in result['warnings']))
                self.assertNotIn('secret-token', json.dumps(result))
                self.assertEqual(raw, package.read_bytes())
                self.assertEqual(source, owner.read_bytes())
                self.assertEqual(REPORT, data)

    def test_invalid_manifest_keeps_config_priority_over_incidental_html(self):
        for config, framework, owner in (
                ('next.config.mjs', 'nextjs', 'app/layout.tsx'),
                ('astro.config.mjs', 'astro', 'src/pages/index.astro'),
                ('nuxt.config.ts', 'nuxt', 'app.vue')):
            with self.subTest(framework=framework), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / 'package.json').write_bytes(b'{"dependencies":{"next":"\xff"}}')
                (root / config).write_text('export default {}', encoding='utf-8')
                source = root / owner
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text('Fixture source', encoding='utf-8')
                for index in range(8):
                    (root / ('index.html' if index == 0 else f'page-{index}.html')).write_text(
                        '<html><head></head><body>Incidental HTML</body></html>', encoding='utf-8')
                saved = {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}
                result = plan.build_plan(REPORT, str(root))
                self.assertEqual(framework, result['framework']['name'])
                self.assertFalse(any('depends on' in item for item in result['framework']['evidence']))
                self.assertTrue(any(item['path'] == owner and item['exists']
                                    for item in result['actions'][0]['likely_files']))
                self.assertGreaterEqual(result['framework']['confidence'], 0)
                self.assertLessEqual(result['framework']['confidence'], 1)
                self.assertTrue(any('package.json' in item for item in result['warnings']))
                self.assertEqual(saved, {path: path.read_bytes() for path in saved})

    def test_invalid_utf8_keeps_independent_config_and_cli_mcp_plans_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / 'package.json'
            raw = b'{"dependencies":{"next":"latest"},"secret-token":"\xff"}'
            package.write_bytes(raw)
            (root / 'astro.config.mjs').write_text('export default {}', encoding='utf-8')
            source = root / 'src/pages/index.astro'
            source.parent.mkdir(parents=True)
            source.write_text('<html><head></head><body>Fixture</body></html>', encoding='utf-8')
            baseline = root / 'before.json'
            baseline.write_text(json.dumps(REPORT), encoding='utf-8')
            saved = {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = plan.main([str(baseline), '--repo', str(root), '--format', 'json'])
            self.assertEqual(0, code)
            with mock.patch.object(Path, 'cwd', return_value=root):
                mcp = mcp_server._plan(REPORT, '.')
            for result in (json.loads(output.getvalue()), mcp):
                self.assertEqual('astro', result['framework']['name'])
                self.assertEqual(['astro.config.* present'], result['framework']['evidence'])
                self.assertTrue(any(owner['path'] == 'src/pages/index.astro' and owner['exists']
                                    for owner in result['actions'][0]['likely_files']))
                self.assertTrue(any('package.json' in item for item in result['warnings']))
                self.assertNotIn('secret-token', json.dumps(result))
            self.assertEqual(saved, {path: path.read_bytes() for path in saved})

    def test_valid_utf8_including_literal_replacement_character_keeps_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for version in ('latest', 'workspace:*', '\ufffd'):
                with self.subTest(version=version):
                    manifest = json.dumps({'dependencies': {'next': version}, 'label': 'Café'}, ensure_ascii=False)
                    result = self.build(root, manifest)
                    self.assertEqual('nextjs', result['framework']['name'])
                    self.assertEqual(['package.json depends on next'], result['framework']['evidence'])
                    self.assertFalse(any('package.json' in item for item in result['warnings']))

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

    def test_opened_manifest_reads_are_bounded_despite_smaller_preflight_size(self):
        case = self
        class Stream(io.BytesIO):
            def fileno(self):
                return descriptor.fileno()
            def read(self, size=-1):
                case.assertGreaterEqual(size, 0)
                case.assertLessEqual(size, 65)
                return super().read(size)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'package.json').write_bytes(b'{}')
            with (root / 'package.json').open('rb') as descriptor, \
                    mock.patch.object(plan, 'MAX_FILE_BYTES', 64), \
                    mock.patch.object(plan, 'open', create=True, return_value=Stream(b'{}' + b' ' * 63)):
                self.assertEqual('', plan._read_small(root, 'package.json'))

    def test_default_budget_rejects_grown_manifest_without_framework_claims(self):
        original_stat = Path.stat
        for size, framework in ((2_000_000, 'nextjs'), (2_000_001, 'unknown')):
            with self.subTest(size=size), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                package = root / 'package.json'
                prefix = '{"dependencies":{"next":"^15"},"secret-token":"not output"}'
                manifest = prefix + ' ' * (size - len(prefix))
                def stale_stat(path, *args, **kwargs):
                    value = original_stat(path, *args, **kwargs)
                    return SimpleNamespace(st_mode=value.st_mode, st_size=0,
                                           st_dev=value.st_dev, st_ino=value.st_ino) if path == package else value
                with mock.patch.object(Path, 'stat', stale_stat):
                    result = self.build(root, manifest)
                self.assertEqual(framework, result['framework']['name'])
                self.assertEqual(size > 2_000_000, any('package.json' in item for item in result['warnings']))
                self.assertNotIn('secret-token', json.dumps(result))

    def test_exact_byte_limit_and_strict_utf8_decoding(self):
        for raw, expected in (('{"label":"é"}'.encode('utf-8'), '{"label":"é"}'), (b'\xff', '')):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                path = root / 'package.json'
                with mock.patch.object(plan, 'MAX_FILE_BYTES', len(raw)):
                    path.write_bytes(raw)
                    self.assertEqual(expected, plan._read_small(root, 'package.json'))
                    path.write_bytes(raw + b' ')
                    self.assertEqual('', plan._read_small(root, 'package.json'))

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
            package = root / 'package.json'
            package.write_text('{"dependencies":{"next":"latest"}}', encoding='utf-8')
            before = package.read_bytes()
            with mock.patch.object(plan, 'open', create=True, side_effect=PermissionError('secret-token')):
                result = plan.build_plan(REPORT, str(root))
            self.assertEqual(before, package.read_bytes())
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
