"""Inventoried manifest names must not admit replacement symlinks or files."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan
from test_plan_manifest import REPORT


def link_or_skip(case, link, target):
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        case.skipTest('Symlinks unavailable: ' + type(exc).__name__)


class TestManifestIdentity(unittest.TestCase):
    def test_stale_inventory_cannot_import_framework_from_a_symlink(self):
        for internal in (False, True):
            with self.subTest(internal=internal), tempfile.TemporaryDirectory() as folder:
                base = Path(folder).resolve()
                root = base / 'repo'
                root.mkdir()
                package = root / 'package.json'
                package.write_text('{}', encoding='utf-8')
                outside = (root if internal else base) / 'other.json'
                raw = '{"dependencies":{"next":"latest"},"secret-token":"fixture"}'
                outside.write_text(raw, encoding='utf-8')
                files = plan.inventory(root)['files']
                package.unlink()
                link_or_skip(self, package, outside)
                warnings = []
                with mock.patch.object(Path, 'open', side_effect=AssertionError('Symlink content was opened')):
                    framework = plan.detect_framework(root, files, warnings)
                self.assertEqual('unknown', framework['name'])
                self.assertEqual([], framework['evidence'])
                self.assertTrue(any('package.json' in warning for warning in warnings))
                self.assertNotIn('secret-token', json.dumps(warnings))
                self.assertTrue(package.is_symlink())
                self.assertEqual(raw, outside.read_text(encoding='utf-8'))

    def test_changed_opened_file_is_closed_without_reading_its_bytes(self):
        original_open = Path.open
        for symlink in (False, True):
            with self.subTest(symlink=symlink), tempfile.TemporaryDirectory() as folder:
                base = Path(folder).resolve()
                root = base / 'repo'
                root.mkdir()
                package = root / 'package.json'
                package.write_text('{}', encoding='utf-8')
                (root / 'astro.config.mjs').write_text('export default {}', encoding='utf-8')
                replacement = base / 'other.json'
                raw = '{"dependencies":{"next":"latest"},"secret-token":"fixture"}'
                replacement.write_text(raw, encoding='utf-8')
                files = plan.inventory(root)['files']
                reads, handles = [], []

                class Stream:
                    def __init__(self, handle):
                        self.handle = handle
                    def __enter__(self):
                        return self
                    def __exit__(self, *args):
                        self.handle.close()
                    def fileno(self):
                        return self.handle.fileno()
                    def read(self, size=-1):
                        reads.append(size)
                        return self.handle.read(size)

                def replace_before_open(path, *args, **kwargs):
                    self.assertEqual(package, path)
                    package.rename(root / 'saved-package.json')
                    if symlink:
                        link_or_skip(self, package, replacement)
                    else:
                        with original_open(package, 'wb') as destination:
                            destination.write(raw.encode('utf-8'))
                    handle = original_open(path, *args, **kwargs)
                    handles.append(handle)
                    return Stream(handle)

                warnings = []
                with mock.patch.object(Path, 'open', autospec=True, side_effect=replace_before_open):
                    framework = plan.detect_framework(root, files, warnings)
                self.assertEqual('astro', framework['name'])
                self.assertEqual(['astro.config.* present'], framework['evidence'])
                self.assertTrue(any('package.json' in warning for warning in warnings))
                self.assertEqual([], reads)
                self.assertEqual(1, len(handles))
                self.assertTrue(handles[0].closed)
                self.assertEqual(raw, replacement.read_text(encoding='utf-8'))
                self.assertEqual('{}', (root / 'saved-package.json').read_text(encoding='utf-8'))

    def test_build_keeps_native_html_owner_after_inventory_manifest_swap(self):
        original_inventory = plan.inventory
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder).resolve()
            root = base / 'repo'
            root.mkdir()
            package = root / 'package.json'
            package.write_text('{}', encoding='utf-8')
            (root / 'index.html').write_text('<html><head></head><body>Fixture</body></html>', encoding='utf-8')
            outside = base / 'other.json'
            outside.write_text('{"dependencies":{"next":"latest"}}', encoding='utf-8')
            data = copy.deepcopy(REPORT)
            before = copy.deepcopy(data)

            def inventory_then_swap(*args, **kwargs):
                result = original_inventory(*args, **kwargs)
                package.unlink()
                link_or_skip(self, package, outside)
                return result

            with mock.patch.object(plan, 'inventory', side_effect=inventory_then_swap):
                result = plan.build_plan(data, str(root))
            self.assertEqual('plain_html', result['framework']['name'])
            action = result['actions'][0]
            self.assertTrue(any(owner['path'] == 'index.html' and owner['exists'] for owner in action['likely_files']))
            self.assertEqual('index.html', action['likely_files'][0]['path'])
            self.assertTrue(any('package.json' in warning for warning in result['warnings']))
            self.assertEqual(before, data)
            self.assertTrue(package.is_symlink())


if __name__ == '__main__':
    unittest.main()
