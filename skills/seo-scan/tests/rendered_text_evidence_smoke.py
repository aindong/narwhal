#!/usr/bin/env python3
"""Render paired text observations without false SSR/JS-only verdicts."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan
from lib import jsdiff
from lib.report import html_document, md_to_html
from test_rendered_text_evidence import measured, RAW, REPLACED, FIXTURE


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--html', type=Path, action='append', default=[])
    args = parser.parse_args(argv)
    if args.artifacts:
        args.artifacts.mkdir(parents=True, exist_ok=True)
    docs = []
    cases = [('equal-count', RAW, REPLACED), ('shorter', RAW, '<main>Replaced content only</main>'),
             ('increase', '<main>Server intro</main>', '<main>Server intro ' + 'client ' * 98 + '</main>'),
             ('identical', RAW, RAW), ('empty', '', ''),
             ('metadata', '<main>A</main><script type="application/ld+json">{}</script>',
              '<title>T</title><main>A</main>' + '<script type="application/ld+json">{}</script>' * 2)]
    for name, raw, rendered in cases:
        dep, report = measured(raw, rendered)
        before = report.to_json()
        if name == 'empty':
            assert [(f.rule_id, f.severity) for f in report.findings] == [('technical.rendered.text.unobserved', 'low')]
        docs += [(name, report.to_html()),
                 (name + '-markdown', html_document('Paired text QA', '', md_to_html(report.to_markdown())))]
        if name == 'equal-count':
            result = plan.build_plan(json.loads(before), str(FIXTURE))
            assert all(a['manual_action'] and not a['likely_files'] and not a['requires_deploy'] for a in result['actions'])
            docs.append(('plan', html_document('Pair verification QA', '', md_to_html(plan.render_markdown(result)))))
        assert before == report.to_json()
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
            for name, output in docs:
                page.set_content(output)
                for mode, width in [('screen', 320), ('screen', 390), ('screen', 1100), ('print', 794)]:
                    page.emulate_media(media=mode)
                    page.set_viewport_size({'width': width, 'height': 1000})
                    text = page.inner_text('body')
                    for claim in ('Content is server-rendered', 'Most content requires JavaScript',
                                  'AI answer engines may not see this content', '% of the content is JS-only'):
                        assert claim not in text, (name, claim)
                    if name.startswith(('equal-count', 'shorter', 'increase')):
                        assert 'whitespace tokens' in text and 'text differs in this pair' in text
                        assert 'not a share of JS-only content' in text
                    if name.startswith('equal-count'):
                        assert '5 served vs 5 rendered' in text and 'net change +0' in text
                    if name.startswith('shorter'):
                        assert 'net change -2' in text
                    if name.startswith('identical'):
                        assert 'Selected extracted text matches' in text and 'not full-page content' in text
                    if name.startswith('empty'):
                        assert 'No selected text observed' in text
                        assert 'Selected extracted text matches' not in text
                        assert 'No flagged findings' not in text
                    if name.startswith('metadata'):
                        assert 'Some may already exist in served HTML' in text
                    if name == 'plan':
                        assert 'Not assigned' in text or 'not assigned' in text
                        assert 'before proposing source edits' in text
                        assert 'Grouped template fixes' not in text
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (name, mode, width)
                    if args.artifacts and width == 390:
                        page.screenshot(path=str(args.artifacts / (name + '-390.png')), full_page=True)
                if args.artifacts and name in ('equal-count', 'plan'):
                    page.pdf(path=str(args.artifacts / (name + '.pdf')), format='A4', print_background=True)
            assert not requests, requests
        finally:
            browser.close()
    print('OK: scoped text equality/deltas and manual render verification on mobile/desktop/print; no SSR/JS-only verdicts, JSON mutation or external rendering requests.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
