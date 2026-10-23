#!/usr/bin/env python3
"""Relative anchor path fixtures agree with Chromium and remain visible in reports."""
import argparse
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit
import crawl_site
from lib import htmlx, links, sitegraph
from lib.report import Report, html_document, md_to_html
from test_relative_link_paths import BASE, CASES, source


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--html', type=Path, action='append', default=[])
    args = parser.parse_args(argv)
    if args.artifacts: args.artifacts.mkdir(parents=True, exist_ok=True)
    targets = [url for _, url in CASES[:3]]
    collected = links.extract_links(htmlx.parse(source(*[ref for ref, _ in CASES[:3]]), BASE), BASE)
    site = {'base': BASE, 'pages_scanned': 4, 'avg_score': 99, 'link_resolution_basis': links.RESOLUTION_BASIS,
            'pages': [{'url': url, 'score': 99} for url in [BASE] + targets], 'recurring': Counter(),
            'graph': sitegraph.analyze(BASE, [BASE] + targets, {BASE: collected}, [], False)}
    data = {'site': BASE, 'page': Report(BASE), 'site_result': site, 'sitemap': {'start': BASE, 'seeds': []}}
    docs = [('crawl', html_document('Relative paths QA', '', md_to_html(crawl_site.render_markdown(site)))),
            ('audit-native', audit.render_html(data))]
    docs += [('installed-' + str(i), path.read_text(encoding='utf-8')) for i, path in enumerate(args.html)]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(); requests = []
            def deny(route): requests.append(route.request.url); route.abort()
            page.route('http://**/*', deny); page.route('https://**/*', deny)
            for ref, expected in CASES:
                observed = page.evaluate('([ref,base])=>{const u=new URL(ref,base);u.hash="";return u.href}', [ref, BASE])
                assert observed == expected == links.resolve_http_link(ref, BASE), (ref, observed, expected)
            for base, ref in [('https://example.test/start//page.html', 'guide/chapter'),
                              ('https://example.test/start', 'guide//chapter'),
                              ('https://example.test', 'guide//chapter')]:
                observed = page.evaluate('([ref,base])=>new URL(ref,base).href', [ref, base])
                assert observed == links.resolve_http_link(ref, base), (base, ref, observed)
            for name, output in docs:
                page.set_content(output)
                for media, width in [('screen', 320), ('screen', 390), ('screen', 1100), ('print', 794)]:
                    page.emulate_media(media=media); page.set_viewport_size({'width': width, 'height': 1000})
                    body = page.inner_text('body')
                    if not name.startswith('installed-'):
                        for expected in targets + ['Site structure (4 crawled pages, 3 internal links)',
                                                   'Relative anchor paths preserve repeated separators',
                                                   'not full browser URL conformance or server equivalence']:
                            assert expected in body, (name, expected)
                    assert page.locator('script').count() == 0, name
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), (name, media, width)
                    if args.artifacts and width == 390:
                        page.screenshot(path=str(args.artifacts / (name + '-390.png')), full_page=True)
                if args.artifacts and not name.startswith('installed-'):
                    page.pdf(path=str(args.artifacts / (name + '.pdf')), format='A4', print_background=True)
            assert not requests, requests
        finally: browser.close()
    print('OK: bounded relative-path fixtures agree with Chromium URL resolution; distinct targets and scoped policy visible on mobile/desktop/print, no scripts or external requests.')
    return 0


if __name__ == '__main__': raise SystemExit(main())
