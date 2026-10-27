"""Saving a diff must preserve the snapshot files it was computed from."""

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diff_scan
from test_diff_scope import FINDING, report
from _cli_process import run_cli


class TestDiffOutputSafety(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.old, self.new = self.root / 'before.json', self.root / 'after.json'
        self.old_data = report(['technical'], findings=[dict(FINDING)], score=94)
        self.new_data = report(['technical'], findings=[], score=100)
        self.old.write_text(json.dumps(self.old_data), encoding='utf-8')
        self.new.write_text(json.dumps(self.new_data), encoding='utf-8')
        self.originals = self.old.read_bytes(), self.new.read_bytes()

    def invoke(self, output, *flags):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = diff_scan.main([str(self.old), str(self.new), '-o', str(output), *flags])
        return code, out.getvalue(), err.getvalue()

    def assert_inputs_intact(self):
        self.assertEqual(self.originals, (self.old.read_bytes(), self.new.read_bytes()))

    def assert_alias_rejected(self, output, *flags):
        code, out, err = self.invoke(output, *flags)
        self.assertEqual(2, code)
        self.assertEqual('', out)
        self.assertIn('input snapshot', err)
        self.assertNotIn('Traceback', err)
        self.assert_inputs_intact()

    def test_direct_and_normalized_aliases_of_either_input_are_rejected(self):
        for path in (self.old, self.new, str(self.root) + '/./before.json'):
            for format in ('json', 'markdown'):
                with self.subTest(path=str(path), format=format):
                    self.old.write_bytes(self.originals[0])
                    self.new.write_bytes(self.originals[1])
                    self.assert_alias_rejected(path, '--format', format)

    def test_symlink_aliases_preserve_both_snapshots_and_the_link(self):
        for index, source in enumerate((self.old, self.new)):
            alias = self.root / ('symlink-' + str(index))
            try:
                alias.symlink_to(source)
            except OSError:
                self.skipTest('symlinks unavailable')
            self.assert_alias_rejected(alias, '--format', 'json', '--fail-on-regression')
            self.assertTrue(alias.is_symlink())

    def test_relative_input_aliases_are_rejected(self):
        previous = os.getcwd()
        try:
            os.chdir(self.root)
            for name in ('before.json', 'after.json'):
                self.assert_alias_rejected(name, '--format', 'json')
        finally:
            os.chdir(previous)

    def test_hardlink_aliases_preserve_both_snapshots(self):
        for index, source in enumerate((self.old, self.new)):
            alias = self.root / ('hardlink-' + str(index))
            try:
                os.link(source, alias)
            except OSError:
                self.skipTest('hardlinks unavailable')
            self.assert_alias_rejected(alias, '--format', 'json')
            self.assertTrue(os.path.samefile(alias, source))

    def test_identity_is_captured_when_inputs_are_read_not_from_later_path_names(self):
        moved = self.root / 'moved-baseline.json'
        compare = diff_scan.diff_reports

        def rename_after_read(old, new):
            self.old.rename(moved)
            self.old.write_text(json.dumps(self.new_data), encoding='utf-8')
            return compare(old, new)

        with mock.patch.object(diff_scan, 'diff_reports', side_effect=rename_after_read):
            code, out, err = self.invoke(moved, '--format', 'json')
        self.assertEqual(2, code)
        self.assertEqual('', out)
        self.assertIn('input snapshot', err)
        self.assertEqual(self.originals[0], moved.read_bytes())
        self.assertEqual(self.originals[1], self.new.read_bytes())

    def test_actual_open_output_identity_is_checked_and_rejected_handle_closes(self):
        open_file = os.open
        opened = []

        def redirect_open(path, flags, mode=0o777):
            descriptor = open_file(str(self.old), flags, mode)
            opened.append(descriptor)
            return descriptor

        with mock.patch.object(diff_scan.os, 'open', side_effect=redirect_open):
            self.assert_alias_rejected(self.root / 'separate.json', '--format', 'json')
        self.assertEqual(1, len(opened))
        with self.assertRaises(OSError):
            os.fstat(opened[0])

    def test_distinct_new_and_existing_outputs_keep_exact_rendering_and_gate_semantics(self):
        for format, render in (('json', diff_scan.render_json), ('markdown', diff_scan.render_markdown)):
            output = self.root / ('diff.' + format)
            expected = render(diff_scan.diff_reports(self.old_data, self.new_data))
            for existing in (False, True):
                if existing:
                    output.write_text('previous diff' * 1000, encoding='utf-8')
                code, out, err = self.invoke(output, '--format', format, '--fail-on-regression')
                self.assertEqual(0, code)
                self.assertIn('Wrote', out)
                self.assertEqual('', err)
                self.assertEqual(expected, output.read_text(encoding='utf-8'))
                self.assert_inputs_intact()

    def test_write_errors_are_controlled_without_mutating_inputs(self):
        code, out, err = self.invoke(self.root / 'missing' / 'diff.json', '--format', 'json')
        self.assertEqual(2, code)
        self.assertEqual('', out)
        self.assertIn('output', err)
        self.assertNotIn('Traceback', err)
        self.assert_inputs_intact()

    def test_stream_write_failure_closes_output_and_leaves_inputs_intact(self):
        fdopen = os.fdopen
        opened = []

        class FailingStream:
            def __init__(self, descriptor, *args, **kwargs):
                opened.append(descriptor)
                self.stream = fdopen(descriptor, *args, **kwargs)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.stream.close()

            def fileno(self):
                return self.stream.fileno()

            def truncate(self, size):
                return self.stream.truncate(size)

            def write(self, value):
                raise OSError('secret-write-token')

        with mock.patch.object(diff_scan.os, 'fdopen', side_effect=FailingStream):
            code, out, err = self.invoke(self.root / 'separate.json', '--format', 'json')
        self.assertEqual(2, code)
        self.assertEqual('', out)
        self.assertNotIn('secret-write-token', err)
        self.assert_inputs_intact()
        self.assertEqual(1, len(opened))
        with self.assertRaises(OSError):
            os.fstat(opened[0])

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'named pipes unavailable')
    def test_named_pipe_outputs_never_block_or_receive_report_bytes(self):
        control = self.root / 'regular-output.json'
        code, _, error = self.invoke(control, '--format', 'json')
        self.assertEqual(0, code, error)
        self.assertEqual(6, json.loads(control.read_text(encoding='utf-8'))['score_delta'])
        fifo = self.root / 'output-pipe'
        os.mkfifo(fifo)
        for with_reader in (False, True):
            reader = os.open(str(fifo), os.O_RDONLY | os.O_NONBLOCK) if with_reader else None
            try:
                run = run_cli(diff_scan.__file__, [self.old, self.new, '-o', fifo, '--format', 'json'])
                self.assertEqual(2, run.returncode)
                self.assertEqual('', run.stdout)
                self.assertIn('output', run.stderr)
                self.assert_inputs_intact()
                if reader is not None:
                    self.assertEqual(b'', os.read(reader, 100))
            finally:
                if reader is not None:
                    os.close(reader)

    def test_successful_saved_diff_keeps_regression_and_incomparability_exit_codes(self):
        output = self.root / 'separate.json'
        self.new.write_text(json.dumps(report(['technical'], findings=[dict(FINDING)], score=80)), encoding='utf-8')
        code, out, _ = self.invoke(output, '--format', 'json', '--fail-on-regression')
        self.assertEqual(1, code)
        self.assertIn('Wrote', out)
        self.assertTrue(json.loads(output.read_text(encoding='utf-8'))['regression'])
        self.new.write_text(json.dumps(report(['schema'], findings=[], score=100)), encoding='utf-8')
        code, out, _ = self.invoke(output, '--format', 'json', '--fail-on-regression')
        self.assertEqual(2, code)
        self.assertIn('Wrote', out)
        self.assertIsNone(json.loads(output.read_text(encoding='utf-8'))['regression'])

    def test_a_distinct_output_symlink_keeps_its_existing_follow_behavior(self):
        target, alias = self.root / 'separate.json', self.root / 'latest.json'
        target.write_text('previous diff', encoding='utf-8')
        try:
            alias.symlink_to(target)
        except OSError:
            self.skipTest('symlinks unavailable')
        code, _, err = self.invoke(alias, '--format', 'json')
        self.assertEqual(0, code)
        self.assertEqual('', err)
        self.assertTrue(alias.is_symlink())
        self.assertEqual(diff_scan.render_json(diff_scan.diff_reports(self.old_data, self.new_data)),
                         target.read_text(encoding='utf-8'))
        self.assert_inputs_intact()

    def test_unencodable_output_is_rejected_before_opening_or_truncation(self):
        self.new_data['findings'] = [dict(FINDING, title='\ud800', rule_id='technical.new.unencodable')]
        self.new.write_text(json.dumps(self.new_data), encoding='utf-8')
        output = self.root / 'diff.json'
        output.write_bytes(b'previous output')
        with mock.patch.object(diff_scan.os, 'open') as open_output:
            code, out, err = self.invoke(output, '--format', 'json')
        self.assertEqual(2, code)
        self.assertEqual('', out)
        self.assertIn('UTF-8', err)
        self.assertEqual(b'previous output', output.read_bytes())
        open_output.assert_not_called()


if __name__ == '__main__':
    unittest.main()
