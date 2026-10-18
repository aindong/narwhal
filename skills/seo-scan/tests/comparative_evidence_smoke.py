#!/usr/bin/env python3
"""Comparison/brief lexical cues stay non-prescriptive in actual Chromium."""
import argparse
import copy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import brief
import compare
from lib.report import html_document, md_to_html
from test_comparative_evidence import page, result


def main(argv=None):
    """Inspect current/legacy/mobile/print reports without following source links."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--html', type=Path, action='append', default=[])
    args = parser.parse_args(argv)
    if args.artifacts:
        args.artifacts.mkdir(parents=True, exist_ok=True)
    own = page('linked', '<h1>Manual</h1><p>Consult the '
               '<a href="https://primary.test/spec">original specification</a>.</p>')
    rival = page('labels', '<h1>Labels</h1><p>study research report survey cited source: according to</p>')
    values = [('compare', result(own, rival), compare.render_markdown, compare.render_json),
              ('brief', brief.synthesize(own, [rival], None), brief.render_markdown, brief.render_json),
              ('topic-zero', brief.synthesize(None, [own], None, topic='Manual'), brief.render_markdown, brief.render_json)]
    legacy = copy.deepcopy(values[1][1])
    for facts in [legacy['you']] + legacy['competitors']:
        del facts['evidence_cues']
    legacy['gaps'].append({'what': 'Evidence density (stats/citations)', 'who': [rival['url']], 'action': 'ADD_TO_QUOTA'})
    legacy['structure'].update({'evidence_target': '<img src="https://evil.test/pixel">', 'your_evidence': 0})
    values.append(('legacy', legacy, brief.render_markdown, brief.render_json))
    docs = []
    for name, value, renderer, serializer in values:
        before = serializer(value)
        docs.append((name, html_document('Cue observation QA', '', md_to_html(renderer(value)))))
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
                    assert page_.get_by_role('heading', name='Statistics/citation cues (not verified evidence)', exact=True).count() == 1, name
                    text = page_.inner_text('body')
                    assert 'not verified statistics, citations or sources' in text, name
                    assert 'do not invent statistics or citations' in text, name
                    assert 'source validity, ranking and citation impact are not measured' in text, name
                    assert 'ADD_TO_QUOTA' not in text and 'add concrete numbers' not in text, name
                    assert 'they carry ~0' not in text, name
                    assert not page_.locator('img[src*="evil.test"]').count(), name
                    if name == 'legacy':
                        assert 'Legacy evidence-target fields' in text and 'basis unrecorded' in text
                    if name == 'topic-zero':
                        assert '0–0 combined pattern matches' in text and 'Your page:' not in text
                    assert page_.evaluate('document.documentElement.scrollWidth <= innerWidth'), (name, mode, width)
                    if args.artifacts and width == 390:
                        page_.screenshot(path=str(args.artifacts / (name + '-390.png')), full_page=True)
                if args.artifacts and name in ('compare', 'brief'):
                    page_.pdf(path=str(args.artifacts / (name + '.pdf')), format='A4', print_background=True)
            assert not requests, requests
        finally:
            browser.close()
    print('OK: cue counts/limits visible on mobile/desktop/print; no source quota, JSON mutation or external requests.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
