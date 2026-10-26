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


def mcp_tool(name, arguments, root, *, expected_error=False):
    """Exercise the installed server's real stdio boundary when explicitly requested."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def call(errors):
        params = StdioServerParameters(command=sys.executable, args=['-I', '-m', 'narwhal', 'mcp'], cwd=str(root))
        async with stdio_client(params, errlog=errors) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = (await session.call_tool(name, arguments)).model_dump(by_alias=True)
                assert result['isError'] == expected_error, result
                if expected_error:
                    return '\n'.join(item['text'] for item in result['content'] if item['type'] == 'text')
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
                return result

            def read(name):
                return json.loads((root / name).read_text(encoding='utf-8'))

            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                options = ['scan', url, '--allow-private', '--only', 'technical', '--no-image-checks',
                           '--max-bytes', '6000000', '--no-config', '--format', 'json']
                run(options + ['-o', 'before.json'])
                baseline = (root / 'before.json').read_bytes()
                assert read('before.json')['status'] == 200
                ambiguous = '{"status":503,' + baseline.decode('utf-8').lstrip()[1:]
                (root / 'ambiguous.json').write_text(ambiguous, encoding='utf-8')
                rejected_output = root / 'rejected-output.json'
                rejected_output.write_bytes(b'previous output')
                rejected_commands = [
                    ['plan', 'ambiguous.json', '--repo', str(site)],
                    ['diff', 'ambiguous.json', 'before.json', '--require-comparable', '--fail-on-regression'],
                    ['diff', 'before.json', 'ambiguous.json', '--require-comparable', '--fail-on-regression'],
                ]
                for command in rejected_commands:
                    rejected = run(command + ['--format', 'json', '-o', rejected_output.name], expected=2)
                    assert rejected.stdout == '' and 'duplicate' in rejected.stderr.lower(), rejected
                    assert rejected_output.read_bytes() == b'previous output'
                if use_mcp:
                    valid_json = baseline.decode('utf-8')
                    for left, right in ((ambiguous, valid_json), (valid_json, ambiguous)):
                        error = mcp_tool('diff_reports', {'old_json': left, 'new_json': right},
                                         root, expected_error=True)
                        assert 'duplicate' in error.lower(), error
                assert (root / 'ambiguous.json').read_text(encoding='utf-8') == ambiguous
                assert (root / 'before.json').read_bytes() == baseline
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
                invalid_scope = read('before.json')
                invalid_scope['meta']['scan_scope'] = {'requested': 'technical', 'completed': []}
                invalid_status = read('before.json')
                invalid_status['status'] = '200'
                invalid_completeness = read('before.json')
                invalid_completeness['meta']['coverage']['response_truncated'] = 'false'
                invalid_selection = read('before.json')
                invalid_selection['meta']['scan_scope']['not_selected'].append('technical')
                invalid_failure = read('before.json')
                invalid_failure.update(status=503, hard_fail=True)
                invalid_rendering = read('before.json')
                invalid_rendering['rendered'] = not invalid_rendering['meta']['scan_settings']['rendered']
                invalid_mixed = read('before.json')
                invalid_mixed['response_truncated'] = 'false'
                for label, invalid in (('scope', invalid_scope), ('status', invalid_status),
                                       ('completeness', invalid_completeness), ('selection', invalid_selection),
                                       ('failure', invalid_failure), ('mixed-completeness', invalid_mixed),
                                       ('rendering', invalid_rendering)):
                    source, output = 'invalid-' + label + '.json', 'invalid-' + label + '-plan.json'
                    (root / source).write_text(json.dumps(invalid), encoding='utf-8')
                    if use_mcp:
                        invalid_plan = mcp_tool('plan_remediation', {'report': invalid, 'repo': 'site'}, root)
                    else:
                        run(['plan', source, '--repo', str(site), '--format', 'json', '-o', output])
                        invalid_plan = read(output)
                    invalid_action = next(a for a in invalid_plan['actions'] if a['rule_id'] == RULE)
                    assert invalid_action['automation_eligibility']['eligible'] is False, invalid_action
                    assert 'known_incomplete_source_evidence' in invalid_action['automation_eligibility']['blockers']
                    comparison = 'invalid-' + label + '-diff.json'
                    run(['diff', source, 'before.json', '--require-comparable', '--fail-on-regression',
                         '--format', 'json', '-o', comparison], expected=2)
                    assert read(comparison)['comparison']['status'] == 'incomparable'
                    assert read(comparison)['score_delta'] is None and read(comparison)['resolved'] == []
                    run(['diff', source, 'before.json', '--fail-on-regression'], expected=2)
                    if use_mcp:
                        invalid_diff = mcp_tool('diff_reports', {'old_json': json.dumps(invalid),
                            'new_json': json.dumps(read('before.json'))}, root)
                        assert invalid_diff['comparison']['status'] == 'incomparable'
                        assert invalid_diff['score_delta'] is None and invalid_diff['resolved'] == []
                assert {path.name: path.read_bytes() for path in site.iterdir()} == original
                # Only this generated fixture's templates are executed, as argv without a shell.
                verification = [shlex.split(step, comments=True) for step in action['verification']
                                if step.startswith('narwhal ')]
                assert [command[1] for command in verification] == ['scan', 'scan', 'diff', 'scan', 'diff'], verification
                for command in verification:
                    if command[1] == 'scan':
                        assert command[command.index('--max-bytes') + 1] == '6000000', command
                local_before, local_after, local_diff, original_after, original_diff = verification
                def scan_arguments(command):
                    args = [url if token == '<local-preview-url>' else token for token in command[1:]]
                    # Restore unrecorded config/access settings for this intentional local fixture.
                    args.insert(args.index('--'), '--no-config')
                    if '--allow-private' not in args:
                        args.insert(args.index('--'), '--allow-private')
                    return args
                def diff_arguments(command, output):
                    args = command[1:]
                    separator = args.index('--')
                    args[separator:separator] = ['--format', 'json', '-o', output]
                    return args
                assert local_before[-1] == local_after[-1] == '<local-preview-url>'
                run(scan_arguments(local_before))
                page_baseline = (root / 'page-before.json').read_bytes()
                diff_command = diff_arguments(original_diff, 'diff.json')
                assert '--fail-on-regression' in diff_command and '--require-comparable' in diff_command, diff_command
                target.write_text(html.replace('</head>', VIEWPORT + '</head>'), encoding='utf-8')
                run(scan_arguments(local_after))
                run(diff_arguments(local_diff, 'page-diff.json'))
                page_diff = read('page-diff.json')
                for name in ('page-before.json', 'page-after.json'):
                    assert read(name)['meta']['coverage']['response_byte_limit'] == 6_000_000
                assert page_diff['comparison']['status'] == 'comparable', page_diff
                assert {item['rule_id'] for item in page_diff['resolved']} == {RULE}, page_diff
                assert (root / 'page-before.json').read_bytes() == page_baseline
                # Exercise the original-target commands on the fixture too; this is not deployment proof.
                run(scan_arguments(original_after))
                run(diff_command)
                assert (root / 'before.json').read_bytes() == baseline, 'Verification overwrote the baseline'
                before, after, diff = read('before.json'), read('after.json'), read('diff.json')
                assert before['meta']['coverage']['response_byte_limit'] == after['meta']['coverage']['response_byte_limit'] == 6_000_000
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
                pricing_html = pricing_html.replace('href="' + url + '"', 'href="' + pricing_url + '"')
                pricing.write_text(pricing_html, encoding='utf-8')
                (site / 'sitemap.xml').write_text(
                    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                    '<url><loc>' + url + '</loc></url><url><loc>' + pricing_url + '</loc></url></urlset>', encoding='utf-8')
                audit_options = ['audit', url, '--allow-private', '--max-pages', '2', '--no-config', '--format', 'json']
                run(audit_options + ['-o', 'audit-before.json'])
                audit_before = read('audit-before.json')
                assert all(type(page['status']) is int and page['status'] == 200
                           and page['rendered'] is False for page in audit_before['crawl']['pages'])
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
                viewport_action = next(a for a in audit_plan['actions'] if a['rule_id'] == RULE)
                assert [o['path'] for o in viewport_action['likely_files']] == ['pricing/index.html'], viewport_action
                assert viewport_action['automation_eligibility']['eligible'] is True, viewport_action
                assert viewport_action['automation_eligibility']['blockers'] == [], viewport_action
                try:
                    pricing.unlink()
                    if use_mcp:
                        ownerless_plan = mcp_tool('plan_remediation', {'report': audit_before, 'repo': 'site'}, root)
                    else:
                        run(['plan', 'audit-before.json', '--repo', str(site), '--format', 'json', '-o', 'ownerless-plan.json'])
                        ownerless_plan = read('ownerless-plan.json')
                    assert not pricing.exists() and not pricing.is_symlink(), 'Ownerless planning created source'
                finally:
                    pricing.write_bytes(source_bytes['pricing/index.html'])
                ownerless = next(a for a in ownerless_plan['actions'] if a['rule_id'] == RULE)
                assert ownerless['likely_files'] == [] and ownerless['manual_action'] is True, ownerless
                assert ownerless['automation_eligibility']['eligible'] is False, ownerless
                assert 'no_existing_owner_candidate' in ownerless['automation_eligibility']['blockers'], ownerless
                assert source_bytes == {str(p.relative_to(site)): p.read_bytes() for p in site.rglob('*') if p.is_file()}
                pricing.write_text(pricing_html.replace('</head>',
                    '<title>Pricing and plans for local workflow verification</title></head>'), encoding='utf-8')
                run(audit_options + ['-o', 'audit-after.json'])
                audit_after = read('audit-after.json')
                assert title_rule not in {r['rule_id'] for r in audit_after['crawl']['recurring']}, audit_after['crawl']['recurring']
                run(['diff', 'audit-before.json', 'audit-after.json', '--require-comparable', '--fail-on-regression',
                     '--format', 'json', '-o', 'audit-diff.json'])
                audit_diff = read('audit-diff.json')
                assert audit_diff['comparison']['status'] == 'comparable' and audit_diff['score_delta'] > 0, audit_diff
                changes = audit_diff['crawl_rule_changes']
                assert changes['status'] == 'compared' and any(
                    row['rule_id'] == title_rule for row in changes['removed']), changes
                if use_mcp:
                    assert audit_diff == mcp_tool('diff_reports', {
                        'old_json': json.dumps(audit_before), 'new_json': json.dumps(audit_after)}, root)
                malformed = json.loads(json.dumps(audit_before))
                malformed['crawl']['pages'].append(None)
                (root / 'audit-malformed-sample.json').write_text(json.dumps(malformed), encoding='utf-8')
                run(['diff', 'audit-malformed-sample.json', 'audit-after.json', '--require-comparable',
                     '--fail-on-regression', '--format', 'json', '-o', 'audit-malformed-sample-diff.json'], expected=2)
                malformed_diff = read('audit-malformed-sample-diff.json')
                assert malformed_diff['comparison']['status'] == 'incomparable', malformed_diff
                assert malformed_diff['score_delta'] is None and malformed_diff['resolved'] == [], malformed_diff
                if use_mcp:
                    assert malformed_diff == mcp_tool('diff_reports', {
                        'old_json': json.dumps(malformed), 'new_json': json.dumps(audit_after)}, root)
                legacy = json.loads(json.dumps(audit_before))
                legacy['crawl'].pop('recurring')
                (root / 'audit-unverified.json').write_text(json.dumps(legacy), encoding='utf-8')
                run(['diff', 'audit-unverified.json', 'audit-after.json', '--require-comparable',
                     '--fail-on-regression', '--format', 'json', '-o', 'audit-unverified-diff.json'], expected=2)
                assert read('audit-unverified-diff.json')['crawl_rule_changes']['status'] == 'unverified'
                inconsistent = json.loads(json.dumps(audit_before))
                inconsistent['crawl']['pages_scanned'] += 1
                (root / 'audit-inconsistent.json').write_text(json.dumps(inconsistent), encoding='utf-8')
                run(['diff', 'audit-inconsistent.json', 'audit-after.json', '--require-comparable',
                     '--fail-on-regression', '--format', 'json', '-o', 'audit-inconsistent-diff.json'], expected=2)
                inconsistent_diff = read('audit-inconsistent-diff.json')
                assert inconsistent_diff['crawl_rule_changes']['status'] == 'unverified'
                assert inconsistent_diff['comparison']['status'] == 'incomparable'
                assert inconsistent_diff['score_delta'] is None and inconsistent_diff['resolved'] == [], inconsistent_diff
                run(['diff', 'audit-inconsistent.json', 'audit-after.json', '--fail-on-regression'], expected=2)
                if use_mcp:
                    assert inconsistent_diff == mcp_tool('diff_reports', {
                        'old_json': json.dumps(inconsistent), 'new_json': json.dumps(audit_after)}, root)
                incomplete = json.loads(json.dumps(audit_before))
                incomplete['crawl']['pages'][1]['scan_scope'] = {'requested': ['technical'], 'completed': []}
                (root / 'audit-incomplete-scope.json').write_text(json.dumps(incomplete), encoding='utf-8')
                run(['diff', 'audit-incomplete-scope.json', 'audit-after.json', '--require-comparable',
                     '--fail-on-regression', '--format', 'json', '-o', 'audit-incomplete-scope-diff.json'], expected=2)
                assert read('audit-incomplete-scope-diff.json')['comparison']['status'] == 'incomparable'
                assert all(page['scan_scope']['requested'] and set(page['scan_scope']['requested']) ==
                           set(page['scan_scope']['completed']) for page in audit_before['crawl']['pages'])
                assert RULE in {r['rule_id'] for r in audit_after['crawl']['recurring']}
                pricing.write_text(pricing.read_text(encoding='utf-8').replace('</head>', VIEWPORT + '</head>'), encoding='utf-8')
                run(audit_options + ['-o', 'audit-viewport-after.json'])
                viewport_after = read('audit-viewport-after.json')
                assert RULE not in {r['rule_id'] for r in viewport_after['crawl']['recurring']}
                run(['diff', 'audit-after.json', 'audit-viewport-after.json', '--require-comparable',
                     '--fail-on-regression', '--format', 'json', '-o', 'audit-viewport-diff.json'])
                viewport_diff = read('audit-viewport-diff.json')
                assert viewport_diff['comparison']['status'] == 'comparable' and viewport_diff['score_delta'] > 0, viewport_diff
                assert {r['rule_id'] for r in viewport_diff['crawl_rule_changes']['removed']} == {RULE}, viewport_diff
                if use_mcp:
                    assert viewport_diff == mcp_tool('diff_reports', {
                        'old_json': json.dumps(audit_after), 'new_json': json.dumps(viewport_after)}, root)
                print('Installed inner viewport cycle passed: observed pricing owner -> missing owner withheld automation '
                      '-> explicit viewport edit -> recurring rule no longer observed. Local page proof only.')
                # Removed crawl rules are sample observations, not individual page-resolution classifications.
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
