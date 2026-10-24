"""Saved remediation plans must preserve the original scan/audit baseline."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan
from lib.report import Report


class TestPlanOutputSafety(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.repo = self.root / 'site'
        self.repo.mkdir()
        self.source = self.repo / 'index.html'
        self.source.write_text('<html></html>', encoding='utf-8')
        report = Report('https://example.test/')
        report.add('technical', 'high', 'Missing title', rule_id='technical.missing.title')
        self.data = json.loads(report.to_json())
        self.baseline = self.root / 'before.json'
        self.baseline.write_text(json.dumps(self.data), encoding='utf-8')
        self.original = self.baseline.read_bytes()

    def invoke(self, output=None, format='json', report=None):
        args = [str(report or self.baseline), '--repo', str(self.repo), '--format', format]
        if output is not None:
            args += ['-o', str(output)]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = plan.main(args)
        return code, out.getvalue(), err.getvalue()

    def assert_intact(self):
        self.assertEqual(self.original, self.baseline.read_bytes())
        self.assertEqual('<html></html>', self.source.read_text(encoding='utf-8'))

    def assert_alias_rejected(self, output, **kwargs):
        code, out, err = self.invoke(output, **kwargs)
        self.assertEqual(2, code)
        self.assertEqual('', out)
        self.assertIn('input snapshot', err)
        self.assert_intact()

    def test_direct_and_relative_baseline_aliases_are_rejected_in_both_formats(self):
        for format in ('json', 'markdown'):
            self.assert_alias_rejected(self.baseline, format=format)
        previous = os.getcwd()
        try:
            os.chdir(self.root)
            self.assert_alias_rejected('before.json')
        finally:
            os.chdir(previous)

    def test_link_aliases_and_linked_input_reports_cannot_replace_the_baseline(self):
        checked = 0
        for kind in ('symlink', 'hardlink'):
            alias = self.root / (kind + '.json')
            try:
                if kind == 'symlink':
                    alias.symlink_to(self.baseline)
                else:
                    os.link(self.baseline, alias)
            except OSError:
                continue
            checked += 1
            self.assert_alias_rejected(alias)
            self.assert_alias_rejected(self.baseline, report=alias)
            self.assertTrue(os.path.samefile(alias, self.baseline))
        if not checked:
            self.skipTest('file links unavailable')

    def test_baseline_identity_is_pinned_before_source_planning(self):
        moved = self.root / 'moved-baseline.json'
        build = plan.build_plan

        def rename_after_read(*args, **kwargs):
            self.baseline.rename(moved)
            self.baseline.write_text('{"findings":[]}', encoding='utf-8')
            return build(*args, **kwargs)

        with mock.patch.object(plan, 'build_plan', side_effect=rename_after_read):
            code, out, err = self.invoke(moved)
        self.assertEqual(2, code)
        self.assertEqual('', out)
        self.assertIn('input snapshot', err)
        self.assertEqual(self.original, moved.read_bytes())

    def test_distinct_outputs_and_stdout_retain_exact_plan_content(self):
        expected = plan.build_plan(self.data, str(self.repo), report_source=str(self.baseline.resolve()))
        for format, render in (('json', plan.render_json), ('markdown', plan.render_markdown)):
            code, out, err = self.invoke(format=format)
            self.assertEqual(0, code)
            self.assertEqual('', err)
            self.assertEqual(render(expected), out)
            output = self.root / ('plan.' + format)
            for prior in (None, 'previous plan' * 1000):
                if prior is not None:
                    output.write_text(prior, encoding='utf-8')
                code, out, err = self.invoke(output, format=format)
                self.assertEqual(0, code)
                self.assertIn('Wrote remediation plan', out)
                self.assertEqual('', err)
                self.assertEqual(render(expected), output.read_text(encoding='utf-8'))
                self.assert_intact()

    def test_home_expansion_is_shared_by_loading_and_verification_provenance(self):
        expand = Path.expanduser

        def controlled_home(path):
            return self.baseline if path == Path('~/controlled-before.json') else expand(path)

        with mock.patch.object(Path, 'expanduser', controlled_home):
            code, out, err = self.invoke(report='~/controlled-before.json')
        self.assertEqual(0, code)
        self.assertEqual('', err)
        result = json.loads(out)
        self.assertEqual(str(self.baseline.resolve()), result['provenance']['report'])
        self.assertEqual(str(self.baseline.resolve()), result['actions'][0]['provenance']['report'])
        self.assertIn(str(self.baseline.resolve()), result['actions'][0]['verification'][-1])
        self.assert_intact()

    def test_encoding_and_write_errors_preserve_the_baseline_and_existing_output(self):
        output = self.root / 'plan.json'
        output.write_bytes(b'previous output')
        self.data['findings'][0]['title'] = '\ud800'
        self.baseline.write_text(json.dumps(self.data), encoding='utf-8')
        before = self.baseline.read_bytes()
        code, out, err = self.invoke(output)
        self.assertEqual(2, code)
        self.assertEqual('', out)
        self.assertIn('UTF-8', err)
        self.assertEqual(b'previous output', output.read_bytes())
        self.assertEqual(before, self.baseline.read_bytes())
        self.baseline.write_bytes(self.original)
        code, out, err = self.invoke(self.root / 'missing' / 'plan.json')
        self.assertEqual(2, code)
        self.assertEqual('', out)
        self.assertIn('output', err)
        self.assertNotIn('UTF-8', err)
        self.assertNotIn('Traceback', err)
        self.assert_intact()

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'named pipes unavailable')
    def test_plan_output_to_a_fifo_is_rejected_without_blocking(self):
        fifo = self.root / 'output-pipe'
        os.mkfifo(fifo)
        for with_reader in (False, True):
            reader = os.open(str(fifo), os.O_RDONLY | os.O_NONBLOCK) if with_reader else None
            try:
                run = subprocess.run([sys.executable, plan.__file__, str(self.baseline), '--repo', str(self.repo),
                                      '--format', 'json', '-o', str(fifo)],
                                     capture_output=True, text=True, timeout=5)
                self.assertEqual(2, run.returncode)
                self.assertEqual('', run.stdout)
                self.assertIn('output', run.stderr)
                self.assert_intact()
                if reader is not None:
                    self.assertEqual(b'', os.read(reader, 100))
            finally:
                if reader is not None:
                    os.close(reader)


if __name__ == '__main__':
    unittest.main()
