#!/usr/bin/env python3
"""Syntax repairs and manual JSON-LD processing verification stay distinct."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan
from lib.report import html_document, md_to_html
from test_jsonld_error_stages import page, DEPTH, UNICODE, FIXTURE


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--html', type=Path, action='append', default=[])
    args = parser.parse_args(argv)
    if args.artifacts:
        args.artifacts.mkdir(parents=True, exist_ok=True)
    _, report = page([DEPTH, UNICODE])
    _, mixed = page(['{"@type":"Recipe"}', '{bad', DEPTH])
    before = report.to_json()
    result = plan.build_plan(json.loads(before), str(FIXTURE))
    assert all(a['manual_action'] and not a['likely_files'] for a in result['actions'])
    docs = [('processing-native', report.to_html()),
            ('processing-markdown', html_document('Processing QA', '', md_to_html(report.to_markdown()))),
            ('processing-plan', html_document('Plan QA', '', md_to_html(plan.render_markdown(result)))),
            ('mixed', mixed.to_html())]
    assert before == report.to_json()
    docs += [('installed-' + str(i), path.read_text(encoding='utf-8')) for i, path in enumerate(args.html)]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            browser_page = browser.new_page()
            requests = []

            def deny(route):
                requests.append(route.request.url)
                route.abort()

            browser_page.route('http://**/*', deny)
            browser_page.route('https://**/*', deny)
            for name, html in docs:
                browser_page.set_content(html)
                for mode, width in [('screen', 320), ('screen', 390), ('screen', 1100), ('print', 794)]:
                    browser_page.emulate_media(media=mode)
                    browser_page.set_viewport_size({'width': width, 'height': 1000})
                    text = browser_page.inner_text('body')
                    assert 'JSON-LD processing needs verification' in text
                    assert 'malformed blocks are ignored' not in text
                    if name.startswith('processing-'):
                        assert 'Invalid JSON-LD' not in text
                    if name == 'processing-plan':
                        assert 'not assigned (verification only)' in text
                        assert 'Verification scope: Page report' in text
                        assert 'Grouped template fixes' not in text
                    if name == 'mixed':
                        assert 'Invalid JSON-LD' in text and 'syntax error' in text
                        assert 'Recipe missing required' in text
                        assert 'https://developers.google.com/search/docs/appearance/structured-data/recipe' in text
                    assert browser_page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (name, mode, width)
                    if args.artifacts and width == 390:
                        browser_page.screenshot(path=str(args.artifacts / (name + '-390.png')), full_page=True)
                if args.artifacts and name in ('processing-native', 'processing-plan'):
                    browser_page.pdf(path=str(args.artifacts / (name + '.pdf')), format='A4', print_background=True)
            assert not requests, requests
        finally:
            browser.close()
    print('OK: JSON-LD syntax/processing remedies distinct on mobile/desktop/print; manual processing verification, JSON stable and no external requests.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
