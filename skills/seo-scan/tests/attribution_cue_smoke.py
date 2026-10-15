#!/usr/bin/env python3
"""Browser regression for literal attribution candidates and scoped reports."""

import argparse
import html
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_content
import render_report
from lib import htmlx
from lib.report import Report


def examples():
    values = ('Jane Doe', '王小明', '``` </code><script>window.attributionProbe=true</script>'
              ' [name](https://outside.test/) <img src=https://outside.test/image>',
              'https://outside.test/' + 'x' * 200)
    for index, value in enumerate(values):
        source = '<meta name="author" content="' + html.escape(value, quote=True) + '">'
        report = Report('https://example.test/guide', fetched_status=200)
        audit_content._authorship(htmlx._parse_stdlib(source, report.url), '', report, article=True)
        yield 'candidate-' + str(index), report
    for article in (True, False):
        report = Report('https://example.test/guide', fetched_status=200)
        audit_content._authorship(htmlx._parse_stdlib('<p>Filter by category.</p>', report.url),
                                 'Filter by category.', report, article=article)
        yield 'missing-' + str(article).lower(), report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--html', type=Path, help='optional installed-CLI native HTML with one byline witness')
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
            cases = []
            for name, report in examples():
                candidates = report.meta['authorship_cues']['candidates']
                expected = ('Author metadata: ' + candidates[0]['value']
                            + (' [value clipped]' if candidates[0]['truncated'] else '')) if candidates else None
                for kind, output in (('native', report.to_html()), ('markdown', render_report.render(report.to_markdown()))):
                    cases.append((name + '-' + kind, output, expected, name != 'missing-false'))
            if args.html:
                cases.append(('installed-cli', args.html.read_text(encoding='utf-8'),
                              'Leading byline-like block: By Jane Doe', True))
            for name, output, expected, has_section in cases:
                page.set_content(output)
                heading = page.get_by_role('heading', name='Attribution cue evidence (not identity verification)', exact=True)
                assert heading.count() == int(has_section), name
                if has_section:
                    evidence = heading.locator('xpath=following-sibling::pre[1]/code')
                    assert evidence.count() == 1, name
                    text = evidence.text_content()
                    if expected:
                        assert expected in text, (name, text)
                    else:
                        assert 'attribution remains unverified' in text, (name, text)
                    assert evidence.locator('*').count() == 0, name
                    assert 'writer identity, rendered visibility, expertise' in page.inner_text('body'), name
                assert page.evaluate('window.attributionProbe') is None, name
                assert page.locator('a[href^="https://outside.test/"],img[src^="https://outside.test/"]').count() == 0, name
                for mode, width, height in (('desktop', 1100, 900), ('mobile', 390, 844), ('print', 794, 1123)):
                    page.emulate_media(media='print' if mode == 'print' else 'screen')
                    page.set_viewport_size({'width': width, 'height': height})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (name, mode)
                    if has_section:
                        assert evidence.is_visible(), (name, mode)
                        assert evidence.text_content() == text, (name, mode)
                    if args.artifacts:
                        page.screenshot(path=str(args.artifacts / (name + '-' + mode + '.png')), full_page=True)
                if args.artifacts:
                    page.pdf(path=str(args.artifacts / (name + '.pdf')), format='A4', print_background=True)
            assert not requests, requests
        finally:
            browser.close()
    print('OK: literal attribution candidates/uncertainty, desktop/mobile/print, no active source markup or external requests.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
