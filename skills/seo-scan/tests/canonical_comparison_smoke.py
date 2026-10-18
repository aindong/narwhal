#!/usr/bin/env python3
"""Canonical observations and manual uncertainty survive screen/print rendering."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit
import crawl_site
import plan
from lib.report import html_document, md_to_html
from test_canonical_comparison import measured, URL, FIXTURE


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--html', type=Path, action='append', default=[])
    args = parser.parse_args(argv)
    if args.artifacts: args.artifacts.mkdir(parents=True, exist_ok=True)
    docs = []
    for name, href in (('same', URL), ('unicode', 'https://example.test/café'), ('different', URL + '?item=two'),
                       ('unknown', 'https://['), ('literal', '/other?x=&lt;script&gt;window.canonicalProbe=1&lt;/script&gt;')):
        doc, report = measured(href, 'https://example.test/caf%C3%A9' if name == 'unicode' else URL)
        original = report.to_json()
        docs += [(name, report.to_html()),
                 (name + '-markdown', html_document('Canonical QA', '', md_to_html(report.to_markdown())))]
        if name == 'unknown':
            result = plan.build_plan(json.loads(original), str(FIXTURE))
            docs.append(('plan', html_document('Canonical review QA', '', md_to_html(plan.render_markdown(result)))))
            site = {'base': URL, 'pages_scanned': 1, 'avg_score': report.score(),
                    'pages': [{'url': URL, 'score': report.score(), 'canonical_comparison_unverified': True}],
                    'recurring': Counter(), 'duplicates': []}
            data = {'site': URL, 'page': report, 'site_result': site, 'sitemap': {'start': URL, 'seeds': []}}
            docs += [('crawl', html_document('Crawl QA', '', md_to_html(crawl_site.render_markdown(site)))),
                     ('audit', audit.render_html(data))]
        assert original == report.to_json()
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
                    if name.startswith('same'): assert 'Self-referencing canonical' in text, name
                    if name.startswith('unicode'):
                        assert 'Self-referencing canonical' in text and 'café' in text, name
                    if name.startswith('different'):
                        assert 'Canonical points elsewhere' in text and 'query' in text, name
                    if name.startswith(('unknown', 'literal')):
                        assert 'Review unverified canonical comparison' in text, name
                        assert 'score comparisons are unverified' in text, name
                    if name in ('crawl', 'audit'):
                        assert 'HTML canonical comparison needs verification on 1 scanned page(s)' in text, name
                    if name == 'plan':
                        assert 'Manual / external' in text and 'not assigned (verification only)' in text
                        assert 'do not add duplicate' in text
                    assert page.evaluate('window.canonicalProbe === undefined'), name
                    assert page.locator('script').count() == 0, name
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), (name, media, width)
                    if args.artifacts and width == 390:
                        page.screenshot(path=str(args.artifacts / (name + '-390.png')), full_page=True)
                if args.artifacts and name in ('unknown', 'different', 'plan'):
                    page.pdf(path=str(args.artifacts / (name + '.pdf')), format='A4', print_background=True)
            assert not requests, requests
        finally: browser.close()
    print('OK: canonical component distinctions and uncertainty on mobile/desktop/print; manual-only unassessed plans, literal input, unchanged JSON and no external resource requests.')
    return 0


if __name__ == '__main__': raise SystemExit(main())
