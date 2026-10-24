#!/usr/bin/env python3
"""Chromium regression: page headlines describe findings, not page quality."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from lib.report import Report
from test_http_terminal_status import scanned


def cases():
    """Controlled reported findings, including unknown and incomplete scope."""
    entries = [('critical', 'critical', 'Critical findings first'),
               ('high', 'high', 'High-priority findings'),
               ('medium', 'medium', 'Medium-priority findings'),
               ('low', 'low', 'Low-priority findings'),
               ('passed', 'good', 'No flagged findings'),
               ('empty', None, 'No flagged findings'),
               ('full-empty', None, 'No flagged findings'),
               ('legacy-empty', None, 'No flagged findings'),
               ('unmeasured', 'critical', 'Not Measured'),
               ('no-completed', None, 'Not Measured')]
    for name, severity, expected in entries:
        groups = ['technical', 'content', 'schema', 'geo'] if name == 'full-empty' else ['geo']
        report = Report('https://example.test/synthetic/' + name, fetched_status=200,
                        meta={'scan_scope': {'requested': groups, 'completed': groups}})
        if severity:
            report.add('geo', severity, 'Synthetic QA observation', 'Not an SEO judgment',
                       'Review this synthetic example only.')
        if name == 'legacy-empty':
            report.meta = {}
        if name == 'unmeasured':
            report.hard_fail = True
            report.fetched_status = 404
        if name in ('unmeasured', 'no-completed'):
            report.meta['scan_scope']['completed'] = []
        yield name, report, expected
    # Real scanner execution (only HTTP mocked) must not score terminal bodies.
    for status in (301, 304):
        yield 'terminal-' + str(status), scanned(status, body='' if status == 304 else '<html><h1>Redirect body</h1></html>'), 'Not Measured'


def main(argv=None):
    """Check actual CSS-transformed headlines, scope, responsive/print and data."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, help='optional screenshots and PDF output directory')
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
            for name, report, expected in cases():
                before, markdown = report.to_json(), report.to_markdown()
                page.set_content(report.to_html())
                for mode, width, height in (('desktop', 1100, 900), ('mobile', 390, 844), ('print', 794, 1123)):
                    page.emulate_media(media='print' if mode == 'print' else 'screen')
                    page.set_viewport_size({'width': width, 'height': height})
                    headline = page.locator('.hero .grade')
                    assert headline.is_visible()
                    assert headline.text_content() == expected, (name, mode)
                    # Existing CSS capitalizes words; compare visible wording too.
                    assert headline.inner_text().casefold() == expected.casefold(), (name, mode)
                    hero = page.locator('.hero').inner_text()
                    if expected == 'Not Measured':
                        assert 'Score band:' not in hero
                    else:
                        assert '(reported findings, not page quality)' in hero
                    gauge = page.locator('.hero .gauge')
                    assert gauge.get_attribute('aria-label') == f'{report.score_label()} {report.score()} of 100'
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (name, mode)
                    if args.artifacts:
                        page.screenshot(path=str(args.artifacts / (name + '-' + mode + '.png')), full_page=True)
                assert 'All checks passed' not in page.inner_text('body')
                if name == 'legacy-empty':
                    assert 'Auditor selection was not recorded' in page.inner_text('body')
                if name == 'full-empty':
                    assert 'not a site-wide or exhaustive validation' in page.inner_text('body')
                assert report.to_json() == before and report.to_markdown() == markdown
                if args.artifacts:
                    page.pdf(path=str(args.artifacts / (name + '.pdf')), format='A4', print_background=True)
            assert not requests, requests
        finally:
            browser.close()
    print('OK: page headlines reflect findings/unknown scope on desktop/mobile/print; scores/data unchanged, no external requests.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
