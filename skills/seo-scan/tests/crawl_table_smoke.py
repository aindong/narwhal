#!/usr/bin/env python3
"""Chromium regression for literal crawl-table values and responsive output."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import crawl_site
from lib import report


def fixture():
    """Include table pipes, apparent links/emphasis, code and literal slashes."""
    base = 'https://example.test/'
    return {'base': base, 'pages_scanned': 4, 'avg_score': 75,
            'pages': [{'url': base + suffix, 'score': 75} for suffix in
                      ('catalog|featured', '[guide](https://outside.test/)', '_topic_/', r'a\|`b`')],
            'recurring': Counter(), 'links': {'checked': 1, 'skipped_over_cap': 0,
                'broken': [{'status': 0, 'error': 'request | [error](https://outside.test/) ~~timeout~~  Bad\tGateway',
                            'internal': False, 'url': base + 'a|b', 'sources': [base + '`source`']}]}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', type=Path, help='actual installed-CLI HTML artifact')
    parser.add_argument('--json', type=Path, help='matching crawl JSON for expected URLs')
    parser.add_argument('--artifacts', type=Path)
    args = parser.parse_args(argv)
    data = json.loads(args.json.read_text()) if args.json else fixture()
    html = args.html.read_text() if args.html else report.html_document(
        'Literal crawl tables', '', report.md_to_html(crawl_site.render_markdown(data)))
    expected = [[str(page['score']), page['url']] for page in sorted(data['pages'], key=lambda page: page['score'])[:10]]
    if args.artifacts:
        args.artifacts.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={'width': 1100, 'height': 950})
            requests = []
            def deny(route):
                requests.append(route.request.url)
                route.abort()
            page.route('http://**/*', deny)
            page.route('https://**/*', deny)
            page.set_content(html)
            heading = page.get_by_role('heading', name='Weakest pages', exact=True)
            table = heading.locator('xpath=following-sibling::div[1]//table')
            def verify():
                rows = table.locator('tbody tr').evaluate_all('(rows) => rows.map(r => Array.from(r.cells, c => c.textContent))')
                assert rows == expected, rows
                assert table.locator('tbody td a,tbody td em,tbody td strong,tbody td img,tbody td script').count() == 0
            verify()
            if not args.html:
                broken = page.get_by_role('heading', name='Broken or unreachable targets (1 of 1 checked)', exact=True).locator('xpath=following-sibling::div[1]//table')
                assert broken.locator('tbody tr td').all_text_contents() == [
                    'request | [error](https://outside.test/) ~~timeout~~  Bad\tGateway', 'external', 'https://example.test/a|b', 'https://example.test/`source`']
                assert broken.locator('a,em,strong,del,img,script').count() == 0
            if args.artifacts:
                heading.scroll_into_view_if_needed()
                page.screenshot(path=str(args.artifacts / 'desktop.png'))
            page.set_viewport_size({'width': 390, 'height': 844})
            verify()
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            if args.artifacts:
                heading.scroll_into_view_if_needed()
                page.screenshot(path=str(args.artifacts / 'mobile.png'))
            page.emulate_media(media='print')
            verify()
            if args.artifacts:
                page.pdf(path=str(args.artifacts / 'crawl.pdf'), format='A4', print_background=True)
            assert requests == [], requests
        finally:
            browser.close()
    print('OK: crawl table cells preserve literal data on desktop/mobile/print, without injected table markup or external requests.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
