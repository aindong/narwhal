#!/usr/bin/env python3
"""Declared anchor bases: bounded browser agreement, explicit uncertainty and safe reports."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit
import crawl_site
from lib import htmlx, links, sitegraph
from lib.report import Report, html_document, md_to_html
from test_document_base_links import BASE

CASES = [
    ('', 'guide', 'https://example.test/start/guide'),
    ('<base href="/catalog/">', 'guide', 'https://example.test/catalog/guide'),
    ('<base href="https://outside.test/catalog/">', 'guide', 'https://outside.test/catalog/guide'),
    ('<base href="./assets//">', 'guide', 'https://example.test/start/assets//guide'),
    ('<base href=""><base href="https://outside.test/">', 'guide', 'https://example.test/start/guide'),
    ('<base target="_blank"><base href="/catalog/">', 'guide', 'https://example.test/catalog/guide'),
    ('<template><base href="https://outside.test/"></template><base href="/catalog/">', 'guide', 'https://example.test/catalog/guide'),
    ('<title><base href="https://outside.test/"></title><base href="/catalog/">', 'guide', 'https://example.test/catalog/guide'),
    ('<![bad]><base href="/catalog/">', 'guide', 'https://example.test/catalog/guide'),
    ('<base href="#part">', 'guide', 'https://example.test/start/guide'),
    ('<base href="data:text/plain,x">', 'guide', 'https://example.test/start/guide'),
    ('<base href="javascript:alert(1)">', 'guide', 'https://example.test/start/guide'),
    ('<base href="https:catalog/">', 'guide', 'https://example.test/start/catalog/guide'),
    ('<base href="/catalog/">', 'https://fixed.test/absolute', 'https://fixed.test/absolute'),
    ('<base href="http://[">', 'https://fixed.test/absolute', 'https://fixed.test/absolute'),
]


def fixture(head, href='guide'):
    return '<!doctype html><html><head>' + head + '</head><body><a href="' + href + '">Guide</a></body></html>'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--html', type=Path, action='append', default=[])
    args = parser.parse_args(argv)
    if args.artifacts: args.artifacts.mkdir(parents=True, exist_ok=True)
    receipt = {'basis': links.DOCUMENT_BASE_BASIS, 'status': 'unverified', 'reason': '<script>secret</script>'}
    report = Report(BASE, fetched_status=200)
    report.meta['anchor_base'] = receipt; report.meta['anchor_resolution_basis'] = links.RESOLUTION_BASIS
    site = {'base': BASE, 'pages_scanned': 1, 'avg_score': 100, 'link_resolution_basis': links.RESOLUTION_BASIS,
            'pages': [{'url': BASE, 'score': 100, 'anchor_base': receipt}], 'recurring': Counter(),
            'graph': sitegraph.analyze(BASE, [BASE], {}, [], False)}
    data = {'site': BASE, 'page': report, 'site_result': site, 'sitemap': {'start': BASE, 'seeds': []}}
    before = report.to_json()
    wrap = lambda md: html_document('Document base QA', '', md_to_html(md))
    docs = [('page-native', report.to_html()), ('page-markdown', wrap(report.to_markdown())),
            ('crawl', wrap(crawl_site.render_markdown(site))), ('audit-native', audit.render_html(data)),
            ('audit-markdown', wrap(audit.render_markdown(data)))]
    assert report.to_json() == before
    docs += [('installed-' + str(i), path.read_text(encoding='utf-8')) for i, path in enumerate(args.html)]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for head, href, expected in CASES:
                page = browser.new_page(); source = fixture(head, href); requests = []
                def source_route(route):
                    requests.append(route.request.url)
                    if route.request.url == BASE: route.fulfill(status=200, content_type='text/html', body=source)
                    else: route.abort()
                page.route('**/*', source_route); page.goto(BASE)
                observed = page.locator('a').evaluate('(a)=>{const u=new URL(a.href);u.hash="";return u.href}')
                doc = htmlx.parse(source, BASE)
                assert expected == observed == links.extract_links(doc, BASE)[0]['url'], (head, observed, expected)
                assert requests == [BASE], requests  # fulfilled in-process; no public HTTP or anchor navigation
                page.close()
            # Explicit unsupported scope must not fabricate browser-derived targets.
            for head in ('<base href="http://[">', '<base href="mailto:a@example.test">',
                         '<meta http-equiv="Content-Security-Policy" content="base-uri &apos;none&apos;"><base href="/catalog/">'):
                diagnostics = {}
                assert not links.extract_links(htmlx.parse(fixture(head), BASE), BASE, diagnostics=diagnostics)
                assert links.unassessed_base(diagnostics)
                assert diagnostics['unassessed_base_occurrences'] == 1
            page = browser.new_page(); requests = []
            def deny(route): requests.append(route.request.url); route.abort()
            page.route('http://**/*', deny); page.route('https://**/*', deny)
            for name, output in docs:
                page.set_content(output)
                for media, width in [('screen', 320), ('screen', 390), ('screen', 1100), ('print', 794)]:
                    page.emulate_media(media=media); page.set_viewport_size({'width': width, 'height': 1000})
                    body = page.inner_text('body')
                    if not name.startswith('installed-'):
                        for expected in ('Declared anchor-base observations (not scored)', 'Declared anchor base is unassessed',
                                         'not reported as dead', 'before source edits or broader crawling'):
                            assert expected in body, (name, expected)
                        assert 'secret' not in body, name
                    assert page.locator('script').count() == 0, name
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), (name, media, width)
                    if args.artifacts and width == 390:
                        page.screenshot(path=str(args.artifacts / (name + '-390.png')), full_page=True)
                if args.artifacts and name in ('page-native', 'audit-native', 'crawl'):
                    page.pdf(path=str(args.artifacts / (name + '.pdf')), format='A4', print_background=True)
            assert not requests, requests
        finally: browser.close()
    print(f'OK: {len(CASES)} bounded declared-base anchor cases agree with Chromium; unsupported bases remain unassessed across page/crawl/audit mobile/desktop/print, no JSON mutation/scripts/external requests.')
    return 0


if __name__ == '__main__': raise SystemExit(main())
