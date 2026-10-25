"""Configured credentials alone must not enable account-service integrations."""
from collections import Counter
import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit
import brief
import cli
import gsc
import mcp_server
from lib.report import Report
from test_brief_grounding import page, BASE, OWN_HTML, RIVAL, RIVAL_HTML


@contextlib.contextmanager
def services():
    with mock.patch.dict(os.environ, {'GSC_ACCESS_TOKEN': 'fixture-unused', 'CRUX_API_KEY': 'fixture-unused'}), \
            mock.patch.object(gsc, 'gather', return_value={'found': True, 'striking': [], 'property': 'fixture'}) as queries, \
            mock.patch.object(audit, 'gather_vitals', return_value={'field': None, 'lab': None}) as vitals, \
            mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')), \
            mock.patch('socket.socket.connect', side_effect=AssertionError('No network')):
        yield queries, vitals


class TestServiceOptIn(unittest.TestCase):
    def test_registered_mcp_schema_and_dispatch_keep_service_opt_in_when_sdk_present(self):
        try:
            server = mcp_server.build_server()
        except ImportError:
            self.skipTest('optional MCP SDK is not installed')

        async def check():
            tools = {tool.name: tool for tool in await server.list_tools()}
            tool = tools['content_brief']
            schema = getattr(tool, 'inputSchema', None)
            if schema is None:
                schema = tool.input_schema
            self.assertIs(False, schema['properties']['use_gsc']['default'])
            for arguments, expected in (({}, 0), ({'use_gsc': True}, 1)):
                with services() as (queries, _), mock.patch.object(brief, '_page', return_value=page(BASE, OWN_HTML)):
                    await server.call_tool('content_brief', {'your_url': BASE, **arguments})
                    self.assertEqual(expected, queries.call_count)
        asyncio.run(check())

    def test_brief_python_and_mcp_default_skip_gsc_despite_credentials(self):
        for call in (brief.run, mcp_server._brief):
            with services() as (queries, vitals), mock.patch.object(brief, '_page', return_value=page(BASE, OWN_HTML)):
                data = call(BASE)
                self.assertFalse(data['gsc']['found'])
                queries.assert_not_called()
                vitals.assert_not_called()

    def test_brief_python_and_mcp_explicit_opt_in_queries_only_own_page(self):
        for call in (brief.run, mcp_server._brief):
            with services() as (queries, vitals), mock.patch.object(brief, '_page', side_effect=[
                    page(BASE, OWN_HTML), page(RIVAL, RIVAL_HTML)]) as fetch:
                data = call(BASE, [RIVAL], use_gsc=True, topic='Explicit focus')
                self.assertTrue(data['gsc']['found'])
                self.assertEqual('Explicit focus', data['topic'])
                self.assertEqual(RIVAL, data['competitors'][0]['url'])
                self.assertEqual([BASE, RIVAL], [c.args[0] for c in fetch.call_args_list])
                queries.assert_called_once()
                self.assertEqual(BASE, queries.call_args.args[0])
                self.assertEqual(28, queries.call_args.kwargs['days'])
                self.assertEqual(50, queries.call_args.kwargs['min_impressions'])
                vitals.assert_not_called()

    def test_brief_cli_default_opt_in_and_legacy_opt_out(self):
        for flags, expected in (([], False), (['--gsc'], True), (['--no-gsc'], False),
                                (['--gsc', '--days', '7', '--min-impressions', '5'], True)):
            with self.subTest(flags=flags), services() as (queries, _), \
                    mock.patch.object(brief, '_page', return_value=page(BASE, OWN_HTML)), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                code = cli.main(['brief', BASE, '--no-config', '--format', 'json', *flags])
                self.assertEqual(0, code)
                self.assertEqual(expected, json.loads(output.getvalue())['gsc']['found'])
                self.assertEqual(int(expected), queries.call_count)
                if expected:
                    self.assertEqual(7 if '--days' in flags else 28, queries.call_args.kwargs['days'])
                    self.assertEqual(5 if '--min-impressions' in flags else 50,
                                     queries.call_args.kwargs['min_impressions'])

    def test_explicit_topic_site_remains_opt_in_and_no_gsc_disables_it(self):
        for flags, expected in (([], True), (['--no-gsc'], False)):
            with services() as (queries, _), mock.patch.object(brief, '_page', return_value=page(RIVAL, RIVAL_HTML)), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(0, brief.main(['--topic', 'widgets', RIVAL, '--gsc-site', BASE,
                                               '--days', '7', '--min-impressions', '5',
                                               '--no-config', '--format', 'json', *flags]))
                self.assertEqual(int(expected), queries.call_count)
                self.assertEqual('widgets', json.loads(output.getvalue())['topic'])
                if expected:
                    self.assertEqual(BASE, queries.call_args.args[0])
                    self.assertEqual(7, queries.call_args.kwargs['days'])
                    self.assertEqual(5, queries.call_args.kwargs['min_impressions'])

    def test_failed_page_grounding_prevents_even_opted_in_account_calls(self):
        for arguments in ([BASE, '--gsc'], ['--topic', 'widgets', RIVAL, '--gsc-site', BASE]):
            with services() as (queries, _), mock.patch.object(brief, '_page', side_effect=ValueError('fixture unavailable')), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(2, cli.main(['brief', *arguments, '--no-config', '--format', 'json']))
                self.assertIn('error', json.loads(output.getvalue()))
                queries.assert_not_called()

    def test_conflicting_brief_flags_fail_before_page_or_account_calls(self):
        with services() as (queries, _), mock.patch.object(brief, '_page') as fetch, \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                brief.main([BASE, '--no-config', '--gsc', '--no-gsc'])
            self.assertEqual(2, error.exception.code)
            fetch.assert_not_called()
            queries.assert_not_called()

    def test_audit_default_and_each_explicit_service_flag_are_independent(self):
        site = {'base': BASE, 'pages_scanned': 1, 'pages': [{'url': BASE}],
                'avg_score': 100, 'recurring': Counter()}
        for flags, expected in (([], (False, False)), (['--gsc'], (True, False)),
                                (['--vitals'], (False, True)), (['--gsc', '--vitals'], (True, True))):
            with self.subTest(flags=flags), services() as (queries, vitals), \
                    mock.patch.object(audit.scanner, 'scan', return_value=Report(BASE)), \
                    mock.patch.object(audit.crawl_site, 'crawl', return_value=site), \
                    mock.patch.object(audit.validate_sitemap, 'analyze', return_value={'start': BASE, 'seeds': []}), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(0, cli.main(['audit', BASE, '--no-config', '--format', 'json', *flags]))
                payload = json.loads(output.getvalue())
                self.assertEqual(expected, (queries.called, vitals.called))
                self.assertEqual(expected, ('gsc' in payload, 'vitals' in payload))


if __name__ == '__main__':
    unittest.main()
