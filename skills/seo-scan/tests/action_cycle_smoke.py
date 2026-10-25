"""Installed-CLI action cycle on a disposable local site; not an offline unit test.

Run after installing the wheel: python skills/seo-scan/tests/action_cycle_smoke.py
The planner stays read-only. This fixture explicitly applies one inspected edit.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

RULE = 'technical.no.responsive.viewport.tag'
VIEWPORT = '<meta name="viewport" content="width=device-width, initial-scale=1">'


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


def main():
    with tempfile.TemporaryDirectory(prefix='narwhal-action-cycle-') as directory:
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
                run(['plan', 'before.json', '--repo', str(site), '--format', 'json', '-o', 'plan.json'])
                assert {path.name: path.read_bytes() for path in site.iterdir()} == original, 'Planning changed source files'
                action = next(a for a in read('plan.json')['actions'] if a['rule_id'] == RULE)
                assert action['automation_eligibility']['eligible'] is True, action
                assert action['manual_action'] is False, action
                assert any(owner['path'] == 'index.html' and owner['exists'] is True
                           for owner in action['likely_files']), action
                target.write_text(html.replace('</head>', VIEWPORT + '</head>'), encoding='utf-8')
                run(options + ['-o', 'after.json'])
                run(['diff', 'before.json', 'after.json', '--fail-on-regression', '--format', 'json', '-o', 'diff.json'])
                before, after, diff = read('before.json'), read('after.json'), read('diff.json')
                old = {f['rule_id'] for f in before['findings'] if f['severity'] != 'good'}
                new = {f['rule_id'] for f in after['findings'] if f['severity'] != 'good'}
                assert old - new == {RULE} and not new - old, (old, new)
                assert diff['comparison']['status'] == 'comparable', diff['comparison']
                assert {f['rule_id'] for f in diff['resolved']} == {RULE}, diff
                assert diff['score_delta'] == after['score'] - before['score'] > 0, diff
                run(['diff', 'after.json', 'before.json', '--fail-on-regression',
                     '--format', 'json', '-o', 'regression.json'], expected=1)
                regression = read('regression.json')
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
                assert unverified['comparison']['status'] == 'incomparable', unverified
                assert unverified['score_delta'] is None and unverified['resolved'] == [], unverified
                fixed_sources = {path.name: path.read_bytes() for path in site.iterdir()}
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
                print('Installed action cycle passed: planned owner -> explicit fixture edit -> one resolved issue; '
                      'score {} -> {}; reverse regression rejected; partial rescan withheld fix claims '
                      'and requested manual verification.'.format(before['score'], after['score']))
            finally:
                server.shutdown()
                thread.join(timeout=5)
                assert not thread.is_alive(), 'Preview server did not stop'


if __name__ == '__main__':
    main()
