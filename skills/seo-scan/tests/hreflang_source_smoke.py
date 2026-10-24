#!/usr/bin/env python3
"""Hreflang URL omissions and unassessed relationships stay explicit in reports."""
import argparse
from collections import Counter
import copy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit
import crawl_site
from lib import htmlx, hreflang, sitegraph
from lib.report import html_document, md_to_html
from test_hreflang_source_syntax import BASE, VALID, alts, page_report, receipt, source


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--html', type=Path, action='append', default=[])
    args = parser.parse_args(argv)
    if args.artifacts: args.artifacts.mkdir(parents=True, exist_ok=True)
    report = page_report('http://secret:password@[broken', VALID)
    measured = hreflang.analyze({BASE: alts(BASE, VALID), VALID: []},
                                coverage={BASE: receipt(BASE, VALID), VALID: receipt('/en/')})
    site = {'base': BASE, 'pages_scanned': 2, 'avg_score': report.score(), 'recurring': Counter(),
            'hreflang_policy_basis': hreflang.EXTRACTION_BASIS, 'hreflang': measured,
            'pages': [{'url': BASE, 'score': report.score(), 'hreflang_extraction': receipt(BASE, VALID), 'hreflang_comparison_unverified': False},
                      {'url': VALID, 'score': report.score(), 'hreflang_extraction': receipt('/en/'), 'hreflang_comparison_unverified': True}],
            'graph': sitegraph.analyze(BASE, [BASE, VALID], {}, [], False)}
    data = {'site': BASE, 'page': report, 'site_result': site, 'sitemap': {'start': BASE, 'seeds': []}}
    before, graph_before = report.to_json(), copy.deepcopy(measured)
    wrap = lambda md: html_document('Hreflang source QA', '', md_to_html(md))
    docs = [('page-native', report.to_html()), ('page-markdown', wrap(report.to_markdown())),
            ('crawl', wrap(crawl_site.render_markdown(site))), ('audit-native', audit.render_html(data)),
            ('audit-markdown', wrap(audit.render_markdown(data))),
            ('cluster', wrap('\n'.join(hreflang.render_markdown(measured))))]
    legacy = copy.deepcopy(measured); legacy.pop('analysis_basis'); legacy.pop('source_coverage')
    docs.append(('legacy', wrap('\n'.join(hreflang.render_markdown(legacy)))))
    hostile = hreflang.analyze({BASE: [{'lang': '<img src=x onerror=alert(1)>', 'href': BASE},
                                      {'lang': 'fr', 'href': VALID + '?x=![](https://outside.test/track)'}], VALID: []})
    docs.append(('literal', wrap('\n'.join(hreflang.render_markdown(hostile)))))
    assert before == report.to_json() and graph_before == measured
    docs += [('installed-' + str(i), path.read_text(encoding='utf-8')) for i, path in enumerate(args.html)]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(); requests = []
            def deny(route): requests.append(route.request.url); route.abort()
            page.route('http://**/*', deny); page.route('https://**/*', deny)
            # Source qualification differs from DOM navigation resolution: do not fabricate absolute annotations.
            raw = '<base href="https://example.test/catalog/">' + source('/fr/', VALID)
            page.set_content(raw)
            assert page.locator('link[hreflang]').first.get_attribute('href') == '/fr/'
            assert page.locator('link[hreflang]').first.evaluate('(link)=>link.href') == VALID
            for parser_fn in (htmlx._parse_stdlib, htmlx.parse):
                value = {}; result = hreflang.extract(parser_fn(raw, BASE), BASE, diagnostics=value)
                assert result == alts(VALID) and value['omitted'] == {'not_fully_qualified': 1}
            for name, output in docs:
                page.set_content(output)
                for media, width in [('screen', 320), ('screen', 390), ('screen', 1100), ('print', 794)]:
                    page.emulate_media(media=media); page.set_viewport_size({'width': width, 'height': 1000})
                    body = page.inner_text('body')
                    if name in ('page-native', 'page-markdown', 'audit-native', 'audit-markdown'):
                        for expected in ('HTML hreflang source coverage', '1 of 2 declarations', 'not HTTP failures',
                                         'Confirm intended language-page URLs before source edits'):
                            assert expected in body, (name, expected)
                    if name in ('crawl', 'audit-native', 'audit-markdown', 'cluster'):
                        assert 'Unassessed due to source gaps/partial snapshots: 1 directed pair(s)' in body, name
                        assert 'Missing return tags' not in body, name
                    if name == 'legacy': assert 'coverage was not recorded' in body
                    if name == 'literal': assert '<img src=x onerror=alert(1)>' in body
                    if name in ('cluster', 'legacy', 'literal'): assert '🟢' not in body
                    if not name.startswith('installed-'):
                        assert 'password' not in body, name
                    assert page.locator('script,[onerror]').count() == 0, name
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), (name, media, width)
                    if args.artifacts and width == 390:
                        page.screenshot(path=str(args.artifacts / (name + '-390.png')), full_page=True)
                if args.artifacts and name in ('page-native', 'audit-native', 'cluster'):
                    page.pdf(path=str(args.artifacts / (name + '.pdf')), format='A4', print_background=True)
            assert not requests, requests
        finally: browser.close()
    print('OK: source qualification, omitted URLs, partial/unrecorded relationship scope and literal previews across page/crawl/audit mobile/desktop/print; no mutation/scripts/external requests or rejected credential values.')
    return 0


if __name__ == '__main__': raise SystemExit(main())
