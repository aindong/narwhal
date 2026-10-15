#!/usr/bin/env python3
"""Browser regression for branded Markdown tables; optional Playwright only."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import render_report
from lib import report


def sample_markdown():
    """Return representative readable, literal and deliberately wide tables."""
    header = '| ' + ' | '.join('Column %02d' % n for n in range(1, 15)) + ' |'
    divider = '|' + ':--|' * 14
    values = '| ' + ' | '.join('Value %02d' % n for n in range(1, 15)) + ' |'
    return ('# Report table verification\n\n## Actions\n\n'
            '| Rule \\| scope | Evidence |\n|:--|:--|\n'
            '| **Title** | `café\\|🐳` |\n'
            '| Link | [Guide](https://example.test/_guide_) |\n'
            '| Literal HTML | <script>window.tableProbe=true</script> |\n'
            '|  | Empty first cell |\n\n## Wide comparison\n\n'
            + header + '\n' + divider + '\n' + values + '\n')


def main(argv=None):
    """Verify screen, keyboard, print and native score-table style isolation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', type=Path, help='verify an installed-CLI artifact instead of rendering source')
    parser.add_argument('--artifacts', type=Path, help='optional screenshot/PDF directory')
    args = parser.parse_args(argv)
    html = args.html.read_text(encoding='utf-8') if args.html else render_report.render(sample_markdown())
    if args.artifacts:
        args.artifacts.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={'width': 1100, 'height': 950})
            requests = []
            page.route('http://**/*', lambda route: (requests.append(route.request.url), route.abort()))
            page.route('https://**/*', lambda route: (requests.append(route.request.url), route.abort()))
            page.set_content(html)
            wrappers = page.locator('.table-scroll')
            assert wrappers.count() == 2, 'Markdown tables need their own scroll containers'
            assert page.locator('table.markdown thead th[scope="col"]').count() == 16
            assert wrappers.evaluate_all('(nodes) => nodes.every(n => n.tabIndex === 0 && n.getAttribute("role") === "region" && n.getAttribute("aria-label"))')
            rows = page.locator('table tr').evaluate_all('(rows) => rows.map(r => Array.from(r.cells, c => c.textContent))')
            assert rows[0] == ['Rule | scope', 'Evidence']
            assert rows[1] == ['Title', 'café|🐳']
            assert rows[4] == ['', 'Empty first cell']
            assert len(rows[-1]) == 14 and rows[-1][-1] == 'Value 14'
            styles = page.locator('table.markdown').first.locator('th,td').evaluate_all('(cells) => cells.map(c => {const s=getComputedStyle(c); return {padding:s.padding,align:s.textAlign,border:s.borderBottomWidth}})')
            assert all(s['padding'] == '10px 12px' and s['align'] == 'left' for s in styles), styles
            assert styles[0]['border'] == '1px'
            assert page.locator('table script, table img, table code *').count() == 0
            assert page.evaluate('window.tableProbe') is None
            assert page.locator('table a').get_attribute('href') == 'https://example.test/_guide_'
            if args.artifacts:
                page.screenshot(path=str(args.artifacts / 'desktop.png'), full_page=True)

            page.set_viewport_size({'width': 390, 'height': 844})
            wide = wrappers.nth(1)
            assert wide.evaluate('(n) => n.scrollWidth > n.clientWidth'), 'Wide table must scroll locally'
            assert wide.locator('th').evaluate_all('(cells) => cells.every(c => c.getBoundingClientRect().width >= 8 * parseFloat(getComputedStyle(document.documentElement).fontSize))'), 'Columns collapsed into single-character text'
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Table widened the page'
            wide.focus()
            assert wide.evaluate('(n) => document.activeElement === n && getComputedStyle(n).outlineWidth === "2px"')
            page.keyboard.press('ArrowRight')
            page.wait_for_function('(n) => n.scrollLeft > 0', arg=wide.element_handle(), timeout=5000)
            assert page.locator('table tr').evaluate_all('(rows) => rows.map(r => Array.from(r.cells, c => c.textContent))') == rows
            if args.artifacts:
                page.screenshot(path=str(args.artifacts / 'mobile.png'), full_page=True)

            page.set_viewport_size({'width': 794, 'height': 1123})
            page.emulate_media(media='print')
            assert wrappers.evaluate_all('(nodes) => nodes.every(n => getComputedStyle(n).overflowX === "visible")')
            assert wide.evaluate('(n) => getComputedStyle(n).outlineWidth === "0px"'), 'Keyboard focus ring leaked into print'
            assert page.locator('table.markdown').evaluate_all('(nodes) => nodes.every(n => getComputedStyle(n).tableLayout === "fixed")')
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            assert page.locator('table tr').evaluate_all('(rows) => rows.map(r => Array.from(r.cells, c => c.textContent))') == rows
            if args.artifacts:
                page.screenshot(path=str(args.artifacts / 'print.png'), full_page=True)
                page.pdf(path=str(args.artifacts / 'tables.pdf'), format='A4', print_background=True)

            # Dedicated Markdown selectors must not restyle native score tables.
            page.emulate_media(media='screen')
            page.set_content(report.html_document('Score table', '', '<table class="areas"><tr><th>Area</th><th>Score</th></tr><tr><td>Technical</td><td>90</td></tr></table>'))
            cells = page.locator('table.areas th,table.areas td').evaluate_all('(cells) => cells.map(c => {const s=getComputedStyle(c);return {padding:s.padding,align:s.textAlign}})')
            assert [s['padding'] for s in cells] == ['8px 6px'] * 4
            assert [s['align'] for s in cells] == ['left', 'center', 'left', 'center']
            assert requests == [], requests
        finally:
            browser.close()
    print('OK: Markdown table styling, mobile/keyboard scrolling, print cells, inert HTML and native score-table styles.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
