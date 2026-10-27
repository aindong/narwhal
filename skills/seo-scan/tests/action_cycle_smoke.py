"""Installed-CLI action cycle on a disposable local site; not an offline unit test.

Run after installing the wheel: python skills/seo-scan/tests/action_cycle_smoke.py
Add --mcp with an MCP SDK installed to verify planning/diffs over real stdio.
The planner stays read-only. This fixture explicitly applies one inspected edit.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser
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


def comparison_explanations(run, read, root, page, audit, use_mcp):
    """Exercise readable comparison decisions from native saved snapshots."""
    legacy = json.loads(json.dumps(page))
    legacy['meta'].pop('scan_scope')
    missing_policy = json.loads(json.dumps(page))
    missing_policy['meta'].pop('hreflang_policy_basis')
    missing_crawl_policy = json.loads(json.dumps(audit))
    missing_crawl_policy['crawl'].pop('hreflang_acquisition_basis')
    for label, old, new, status, expected in (
            ('matching', page, page, 'comparable', 0),
            ('unknown', legacy, legacy, 'unknown', 2),
            ('page-policy', page, missing_policy, 'incomparable', 2),
            ('crawl-policy', audit, missing_crawl_policy, 'incomparable', 2)):
        names = ['explanation-' + label + '-' + side + '.json' for side in ('old', 'new')]
        saved = [json.dumps(data).encode('utf-8') for data in (old, new)]
        for name, data in zip(names, saved):
            (root / name).write_bytes(data)
        flags = ['--require-comparable', '--fail-on-regression']
        result = json.loads(run(['diff', *names, *flags, '--format', 'json'], expected=expected).stdout)
        comparison = result['comparison']
        assert comparison['status'] == status, result
        reasons = comparison['reasons']
        assert isinstance(reasons, list) and bool(reasons) == (status != 'comparable'), result
        assert all(isinstance(reason, str) and reason.strip() for reason in reasons), result
        markdown = run(['diff', *names, *flags], expected=expected).stdout
        assert markdown.strip() and all(reason in markdown for reason in reasons), markdown
        if status == 'incomparable':
            assert result['score_delta'] is None and result['regression'] is None and result['resolved'] == [], result
        if status == 'unknown':
            run(['diff', *names, '--fail-on-regression'])
        if use_mcp:
            assert result == mcp_tool('diff_reports', {
                'old_json': saved[0].decode('utf-8'), 'new_json': saved[1].decode('utf-8')}, root)
        assert all((root / name).read_bytes() == data for name, data in zip(names, saved))
    print('Installed comparison explanation checks passed: matching execution has no spurious scope reason; '
          'unknown scope and page/crawl policy gaps have readable JSON/Markdown explanations; '
          + ('MCP stdio parity checked; ' if use_mcp else '')
          + 'strict and legacy gates and saved input bytes are preserved.')


def literal_comparison_reasons(run, read, root, audit, use_mcp):
    """Untrusted saved URL labels stay evidence rather than report markup."""
    class Elements(HTMLParser):
        def __init__(self):
            super().__init__()
            self.tags, self.text = [], []

        def handle_starttag(self, tag, attrs):
            self.tags.append((tag, dict(attrs)))

        def handle_data(self, data):
            self.text.append(data)

    payload = 'https://example.test/`evidence```\n\n## Forged diff\n\n[Run](https://other.test)\n<script>bad()</script>'
    old, new = (json.loads(json.dumps(audit)) for _ in range(2))
    for data in (old, new):
        data['crawl']['pages'][0]['url'] = payload
    row = new['crawl']['pages'][0]
    row['rendered'] = row['scan_settings']['rendered'] = not row['rendered']
    names = ['literal-reason-before.json', 'literal-reason-after.json']
    saved = [json.dumps(data).encode('utf-8') for data in (old, new)]
    for name, data in zip(names, saved):
        (root / name).write_bytes(data)
    flags = ['--require-comparable', '--fail-on-regression']
    difference = json.loads(run(['diff', *names, *flags, '--format', 'json'], expected=2).stdout)
    assert difference['comparison']['status'] == 'incomparable' and difference['score_delta'] is None, difference
    assert difference['regression'] is None and difference['resolved'] == [], difference
    reasons = difference['comparison']['reasons']
    assert any(payload in reason for reason in reasons), reasons
    run(['diff', *names, *flags, '-o', 'literal-reason.md'], expected=2)
    markdown = (root / 'literal-reason.md').read_text(encoding='utf-8')
    assert '\n## Forged diff' not in markdown, markdown
    run(['render', 'literal-reason.md', '-o', 'literal-reason.html'])
    parsed = Elements()
    parsed.feed((root / 'literal-reason.html').read_text(encoding='utf-8'))
    assert not any(tag == 'script' or tag == 'a' and attrs.get('href') == 'https://other.test'
                   for tag, attrs in parsed.tags), parsed.tags
    assert all(' '.join(reason.split()) in ' '.join(parsed.text) for reason in reasons), parsed.text
    if use_mcp:
        assert difference == mcp_tool('diff_reports', {
            'old_json': saved[0].decode('utf-8'), 'new_json': saved[1].decode('utf-8')}, root)
    assert all((root / name).read_bytes() == data for name, data in zip(names, saved))
    print('Installed literal comparison reasons passed: crafted crawl labels cannot add report headings, '
          'links or script elements; exported HTML retains literal reason text, raw JSON evidence and strict rejection. '
          + ('MCP stdio parity checked.' if use_mcp else 'CLI verified.'))


def merchant_comparison_cycle(run, read, root, site, url, use_mcp):
    """A skipped price comparison is not a repaired mismatch."""
    original_sources = {p: p.read_bytes() for p in site.rglob('*') if p.is_file()}
    original_reports = {p: p.read_bytes() for p in root.glob('*.json')}
    destination = url + 'merchant/'
    target = site / 'merchant/index.html'
    target.parent.mkdir()
    snapshots = {}
    merchant_sources = {}
    options = ['scan', destination, '--allow-private', '--only', 'schema', '--no-image-checks',
               '--max-bytes', '6000000', '--no-config', '--format', 'json']
    for label, prices in (('before', ['129.00']), ('ambiguous', ['129.00', '139.00']),
                          ('unobserved', ['129.00']), ('range', ['129.00']),
                          ('missing', ['129.00']),
                          ('corrected', ['149.00', '149.00'])):
        product = {'@context': 'https://schema.org', '@type': 'Product', 'name': 'Trail Shoe',
                   'url': destination, 'image': url + 'shoe.jpg', 'description': 'A stable trail shoe.',
                   'brand': {'@type': 'Brand', 'name': 'Northstar'}, 'sku': 'TS-42',
                   'offers': [{'@type': 'Offer', 'price': price, 'priceCurrency': 'USD',
                               'availability': 'https://schema.org/InStock', 'url': destination,
                               'itemCondition': 'https://schema.org/NewCondition',
                               'seller': {'@type': 'Organization', 'name': 'Seller ' + str(index)}}
                              for index, price in enumerate(prices)]}
        if label == 'range':
            product['offers'][0].update({'@type': 'AggregateOffer', 'lowPrice': '129.00',
                                         'highPrice': '159.00', 'offerCount': 2})
        if label == 'missing':
            product['offers'][0].pop('price')
        source = ('<!doctype html><html><head><title>Trail Shoe</title>'
                  '<meta property="og:type" content="product">'
                  '<meta property="product:price:amount" content="149.00">'
                  '<meta property="product:price:currency" content="USD">'
                  '<meta property="product:availability" content="in stock">'
                  '<meta property="product:retailer_item_id" content="TS-42">'
                  '<script type="application/ld+json">' + json.dumps(product)
                  + '</script></head><body><h1>Trail Shoe</h1><button>Add to cart</button></body></html>')
        if label == 'unobserved':
            source = source.replace('<meta property="product:price:amount" content="149.00">', '')
        merchant_sources[label] = source
        target.write_text(source, encoding='utf-8')
        name = 'merchant-' + label + '.json'
        run(options + ['-o', name])
        report = read(name)
        scope = report['meta']['scan_scope']
        assert report['status'] == 200 and scope['requested'] == scope['completed'] == ['schema'], report
        snapshots[label] = report
        assert target.read_text(encoding='utf-8') == source
    saved_reports = {p: p.read_bytes() for p in root.glob('*.json')}
    mismatch = 'schema.ecommerce.price.mismatch'
    ambiguity = 'schema.ecommerce.offer.comparison.ambiguous'
    assert mismatch in {f['rule_id'] for f in snapshots['before']['findings']}
    assert mismatch not in {f['rule_id'] for f in snapshots['ambiguous']['findings']}
    assert snapshots['ambiguous']['meta']['ecommerce']['offer_comparison_status']['price'] == 'skipped_ambiguous'
    assert 'price' not in snapshots['unobserved']['meta']['ecommerce']['visible_facts']
    assert snapshots['range']['meta']['ecommerce']['aggregate_price_comparison']['within_range'] is True
    for label in ('unobserved', 'range', 'missing'):
        assert mismatch not in {f['rule_id'] for f in snapshots[label]['findings']}
        if label != 'missing':
            assert snapshots[label]['score'] > snapshots['before']['score']
        name = 'merchant-' + label + '.json'
        run(['diff', 'merchant-before.json', name, '--require-comparable', '--fail-on-regression',
             '--format', 'json', '-o', name + '.diff.json'], expected=2)
        difference = read(name + '.diff.json')
        assert difference['comparison']['status'] == 'incomparable' and difference['score_delta'] is None, difference
        assert difference['resolved'] == [], difference
        if use_mcp:
            assert difference == mcp_tool('diff_reports', {
                'old_json': json.dumps(snapshots['before']), 'new_json': json.dumps(snapshots[label])}, root)
    try:
        for label in ('before', 'unobserved'):
            target.write_text(merchant_sources[label], encoding='utf-8')
            run(['crawl', destination, '--allow-private', '--max-pages', '1', '--no-config',
                 '--format', 'json', '-o', 'merchant-crawl-' + label + '.json'])
            rows = read('merchant-crawl-' + label + '.json')['pages']
            assert len(rows) == 1 and rows[0]['url'] == destination, rows
            basis = rows[0]['merchant_comparison_basis']
            assert ('price' in basis['visible_fields']) == (label == 'before'), basis
    finally:
        target.write_text(merchant_sources['corrected'], encoding='utf-8')
    for missing in ('receipt', 'method', 'scope', 'rendered', 'rule_config'):
        crawl = read('merchant-crawl-before.json')
        crawl['pages'] = json.loads(json.dumps(crawl['pages'] * 2))
        crawl['pages_scanned'] = 2
        if missing == 'receipt':
            crawl['pages'][1].pop('merchant_comparison_basis')
        elif missing == 'method':
            crawl['pages'][1]['merchant_comparison_basis']['price_method'] = None
        elif missing == 'scope':
            crawl['pages'][1].pop('scan_scope')
        elif missing == 'rendered':
            crawl['pages'][1].pop('rendered')
            crawl['pages'][1]['scan_settings'].pop('rendered')
        else:
            crawl['pages'][1]['scan_settings'].pop('rule_config')
        supplied = {'site': url, 'overall_score': crawl['avg_score'],
                    'homepage': snapshots['corrected'], 'crawl': crawl, 'sitemap': {}}
        name = 'merchant-duplicate-' + missing + '.json'
        saved = json.dumps(supplied).encode('utf-8')
        (root / name).write_bytes(saved)
        run(['diff', name, name, '--require-comparable', '--fail-on-regression',
             '--format', 'json', '-o', name + '.diff.json'], expected=2)
        difference = read(name + '.diff.json')
        assert difference['comparison']['status'] == 'incomparable' and difference['score_delta'] is None, difference
        assert difference['resolved'] == [], difference
        if use_mcp:
            assert difference == mcp_tool('diff_reports', {
                'old_json': saved.decode('utf-8'), 'new_json': saved.decode('utf-8')}, root)
        assert (root / name).read_bytes() == saved
    run(['diff', 'merchant-missing.json', 'merchant-corrected.json', '--require-comparable', '--fail-on-regression',
         '--format', 'json', '-o', 'merchant-missing-fixed.diff.json'])
    repaired = read('merchant-missing-fixed.diff.json')
    assert repaired['comparison']['status'] == 'comparable' and repaired['score_delta'] > 0, repaired
    assert 'schema.ecommerce.offer.missing.price' in {f['rule_id'] for f in repaired['resolved']}, repaired
    if use_mcp:
        assert repaired == mcp_tool('diff_reports', {
            'old_json': json.dumps(snapshots['missing']), 'new_json': json.dumps(snapshots['corrected'])}, root)
    for label, supplied, rule in (
            ('ambiguous', snapshots['ambiguous'], ambiguity),
            ('ignored', dict(snapshots['ambiguous'], findings=[]), 'schema.ecommerce.comparison.unverified')):
        name = 'merchant-' + label + '.json'
        if label == 'ignored':
            (root / name).write_text(json.dumps(supplied), encoding='utf-8')
        run(['plan', name, '--repo', str(site), '--format', 'json', '-o', name + '.plan.json'])
        built = read(name + '.plan.json')
        action = next(a for a in built['actions'] if a['rule_id'] == rule)
        assert (action['safety'], action['manual_action'], action['requires_deploy'], action['likely_files']) == (
            'manual_external', True, False, []), action
        assert not any(rule in group['rule_ids'] for group in built['groups']), built
        run(['diff', 'merchant-before.json', name, '--require-comparable', '--fail-on-regression',
             '--format', 'json', '-o', name + '.diff.json'], expected=2)
        difference = read(name + '.diff.json')
        assert difference['comparison']['status'] == 'incomparable' and difference['score_delta'] is None, difference
        assert difference['resolved'] == [], difference
        if use_mcp:
            received = mcp_tool('plan_remediation', {'report': supplied, 'repo': 'site'}, root)
            mcp_action = next(a for a in received['actions'] if a['rule_id'] == rule)
            for key in ('rule_id', 'safety', 'manual_action', 'requires_deploy', 'likely_files', 'verification'):
                assert mcp_action[key] == action[key], (key, mcp_action, action)
            assert not any(rule in group['rule_ids'] for group in received['groups']), received
            assert difference == mcp_tool('diff_reports', {
                'old_json': json.dumps(snapshots['before']), 'new_json': json.dumps(supplied)}, root)
    run(['diff', 'merchant-before.json', 'merchant-corrected.json', '--require-comparable', '--fail-on-regression',
         '--format', 'json', '-o', 'merchant-fixed.diff.json'])
    corrected = read('merchant-fixed.diff.json')
    assert corrected['comparison']['status'] == 'comparable' and corrected['score_delta'] > 0, corrected
    assert {f['rule_id'] for f in corrected['resolved']} == {mismatch}, corrected
    if use_mcp:
        assert corrected == mcp_tool('diff_reports', {
            'old_json': json.dumps(snapshots['before']), 'new_json': json.dumps(snapshots['corrected'])}, root)
    run(['diff', 'merchant-corrected.json', 'merchant-before.json', '--require-comparable', '--fail-on-regression',
         '--format', 'json', '-o', 'merchant-reverse.diff.json'], expected=1)
    assert read('merchant-reverse.diff.json')['regression'] is True
    for label, recurring in (('null', None), ('number', 7)):
        supplied = {'site': destination, 'overall_score': snapshots['corrected']['score'],
                    'homepage': snapshots['corrected'], 'crawl': {
                        'pages_scanned': 1, 'pages': [{'url': destination}], 'recurring': recurring}, 'sitemap': {}}
        name = 'merchant-malformed-' + label + '.json'
        saved = json.dumps(supplied).encode('utf-8')
        (root / name).write_bytes(saved)
        run(['diff', name, name, '--format', 'json', '-o', name + '.diff.json'])
        difference = read(name + '.diff.json')
        aggregate = difference['crawl_rule_changes']
        assert aggregate['status'] == 'unverified' and aggregate['regression'] is None, aggregate
        assert aggregate['removed'] == [] and aggregate['reason'], aggregate
        if use_mcp:
            assert difference == mcp_tool('diff_reports', {
                'old_json': saved.decode('utf-8'), 'new_json': saved.decode('utf-8')}, root)
        assert (root / name).read_bytes() == saved
    assert all(p.read_bytes() == body for p, body in original_reports.items())
    assert all(p.read_bytes() == body for p, body in saved_reports.items())
    assert all(p.read_bytes() == body for p, body in original_sources.items())
    assert target.read_text(encoding='utf-8') == source
    print('Installed merchant comparison cycle passed: ambiguous Offers and ignored notes cannot claim a repaired price '
          'or score gain; plans require ownerless manual verification; actual consensus price correction compares '
          'and reverse regression fails. Malformed crawl aggregates remain unverified. '
          'Prior source/report bytes are preserved; no production or ranking proof.')
    print('Installed merchant basis checks passed: removing observed price or changing exact amount to range '
          'compatibility withholds score/resolution claims; native crawl receipts retain observed field coverage. '
          'Lost price checks and unknown duplicate rows cannot claim resolution; missing-price repair remains comparable.')
    print('Installed crawl setting checks passed: duplicate rows preserve missing scope, rendering and rule-configuration '
          'evidence; strict CLI/MCP comparisons withhold score and resolution claims.')


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
                comparison_explanations(run, read, root, read('before.json'), audit_before, use_mcp)
                literal_comparison_reasons(run, read, root, audit_before, use_mcp)
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
                llms_missing = 'geo.no.llms.txt'
                llms_unknown = 'geo.llms.txt.availability.unverified'
                receipt = audit_before['homepage']['meta']['llms_txt']
                assert receipt['state'] == 'observed', receipt
                for label, unsupported, homepage_gap in (('null', None, True),
                                                         ('future', dict(receipt, version=99), True),
                                                         ('crawl-only', None, False)):
                    supplied = json.loads(json.dumps(audit_before))
                    if homepage_gap:
                        supplied['homepage']['meta']['llms_txt'] = unsupported
                    supplied['crawl']['llms_txt'] = unsupported
                    stale = {'category': 'geo', 'severity': 'low', 'scope': 'site',
                             'rule_id': llms_missing, 'title': 'No root llms.txt observed'}
                    supplied['homepage']['findings'].append(stale)
                    supplied['crawl']['recurring'].append(dict(stale, count=2))
                    name = 'llms-receipt-' + label + '.json'
                    saved = json.dumps(supplied).encode('utf-8')
                    (root / name).write_bytes(saved)
                    if use_mcp:
                        received = mcp_tool('plan_remediation', {'report': supplied, 'repo': 'site'}, root)
                    else:
                        run(['plan', name, '--repo', str(site), '--format', 'json', '-o', name + '.plan.json'])
                        received = read(name + '.plan.json')
                    selected = {a['rule_id']: a for a in received['actions'] if a['rule_id'] in (llms_missing, llms_unknown)}
                    assert set(selected) == {llms_unknown}, (label, selected)
                    note = selected[llms_unknown]
                    assert note['safety'] == 'manual_external' and note['manual_action'] is True, note
                    assert note['likely_files'] == [] and note['requires_deploy'] is False, note
                    assert not any(llms_unknown in group['rule_ids'] for group in received['groups']), received
                    run(['diff', name, name, '--require-comparable', '--fail-on-regression', '--format', 'json',
                         '-o', name + '.diff.json'], expected=2)
                    difference = read(name + '.diff.json')
                    assert difference['comparison']['status'] == 'incomparable' and difference['score_delta'] is None, difference
                    assert difference['resolved'] == [], difference
                    if use_mcp:
                        assert difference == mcp_tool('diff_reports', {
                            'old_json': saved.decode('utf-8'), 'new_json': saved.decode('utf-8')}, root)
                    assert (root / name).read_bytes() == saved
                    assert source_bytes == {str(p.relative_to(site)): p.read_bytes() for p in site.rglob('*') if p.is_file()}
                print('Installed llms.txt receipt checks passed: null/future and independent crawl evidence withheld stale file-creation advice; '
                      'manual verification stayed ownerless and identical reports failed comparability.')
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
                for label in ('container', 'review-flag'):
                    supplied = json.loads(json.dumps(schema_before))
                    if label == 'container':
                        supplied['meta']['structured_data'] = None
                    else:
                        supplied['meta']['scan_settings']['schema_extraction_reviewed'] = 'true'
                    name = 'schema-unsupported-' + label + '.json'
                    saved = json.dumps(supplied).encode('utf-8')
                    (root / name).write_bytes(saved)
                    if use_mcp:
                        received = mcp_tool('plan_remediation', {'report': supplied, 'repo': 'site'}, root)
                    else:
                        run(['plan', name, '--repo', str(site), '--format', 'json', '-o', name + '.plan.json'])
                        received = read(name + '.plan.json')
                    note, = received['actions']
                    assert note['rule_id'] == 'schema.extraction.unverified' and note['safety'] == 'manual_external', note
                    assert note['manual_action'] is True and note['requires_deploy'] is False and note['likely_files'] == [], note
                    assert received['groups'] == [] and received['source_score'] == supplied['score'], received
                    run(['diff', name, name, '--require-comparable', '--fail-on-regression', '--format', 'json',
                         '-o', name + '.diff.json'], expected=2)
                    difference = read(name + '.diff.json')
                    assert difference['comparison']['status'] == 'incomparable' and difference['score_delta'] is None, difference
                    assert difference['resolved'] == [], difference
                    if use_mcp:
                        assert difference == mcp_tool('diff_reports', {
                            'old_json': saved.decode('utf-8'), 'new_json': saved.decode('utf-8')}, root)
                    assert (root / name).read_bytes() == saved
                    assert schema_sources == {str(p.relative_to(site)): p.read_bytes() for p in site.rglob('*') if p.is_file()}
                print('Installed schema receipt checks passed: unsupported containers/review flags withheld absence advice; '
                      'verification stayed ownerless and identical reports failed comparability.')
                bounded_url = url + 'bounded/'
                bounded = site / 'bounded/index.html'
                bounded.parent.mkdir()
                bounded_body = ('<!doctype html><html><head><title>Bounded schema fixture</title></head><body>'
                                '<h1>Bounded schema fixture</h1>' + ' ' * 65000
                                + '<script type="application/ld+json">'
                                + json.dumps({'@context': 'https://schema.org', '@type': 'WebSite',
                                              'name': 'Bounded schema fixture', 'url': bounded_url})
                                + '</script></body></html>')
                bounded.write_text(bounded_body, encoding='utf-8')
                schema_sources['bounded/index.html'] = bounded_body.encode('utf-8')
                bounded_options = list(schema_options)
                bounded_options[1] = bounded_url
                bounded_options[bounded_options.index('--max-bytes') + 1] = '64000'
                run(bounded_options + ['-o', 'schema-bounded.json'])
                bounded_bytes = (root / 'schema-bounded.json').read_bytes()
                limited = read('schema-bounded.json')
                assert limited['meta']['response_truncated'] is True and limited['status'] == 200, limited
                extraction = limited['meta']['structured_data']
                assert extraction['nodes_count'] == 0 and extraction['extraction_coverage']['status'] == 'no_known_problem', extraction
                assert schema_rule not in {f['rule_id'] for f in limited['findings']}, limited
                if use_mcp:
                    limited_plan = mcp_tool('plan_remediation', {'report': limited, 'repo': 'site'}, root)
                else:
                    run(['plan', 'schema-bounded.json', '--repo', str(site), '--format', 'json', '-o', 'schema-bounded-plan.json'])
                    limited_plan = read('schema-bounded-plan.json')
                note = next(a for a in limited_plan['actions'] if a['rule_id'] == 'schema.extraction.unverified')
                assert note['safety'] == 'manual_external' and note['manual_action'] is True, note
                assert note['likely_files'] == [] and note['requires_deploy'] is False, note
                assert schema_rule not in {a['rule_id'] for a in limited_plan['actions']}, limited_plan
                bounded_options[bounded_options.index('--max-bytes') + 1] = '6000000'
                run(bounded_options + ['-o', 'schema-bounded-full.json'])
                whole = read('schema-bounded-full.json')
                whole_bytes = (root / 'schema-bounded-full.json').read_bytes()
                assert whole['meta']['structured_data']['types_by_format'] == {'jsonld': ['WebSite']}, whole
                assert whole['meta']['coverage']['response_truncated'] is False, whole
                run(['diff', 'schema-bounded.json', 'schema-bounded-full.json', '--require-comparable',
                     '--fail-on-regression', '--format', 'json', '-o', 'schema-bounded-diff.json'], expected=2)
                bounded_diff = read('schema-bounded-diff.json')
                assert bounded_diff['comparison']['status'] == 'incomparable' and bounded_diff['score_delta'] is None, bounded_diff
                assert bounded_diff['resolved'] == [], bounded_diff
                if use_mcp:
                    assert bounded_diff == mcp_tool('diff_reports', {
                        'old_json': bounded_bytes.decode('utf-8'), 'new_json': whole_bytes.decode('utf-8')}, root)
                assert (root / 'schema-bounded.json').read_bytes() == bounded_bytes
                assert (root / 'schema-bounded-full.json').read_bytes() == whole_bytes
                assert schema_sources == {str(p.relative_to(site)): p.read_bytes() for p in site.rglob('*') if p.is_file()}
                print('Installed bounded schema checks passed: real HTML byte cap withheld missing-markup advice; '
                      'raising only the budget observed existing WebSite markup without claiming a source fix.')
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
                llms_reports = {p: p.read_bytes() for p in root.glob('*.json')}
                llms_path = site / 'llms.txt'
                llms_path.unlink()
                llms_sources = {str(p.relative_to(site)): p.read_bytes() for p in site.rglob('*') if p.is_file()}
                geo_options = list(options)
                geo_options[geo_options.index('--only') + 1] = 'geo'
                run(geo_options + ['-o', 'llms-before.json'])
                llms_baseline = (root / 'llms-before.json').read_bytes()
                llms_before = read('llms-before.json')
                assert llms_before['meta']['llms_txt']['state'] == 'absent', llms_before
                assert llms_before['meta']['llms_txt']['http_status'] == 404, llms_before
                if use_mcp:
                    llms_plan = mcp_tool('plan_remediation', {'report': llms_before, 'repo': 'site'}, root)
                else:
                    run(['plan', 'llms-before.json', '--repo', str(site), '--format', 'json', '-o', 'llms-plan.json'])
                    llms_plan = read('llms-plan.json')
                llms_action = next(a for a in llms_plan['actions'] if a['rule_id'] == llms_missing)
                assert llms_action['artifact'] == 'llms_txt' and llms_action['safety'] == 'deploy_verification', llms_action
                assert llms_action['requires_deploy'] is True and llms_action['manual_action'] is False, llms_action
                assert any(o['path'] == 'llms.txt' and o['exists'] is False for o in llms_action['likely_files']), llms_action
                assert any('run after deploy' in step for step in llms_action['verification']), llms_action
                assert not any('--allow-private' in step for step in llms_action['verification']), llms_action
                run(['llms', url, '--allow-private', '--max-pages', '2', '--concurrency', '1', '--no-config',
                     '-o', 'llms-starter.txt'])
                starter_bytes = (root / 'llms-starter.txt').read_bytes()
                starter = starter_bytes.decode('utf-8')
                entries = {'Local workflow verification for Narwhal development': url,
                           'Pricing and plans for local workflow verification': pricing_url}
                for title, destination in entries.items():
                    source = llms_sources['index.html' if destination == url else 'pricing/index.html'].decode('utf-8')
                    assert '<title>' + title + '</title>' in source
                assert sorted(line for line in starter.splitlines() if line.startswith('- [')) == sorted(
                    '- [' + title + '](' + destination + ')' for title, destination in entries.items()), starter
                assert 'TODO' not in starter, starter
                assert llms_sources == {str(p.relative_to(site)): p.read_bytes() for p in site.rglob('*') if p.is_file()}
                # Both entry points were inspected above; remove the starter comment for this disposable fixture.
                curated = '\n'.join(line for line in starter.splitlines() if not line.startswith('<!--')) + '\n'
                llms_path.write_text(curated, encoding='utf-8')
                run(geo_options + ['-o', 'llms-after.json'])
                llms_after = read('llms-after.json')
                llms_after_bytes = (root / 'llms-after.json').read_bytes()
                for page in (llms_before, llms_after):
                    scope = page['meta']['scan_scope']
                    assert page['status'] == 200 and scope['requested'] == scope['completed'] == ['geo'], page
                observation = llms_after['meta']['llms_txt']
                assert (observation['basis'], observation['http_status'], observation['state'], observation['reason']) == (
                    'root_http_response', 200, 'observed', 'candidate_text'), observation
                run(['diff', 'llms-before.json', 'llms-after.json', '--require-comparable', '--fail-on-regression',
                     '--format', 'json', '-o', 'llms-diff.json'])
                llms_diff = read('llms-diff.json')
                assert llms_diff['comparison']['status'] == 'comparable' and llms_diff['regression'] is False, llms_diff
                assert {f['rule_id'] for f in llms_diff['resolved']} == {llms_missing}, llms_diff
                assert [(f['rule_id'], f['severity']) for f in llms_diff['added']] == [('geo.llms.txt.published', 'good')], llms_diff
                assert llms_diff['score_delta'] > 0, llms_diff
                if use_mcp:
                    assert llms_diff == mcp_tool('diff_reports', {
                        'old_json': llms_baseline.decode('utf-8'), 'new_json': json.dumps(llms_after)}, root)
                    llms_completed = mcp_tool('plan_remediation', {'report': llms_after, 'repo': 'site'}, root)
                else:
                    run(['plan', 'llms-after.json', '--repo', str(site), '--format', 'json', '-o', 'llms-completed-plan.json'])
                    llms_completed = read('llms-completed-plan.json')
                assert not {llms_missing, llms_unknown, 'geo.llms.txt.published'} & {a['rule_id'] for a in llms_completed['actions']}
                run(['diff', 'llms-after.json', 'llms-before.json', '--require-comparable', '--fail-on-regression',
                     '--format', 'json', '-o', 'llms-regression.json'], expected=1)
                assert read('llms-regression.json')['regression'] is True
                assert (root / 'llms-before.json').read_bytes() == llms_baseline
                assert (root / 'llms-after.json').read_bytes() == llms_after_bytes
                assert (root / 'llms-starter.txt').read_bytes() == starter_bytes
                assert all(p.read_bytes() == data for p, data in llms_reports.items())
                llms_sources['llms.txt'] = curated.encode('utf-8')
                assert llms_sources == {str(p.relative_to(site)): p.read_bytes() for p in site.rglob('*') if p.is_file()}
                print('Installed llms.txt action cycle passed: observed root 404 -> deployment-required plan -> generated and inspected '
                      'entry points -> explicit fixture edit -> observed root text candidate; comparable local GEO diff and reverse '
                      'regression checked. Production root verification remains pending deployment; no engine-adoption or ranking proof.')
                merchant_comparison_cycle(run, read, root, site, url, use_mcp)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                assert not thread.is_alive(), 'Preview server did not stop'


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mcp', action='store_true', help='Also exercise installed MCP planning and diffs over stdio')
    main(use_mcp=parser.parse_args().mcp)
