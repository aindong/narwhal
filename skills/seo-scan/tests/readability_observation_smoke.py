#!/usr/bin/env python3
"""Render scoped readability inputs without comprehension/citability verdicts."""
import argparse
import json
from pathlib import Path
from _measurement_browser import expand_measurements
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan
from lib.report import html_document, md_to_html
from test_readability_observation import measured, FIXTURE


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--html', type=Path, action='append', default=[])
    args = parser.parse_args(argv)
    if args.artifacts:
        args.artifacts.mkdir(parents=True, exist_ok=True)
    docs = []
    cases = [('short', 'Controlled guide Useful instructions.', {'article': True}),
             ('passing', 'Use the tool. Check the page.', {}),
             ('mixed', 'API 这是使用说明。', {'language':'en'}),
             ('accented', 'A café guide.', {'language':'en'}),
             ('foreign', 'A concise definition.', {'language':'fr'}),
             ('hub', 'Useful site links. More pages.', {'hub':True}), ('empty', '', {})]
    for name, sample, options in cases:
        report = measured(sample, **options)
        before = report.to_json()
        docs += [(name, report.to_html()),
                 (name + '-markdown', html_document('Readability QA', '', md_to_html(report.to_markdown())))]
        if name == 'short':
            result = plan.build_plan(json.loads(before), str(FIXTURE))
            assert result['actions'][0]['safety'] == 'review_required'
            docs.append(('plan', html_document('Audience review QA', '', md_to_html(plan.render_markdown(result)))))
            legacy = json.loads(before)
            legacy['findings'][0].update(title='Content is very hard to read', severity='medium',
                                         recommendation='harder for readers and for AI engines to quote cleanly')
            result = plan.build_plan(legacy, str(FIXTURE))
            saved = json.dumps(result, sort_keys=True)
            docs.append(('legacy-plan', html_document('Recorded formula review QA', '', md_to_html(plan.render_markdown(result)))))
            assert saved == json.dumps(result, sort_keys=True)
        assert before == report.to_json()
    docs += [('installed-' + p.stem, p.read_text(encoding='utf-8')) for p in args.html]
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
                for media, width in [('screen',320),('screen',390),('screen',1100),('print',794)]:
                    tab.emulate_media(media=media)
                    tab.set_viewport_size({'width':width,'height':1000})
                    text = tab.inner_text('body')
                    for claim in ('Content is very hard to read', 'Content is fairly hard to read',
                                  'Readable prose', 'harder for readers and for AI engines to quote cleanly'):
                        assert claim not in text, (name, claim)
                    if name == 'installed-compare':
                        assert 'Page readability-formula review' in text and 'Uninterpreted' in text
                    elif name != 'installed-brief':
                        assert 'not measured reader comprehension' in text or 'do not establish reader comprehension' in text
                    if name.startswith('short'):
                        assert '4 ASCII-pattern matches' in text
                        assert '1 punctuation-split fragments' in text
                        assert 'estimate -8.7' in text and 'estimate 15.5' in text
                        assert 'Review below-30 readability formula estimate' in text
                    if name.startswith('passing'):
                        assert 'No below-range readability formula flag' in text
                        assert 'estimate -2.6' in text
                    if name.startswith(('mixed','accented','foreign','hub','empty')):
                        assert 'Formula interpretation withheld' in text
                        assert 'No below-range readability formula flag' not in text
                        assert 'Review below-' not in text
                    if name in ('plan','legacy-plan'):
                        assert 'preserve necessary technical terms' in text
                        assert 'Do not pad or rewrite solely to reach a formula target' in text
                        assert 'Input report priority retained' in text
                    assert tab.evaluate('document.documentElement.scrollWidth <= innerWidth'), (name,media,width)
                    if args.artifacts and width == 390:
                        tab.screenshot(path=str(args.artifacts/(name+'-390.png')),full_page=True)
                if args.artifacts and name in ('short','plan'):
                    tab.pdf(path=str(args.artifacts/(name+'.pdf')),format='A4',print_background=True)
            assert not requests, requests
        finally:
            browser.close()
    print('OK: literal formula inputs/estimates, uninterpreted unsupported samples and conditional audience plans on mobile/desktop/print; no comprehension/citability verdicts, JSON mutation or external rendering requests.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
