#!/usr/bin/env python3
"""Contextual style observations and legacy plans on mobile and in print."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan
from lib.report import html_document, md_to_html
from test_style_review import measured, INSTRUCTIONS, QUOTED, FIXTURE, URL, RATE, COUNT, RATIO
from test_content_phrases import BASE


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--html', type=Path, action='append', default=[])
    args = parser.parse_args(argv)
    if args.artifacts: args.artifacts.mkdir(parents=True, exist_ok=True)
    docs = []
    for name, text in (('instructions', INSTRUCTIONS), ('quoted', QUOTED), ('pass', BASE)):
        report = measured(text, '<script>window.styleProbe=1</script>visible text')
        original = report.to_json()
        docs += [(name, report.to_html()),
                 (name + '-markdown', html_document('Style QA', '', md_to_html(report.to_markdown())))]
        if name == 'quoted':
            current = plan.build_plan(json.loads(original), str(FIXTURE))
            docs.append(('current-plan', html_document('Current style plan', '', md_to_html(plan.render_markdown(current)))))
        assert original == report.to_json()
    for index, (rid, title) in enumerate(((RATE, 'Filler / padding language'),
                                        (COUNT, 'Some filler phrasing'), (RATIO, 'Repetitive vocabulary'))):
        legacy = {'url': URL, 'findings': [{'category': 'content', 'severity': 'medium',
            'rule_id': rid, 'title': title, 'recommendation': 'OLD_SPUN_CLAIM'}]}
        result = plan.build_plan(legacy, str(FIXTURE))
        original = json.dumps(result, sort_keys=True)
        docs.append(('legacy-plan-' + str(index), html_document('Legacy style plan', '', md_to_html(plan.render_markdown(result)))))
        assert original == json.dumps(result, sort_keys=True)
    docs += [('installed-' + p.stem, p.read_text(encoding='utf-8')) for p in args.html]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(); requests = []
            def deny(route): requests.append(route.request.url); route.abort()
            page.route('http://**/*', deny); page.route('https://**/*', deny)
            for name, output in docs:
                page.set_content(output)
                for media, width in [('screen', 320), ('screen', 390), ('screen', 1100), ('print', 794)]:
                    page.emulate_media(media=media); page.set_viewport_size({'width': width, 'height': 1000})
                    text = page.inner_text('body')
                    for unsupported in ('heavy repetition signals', 'padding dilutes', 'OLD_SPUN_CLAIM'):
                        assert unsupported not in text, (name, unsupported)
                    if name.startswith('installed-'):
                        pass  # supplied reports have no fixture-specific finding expectation
                    elif 'plan' in name:
                        assert 'Review recorded style-pattern observation' in text, name
                        assert 'consistent technical terms' in text, name
                        assert 'not verified padding' in text, name
                    elif name.startswith('pass'):
                        assert 'Few configured style-pattern matches' in text, name
                        assert 'does not establish originality or content quality' in text, name
                    elif name.startswith(('instructions', 'quoted')):
                        assert 'Review lower type/token ratio' in text, name
                        assert 'consistent technical terms' in text, name
                    assert page.evaluate('window.styleProbe === undefined'), name
                    assert page.locator('script').count() == 0, name
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), (name, media, width)
                    if args.artifacts and width == 390:
                        page.screenshot(path=str(args.artifacts / (name + '-390.png')), full_page=True)
                if args.artifacts and name in ('quoted', 'current-plan', 'legacy-plan-2'):
                    page.pdf(path=str(args.artifacts / (name + '.pdf')), format='A4', print_background=True)
            assert not requests, requests
        finally: browser.close()
    print('OK: literal style counts and contextual current/legacy plans on mobile/desktop/print; no padding/spun diagnosis, active markup, JSON mutation or external requests.')
    return 0


if __name__ == '__main__': raise SystemExit(main())
