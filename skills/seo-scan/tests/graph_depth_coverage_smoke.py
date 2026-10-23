#!/usr/bin/env python3
"""Zero-edge graph evidence and depth uncertainty survive all report surfaces."""
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
from test_graph_depth_coverage import BASE, links, zero_graph


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--html', type=Path, action='append', default=[])
    args = parser.parse_args(argv)
    if args.artifacts: args.artifacts.mkdir(parents=True, exist_ok=True)
    g = zero_graph(count=7, orphans=10)
    site = {'base': BASE, 'pages_scanned': 8, 'avg_score': 99,
            'pages': [{'url': BASE, 'score': 99}], 'recurring': Counter(), 'graph': g}
    data = {'site': BASE, 'page': Report(BASE), 'site_result': site, 'sitemap': {'start': BASE, 'seeds': []}}
    before = json.dumps(g, sort_keys=True)
    wrap = lambda content: html_document('Graph coverage QA', '', md_to_html(content))
    docs = [('graph', wrap('\n'.join(sitegraph.render_markdown(g)))),
            ('crawl', wrap(crawl_site.render_markdown(site))),
            ('audit', wrap(audit.render_markdown(data))), ('audit-native', audit.render_html(data))]
    absent = sitegraph.analyze(BASE, [BASE + 'absent/a', BASE + 'absent/b'],
                               {BASE + 'absent/a': links(BASE + 'absent/b')}, [], False)
    legacy = copy.deepcopy(g); del legacy['depth_coverage']
    empty = sitegraph.analyze(BASE, [], {}, [], False)
    for name, graph in [('absent', absent), ('legacy', legacy), ('empty', empty)]:
        docs.append((name, wrap('\n'.join(sitegraph.render_markdown(graph)))))
    literal_url = BASE + 'unlinked/<img src=x onerror=alert(1)>'
    literal = sitegraph.analyze(BASE, [BASE, literal_url], {}, [], False)
    docs.append(('literal', wrap('\n'.join(sitegraph.render_markdown(literal)))))
    assert before == json.dumps(g, sort_keys=True)
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
                    body = page.inner_text('body')
                    if name in ('graph', 'crawl', 'audit', 'audit-native', 'legacy'):
                        for expected in ('Site structure (8 crawled pages, 0 internal links)',
                                         'zero recorded edges does not prove the site has no links',
                                         'No inbound internal links observed in the sample (7)',
                                         'Orphan candidates', BASE + 'outside/7', BASE + 'unlinked/4',
                                         '… +2 more (see JSON)', 'larger cap does not itself repair missing edges'):
                            assert expected in body, (name, expected)
                        assert BASE + 'outside/8' not in body, name
                        assert BASE + 'unlinked/5' not in body, name
                    if name in ('graph', 'crawl', 'audit', 'audit-native'):
                        assert 'among 1 reachable of 8 supplied graph nodes' in body, name
                    elif name in ('absent', 'empty'):
                        assert 'Depth from the start URL is unassessed' in body, name
                        assert 'not a measured zero-hop site' in body, name
                    elif name == 'legacy':
                        assert 'start/BFS coverage is unrecorded or unsupported' in body
                        assert 'listed as unreachable (start/BFS scope unverified)' in body
                    elif name == 'literal':
                        assert literal_url in body
                    # Optional complete reports may contain unrelated passing checks.
                    if not name.startswith('installed-'):
                        assert '🟢' not in body, name
                    assert page.locator('script').count() == 0, name
                    assert page.locator('[onerror]').count() == 0, name
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), (name, media, width)
                    if args.artifacts and width == 390:
                        page.screenshot(path=str(args.artifacts / (name + '-390.png')), full_page=True)
                if args.artifacts and name in ('graph', 'audit-native', 'absent'):
                    page.pdf(path=str(args.artifacts / (name + '.pdf')), format='A4', print_background=True)
            assert not requests, requests
        finally: browser.close()
    print('OK: zero-edge observations, bounded lists and known/absent/legacy BFS scope on mobile/desktop/print; no JSON mutation, scripts or external requests.')
    return 0


if __name__ == '__main__': raise SystemExit(main())
