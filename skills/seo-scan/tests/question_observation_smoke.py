#!/usr/bin/env python3
"""Exact heading cues and candidate provenance in real Chromium reports."""
import argparse
import copy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import brief
import compare
from lib.report import html_document, md_to_html
from test_question_observation import page, result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--html', type=Path, action='append', default=[])
    args = parser.parse_args(argv)
    if args.artifacts:
        args.artifacts.mkdir(parents=True, exist_ok=True)
    below, zero, edge = page('below', 8, 41), page('zero', 0, 1), page('edge', 1, 5)
    values = [('below', result(zero, below), compare.render_markdown, compare.render_json),
              ('optional', result(below, edge), compare.render_markdown, compare.render_json),
              ('brief', brief.synthesize(below, [edge], None), brief.render_markdown, brief.render_json),
              ('topic', brief.synthesize(None, [edge], None, topic='Manual'), brief.render_markdown, brief.render_json)]
    # Explicit synthetic provenance, not actual Search Console acquisition.
    values[2][1]['questions'] = [{'question': 'Why do widgets drift?', 'source': 'synthetic query fixture', 'source_kind': 'gsc_query'},
                                {'question': 'How to calibrate?', 'source': edge['url'], 'source_kind': 'compared_heading'}]
    legacy = copy.deepcopy(values[2][1])
    for facts in [legacy['you']] + legacy['competitors']:
        del facts['question_cues']
    legacy['questions'] = [{'question': 'Why do widgets drift?', 'source': 'legacy string with impressions'}]
    legacy['gaps'].append({'what': 'Question-based headings', 'who': [edge['url']], 'action': 'REWRITE_ALL_HEADINGS'})
    values.append(('legacy', legacy, brief.render_markdown, brief.render_json))
    docs = []
    for name, value, renderer, serializer in values:
        before = serializer(value)
        docs.append((name, html_document('Heading cue QA', '', md_to_html(renderer(value)))))
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
                    assert page_.get_by_role('heading', name='Question-heading cues (contextual review)', exact=True).count() == 1, name
                    text = page_.inner_text('body')
                    assert 'not an engine requirement' in text and 'questions are optional' in text, name
                    assert 'REWRITE_ALL_HEADINGS' not in text and 'citable passages are what AI answer engines lift' not in text
                    assert '20%' not in text, name
                    if name == 'below':
                        assert '8/41 heading-pattern matches' in text
                        assert 'Question-heading cue difference (review)' not in text
                    if name == 'brief':
                        assert 'Recorded GSC query' in text and 'Compared-page heading; not verified query data' in text
                        assert 'Structure review (optional)' in text
                    if name == 'legacy':
                        assert 'Source kind unrecorded' in text and 'flag is unverified' in text
                        assert 'Recorded GSC query' not in text
                    assert page_.evaluate('document.documentElement.scrollWidth <= innerWidth'), (name, mode, width)
                    if args.artifacts and width == 390:
                        page_.screenshot(path=str(args.artifacts / (name + '-390.png')), full_page=True)
                if args.artifacts and name in ('below', 'brief'):
                    page_.pdf(path=str(args.artifacts / (name + '.pdf')), format='A4', print_background=True)
            assert not requests, requests
        finally:
            browser.close()
    print('OK: exact question-heading fractions/provenance/optional advice on mobile/desktop/print; JSON unchanged, no external requests.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
