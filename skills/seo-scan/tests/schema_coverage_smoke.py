#!/usr/bin/env python3
"""Known schema extraction gaps stay visible without absence/score claims."""
import argparse
from collections import Counter
import copy
from pathlib import Path
import sys
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import brief
import audit
import crawl_site
import compare
from lib import microdata
from lib.report import Report, html_document, md_to_html
from test_schema_coverage import page, comparison, THING, RECIPE


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--html', type=Path, action='append', default=[])
    args = parser.parse_args(argv)
    if args.artifacts:
        args.artifacts.mkdir(parents=True, exist_ok=True)
    clean, _ = page('clean', RECIPE)
    with mock.patch.object(microdata, 'MAX_ITEMS', 2):
        partial, report = page('partial', THING * 2 + RECIPE)
    values = [('compare', comparison(partial, clean), compare.render_markdown, compare.render_json),
              ('brief', brief.synthesize(partial, [clean], None), brief.render_markdown, brief.render_json)]
    legacy = copy.deepcopy(values[0][1])
    del legacy['you']['schema_extraction']
    legacy['schema_comparison']['status'] = 'no_known_problem'  # stale root cannot override facts
    legacy['gaps'].append({'what': 'Schema types: Recipe', 'who': [clean['url']], 'action': 'ADD_DUPLICATE_SCHEMA'})
    values.append(('legacy', legacy, compare.render_markdown, compare.render_json))
    docs = []
    for name, value, renderer, serializer in values:
        before = serializer(value)
        docs.append((name, html_document('Schema coverage QA', '', md_to_html(renderer(value)))))
        assert before == serializer(value), name
    before = report.to_json()
    docs += [('page-native', report.to_html()),
             ('page-markdown', html_document('Page coverage QA', '', md_to_html(report.to_markdown())))]
    assert before == report.to_json()
    site = {'base': 'https://example.test/', 'pages_scanned': 1, 'avg_score': 100,
            'pages': [{'url': 'https://example.test/leaf', 'score': 100,
                       'schema_extraction_unverified': True}], 'recurring': Counter()}
    audit_data = {'site': site['base'], 'page': Report(site['base']), 'site_result': site,
                  'sitemap': {'start': site['base'], 'seeds': []}}
    before = crawl_site.render_json(site)
    docs += [('crawl-markdown', html_document('Crawl coverage QA', '', md_to_html(crawl_site.render_markdown(site)))),
             ('audit-markdown', html_document('Audit coverage QA', '', md_to_html(audit.render_markdown(audit_data)))),
             ('audit-native', audit.render_html(audit_data))]
    assert before == crawl_site.render_json(site)
    docs += [('installed-' + str(i), path.read_text(encoding='utf-8')) for i, path in enumerate(args.html)]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page_ = browser.new_page()
            requests = []

            def deny(route):
                requests.append(route.request.url)
                route.abort()

            page_.route('http://**/*', deny)
            page_.route('https://**/*', deny)
            for name, output in docs:
                page_.set_content(output)
                for mode, width in (('screen', 320), ('screen', 390), ('screen', 1100), ('print', 794)):
                    page_.emulate_media(media=mode)
                    page_.set_viewport_size({'width': width, 'height': 1000})
                    text = page_.inner_text('body')
                    assert 'schema/overall score comparisons' in text and 'unverified' in text, name
                    assert 'Schema types: Recipe' not in text and 'ADD_DUPLICATE_SCHEMA' not in text, name
                    if name == 'legacy':
                        assert 'coverage unrecorded' in text, name
                    if name == 'brief':
                        assert 'Existing own-page markup is unverified' in text
                        assert 'Recipe' in text  # candidate remains inspectable, not an absence verdict
                    assert page_.evaluate('document.documentElement.scrollWidth <= innerWidth'), (name, mode, width)
                    if args.artifacts and width == 390:
                        page_.screenshot(path=str(args.artifacts / (name + '-390.png')), full_page=True)
                if args.artifacts and name in ('compare', 'brief'):
                    page_.pdf(path=str(args.artifacts / (name + '.pdf')), format='A4', print_background=True)
            assert not requests, requests
        finally:
            browser.close()
    print('OK: schema extraction uncertainty/observations visible on mobile/desktop/print; no false absence claim, JSON mutation or external requests.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
