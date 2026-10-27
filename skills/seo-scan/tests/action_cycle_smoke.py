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


def mcp_result(result, *, expected_error=False):
    wire = result.model_dump(by_alias=True)
    assert wire['isError'] == expected_error, wire
    if expected_error:
        return '\n'.join(item['text'] for item in wire['content'] if item['type'] == 'text')
    if wire.get('structuredContent') is not None:
        return wire['structuredContent']
    return json.loads(next(item['text'] for item in wire['content'] if item['type'] == 'text'))


def mcp_session(exercise, root):
    """Exercise the installed server's real stdio boundary when explicitly requested."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def call(errors):
        params = StdioServerParameters(command=sys.executable, args=['-I', '-m', 'narwhal', 'mcp'], cwd=str(root))
        async with stdio_client(params, errlog=errors) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = (await session.initialize()).model_dump(by_alias=True)
                assert initialized['serverInfo']['name'] == 'narwhal', initialized
                return await exercise(session)

    with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as errors:
        try:
            return asyncio.run(asyncio.wait_for(call(errors), timeout=30))
        except Exception:
            errors.seek(0)
            sys.stderr.write(errors.read()[-4000:])
            raise


def mcp_tool(name, arguments, root, *, expected_error=False):
    async def call(session):
        return mcp_result(await session.call_tool(name, arguments), expected_error=expected_error)
    return mcp_session(call, root)


def mcp_recovery(report, root):
    """Bad input and its correction must work in one installed server session."""
    async def exercise(session):
        async def tool(name, arguments, *, error=False):
            return mcp_result(await session.call_tool(name, arguments), expected_error=error)

        diagnostic = await tool('generate_schema', {
            'type': 'Product', 'fields': {'offers': '{"secret-token":99,"secret-token":9}'}}, error=True)
        assert 'duplicate' in diagnostic.lower() and 'secret-token' not in diagnostic
        assert len(diagnostic) < 500
        generated = await tool('generate_schema', {
            'type': 'Product', 'fields': {'offers': '[{"price":9},{"price":99}]'}})
        assert generated['offers'] == [{'price': 9}, {'price': 99}]

        valid_json = json.dumps(report)
        ambiguous = '{"status":503,' + valid_json.lstrip()[1:]
        for left, right in ((ambiguous, valid_json), (valid_json, ambiguous)):
            diagnostic = await tool('diff_reports', {'old_json': left, 'new_json': right}, error=True)
            assert 'duplicate' in diagnostic.lower() and len(diagnostic) < 500, diagnostic
            diff = await tool('diff_reports', {'old_json': valid_json, 'new_json': valid_json})
            assert diff['comparison']['status'] == 'comparable' and diff['score_delta'] == 0, diff
            assert diff['regression'] is False and not any(diff[key] for key in ('added', 'resolved', 'worsened', 'improved')), diff

        cases = [({'report': report, 'repo': 'missing-secret-token'}, 'existing directory'),
                 ({'report': report, 'repo': 'site/index.html'}, 'existing directory'),
                 ({'report': dict(report, score='secret-token'), 'repo': 'site'}, 'finite')]
        for arguments, reason in cases:
            diagnostic = await tool('plan_remediation', arguments, error=True)
            assert reason in diagnostic.lower() and len(diagnostic) < 500, diagnostic
            assert root.name not in diagnostic and str(root.resolve()) not in diagnostic, diagnostic
            assert 'secret-token' not in diagnostic, diagnostic
            planned = await tool('plan_remediation', {'report': report, 'repo': 'site'})
            action = next(action for action in planned['actions'] if action['rule_id'] == RULE)
            assert action['automation_eligibility']['eligible'] is True and action['manual_action'] is False, action
            assert any(owner['path'] == 'index.html' and owner['exists'] is True for owner in action['likely_files']), action
        return planned

    planned = mcp_session(exercise, root)
    print('Installed MCP recovery passed: schema, both diff inputs and planner path/report errors '
          'each followed by a valid request in one session; bounded diagnostics and native owner retained.')
    return planned


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

            offers = '[{"price":9},{"price":99}]'
            generated = json.loads(run(['schema', 'Product', '--field', 'name=Widget',
                                        '--field', 'offers=' + offers, '--raw']).stdout)
            assert generated['@context'] == 'https://schema.org'
            assert generated['offers'] == json.loads(offers)
            duplicate = '{"secret-token":99,"secret-token":9}'
            for mode in ([], ['--raw']):
                rejected = run(['schema', 'Product', '--field', 'offers=' + duplicate, *mode], expected=2)
                assert not rejected.stdout
                assert 'duplicate' in rejected.stderr.lower()
                assert 'secret-token' not in rejected.stderr
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
                assert (root / 'ambiguous.json').read_text(encoding='utf-8') == ambiguous
                assert (root / 'before.json').read_bytes() == baseline
                if use_mcp:
                    planned = mcp_recovery(read('before.json'), root)
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
                for label, changes, eligible in (
                        ('empty-url', {'url': '', 'final_url': ''}, False),
                        ('file-url', {'final_url': 'file:///tmp/index.html'}, False),
                        ('bad-port', {'final_url': 'https://example.test:bad/'}, False),
                        ('malformed-final', {'final_url': {}}, False),
                        ('site-scope', {'status': 206}, False),
                        ('empty-final', {'final_url': ''}, True)):
                    supplied = read('before.json')
                    supplied.update(changes)
                    if label == 'site-scope':
                        next(f for f in supplied['findings'] if f['rule_id'] == RULE)['scope'] = 'site'
                    source, output = label + '.json', label + '-plan.json'
                    source_bytes = json.dumps(supplied).encode('utf-8')
                    (root / source).write_bytes(source_bytes)
                    if use_mcp:
                        supplied_plan = mcp_tool('plan_remediation', {'report': supplied, 'repo': 'site'}, root)
                    else:
                        run(['plan', source, '--repo', str(site), '--format', 'json', '-o', output])
                        supplied_plan = read(output)
                    supplied_action = next(a for a in supplied_plan['actions'] if a['rule_id'] == RULE)
                    assert supplied_action['automation_eligibility']['eligible'] is eligible, (label, supplied_action)
                    assert supplied_action['safety'] == ('safely_automatable' if eligible else 'review_required')
                    assert any(owner['path'] == 'index.html' and owner['exists'] is True
                               for owner in supplied_action['likely_files']), supplied_action
                    if not eligible:
                        assert 'known_incomplete_source_evidence' in supplied_action['automation_eligibility']['blockers']
                    assert supplied_plan['target'] == (supplied.get('final_url') or supplied.get('url') or '')
                    assert (root / source).read_bytes() == source_bytes
                    assert {path.name: path.read_bytes() for path in site.iterdir()} == original
                print('Installed URL evidence checks passed: five invalid URL/scope cases withheld automation; '
                      'native empty final URL retained its candidate; source and report bytes preserved.')
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
                sitemap_source = 'technical.sitemap.validation.issues'
                sitemap_unknown = 'technical.sitemap.validation.unverified'
                for label, changes, expected in (
                        ('zero', {'problems': {'not-absolute': 0}, 'invalid_lastmod': 0}, set()),
                        ('unknown', {'problems': {}, 'invalid_lastmod': '0'}, {sitemap_unknown}),
                        ('mixed', {'problems': {'not-absolute': 1}, 'invalid_lastmod': '0'},
                         {sitemap_source, sitemap_unknown}),
                        ('bad-execution', {'errors': [], 'fetch_failures': False}, {sitemap_unknown}),
                        ('contradictory-execution', {'errors': [], 'sitemaps_attempted': 3,
                                                    'sitemaps_fetched': 1, 'fetch_failures': 0}, {sitemap_unknown}),
                        ('mixed-execution', {'errors': [], 'problems': {'not-absolute': 1}, 'fetch_failures': False},
                         {sitemap_source, sitemap_unknown})):
                    supplied = json.loads(json.dumps(audit_before))
                    supplied['sitemap'].update(changes)
                    name = 'sitemap-count-' + label + '.json'
                    supplied_bytes = json.dumps(supplied).encode('utf-8')
                    (root / name).write_bytes(supplied_bytes)
                    if use_mcp:
                        received = mcp_tool('plan_remediation', {'report': supplied, 'repo': 'site'}, root)
                    else:
                        run(['plan', name, '--repo', str(site), '--format', 'json', '-o', name + '.plan.json'])
                        received = read(name + '.plan.json')
                    selected = {a['rule_id']: a for a in received['actions']
                                if a['rule_id'] in (sitemap_source, sitemap_unknown)}
                    assert set(selected) == expected, (label, selected)
                    if sitemap_unknown in selected:
                        note = selected[sitemap_unknown]
                        assert note['manual_action'] is True and note['safety'] == 'manual_external'
                        assert note['likely_files'] == [] and note['requires_deploy'] is False
                        assert not any(sitemap_unknown in group['rule_ids'] for group in received['groups'])
                    if sitemap_source in selected:
                        action = selected[sitemap_source]
                        assert action['safety'] == 'deploy_verification' and action['requires_deploy'] is True
                        assert any(o['path'] == 'sitemap.xml' and o['exists'] is True for o in action['likely_files'])
                    assert (root / name).read_bytes() == supplied_bytes
                    assert source_bytes == {str(p.relative_to(site)): p.read_bytes() for p in site.rglob('*') if p.is_file()}
                print('Installed sitemap count checks passed: zero summaries withheld repair advice; malformed counts '
                      'required manual verification; independent positive evidence retained its source candidate; '
                      'explicit malformed/inconsistent execution receipts stayed visible.')
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
                prior_reports = {p: p.read_bytes() for p in root.glob('*.json')}
                schema_sources = {str(p.relative_to(site)): p.read_bytes() for p in site.rglob('*') if p.is_file()}
                schema_options = list(options)
                schema_options[schema_options.index('--only') + 1] = 'schema'
                run(schema_options + ['-o', 'schema-before.json'])
                schema_baseline = (root / 'schema-before.json').read_bytes()
                schema_before = read('schema-before.json')
                schema_rule = 'schema.no.structured.data'
                assert schema_rule in {f['rule_id'] for f in schema_before['findings']}
                try:
                    target.write_bytes(schema_sources['index.html'] + b'<script type="application/ld+json">{bad</script>')
                    run(schema_options + ['-o', 'schema-uncertain.json'])
                finally:
                    target.write_bytes(schema_sources['index.html'])
                uncertain = read('schema-uncertain.json')
                assert uncertain['meta']['scan_settings']['schema_extraction_reviewed'] is False, uncertain
                assert schema_rule not in {f['rule_id'] for f in uncertain['findings']}, uncertain
                # A stale saved absence finding must not override observed extraction uncertainty.
                uncertain['findings'].append(next(f for f in schema_before['findings'] if f['rule_id'] == schema_rule))
                uncertain_bytes = json.dumps(uncertain).encode('utf-8')
                (root / 'schema-uncertain-legacy.json').write_bytes(uncertain_bytes)
                if use_mcp:
                    uncertain_plan = mcp_tool('plan_remediation', {'report': uncertain, 'repo': 'site'}, root)
                else:
                    run(['plan', 'schema-uncertain-legacy.json', '--repo', str(site), '--format', 'json',
                         '-o', 'schema-uncertain-plan.json'])
                    uncertain_plan = read('schema-uncertain-plan.json')
                uncertain_actions = {a['rule_id']: a for a in uncertain_plan['actions']}
                assert set(uncertain_actions) == {'schema.invalid.json.ld', 'schema.extraction.unverified'}, uncertain_actions
                verification = uncertain_actions['schema.extraction.unverified']
                assert (verification['safety'], verification['scope'], verification['severity']) == ('manual_external', 'page', 'low'), verification
                assert verification['manual_action'] is True and verification['requires_deploy'] is False, verification
                assert not verification['likely_files'] and not uncertain_plan['groups'], uncertain_plan
                syntax_repair = uncertain_actions['schema.invalid.json.ld']
                assert syntax_repair['safety'] == 'review_required' and syntax_repair['artifact'] == 'json_ld', syntax_repair
                assert any(o['path'] == 'index.html' and o['exists'] is True for o in syntax_repair['likely_files']), syntax_repair
                assert uncertain_plan['source_score'] == uncertain['score'], uncertain_plan
                assert json.dumps(uncertain).encode('utf-8') == uncertain_bytes
                assert (root / 'schema-uncertain-legacy.json').read_bytes() == uncertain_bytes
                run(['diff', 'schema-uncertain-legacy.json', 'schema-uncertain-legacy.json', '--require-comparable',
                     '--fail-on-regression', '--format', 'json', '-o', 'schema-uncertain-diff.json'], expected=2)
                uncertain_diff = read('schema-uncertain-diff.json')
                assert uncertain_diff['comparison']['status'] == 'incomparable' and uncertain_diff['score_delta'] is None, uncertain_diff
                assert not uncertain_diff['resolved'], uncertain_diff
                if use_mcp:
                    assert uncertain_diff == mcp_tool('diff_reports', {
                        'old_json': uncertain_bytes.decode('utf-8'), 'new_json': uncertain_bytes.decode('utf-8')}, root)
                assert (root / 'schema-uncertain-legacy.json').read_bytes() == uncertain_bytes
                assert schema_sources == {str(p.relative_to(site)): p.read_bytes() for p in site.rglob('*') if p.is_file()}
                print('Installed schema uncertainty checks passed: actual JSON-LD extraction error overrides stale absence advice; '
                      'syntax repair stays reviewable, verification stays ownerless and identical uncertain reports fail comparability.')
                if use_mcp:
                    schema_plan = mcp_tool('plan_remediation', {'report': schema_before, 'repo': 'site'}, root)
                else:
                    run(['plan', 'schema-before.json', '--repo', str(site), '--format', 'json', '-o', 'schema-plan.json'])
                    schema_plan = read('schema-plan.json')
                schema_action = next(a for a in schema_plan['actions'] if a['rule_id'] == schema_rule)
                assert schema_action['artifact'] == 'json_ld' and schema_action['safety'] == 'review_required', schema_action
                assert not (schema_action.get('automation_eligibility') or {}).get('eligible'), schema_action
                assert any(o['path'] == 'index.html' and o['exists'] is True for o in schema_action['likely_files'])
                fields = {'name': 'Local workflow verification', 'url': url}
                assert '<h1>' + fields['name'] + '</h1>' in schema_sources['index.html'].decode('utf-8')
                assert fields['url'] == schema_before['final_url']
                generation = ['schema', 'WebSite', '--no-recommended',
                              '--field', 'name=' + fields['name'], '--field', 'url=' + url]
                node = json.loads(run(generation + ['--raw']).stdout)
                assert node == {'@context': 'https://schema.org', '@type': 'WebSite', **fields}, node
                script = run(generation).stdout
                assert json.loads(script.split('>', 1)[1].rsplit('</script>', 1)[0]) == node
                if use_mcp:
                    starter = mcp_tool('generate_schema', {'type': 'WebSite', 'fields': fields}, root)
                    # This fixture has no search action; curate the starter instead of inventing one.
                    assert 'TODO' in starter.pop('potentialAction')
                    assert starter == node, starter
                    script = '<script type="application/ld+json">' + json.dumps(starter).replace('<', '\\u003c') + '</script>'
                assert 'TODO' not in script
                assert schema_sources == {str(p.relative_to(site)): p.read_bytes() for p in site.rglob('*') if p.is_file()}
                fresh_names = {'page-before.json': 'schema-page-before.json', 'page-after.json': 'schema-page-after.json'}
                schema_commands = [[fresh_names.get(token, token) for token in shlex.split(step, comments=True)]
                                   for step in schema_action['verification'] if step.startswith('narwhal ')]
                assert [command[1] for command in schema_commands] == ['scan', 'scan', 'diff', 'scan', 'diff']
                for command in schema_commands:
                    if command[1] == 'scan':
                        assert command[command.index('--only') + 1] == 'schema', command
                        assert command[command.index('--max-bytes') + 1] == '6000000', command
                run(scan_arguments(schema_commands[0]))
                schema_page_baseline = (root / 'schema-page-before.json').read_bytes()
                patched = target.read_text(encoding='utf-8').replace('</head>', script + '</head>')
                target.write_text(patched, encoding='utf-8')
                run(scan_arguments(schema_commands[1]))
                schema_after = read('schema-page-after.json')
                for page in (json.loads(schema_page_baseline), schema_after):
                    scope = page['meta']['scan_scope']
                    assert page['status'] == 200 and scope['requested'] == scope['completed'] == ['schema'], page
                    assert page['meta']['coverage']['response_byte_limit'] == 6_000_000
                observed = schema_after['meta']['structured_data']
                assert observed['types_by_format'] == {'jsonld': ['WebSite']}, observed
                assert observed['nodes_count'] == 1 and observed['extraction_coverage']['status'] == 'no_known_problem', observed
                run(diff_arguments(schema_commands[2], 'schema-page-diff.json'))
                schema_diff = read('schema-page-diff.json')
                assert schema_diff['comparison']['status'] == 'comparable' and schema_diff['regression'] is False, schema_diff
                assert {f['rule_id'] for f in schema_diff['resolved']} == {schema_rule}, schema_diff
                assert [(f['rule_id'], f['severity']) for f in schema_diff['added']] == [
                    ('schema.structured.data.present', 'good')], schema_diff
                assert schema_diff['score_delta'] > 0, schema_diff
                if use_mcp:
                    assert schema_diff == mcp_tool('diff_reports', {
                        'old_json': schema_page_baseline.decode('utf-8'), 'new_json': json.dumps(schema_after)}, root)
                schema_after_bytes = (root / 'schema-page-after.json').read_bytes()
                if use_mcp:
                    completed_plan = mcp_tool('plan_remediation', {'report': schema_after, 'repo': 'site'}, root)
                else:
                    run(['plan', 'schema-page-after.json', '--repo', str(site), '--format', 'json',
                         '-o', 'schema-completed-plan.json'])
                    completed_plan = read('schema-completed-plan.json')
                assert completed_plan['actions'] == completed_plan['groups'] == completed_plan['conflicts'] == []
                assert completed_plan['coverage']['actionable_findings'] == completed_plan['coverage']['actions_emitted'] == 0
                assert (root / 'schema-page-after.json').read_bytes() == schema_after_bytes
                run(['diff', 'schema-page-after.json', 'schema-page-before.json', '--require-comparable',
                     '--fail-on-regression', '--format', 'json', '-o', 'schema-regression.json'], expected=1)
                assert read('schema-regression.json')['regression'] is True
                assert (root / 'schema-before.json').read_bytes() == schema_baseline
                assert (root / 'schema-page-before.json').read_bytes() == schema_page_baseline
                assert all(path.read_bytes() == data for path, data in prior_reports.items())
                schema_sources['index.html'] = patched.encode('utf-8')
                assert schema_sources == {str(p.relative_to(site)): p.read_bytes() for p in site.rglob('*') if p.is_file()}
                print('Installed schema action cycle passed: reviewed source owner -> generated and curated WebSite JSON-LD '
                      '-> explicit fixture edit -> one resolved observation in a comparable local rescan; '
                      'no remaining schema actions; prior reports preserved and reverse regression rejected. '
                      'No eligibility or ranking proof.')
            finally:
                server.shutdown()
                thread.join(timeout=5)
                assert not thread.is_alive(), 'Preview server did not stop'


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mcp', action='store_true', help='Also exercise installed MCP planning and diffs over stdio')
    main(use_mcp=parser.parse_args().mcp)
