"""Slow imports must not relax the FIFO I/O deadline or leave child processes."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import _cli_process


@unittest.skipUnless(os.name == 'posix', 'POSIX readiness pipe')
class TestCliProcess(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.cli = self.root / 'cli.py'
        self.processes = []
        popen = subprocess.Popen

        def spawn(*args, **kwargs):
            process = popen(*args, **kwargs)
            self.processes.append(process)
            return process

        patcher = mock.patch.object(_cli_process.subprocess, 'Popen', side_effect=spawn)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.assert_reaped)

    def assert_reaped(self):
        for process in self.processes:
            self.assertIsNotNone(process.poll(), 'CLI child must be terminated and reaped')

    def write_cli(self, source):
        self.cli.write_text(source + '\nif __name__ == "__main__":\n    raise SystemExit(main(sys.argv[1:]))\n',
                            encoding='utf-8')

    def test_status_output_and_arguments_are_preserved(self):
        self.write_cli('import sys\ndef main(args):\n    print(args[0])\n    print("output rejected", file=sys.stderr)\n    return 2\n')
        result = _cli_process.run_cli(self.cli, ['literal argument'])
        self.assertEqual((2, 'literal argument\n', 'output rejected\n'),
                         (result.returncode, result.stdout, result.stderr))

    def test_slow_startup_does_not_consume_the_io_deadline(self):
        self.write_cli('import sys, time\ntime.sleep(0.7)\ndef main(args):\n    print("output rejected")\n    return 2\n')
        with mock.patch.object(_cli_process, 'IO_TIMEOUT', 0.2):
            with self.assertRaises(subprocess.TimeoutExpired):
                subprocess.run([sys.executable, str(self.cli)], capture_output=True, timeout=0.2)
            result = _cli_process.run_cli(self.cli, [])
        self.assertEqual((2, 'output rejected\n'), (result.returncode, result.stdout))

    def test_import_failure_is_reported_and_reaped(self):
        self.write_cli('raise RuntimeError("startup-fault")\n')
        with self.assertRaisesRegex(RuntimeError, 'startup-fault'):
            _cli_process.run_cli(self.cli, [])

    def test_startup_still_has_a_finite_deadline(self):
        self.write_cli('import time\ntime.sleep(10)\n')
        with mock.patch.object(_cli_process, 'STARTUP_TIMEOUT', 0.2):
            with self.assertRaises(subprocess.TimeoutExpired) as raised:
                _cli_process.run_cli(self.cli, [])
        self.assertEqual(0.2, raised.exception.timeout)

    def test_blocking_fifo_writer_still_exceeds_the_io_deadline(self):
        fifo = self.root / 'output-pipe'
        os.mkfifo(fifo)
        self.write_cli('import os, sys\ndef main(args):\n    os.open(args[0], os.O_WRONLY)\n    return 0\n')
        with mock.patch.object(_cli_process, 'IO_TIMEOUT', 0.2):
            with self.assertRaises(subprocess.TimeoutExpired) as raised:
                _cli_process.run_cli(self.cli, [fifo])
        self.assertEqual(0.2, raised.exception.timeout)
