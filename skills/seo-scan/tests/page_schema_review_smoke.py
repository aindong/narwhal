#!/usr/bin/env python3
"""Partial schema scans/plans verify extraction instead of generating duplicates."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan
from lib.report import html_document, md_to_html
from test_page_schema_review import partial, page, payload, FIXTURE, ABSENCE


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--html', type=Path, action='append', default=[])
    args = parser.parse_args(argv)
    if args.artifacts:
        args.artifacts.mkdir(parents=True, exist_ok=True)
    report = partial()
    before = report.to_json()
    result = plan.build_plan(payload(report), str(FIXTURE))
    assert not ABSENCE & {f.rule_id for f in report.findings}
    assert all(a['manual_action'] and not a['likely_files'] for a in result['actions'])
    docs = [('page-native', report.to_html()),
            ('page-markdown', html_document('Schema QA', '', md_to_html(report.to_markdown()))),
            ('plan', html_document('Plan QA', '', md_to_html(plan.render_markdown(result)))),
            ('clean', page('').to_html())]
    assert before == report.to_json()
    docs += [(('installed-plan-' if path.stem.endswith('-plan') else
               'installed-audit-' if path.stem == 'audit' else 'installed-page-') + str(i),
              path.read_text(encoding='utf-8')) for i, path in enumerate(args.html)]
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
                    assert 'unlock rich results' not in text
                    if name == 'clean':
                        assert 'before adding applicable semantic markup' in text
                        assert 'benefits are not established' in text
                    elif name == 'plan' or name.startswith('installed-plan-'):
                        assert 'not assigned (verification only)' in text
                        assert 'Do not add or duplicate markup' in text
                        assert 'Related actions to review' not in text
                    elif name.startswith(('page-', 'installed-page-')):
                        assert 'schema/overall score comparisons are unverified' in text
                        assert 'No Organization/WebSite entity' not in text
                        assert 'Article-like page without Article schema' not in text
                        assert 'Product page has no Product structured data' not in text
                    elif name.startswith('installed-audit-'):
                        assert 'schema/overall score comparisons' in text and 'unverified' in text
                    assert browser_page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (name, mode, width)
                    if args.artifacts and width == 390:
                        browser_page.screenshot(path=str(args.artifacts / (name + '-390.png')), full_page=True)
                if args.artifacts and name in ('page-native', 'plan'):
                    browser_page.pdf(path=str(args.artifacts / (name + '.pdf')), format='A4', print_background=True)
            assert not requests, requests
        finally:
            browser.close()
    print('OK: partial schema page/planner verification and conditional healthy advice on mobile/desktop/print; no duplicate generation, JSON mutation or external requests.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
