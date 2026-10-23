"""Unknown/empty static layouts do not crash read-only remediation planning."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan


class TestPlanStaticFallback(unittest.TestCase):
    def test_empty_static_candidates_do_not_claim_an_existing_owner_or_write_files(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(plan.FRAMEWORK_CANDIDATES, {'unknown': {'static': []}}):
            result = plan.likely_files(Path(root), [], 'unknown', 'llms_txt', 'https://example.test/')
            self.assertEqual(['llms.txt'], [item['path'] for item in result])
            self.assertFalse(result[0]['exists'])
            self.assertLess(result[0]['confidence'], 0.5)
            self.assertFalse(Path(root, 'llms.txt').exists())

    def test_empty_static_candidates_can_find_an_existing_root_resource(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(plan.FRAMEWORK_CANDIDATES, {'unknown': {'static': []}}):
            Path(root, 'llms.txt').write_text('# Existing resource\n', encoding='utf-8')
            result = plan.likely_files(Path(root), ['llms.txt'], 'unknown', 'llms_txt', 'https://example.test/')
        self.assertEqual(['llms.txt'], [item['path'] for item in result])
        self.assertTrue(result[0]['exists'])
        self.assertGreater(result[0]['confidence'], 0.5)


if __name__ == '__main__': unittest.main()
