"""POSIX CLI checks with separate bounded startup and output phases."""
import os
import select
import subprocess
import sys

STARTUP_TIMEOUT = 30
IO_TIMEOUT = 5
CHILD = '''import os, runpy, sys
namespace = runpy.run_path(sys.argv[1], run_name='__fifo_test__')
os.write(int(sys.argv[2]), b'R')
os.close(int(sys.argv[2]))
sys.stdin.readline()
raise SystemExit(namespace['main'](sys.argv[3:]))
'''


def run_cli(path, arguments):
    """Start the I/O deadline after imports, and reap even a blocked writer."""
    ready, signal = os.pipe()
    command = [sys.executable, '-c', CHILD, str(path), str(signal), *map(str, arguments)]
    try:
        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, pass_fds=(signal,)) as process:
            os.close(signal)
            signal = None
            try:
                if not select.select([ready], [], [], STARTUP_TIMEOUT)[0]:
                    raise subprocess.TimeoutExpired(command, STARTUP_TIMEOUT)
                if os.read(ready, 1) != b'R':
                    _, error = process.communicate(timeout=IO_TIMEOUT)
                    raise RuntimeError('CLI startup failed: ' + error)
                output, error = process.communicate('\n', timeout=IO_TIMEOUT)
                return subprocess.CompletedProcess(command, process.returncode, output, error)
            finally:
                if process.poll() is None:
                    process.kill()
    finally:
        os.close(ready)
        if signal is not None:
            os.close(signal)
