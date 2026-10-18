#!/usr/bin/env python3
"""Text-count scope is visible without zero-word or quality claims in Chromium."""
import argparse
from pathlib import Path
from _measurement_browser import expand_measurements
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_content
from lib import htmlx
from lib.report import Report, html_document, md_to_html


def examples():
    """Controlled source inputs, not multilingual segmentation/accuracy labels."""
    for name, language, text, unassessed in (
        ('english-short', 'en', 'A concise definition answers a question.', False),
        ('chinese', 'zh', '自然历史与海洋保护。' * 400, True),
        ('japanese', 'ja', '自然と海洋についての説明です。' * 400, True),
        ('english-accent', 'en', 'A concise résumé describes a café.', True)):
        source = '<html lang="' + language + '"><body><p>' + text + '</p></body></html>'
        report = Report('https://example.test/' + name, fetched_status=200)
        audit_content.audit(htmlx._parse_stdlib(source, report.url), None, report)
        yield name, report, unassessed


def main(argv=None):
    """Inspect native/Markdown notes on narrow/desktop screens and print input."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--html', type=Path, help='also inspect installed-CLI Chinese report')
    args = parser.parse_args(argv)
    if args.artifacts:
        args.artifacts.mkdir(parents=True, exist_ok=True)
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
            docs = []
            for name, report, unassessed in examples():
                before = report.to_json()
                docs += [(name + '-native', report.to_html(), unassessed),
                         (name + '-markdown', html_document('Text-count QA', '', md_to_html(report.to_markdown())), unassessed)]
                assert before == report.to_json()
            if args.html:
                docs.append(('installed-cli', args.html.read_text(encoding='utf-8'), True))
            for name, output, unassessed in docs:
                page.set_content(output)
                expand_measurements(page)
                for mode, width in (('screen', 320), ('screen', 390), ('screen', 1100), ('print', 794)):
                    page.emulate_media(media=mode)
                    page.set_viewport_size({'width': width, 'height': 1000})
                    note = page.get_by_role('heading', name='Text-length observation (not content quality)', exact=True)
                    assert note.count() == 1, name
                    text = page.inner_text('body')
                    assert 'Unicode code points' in text and 'ASCII-pattern matches' in text
                    assert 'not universal word counts' in text and 'not engine requirements' in text
                    assert ('Threshold review was not applied' in text) == unassessed, name
                    assert 'Thin content' not in text and '~0 words' not in text
                    assert 'Sufficient content depth' not in text
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (name, mode, width)
                    if args.artifacts and width == 390:
                        page.screenshot(path=str(args.artifacts / (name + '-390.png')), full_page=True)
                if args.artifacts and (name == 'chinese-native' or name == 'installed-cli'):
                    page.pdf(path=str(args.artifacts / (name + '.pdf')), format='A4', print_background=True)
            assert not requests, requests
        finally:
            browser.close()
    print('OK: scoped text-count notes remain visible/literal on mobile, desktop and print; no zero-word/depth verdicts or external requests.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
