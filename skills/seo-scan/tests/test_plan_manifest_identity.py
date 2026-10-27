"""Inventoried manifest names must not admit replacement symlinks or files."""
import copy
import builtins
import json
import os
import stat
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan
from _cli_process import run_cli
from test_plan_manifest import REPORT


def link_or_skip(case, link, target):
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        case.skipTest('Symlinks unavailable: ' + type(exc).__name__)


class TestManifestIdentity(unittest.TestCase):
    def test_regular_manifest_read_without_nonblocking_constant(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            package = root / 'package.json'
            source = '{"dependencies":{"next":"latest"},"label":"Café"}'
            raw = source.encode('utf-8')
            package.write_bytes(raw)
            platform = SimpleNamespace(open=os.open, fstat=os.fstat, path=os.path)
            with mock.patch.object(plan, 'os', platform):
                self.assertEqual(source, plan._read_small(root, 'package.json'))
            self.assertEqual(raw, package.read_bytes())

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'POSIX FIFO required')
    def test_opened_fifo_cannot_supply_bytes_even_with_matching_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            package = root / 'package.json'
            os.mkfifo(package)
            writer = os.open(package, os.O_RDWR | os.O_NONBLOCK)
            try:
                payload = b'{"dependencies":{"next":"latest"}}'
                os.write(writer, payload)
                # A path check cannot certify the subsequently opened descriptor.
                with mock.patch.object(plan, '_safe_source_candidate', return_value=True):
                    self.assertEqual('', plan._read_small(root, 'package.json'))
                self.assertEqual(payload, os.read(writer, len(payload)))
            finally:
                os.close(writer)

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'POSIX FIFO required')
    def test_manifest_replaced_with_fifo_after_admission_never_blocks(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder).resolve()
            root = base / 'repo'
            root.mkdir()
            package = root / 'package.json'
            original = b'{"dependencies":{"next":"latest"}}'
            package.write_bytes(original)
            (root / 'astro.config.mjs').write_text('export default {}', encoding='utf-8')
            # Parent control makes the reader observable to mutation test selection.
            self.assertEqual('nextjs', plan.detect_framework(root, plan.inventory(root)['files'])['name'])
            runner = base / 'swap.py'
            runner.write_text('''from pathlib import Path
import json, os, sys
sys.path.insert(0, ''' + repr(str(Path(plan.__file__).parent)) + ''')
import plan
def main(args):
    root = Path(args[0])
    original = plan._safe_source_candidate
    def swap(base, rel):
        admitted = original(base, rel)
        if admitted and rel == 'package.json':
            (root / rel).rename(root / 'saved-package.json')
            os.mkfifo(root / rel)
        return admitted
    plan._safe_source_candidate = swap
    warnings = []
    framework = plan.detect_framework(root, plan.inventory(root)['files'], warnings)
    print(json.dumps({'framework': framework, 'warnings': warnings}))
    return 0
''', encoding='utf-8')
            result = run_cli(runner, [root])
            self.assertEqual(0, result.returncode, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual('astro', data['framework']['name'])
            self.assertTrue(any('package.json' in item for item in data['warnings']))
            self.assertEqual(original, (root / 'saved-package.json').read_bytes())
            self.assertTrue(stat.S_ISFIFO(package.stat().st_mode))

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
                with mock.patch.object(plan, 'open', create=True, side_effect=AssertionError('Symlink content was opened')):
                    framework = plan.detect_framework(root, files, warnings)
                self.assertEqual('unknown', framework['name'])
                self.assertEqual([], framework['evidence'])
                self.assertTrue(any('package.json' in warning for warning in warnings))
                self.assertNotIn('secret-token', json.dumps(warnings))
                self.assertTrue(package.is_symlink())
                self.assertEqual(raw, outside.read_text(encoding='utf-8'))

    def test_opened_identity_controls_reads_without_freezing_in_place_edits(self):
        original_open = builtins.open
        for change in ('replacement', 'symlink', 'in_place'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
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
                    if change != 'in_place':
                        package.rename(root / 'saved-package.json')
                    if change == 'symlink':
                        link_or_skip(self, package, replacement)
                    else:
                        with original_open(package, 'wb') as destination:
                            destination.write(raw.encode('utf-8'))
                    handle = original_open(path, *args, **kwargs)
                    handles.append(handle)
                    return Stream(handle)

                warnings = []
                with mock.patch.object(plan, 'open', create=True, side_effect=replace_before_open):
                    framework = plan.detect_framework(root, files, warnings)
                self.assertEqual('nextjs' if change == 'in_place' else 'astro', framework['name'])
                if change == 'in_place':
                    self.assertIn('package.json depends on next', framework['evidence'])
                    self.assertEqual([], warnings)
                    self.assertTrue(reads)
                    self.assertTrue(all(0 < size <= plan.MAX_FILE_BYTES + 1 for size in reads))
                else:
                    self.assertEqual(['astro.config.* present'], framework['evidence'])
                    self.assertTrue(any('package.json' in warning for warning in warnings))
                    self.assertEqual([], reads)
                    self.assertEqual('{}', (root / 'saved-package.json').read_text(encoding='utf-8'))
                self.assertEqual(1, len(handles))
                self.assertTrue(handles[0].closed)
                self.assertEqual(raw, replacement.read_text(encoding='utf-8'))

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
