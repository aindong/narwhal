"""Release version consistency across source, runtime, and plugin manifests."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills/seo-scan/scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import cli  # noqa: E402
from _version import __version__  # noqa: E402
from lib.report import Report, TOOL_VERSION  # noqa: E402

spec = importlib.util.spec_from_file_location("sync_version", ROOT / "scripts/sync_version.py")
sync_version = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_version)


class TestVersionConsistency(unittest.TestCase):
    def test_repository_manifests_match_canonical_version(self):
        self.assertEqual(__version__, sync_version.read_version())
        self.assertEqual([], sync_version.synchronize(check=True))

    def test_loose_cli_and_report_use_the_same_source_version(self):
        self.assertEqual(__version__, cli.__version__)
        self.assertEqual(__version__, TOOL_VERSION)
        self.assertEqual(__version__, json.loads(Report("https://example.test").to_json())["tool_version"])
        result = subprocess.run([sys.executable, str(SCRIPTS / "cli.py"), "--version"],
                                check=True, capture_output=True, text=True)
        self.assertEqual(f"narwhal {__version__}", result.stdout.strip())

    def test_check_detects_drift_without_writing_and_sync_preserves_other_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            version_path = root / sync_version.VERSION_PATH
            version_path.parent.mkdir(parents=True)
            version_path.write_text('__version__ = "9.8.7"\n', encoding="utf-8")
            plugin = root / ".claude-plugin/plugin.json"
            plugin.parent.mkdir()
            plugin.write_text('{"name":"narwhal","version":"0.0.0"}', encoding="utf-8")
            marketplace = root / ".claude-plugin/marketplace.json"
            marketplace.write_text('{"metadata":{"version":"0.0.0","description":"keep"},"plugins":[]}',
                                   encoding="utf-8")
            before = [path.read_bytes() for path in (plugin, marketplace)]
            self.assertEqual(2, len(sync_version.synchronize(root, check=True)))
            self.assertEqual(before, [path.read_bytes() for path in (plugin, marketplace)])
            self.assertEqual(2, len(sync_version.synchronize(root)))
            self.assertEqual({"name": "narwhal", "version": "9.8.7"}, json.loads(plugin.read_text()))
            self.assertEqual("keep", json.loads(marketplace.read_text())["metadata"]["description"])
            self.assertEqual([], sync_version.synchronize(root, check=True))

    def test_invalid_canonical_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / sync_version.VERSION_PATH
            path.parent.mkdir(parents=True)
            path.write_text('__version__ = "release-next"\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "literal X.Y.Z"):
                sync_version.read_version(root)

    def test_malformed_marketplace_cannot_partially_update_plugin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / sync_version.VERSION_PATH
            path.parent.mkdir(parents=True)
            path.write_text('__version__ = "9.8.7"\n', encoding="utf-8")
            plugin = root / ".claude-plugin/plugin.json"
            plugin.parent.mkdir()
            original = '{"name":"narwhal","version":"0.0.0"}'
            plugin.write_text(original, encoding="utf-8")
            (root / ".claude-plugin/marketplace.json").write_text('{broken', encoding="utf-8")
            with self.assertRaises(ValueError):
                sync_version.synchronize(root)
            self.assertEqual(original, plugin.read_text(encoding="utf-8"))
