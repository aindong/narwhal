"""Parallel page scans honor delay without holding a lock across the scan."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import crawl_site as crawl
from lib.report import Report

URL = 'https://example.test/'
URLS = [URL, URL + 'two', URL + 'three']


class Clock:
    def __init__(self, overshoot=0, start=0.0):
        self.value = start
        self.sleeps = []
        self.overshoot = overshoot

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.value += seconds + self.overshoot


class TestCrawlPacing(unittest.TestCase):
    def run_crawl(self, concurrency, delay, clock, overlap=False):
        starts = []
        barrier = threading.Barrier(3) if overlap else None
        def scan(url, **kwargs):
            starts.append(clock.monotonic())
            if barrier:
                barrier.wait(timeout=3)  # all scans must enter before any can complete
            return Report(url, fetched_status=200)
        with mock.patch.object(crawl.scanner, 'gather_context', return_value={}), \
                mock.patch.object(crawl, 'discover', return_value=URLS), \
                mock.patch.object(crawl.scanner, 'scan', side_effect=scan), \
                mock.patch.object(crawl, 'time', SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep)):
            result = crawl.crawl(URL, concurrency=concurrency, delay=delay, max_pages=3)
        self.assertEqual(3, result['pages_scanned'])
        return starts

    def test_parallel_starts_are_spaced_and_scans_can_overlap(self):
        clock = Clock()
        starts = self.run_crawl(3, .25, clock, overlap=True)
        self.assertEqual([0, .25, .5], starts)
        self.assertEqual([.25, .25], clock.sleeps)

    def test_first_scan_does_not_depend_on_clock_origin(self):
        clock = Clock(start=-10)
        self.assertEqual([-10, -9.75, -9.5], self.run_crawl(3, .25, clock, overlap=True))
        self.assertEqual([.25, .25], clock.sleeps)

    def test_late_wakeup_does_not_schedule_catchup_burst(self):
        clock = Clock(overshoot=1)
        starts = self.run_crawl(3, .25, clock, overlap=True)
        self.assertEqual([0, 1.25, 2.5], starts)

    def test_zero_delay_keeps_parallel_scans_unpaced(self):
        clock = Clock()
        self.assertEqual([0, 0, 0], self.run_crawl(3, 0, clock, overlap=True))
        self.assertEqual([], clock.sleeps)

    def test_sequential_delay_retains_postscan_pause(self):
        clock = Clock()
        self.assertEqual([0, .25, .5], self.run_crawl(1, .25, clock))
        self.assertEqual([.25, .25, .25], clock.sleeps)

    def test_invalid_delays_fail_before_discovery_or_http(self):
        for delay in (-1, float('nan'), float('inf'), float('-inf'), True, '0.1', None, 10 ** 1000):
            with self.subTest(delay=str(delay)), mock.patch.object(crawl.scanner, 'gather_context') as gather, \
                    mock.patch.object(crawl.http, 'normalize_url', return_value=URL) as normalize:
                with self.assertRaisesRegex(ValueError, 'delay'):
                    crawl.crawl(URL, delay=delay)
                gather.assert_not_called()
                normalize.assert_not_called()

    def test_cli_invalid_delay_is_controlled_and_does_not_start_crawl(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'crawl.json'
            output.write_bytes(b'prior report')
            for delay in ('-1', 'nan', 'inf'):
                out, err = io.StringIO(), io.StringIO()
                with mock.patch.object(crawl, 'crawl') as run, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = crawl.main([URL, '--no-config', '--delay', delay, '-o', str(output)])
                self.assertEqual(2, code)
                self.assertEqual('', out.getvalue())
                self.assertIn('delay', err.getvalue())
                self.assertEqual(b'prior report', output.read_bytes())
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
