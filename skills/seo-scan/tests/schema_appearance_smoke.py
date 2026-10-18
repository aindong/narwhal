#!/usr/bin/env python3
"""Dated source-backed schema context remains visible and inert in Chromium."""
import argparse
import copy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import brief
import compare
from lib.report import html_document, md_to_html
from test_schema_appearance import MARKUP, page, comparison


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--html', type=Path, action='append', default=[])
    args = parser.parse_args(argv)
    if args.artifacts:
        args.artifacts.mkdir(parents=True, exist_ok=True)
    you, _ = page('you')
    rival, _ = page('rival', MARKUP['jsonld'])
    values = [('compare', comparison(you, rival), compare.render_markdown, compare.render_json),
              ('brief', brief.synthesize(you, [rival], None), brief.render_markdown, brief.render_json),
              ('topic', brief.synthesize(None, [rival], None, topic='Manual'), brief.render_markdown, brief.render_json)]
    legacy = copy.deepcopy(values[1][1])
    for candidate in legacy['schema']:
        del candidate['google_search_appearance']
    values.append(('legacy', legacy, brief.render_markdown, brief.render_json))
    tampered = copy.deepcopy(values[1][1])
    for candidate in tampered['schema']:
        candidate['google_search_appearance']['notices'][0]['source'] = 'https://evil.test/pixel'
    values.append(('legacy-tampered', tampered, brief.render_markdown, brief.render_json))
    docs = []
    for name, value, renderer, serializer in values:
        before = serializer(value)
        docs.append((name, html_document('Schema appearance QA', '', md_to_html(renderer(value)))))
        assert before == serializer(value), name
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
                    assert 'dated offline snapshot' in text and 'not a live Google eligibility test' in text, name
                    assert 'does not invalidate schema.org' in text, name
                    if name.startswith('legacy'):
                        assert 'snapshot unrecorded or unsupported' in text
                        assert 'retired Google Search rich-result appearance' not in text
                    else:
                        assert 'retired Google Search rich-result appearance' in text, name
                        assert '2026-10-12' in text, name
                        assert page_.get_by_role('link', name='Google source', exact=True).count() >= 1
                        for typ, url in (('FAQPage', 'https://developers.google.com/search/updates'),
                                         ('HowTo', 'https://developers.google.com/search/blog/2023/08/howto-faq-changes')):
                            if typ + ': retired Google Search' in text:
                                assert page_.locator('a[href="' + url + '"]').count() >= 1, (name, typ)
                    assert not page_.locator('[href*="evil.test"], img[src*="evil.test"]').count()
                    assert page_.evaluate('document.documentElement.scrollWidth <= innerWidth'), (name, mode, width)
                    if args.artifacts and width == 390:
                        page_.screenshot(path=str(args.artifacts / (name + '-390.png')), full_page=True)
                if args.artifacts and name in ('compare', 'brief'):
                    page_.pdf(path=str(args.artifacts / (name + '.pdf')), format='A4', print_background=True)
            assert not requests, requests
        finally:
            browser.close()
    print('OK: dated schema appearance context/links/semantic limits on mobile/desktop/print; legacy unknown, JSON stable and no external requests.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
