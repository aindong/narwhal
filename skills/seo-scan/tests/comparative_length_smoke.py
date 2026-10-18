#!/usr/bin/env python3
"""Neutral text-length observations in real rendered comparison/brief reports."""
import argparse
import copy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import brief
import compare
from lib import htmlx
from lib.report import Report, html_document, md_to_html


def examples():
    """Controlled counts demonstrate units, not independent SEO accuracy."""
    pages = []
    for name, text in (('you', '自然历史与海洋保护。' * 600), ('rival', 'word ' * 600)):
        url = 'https://' + name + '.test/guide'
        doc = htmlx.Doc(url, title='Guide', text=text, headings=[(1, 'Guide')])
        report = Report(url, fetched_status=200)
        pages.append({'url': url, 'facts': compare.facts(report, doc),
                      'headings': doc.headings, 'text': text})
    you, rival = pages
    data = {'you': you['facts'], 'competitors': [rival['facts']], 'failed': [],
            **compare.gap_analysis(you['facts'], [rival['facts']])}
    yield 'compare', data, compare.render_markdown, compare.render_json, True
    yield 'brief', brief.synthesize(you, [rival], None), brief.render_markdown, brief.render_json, True
    yield 'topic', brief.synthesize(None, [rival], None, topic='Marine guide'), brief.render_markdown, brief.render_json, True
    legacy = copy.deepcopy(data)
    del legacy['text_length']
    for facts in [legacy['you']] + legacy['competitors']:
        del facts['text_length']
    legacy['gaps'].append({'what': 'Content depth', 'who': [rival['url']], 'action': 'EXPAND_TO_TARGET'})
    yield 'legacy-compare', legacy, compare.render_markdown, compare.render_json, False
    old_brief = brief.synthesize(you, [rival], None)
    del old_brief['text_length']
    for facts in [old_brief['you']] + old_brief['competitors']:
        del facts['text_length']
    old_brief['structure']['target_words'] = '<img src="https://evil.test/pixel">'
    old_brief['structure']['your_words'] = 1
    yield 'legacy-brief', old_brief, brief.render_markdown, brief.render_json, False


def main(argv=None):
    """Check visible notes, literal legacy treatment, layout and network silence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--html', type=Path, action='append', default=[],
                        help='also inspect a rendered installed-CLI comparison/brief')
    args = parser.parse_args(argv)
    if args.artifacts:
        args.artifacts.mkdir(parents=True, exist_ok=True)
    docs = []
    for name, value, renderer, serializer, known in examples():
        before = serializer(value)
        output = html_document('Comparative length QA', '', md_to_html(renderer(value)))
        assert before == serializer(value), name
        docs.append((name, output, known))
    docs += [('installed-' + str(i), path.read_text(encoding='utf-8'), True)
             for i, path in enumerate(args.html)]
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
            for name, output, known in docs:
                page.set_content(output)
                for mode, width in (('screen', 320), ('screen', 390), ('screen', 1100), ('print', 794)):
                    page.emulate_media(media=mode)
                    page.set_viewport_size({'width': width, 'height': 1000})
                    heading = page.get_by_role('heading', name='Extracted-text length (not a target)', exact=True)
                    assert heading.count() == 1, name
                    text = page.inner_text('body')
                    assert 'not universal word counts or content depth' in text, name
                    assert 'counts alone do not establish a writing target' in text, name
                    assert 'Ranking and citation impact are not measured' in text, name
                    assert ('recorded range' in text) == known, name
                    assert 'deepest compared page' not in text and 'EXPAND_TO_TARGET' not in text, name
                    assert 'Your page: 0 whitespace tokens' not in text, name
                    assert not page.locator('img[src*="evil.test"]').count(), name
                    if not known:
                        assert 'unrecorded' in text, name
                    if name == 'compare':
                        assert '6000' in text and '1 whitespace tokens' in text, name
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (name, mode, width)
                    if args.artifacts and width == 390:
                        page.screenshot(path=str(args.artifacts / (name + '-390.png')), full_page=True)
                if args.artifacts and name in ('compare', 'brief'):
                    page.pdf(path=str(args.artifacts / (name + '.pdf')), format='A4', print_background=True)
            assert not requests, requests
        finally:
            browser.close()
    print('OK: neutral comparative-length notes on mobile/desktop/print; legacy targets not advice; JSON unchanged and no external requests.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
