#!/usr/bin/env python3
"""Inspect literal date candidates and conditional advice in real Chromium."""
import argparse
import copy
import json
from pathlib import Path
from _measurement_browser import expand_measurements
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import brief
import compare
import plan
from lib.report import html_document, md_to_html
from test_date_cues import page, FIXTURE, URL


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--html', type=Path, action='append', default=[])
    args = parser.parse_args(argv)
    if args.artifacts:
        args.artifacts.mkdir(parents=True, exist_ok=True)
    docs, pages = [], []
    cases = [('modified', '<meta property="article:modified_time" content="2026-10-01">', 'Instructions.'),
             ('blank', '<meta property="article:published_time" content="   ">', 'Instructions.'),
             ('copyright', '', 'Copyright 2026 Example.'),
             ('invalid', '<meta name="date" content="not-a-date">', 'Instructions.'),
             ('literal', '<meta name="date" content="&lt;script&gt;window.dateAttack=1&lt;/script&gt;&#10;```&#10;# TITLE">', 'Instructions.'),
             ('bounded', '<meta name="date" content="' + 'X' * 5000 + '">', 'Instructions.')]
    for name, meta, text in cases:
        doc, report = page(meta, text)
        before = report.to_json()
        docs += [(name, report.to_html()),
                 (name + '-markdown', html_document('Date QA', '', md_to_html(report.to_markdown())))]
        pages.append({'url': URL, 'facts': compare.facts(report, doc), 'headings': doc.headings, 'text': doc.body_text})
        if name == 'blank':
            result = plan.build_plan(json.loads(before), str(FIXTURE))
            assert result['actions'][0]['safety'] == 'review_required'
            docs.append(('plan', html_document('Date plan QA', '', md_to_html(plan.render_markdown(result)))))
        assert before == report.to_json()
    own, rival = pages[:2]
    comparison = {'you': own['facts'], 'competitors': [rival['facts']], **compare.gap_analysis(own['facts'], [rival['facts']])}
    value = brief.synthesize(own, [rival], None)
    topic = brief.synthesize(None, [rival], None, topic='Guide')
    for name, data, renderer in [('compare', comparison, compare.render_markdown), ('brief', value, brief.render_markdown),
                                 ('topic', topic, brief.render_markdown)]:
        before = json.dumps(data, sort_keys=True)
        docs.append((name, html_document('Date QA', '', md_to_html(renderer(data)))))
        assert before == json.dumps(data, sort_keys=True)
        legacy = copy.deepcopy(data)
        legacy.setdefault('gaps', []).append({'what': 'Publish/update date', 'who': [rival['url']], 'action': 'INVENT_A_DATE'})
        legacy.setdefault('leads', []).append({'what': 'Publish/update date', 'detail': 'VERIFIED_FRESHER'})
        docs.append((name + '-legacy', html_document('Legacy date QA', '', md_to_html(renderer(legacy)))))
    docs += [('installed-' + str(i), path.read_text(encoding='utf-8')) for i, path in enumerate(args.html)]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            tab = browser.new_page()
            requests = []

            def deny(route):
                requests.append(route.request.url)
                route.abort()

            tab.route('http://**/*', deny)
            tab.route('https://**/*', deny)
            for name, output in docs:
                tab.set_content(output)
                expand_measurements(tab)
                for mode, width in [('screen', 320), ('screen', 390), ('screen', 1100), ('print', 794)]:
                    tab.emulate_media(media=mode)
                    tab.set_viewport_size({'width': width, 'height': 1000})
                    text = tab.inner_text('body')
                    for claim in ('Date/freshness signal present', 'INVENT_A_DATE', 'VERIFIED_FRESHER'):
                        assert claim not in text, (name, claim)
                    assert 'not validated dates' in text or 'only when useful and known' in text, name
                    if name.startswith(('blank', 'copyright')):
                        assert 'Review article date cues' in text
                        assert 'Date-related candidate observed' not in text
                    if name.startswith('modified'):
                        assert 'article:modified_time metadata: 2026-10-01' in text
                    if name.startswith('invalid'):
                        assert 'name=date metadata: not-a-date' in text
                    if name.startswith('literal'):
                        assert '<script>window.dateAttack=1</script> ``` # TITLE' in text
                        assert tab.evaluate('window.dateAttack === undefined')
                        assert 'TITLE' not in tab.locator('h1,h2,h3,h4,h5,h6').all_text_contents()
                    if name.startswith('bounded'):
                        assert 'X' * 160 in text and 'X' * 161 not in text
                        assert '(clipped)' in text
                    if name.startswith('topic'):
                        assert 'Your page:' not in text
                    assert tab.evaluate('document.documentElement.scrollWidth <= innerWidth'), (name, mode, width)
                    if args.artifacts and width == 390:
                        tab.screenshot(path=str(args.artifacts / (name + '-390.png')), full_page=True)
                if args.artifacts and name in ('modified', 'plan'):
                    tab.pdf(path=str(args.artifacts / (name + '.pdf')), format='A4', print_background=True)
            assert not requests, requests
        finally:
            browser.close()
    print('OK: literal bounded date witnesses, blank/year-only reviews, neutral compare/brief/topic/legacy output and conditional plans on mobile/desktop/print; no freshness verdict, JSON mutation or external rendering requests.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
