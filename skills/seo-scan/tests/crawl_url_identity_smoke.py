#!/usr/bin/env python3
"""Distinct graph URL observations stay visible in native and rendered reports."""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit
import crawl_site
from lib import sitegraph
from lib.report import Report, html_document, md_to_html
from test_crawl_url_identity import BASE, VARIANTS, graph, links


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--html', type=Path, action='append', default=[])
    args = parser.parse_args(argv)
    if args.artifacts: args.artifacts.mkdir(parents=True, exist_ok=True)
    measured = graph()
    site = {'base': BASE, 'pages_scanned': 5, 'avg_score': 99,
            'pages': [{'url': url, 'score': 99} for url in [BASE] + VARIANTS],
            'recurring': Counter(), 'graph': measured}
    data = {'site': BASE, 'page': Report(BASE), 'site_result': site, 'sitemap': {'start': BASE, 'seeds': []}}
    before = json.dumps(measured, sort_keys=True)
    docs = [('graph', html_document('Graph identity QA', '', md_to_html('\n'.join(sitegraph.render_markdown(measured))))),
            ('crawl', html_document('Crawl identity QA', '', md_to_html(crawl_site.render_markdown(site)))),
            ('audit', html_document('Audit identity QA', '', md_to_html(audit.render_markdown(data)))),
            ('audit-native', audit.render_html(data))]
    legacy = copy.deepcopy(measured); del legacy['url_identity_basis']
    docs.append(('legacy', html_document('Legacy identity QA', '', md_to_html('\n'.join(sitegraph.render_markdown(legacy))))))
    orphan = sitegraph.analyze(BASE, [BASE, VARIANTS[0]], {BASE: links(VARIANTS[0])}, VARIANTS, True)
    docs.append(('orphans', html_document('Orphan identity QA', '', md_to_html('\n'.join(sitegraph.render_markdown(orphan))))))
    none = sitegraph.analyze(BASE, [BASE, VARIANTS[0], VARIANTS[1]],
                             {BASE: links(VARIANTS[0])}, [VARIANTS[1]], True)
    docs.append(('none', html_document('No additional candidates QA', '', md_to_html('\n'.join(sitegraph.render_markdown(none))))))
    assert before == json.dumps(measured, sort_keys=True)
    docs += [('installed-' + str(i), path.read_text(encoding='utf-8')) for i, path in enumerate(args.html)]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(); requests = []
            def deny(route): requests.append(route.request.url); route.abort()
            page.route('http://**/*', deny); page.route('https://**/*', deny)
            for name, output in docs:
                page.set_content(output)
                for media, width in [('screen', 320), ('screen', 390), ('screen', 1100), ('print', 794)]:
                    page.emulate_media(media=media); page.set_viewport_size({'width': width, 'height': 1000})
                    text = page.inner_text('body')
                    if name in ('graph', 'crawl', 'audit', 'audit-native', 'legacy'):
                        assert 'Site structure (5 crawled pages' in text, name
                        for url in VARIANTS: assert url in text, (name, url)
                    if name == 'legacy': assert 'URL identity policy was not recorded' in text
                    elif not name.startswith('installed-'):
                        assert 'Other path/query literals remain distinct' in text, name
                    if name == 'orphans': assert 'Orphan candidates (3 sitemap URLs' in text
                    if name == 'none': assert 'this does not prove every sitemap URL is linked' in text
                    assert page.locator('script').count() == 0, name
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), (name, media, width)
                    if args.artifacts and width == 390:
                        page.screenshot(path=str(args.artifacts / (name + '-390.png')), full_page=True)
                if args.artifacts and name in ('graph', 'audit-native', 'orphans'):
                    page.pdf(path=str(args.artifacts / (name + '.pdf')), format='A4', print_background=True)
            assert not requests, requests
        finally: browser.close()
    print('OK: distinct graph URL observations and scoped orphan/legacy policy notes on mobile/desktop/print; no JSON mutation, active markup or external rendering requests.')
    return 0


if __name__ == '__main__': raise SystemExit(main())
