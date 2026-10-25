"""Installed-CLI action cycle on a disposable local site; not an offline unit test.

Run after installing the wheel: python skills/seo-scan/tests/action_cycle_smoke.py
Add --mcp with an MCP SDK installed to verify planning/diffs over real stdio.
The planner stays read-only. This fixture explicitly applies one inspected edit.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import asyncio
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import threading

RULE = 'technical.no.responsive.viewport.tag'
VIEWPORT = '<meta name="viewport" content="width=device-width, initial-scale=1">'


def mcp_tool(name, arguments, root):
    """Exercise the installed server's real stdio boundary when explicitly requested."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def call(errors):
        params = StdioServerParameters(command=sys.executable, args=['-I', '-m', 'narwhal', 'mcp'], cwd=str(root))
        async with stdio_client(params, errlog=errors) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = (await session.call_tool(name, arguments)).model_dump(by_alias=True)
                assert not result['isError'], result
                if result.get('structuredContent') is not None:
                    return result['structuredContent']
                return json.loads(next(item['text'] for item in result['content'] if item['type'] == 'text'))

    with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as errors:
        try:
            return asyncio.run(asyncio.wait_for(call(errors), timeout=30))
        except Exception:
            errors.seek(0)
            sys.stderr.write(errors.read()[-4000:])
            raise


class FixtureHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/' and self.server.partial_html:
            data = (Path(self.directory) / 'index.html').read_bytes()
            body = data[:64]
            self.send_response(206)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Range', 'bytes 0-{}/{}'.format(len(body) - 1, len(data)))
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


def main(use_mcp=False):
    with tempfile.TemporaryDirectory(prefix='narwhal action cycle-') as directory:
        root = Path(directory)
        site = root / 'site'
        site.mkdir()
        handler = partial(FixtureHandler, directory=str(site))
        with ThreadingHTTPServer(('127.0.0.1', 0), handler) as server:
            server.partial_html = False
            url = 'http://127.0.0.1:' + str(server.server_port) + '/'
            html = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                    '<title>Local workflow verification for Narwhal development</title>'
                    '<meta name="description" content="A disposable local page used to verify an agent-led '
                    'audit, remediation plan, source edit, rescan and measured report difference with Narwhal.">'
                    '<link rel="canonical" href="' + url + '"></head><body>'
                    '<h1>Local workflow verification</h1><p>This fixture tests the development workflow. '
                    'Its content and resource responses remain unchanged while one missing viewport declaration '
                    'is added to the page head.</p></body></html>')
            target = site / 'index.html'
            target.write_text(html, encoding='utf-8')
            (site / 'robots.txt').write_text('User-agent: *\nAllow: /\nSitemap: ' + url + 'sitemap.xml\n', encoding='utf-8')
            (site / 'sitemap.xml').write_text('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                                             '<url><loc>' + url + '</loc></url></urlset>', encoding='utf-8')
            (site / 'llms.txt').write_text('# Local workflow fixture\n\nA disposable development fixture.\n', encoding='utf-8')
            original = {path.name: path.read_bytes() for path in site.iterdir()}
            env = dict(os.environ, NO_PROXY='127.0.0.1,localhost', no_proxy='127.0.0.1,localhost')

            def run(args, expected=0):
                # Isolated Python prevents repository/PYTHONPATH imports from replacing the installed package.
                result = subprocess.run([sys.executable, '-I', '-m', 'narwhal', *args], cwd=root,
                                        env=env, capture_output=True, text=True, timeout=30)
                assert result.returncode == expected, (args, result.returncode, result.stdout, result.stderr)

            def read(name):
                return json.loads((root / name).read_text(encoding='utf-8'))

            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                options = ['scan', url, '--allow-private', '--only', 'technical', '--no-image-checks',
                           '--no-config', '--format', 'json']
                run(options + ['-o', 'before.json'])
                baseline = (root / 'before.json').read_bytes()
                if use_mcp:
                    planned = mcp_tool('plan_remediation', {'report': read('before.json'), 'repo': 'site'}, root)
                    (root / 'plan.json').write_text(json.dumps(planned), encoding='utf-8')
                else:
                    run(['plan', 'before.json', '--repo', str(site), '--format', 'json', '-o', 'plan.json'])
                assert {path.name: path.read_bytes() for path in site.iterdir()} == original, 'Planning changed source files'
                action = next(a for a in read('plan.json')['actions'] if a['rule_id'] == RULE)
                assert action['automation_eligibility']['eligible'] is True, action
                assert action['manual_action'] is False, action
                assert any(owner['path'] == 'index.html' and owner['exists'] is True
                           for owner in action['likely_files']), action
                # Only this generated fixture's templates are executed, as argv without a shell.
                verification = [shlex.split(step) for step in action['verification']
                                if step.startswith('narwhal ')]
                assert [command[:2] for command in verification] == [['narwhal', 'scan'], ['narwhal', 'diff']], verification
                scan_command, diff_command = [command[1:] for command in verification]
                assert scan_command.count('<local-preview-url>') == 1, scan_command
                scan_command = [url if token == '<local-preview-url>' else token for token in scan_command]
                # Restore the baseline's unrecorded configuration choice, as the plan instructs.
                scan_command.insert(scan_command.index('--'), '--no-config')
                assert '--fail-on-regression' in diff_command and '--require-comparable' in diff_command, diff_command
                separator = diff_command.index('--')
                diff_command[separator:separator] = ['--format', 'json', '-o', 'diff.json']
                target.write_text(html.replace('</head>', VIEWPORT + '</head>'), encoding='utf-8')
                run(scan_command)
                run(diff_command)
                assert (root / 'before.json').read_bytes() == baseline, 'Verification overwrote the baseline'
                before, after, diff = read('before.json'), read('after.json'), read('diff.json')
                if use_mcp:
                    assert mcp_tool('diff_reports', {'old_json': json.dumps(before), 'new_json': json.dumps(after)}, root) == diff
                old = {f['rule_id'] for f in before['findings'] if f['severity'] != 'good'}
                new = {f['rule_id'] for f in after['findings'] if f['severity'] != 'good'}
                assert old - new == {RULE} and not new - old, (old, new)
                assert diff['comparison']['status'] == 'comparable', diff['comparison']
                assert {f['rule_id'] for f in diff['resolved']} == {RULE}, diff
                assert diff['score_delta'] == after['score'] - before['score'] > 0, diff
                run(['diff', 'after.json', 'before.json', '--fail-on-regression',
                     '--format', 'json', '-o', 'regression.json'], expected=1)
                regression = read('regression.json')
                if use_mcp:
                    assert mcp_tool('diff_reports', {'old_json': json.dumps(after), 'new_json': json.dumps(before)}, root) == regression
                assert regression['comparison']['status'] == 'comparable', regression
                assert regression['score_delta'] == -diff['score_delta'], regression
                server.partial_html = True
                run(options + ['-o', 'partial.json'])
                partial_report = read('partial.json')
                assert partial_report['status'] == 206, partial_report
                assert partial_report['meta']['scan_scope']['completed'] == [], partial_report
                run(['diff', 'before.json', 'partial.json', '--fail-on-regression',
                     '--format', 'json', '-o', 'unverified.json'], expected=2)
                unverified = read('unverified.json')
                if use_mcp:
                    assert mcp_tool('diff_reports', {'old_json': json.dumps(before), 'new_json': json.dumps(partial_report)}, root) == unverified
                assert unverified['comparison']['status'] == 'incomparable', unverified
                assert unverified['score_delta'] is None and unverified['resolved'] == [], unverified
                fixed_sources = {path.name: path.read_bytes() for path in site.iterdir()}
                if use_mcp:
                    planned = mcp_tool('plan_remediation', {'report': partial_report, 'repo': 'site'}, root)
                    (root / 'partial-plan.json').write_text(json.dumps(planned), encoding='utf-8')
                else:
                    run(['plan', 'partial.json', '--repo', str(site), '--format', 'json', '-o', 'partial-plan.json'])
                assert {path.name: path.read_bytes() for path in site.iterdir()} == fixed_sources, 'Partial plan changed sources'
                actions = read('partial-plan.json')['actions']
                assert RULE not in {a['rule_id'] for a in actions}, actions
                assert 'technical.response.partial' in {a['rule_id'] for a in actions}, actions
                for action in actions:
                    assert action['safety'] == 'manual_external', action
                    assert action['manual_action'] is True and action['likely_files'] == [], action
                    assert action['requires_deploy'] is False, action
                    assert not (action.get('automation_eligibility') or {}).get('eligible'), action
                print('Installed action cycle passed: planned owner -> explicit fixture edit -> generated verification commands -> one resolved issue; '
                      'score {} -> {}; reverse regression rejected; partial rescan withheld fix claims '
                      'and requested manual verification; MCP stdio {}.'.format(
                          before['score'], after['score'], 'verified' if use_mcp else 'not requested'))
                server.partial_html = False
                pricing_url = url + 'pricing/'
                pricing = site / 'pricing/index.html'
                pricing.parent.mkdir()
                pricing_html = html.replace('<title>Local workflow verification for Narwhal development</title>', '')
                pricing_html = pricing_html.replace('</head>', VIEWPORT + '</head>').replace(
                    'href="' + url + '"', 'href="' + pricing_url + '"')
                pricing.write_text(pricing_html, encoding='utf-8')
                (site / 'sitemap.xml').write_text(
                    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                    '<url><loc>' + url + '</loc></url><url><loc>' + pricing_url + '</loc></url></urlset>', encoding='utf-8')
                audit_options = ['audit', url, '--allow-private', '--max-pages', '2', '--no-config', '--format', 'json']
                run(audit_options + ['-o', 'audit-before.json'])
                audit_before = read('audit-before.json')
                source_bytes = {str(p.relative_to(site)): p.read_bytes() for p in site.rglob('*') if p.is_file()}
                if use_mcp:
                    audit_plan = mcp_tool('plan_remediation', {'report': audit_before, 'repo': 'site'}, root)
                else:
                    run(['plan', 'audit-before.json', '--repo', str(site), '--format', 'json', '-o', 'audit-plan.json'])
                    audit_plan = read('audit-plan.json')
                title_rule = 'technical.missing.title'
                title_action = next(a for a in audit_plan['actions'] if a['rule_id'] == title_rule)
                assert [owner['path'] for owner in title_action['likely_files']] == ['pricing/index.html'], title_action
                assert title_action['safety'] == 'review_required', title_action
                assert pricing_url in title_action['evidence'], title_action
                assert source_bytes == {str(p.relative_to(site)): p.read_bytes() for p in site.rglob('*') if p.is_file()}
                row = next(r for r in audit_before['crawl']['recurring'] if r['rule_id'] == title_rule)
                assert row['count'] == 1 and row['url_sample']['urls'] == [pricing_url], row
                pricing.write_text(pricing_html.replace('</head>',
                    '<title>Pricing and plans for local workflow verification</title></head>'), encoding='utf-8')
                run(audit_options + ['-o', 'audit-after.json'])
                audit_after = read('audit-after.json')
                assert title_rule not in {r['rule_id'] for r in audit_after['crawl']['recurring']}, audit_after['crawl']['recurring']
                run(['diff', 'audit-before.json', 'audit-after.json', '--require-comparable', '--fail-on-regression',
                     '--format', 'json', '-o', 'audit-diff.json'])
                audit_diff = read('audit-diff.json')
                assert audit_diff['comparison']['status'] == 'comparable' and audit_diff['score_delta'] > 0, audit_diff
                # Audit diff finding classifications cover the homepage; inner resolution is checked above in the rollup.
                print('Installed site action cycle passed: inner-page rule witness -> pricing/index.html -> explicit title edit; '
                      'recurring title rule resolved; comparable overall score delta {}. Local page proof only.'.format(audit_diff['score_delta']))
            finally:
                server.shutdown()
                thread.join(timeout=5)
                assert not thread.is_alive(), 'Preview server did not stop'


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mcp', action='store_true', help='Also exercise installed MCP planning and diffs over stdio')
    main(use_mcp=parser.parse_args().mcp)
