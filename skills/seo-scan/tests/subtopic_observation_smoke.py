#!/usr/bin/env python3
"""Brief term-filter candidates remain reviewable, not semantic coverage verdicts."""
import argparse
import copy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import brief
from lib.report import html_document, md_to_html
from test_subtopic_observation import data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--html', type=Path, action='append', default=[])
    args = parser.parse_args(argv)
    if args.artifacts:
        args.artifacts.mkdir(parents=True, exist_ok=True)
    legacy = data()
    del legacy['subtopic_review']
    del legacy['missing_subtopics'][0]['term_match']
    malformed = data()
    malformed['missing_subtopics'][0]['term_match']['matched_terms'] = False
    values = [('synonyms', data()), ('unrelated', data('Car arrived. Insurance software changed. Costs fell.')),
              ('topic', data(topic=True)), ('legacy', legacy), ('malformed', malformed),
              ('non-ascii', data('', '汽车保险费用'))]
    docs = []
    for name, value in values:
        value = copy.deepcopy(value)
        before = brief.render_json(value)
        docs.append((name, html_document('Subtopic review QA', '', md_to_html(brief.render_markdown(value)))))
        assert before == brief.render_json(value), name
    docs += [('installed-' + str(i), path.read_text(encoding='utf-8')) for i, path in enumerate(args.html)]
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
            for name, html in docs:
                page.set_content(html)
                for mode, width in [('screen', 320), ('screen', 390), ('screen', 1100), ('print', 794)]:
                    page.emulate_media(media=mode)
                    page.set_viewport_size({'width': width, 'height': 1000})
                    text = page.inner_text('body')
                    assert 'Compared-heading candidates (review, not coverage gaps)' in text
                    assert 'synonyms can be missed' in text and 'not required sections' in text
                    assert "Missing subtopics — sections they have, your text doesn't" not in text
                    if name == 'synonyms':
                        assert '0/3 heading terms matched' in text and 'Car insurance costs' in text
                    if name == 'topic':
                        assert 'topic mode has no own-page match measurement' in text
                        assert '0/3 heading terms matched' not in text
                    if name in ('legacy', 'malformed'):
                        assert 'Term-match counts/basis unrecorded or unsupported' in text
                    if name in ('unrelated', 'non-ascii'):
                        assert 'does not establish complete topic coverage' in text
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (name, mode, width)
                    if args.artifacts and width == 390:
                        page.screenshot(path=str(args.artifacts / (name + '-390.png')), full_page=True)
                if args.artifacts and name in ('synonyms', 'topic'):
                    page.pdf(path=str(args.artifacts / (name + '.pdf')), format='A4', print_background=True)
            assert not requests, requests
        finally:
            browser.close()
    print('OK: brief heading-term counts/limits remain visible on mobile/desktop/print; no semantic absence or full-coverage verdict, JSON mutation or external requests.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
