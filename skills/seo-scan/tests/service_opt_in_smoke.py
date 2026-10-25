"""Prove installed service defaults without contacting an account/API endpoint."""
from collections import Counter
import asyncio
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import mock


def main():
    if not sys.flags.isolated:
        with tempfile.TemporaryDirectory(prefix='narwhal service policy-') as folder:
            subprocess.run([sys.executable, '-I', str(Path(__file__).resolve())], cwd=folder, check=True, timeout=30)
        return
    import narwhal
    installed = Path(narwhal.__file__).parent
    sys.path.insert(0, str(installed))
    from narwhal import cli
    audit = cli._load('audit')
    brief = cli._load('brief')
    mcp_server = cli._load('mcp_server')
    import brief as loose_brief
    import compare
    import gsc
    from lib import htmlx
    from lib.report import Report, md_to_html
    assert Path(brief.__file__).parent == installed
    url = 'https://example.test/guide'
    doc = htmlx.parse('<title>Guide</title><h1>Guide</h1><p>Useful guidance.</p>', base_url=url)
    own = {'url': url, 'facts': compare.facts(Report(url, fetched_status=200), doc),
           'headings': list(doc.headings), 'text': doc.body_text or ''}
    sdk_checked = False
    with mock.patch.dict(os.environ, {'GSC_ACCESS_TOKEN': 'fixture-unused'}), \
            mock.patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')), \
            mock.patch('socket.socket.connect', side_effect=AssertionError('No network')), \
            mock.patch.object(brief, '_page', return_value=own), \
            mock.patch.object(loose_brief, '_page', return_value=own):
        for call in (brief.run, loose_brief.run, mcp_server._brief):
            with mock.patch.object(gsc, 'gather', side_effect=AssertionError('Default brief queried account')) as queries:
                assert call(url)['gsc']['found'] is False
                queries.assert_not_called()
            with mock.patch.object(gsc, 'gather', return_value={'found': True, 'striking': []}) as queries:
                assert call(url, use_gsc=True)['gsc']['found'] is True
                queries.assert_called_once()
                assert queries.call_args.args[0] == url
        try:
            server = mcp_server.build_server()
        except ImportError:
            pass
        else:
            async def registered():
                tools = {tool.name: tool for tool in await server.list_tools()}
                tool = tools['content_brief']
                schema = getattr(tool, 'inputSchema', None)
                if schema is None:
                    schema = tool.input_schema
                assert schema['properties']['use_gsc']['default'] is False
                with mock.patch.object(gsc, 'gather', side_effect=AssertionError('Default registered tool queried account')):
                    await server.call_tool('content_brief', {'your_url': url})
                with mock.patch.object(gsc, 'gather', return_value={'found': True, 'striking': []}) as queries:
                    await server.call_tool('content_brief', {'your_url': url, 'use_gsc': True})
                    queries.assert_called_once()
            asyncio.run(registered())
            sdk_checked = True
        for flags, expected in (([], False), (['--gsc'], True), (['--no-gsc'], False)):
            with mock.patch.object(gsc, 'gather', return_value={'found': True, 'striking': []}) as queries, \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                assert cli.main(['brief', url, '--no-config', '--format', 'json', *flags]) == 0
                assert json.loads(output.getvalue())['gsc']['found'] is expected
                assert queries.call_count == int(expected)
        question = 'Why do widgets | tools wobble?'
        measured = {'found': True, 'capped': True, 'striking': [
            {'query': question, 'page': url, 'impressions': 120, 'position': 9}]}
        with mock.patch.object(gsc, 'gather', return_value=measured), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            assert cli.main(['brief', '--topic', 'widgets', url, '--gsc-site', url,
                             '--no-config', '--format', 'json']) == 0
            data = json.loads(output.getvalue())
            assert data['gsc']['capped'] is True
            assert data['gsc']['topic_query_selection']['matching_rows'] == 1
            assert data['gsc']['topic_query_selection']['omitted_rows'] == 0
            corrupt = copy.deepcopy(data)
            corrupt['gsc']['topic_query_selection']['omitted_rows'] = 7
            assert 'omitted matches are unverified' in brief.render_markdown(corrupt)
            assert '<td>' + question + '</td>' in md_to_html(brief.render_markdown(data))
            assert [q['question'] for q in data['questions']] == [question]
            assert [s['type'] for s in data['schema']] == ['FAQPage']
            for call in (brief.run, mcp_server._brief):
                data = call(competitor_urls=[url], topic='widgets', gsc_site=url)
                assert data['gsc']['capped'] is True
                assert [q['question'] for q in data['questions']] == [question]
                assert data['grounding'] == 'queries+pages'
        site = {'base': url, 'pages_scanned': 1, 'pages': [{'url': url}], 'avg_score': 100, 'recurring': Counter()}
        with mock.patch.object(audit.scanner, 'scan', return_value=Report(url)), \
                mock.patch.object(audit.crawl_site, 'crawl', return_value=site), \
                mock.patch.object(audit.validate_sitemap, 'analyze', return_value={'start': url, 'seeds': []}), \
                mock.patch.object(audit, 'gather_vitals', side_effect=AssertionError('Default audit queried vitals')), \
                mock.patch.object(gsc, 'gather', side_effect=AssertionError('Default audit queried account')), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            assert cli.main(['audit', url, '--no-config', '--format', 'json']) == 0
            assert not {'gsc', 'vitals'}.intersection(json.loads(output.getvalue()))
    print('Installed service policy passed: default audit/brief skip services despite credentials; explicit brief API/CLI/MCP-wrapper opt-in retained. Registered SDK checked: {}. Account collectors mocked and sockets blocked; no live-service outcome claimed.'.format(sdk_checked))


if __name__ == '__main__':
    main()
