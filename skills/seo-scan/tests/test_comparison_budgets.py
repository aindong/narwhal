"""Comparison/brief budgets are bounded, uniform, and usable for coverage retries."""

import asyncio
import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import brief
import compare
import mcp_server
import scan
from lib import http

URLS = ['https://example.test/owner', 'https://example.test/rival']
DOM = '<title>Guide</title><h1>Guide</h1><p>' + 'word ' * 350 + '</p>'
RAW = '<div>' + ' ' * 100_000 + '</div>' + DOM


@contextlib.contextmanager
def fixture():
    def fetch(url, **kwargs):
        body = DOM if kwargs.get('render') else RAW
        limit = kwargs['max_bytes']
        headers = {'content-type': 'text/html'}
        if len(body.encode()) > limit:
            body = body.encode()[:limit].decode()
            headers['x-narwhal-truncated'] = 'true'
        return http.Response(url, url, 200, headers, body, 1,
                             rendered=bool(kwargs.get('render')))
    with mock.patch.object(scan, 'gather_context', return_value={}), \
            mock.patch.object(http, 'fetch', side_effect=fetch) as calls:
        yield calls


class TestComparisonBudgets(unittest.TestCase):
    def test_compare_sdk_retries_partial_raw_or_baseline_coverage(self):
        for rendered in (False, True):
            with self.subTest(rendered=rendered), fixture() as calls:
                low = compare.run(URLS, render=rendered, max_bytes=64_000)
                self.assertIn('error', low)
                calls.reset_mock()
                recovered = compare.run(URLS, render=rendered, max_bytes=128_000)
                self.assertNotIn('error', recovered)
                self.assertTrue(calls.call_args_list)
                self.assertEqual({128_000}, {c.kwargs['max_bytes'] for c in calls.call_args_list})
                self.assertEqual(rendered, recovered['you']['rendered'])

    def test_brief_sdk_retries_in_all_page_modes(self):
        for own, rivals in ((URLS[0], URLS[1:]), (None, URLS[1:]), (URLS[0], [])):
            with self.subTest(own=own, rivals=rivals), fixture() as calls:
                kwargs = {'your_url': own, 'competitor_urls': rivals,
                          'topic': 'Guide' if own is None else None,
                          'use_gsc': False, 'render': True}
                self.assertIn('error', brief.run(max_bytes=64_000, **kwargs))
                calls.reset_mock()
                self.assertNotIn('error', brief.run(max_bytes=128_000, **kwargs))
                self.assertTrue(calls.call_args_list)
                self.assertEqual({128_000}, {c.kwargs['max_bytes'] for c in calls.call_args_list})

    def test_sdk_budgets_are_clamped_before_page_io(self):
        for requested, expected in ((1, 64_000), (99_000_000, 20_000_000)):
            for run in (lambda: compare.run(URLS, max_bytes=requested),
                        lambda: brief.run(URLS[0], URLS[1:], use_gsc=False, max_bytes=requested)):
                with self.subTest(requested=requested), fixture() as calls:
                    run()
                    self.assertTrue(calls.call_args_list)
                    self.assertEqual({expected}, {c.kwargs['max_bytes'] for c in calls.call_args_list})

    def test_sdk_invalid_budget_is_rejected_before_network_io(self):
        with mock.patch.object(http, 'fetch') as fetch:
            for run in (lambda: compare.run(URLS, max_bytes='not-an-int'),
                        lambda: brief.run(URLS[0], URLS[1:], use_gsc=False, max_bytes='not-an-int')):
                with self.assertRaises(ValueError):
                    run()
            fetch.assert_not_called()

    def test_cli_supports_explicit_budget_and_keeps_default(self):
        for module in (compare, brief):
            for extra, expected in (([], 5_000_000), (['--max-bytes', '6000000'], 6_000_000)):
                with self.subTest(module=module.__name__, extra=extra), \
                        mock.patch.object(module, 'run', return_value={'error': 'test', 'failed': []}) as run, \
                        contextlib.redirect_stdout(io.StringIO()):
                    module.main(URLS + ['--format', 'json'] + extra)
                    self.assertEqual(expected, run.call_args.kwargs['max_bytes'])

    def test_cli_invalid_budget_never_runs_a_scan(self):
        for module in (compare, brief):
            with mock.patch.object(module, 'run') as run, \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                module.main(URLS + ['--max-bytes', 'not-an-int'])
            self.assertEqual(2, raised.exception.code)
            run.assert_not_called()

    def test_mcp_adapters_clamp_and_forward_without_enabling_private_access(self):
        for requested, expected in ((1, 64_000), (6_000_000, 6_000_000), (99_000_000, 20_000_000)):
            for module, call in ((compare, lambda: mcp_server._compare(URLS[0], URLS[1:], max_bytes=requested)),
                                 (brief, lambda: mcp_server._brief(URLS[0], URLS[1:], use_gsc=False,
                                                                  max_bytes=requested))):
                with self.subTest(requested=requested, module=module.__name__), \
                        mock.patch.object(module, 'run', return_value={}) as run:
                    call()
                    self.assertEqual(expected, run.call_args.kwargs['max_bytes'])
                    self.assertNotIn('allow_private', run.call_args.kwargs)

    def test_new_budget_does_not_bypass_default_private_host_rejection(self):
        urls = ['http://127.0.0.1/owner', 'http://127.0.0.1/rival']
        with mock.patch.object(http, '_fetch_requests') as fetch:
            for data in (compare.run(urls, max_bytes=20_000_000),
                         brief.run(urls[0], urls[1:], use_gsc=False, max_bytes=20_000_000),
                         mcp_server._compare(urls[0], urls[1:], max_bytes=20_000_000),
                         mcp_server._brief(urls[0], urls[1:], use_gsc=False, max_bytes=20_000_000)):
                self.assertIn('error', data)
            fetch.assert_not_called()

    def test_registered_mcp_tools_expose_and_accept_the_budget_when_sdk_present(self):
        try:
            server = mcp_server.build_server()
        except ImportError:
            self.skipTest('optional MCP SDK is not installed')

        async def check():
            tools = {tool.name: tool for tool in await server.list_tools()}
            for name, module, arguments in (
                    ('compare_pages', compare, {'your_url': URLS[0], 'competitor_urls': URLS[1:]}),
                    ('content_brief', brief, {'your_url': URLS[0], 'competitor_urls': URLS[1:],
                                             'use_gsc': False})):
                schema = getattr(tools[name], 'inputSchema', None)
                if schema is None:  # MCP SDK 2.x uses Python snake_case names.
                    schema = tools[name].input_schema
                budget = schema['properties']['max_bytes']
                self.assertEqual('integer', budget['type'])
                self.assertEqual(5_000_000, budget['default'])
                with mock.patch.object(module, 'run', return_value={}) as run:
                    await server.call_tool(name, {**arguments, 'max_bytes': 99_000_000})
                    self.assertEqual(20_000_000, run.call_args.kwargs['max_bytes'])
                    self.assertNotIn('allow_private', run.call_args.kwargs)
        asyncio.run(check())


if __name__ == '__main__':
    unittest.main()
