"""Crawl workers must not race the first RDFa module initialization."""

from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from lib import htmlx, rdfa

HTML = '<div vocab="https://schema.org/" typeof="Organization"><span property="name">Fixture</span></div>'
URL = 'https://example.test/'


class TestColdRDFa(unittest.TestCase):
    def test_fresh_helper_load_initializes_module_before_parallel_independent_docs(self):
        code = '''
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
sys.path.insert(0, SCRIPTS)
from lib import htmlx
assert 'lib.rdfa' in sys.modules
assert not any(name in sys.modules for name in ('bs4', 'lxml', 'trafilatura'))
barrier = Barrier(16)
documents = [htmlx._parse_stdlib(HTML, URL) for _ in range(16)]
assert all(doc._rdfa_cache is None for doc in documents)
def collect(index):
    barrier.wait(timeout=5)
    return documents[index].rdfa
with ThreadPoolExecutor(max_workers=16) as executor:
    rows = list(executor.map(collect, range(16)))
assert all(row and row[0]['name'] == 'Fixture' for row in rows), rows
assert all(doc.rdfa is row for doc, row in zip(documents, rows))
print('cold parallel extraction passed')
'''
        code = 'SCRIPTS=' + repr(str(SCRIPTS)) + '\nHTML=' + repr(HTML) + '\nURL=' + repr(URL) + '\n' + code
        for iteration in range(3):
            with self.subTest(fresh_start=iteration):
                result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=15)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual('cold parallel extraction passed', result.stdout.strip())

    def test_extraction_is_still_lazy_cached_and_patchable_per_document(self):
        doc = htmlx._parse_stdlib(HTML, URL)
        with mock.patch.object(rdfa, 'extract', wraps=rdfa.extract) as extract:
            self.assertIsNone(doc._rdfa_cache)
            self.assertEqual(0, extract.call_count)
            rows = doc.rdfa
            self.assertIs(rows, doc.rdfa)
            self.assertEqual([], doc.rdfa_warnings)
            extract.assert_called_once_with(doc.document_html, URL)

    def test_independent_documents_do_not_share_extracted_results(self):
        first, second = [htmlx._parse_stdlib(HTML, URL) for _ in range(2)]
        self.assertEqual(first.rdfa, second.rdfa)
        self.assertIsNot(first.rdfa, second.rdfa)
        self.assertIsNot(first.rdfa_warnings, second.rdfa_warnings)


if __name__ == '__main__':
    unittest.main()
