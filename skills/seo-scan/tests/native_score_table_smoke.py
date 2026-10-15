#!/usr/bin/env python3
"""Native score tables must remain readable inside narrow report cards."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from lib.report import Report


def examples():
    for name, categories, count in (('single', ['content'], 1),
                                    ('all-areas', ['technical', 'content', 'schema', 'geo'], 1),
                                    ('three-digit', ['content'], 137)):
        report = Report('https://example.test/synthetic/' + name, fetched_status=200)
        for category in categories:
            for severity in ('critical', 'high', 'medium', 'low', 'good'):
                for _ in range(count):
                    report.add(category, severity, 'Synthetic report-layout observation')
        yield name, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', type=Path, help='also check an installed-CLI native HTML report')
    parser.add_argument('--artifacts', type=Path)
    args = parser.parse_args(argv)
    if args.artifacts:
        args.artifacts.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            requests = []
            def deny(route):
                requests.append(route.request.url)
                route.abort()
            page.route('http://**/*', deny)
            page.route('https://**/*', deny)
            cases = [(name, report.to_html(), report) for name, report in examples()]
            if args.html:
                cases.append(('installed-cli', args.html.read_text(encoding='utf-8'), None))
            for name, output, report in cases:
                page.set_content(output)
                region = page.get_by_role('region', name='Score breakdown by area; scroll horizontally if needed', exact=True)
                assert region.count() == 1, (name, 'missing bounded score-table region')
                assert region.get_attribute('tabindex') == '0', name
                assert 'Scroll horizontally if needed to view all scores and severity counts.' in page.inner_text('body'), name
                table = region.locator('table.areas')
                assert table.locator('thead th[scope="col"]').count() == 7, name
                assert table.get_by_role('columnheader').all_text_contents() == ['Area', 'Score', '🔴', '🟠', '🟡', '🔵', '🟢'], name
                assert table.get_by_role('columnheader', name='Critical', exact=True).count() == 1, name
                for label in ('High', 'Medium', 'Low', 'Passed'):
                    assert table.get_by_role('columnheader', name=label, exact=True).count() == 1, (name, label)
                rows = table.locator('tbody tr').evaluate_all('(rows) => rows.map(r => Array.from(r.cells,c => c.textContent))')
                if report:
                    count = '137' if name == 'three-digit' else '1'
                    assert all(row[2:] == [count] * 5 for row in rows), rows
                for width in (320, 360, 390, 414, 768, 1100):
                    page.emulate_media(media='screen')
                    page.set_viewport_size({'width': width, 'height': 900})
                    region.evaluate('(n) => n.scrollLeft=0')
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (name, width, 'page overflow')
                    assert region.evaluate('(n) => n.getBoundingClientRect().right <= n.closest(".card").getBoundingClientRect().right'), (name, width, 'card overflow')
                    assert table.locator('tbody tr').evaluate_all('(rows) => rows.map(r => Array.from(r.cells,c => c.textContent))') == rows
                    if width <= 390:
                        assert region.evaluate('(n) => n.scrollWidth > n.clientWidth'), (name, width, 'unreadably compressed table')
                        region.focus()
                        assert region.evaluate('(n) => document.activeElement === n && getComputedStyle(n).outlineWidth === "2px"'), (name, width)
                        page.keyboard.press('ArrowRight')
                        try:
                            page.wait_for_function('document.querySelector(".score-table-scroll").scrollLeft > 0', timeout=10000)
                        except Exception as exc:
                            geometry = region.evaluate('(n) => ({left:n.scrollLeft,width:n.clientWidth,content:n.scrollWidth,focused:document.activeElement===n})')
                            raise AssertionError((name, width, 'ArrowRight did not scroll', geometry)) from exc
                        # Chromium animates keyboard scrolling. Observe its
                        # completion before resetting the offset or resizing;
                        # otherwise a previous animation can undo the reset.
                        settled = region.evaluate('''async n => {
                            let previous=n.scrollLeft, stable=0;
                            for(let frame=0;frame<180;frame++){
                                await new Promise(resolve=>requestAnimationFrame(resolve));
                                const current=n.scrollLeft;
                                stable=current===previous?stable+1:0;
                                previous=current;
                                if(stable>=6)return true;
                            }
                            return false;
                        }''')
                        assert settled, (name, width, 'keyboard scroll never settled')
                        region.evaluate('(n) => n.scrollLeft=n.scrollWidth')
                        assert table.locator('tbody tr').first.locator('td').last.evaluate('(n) => {const r=n.getBoundingClientRect(), p=n.closest(".score-table-scroll").getBoundingClientRect();return r.right<=p.right+1&&r.left>=p.left;}'), (name, width, 'last count inaccessible')
                    if args.artifacts and width in (320, 390, 1100):
                        region.evaluate('(n) => n.scrollLeft=0')
                        region.locator('xpath=..').screenshot(path=str(args.artifacts / (name + '-' + str(width) + '.png')))
                page.set_viewport_size({'width': 794, 'height': 1123})
                page.emulate_media(media='print')
                assert region.evaluate('(n) => getComputedStyle(n).overflowX === "visible" && getComputedStyle(n).outlineWidth === "0px"'), (name, 'print clipping/focus')
                assert table.evaluate('(n) => n.getBoundingClientRect().right <= n.closest(".card").getBoundingClientRect().right'), (name, 'print card overflow')
                assert table.locator('tbody tr').evaluate_all('(rows) => rows.map(r => Array.from(r.cells,c => c.textContent))') == rows
                if args.artifacts:
                    region.locator('xpath=..').screenshot(path=str(args.artifacts / (name + '-print.png')))
                    if name != 'three-digit':
                        page.pdf(path=str(args.artifacts / (name + '.pdf')), format='A4', print_background=True)
            assert not requests, requests
        finally:
            browser.close()
    print('OK: native score tables scroll locally/with keyboard at 320–390px; severity columns/data and print remain intact, no external requests.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
