#!/usr/bin/env python3
"""Reported quick-win previews stay literal, readable and bounded in Chromium."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_technical
from lib import htmlx
from lib.report import Report, html_document, md_to_html


def cases():
    """Controlled reported fields, not real-site judgments or accuracy labels."""
    report = Report('https://example.test/guide', fetched_status=200)
    audit_technical._headings(htmlx._parse_stdlib('<h1>Guide</h1><h4>Details</h4>', report.url), report)
    yield 'heading', report, ['An H1 is followed by an H4.']
    for name, detail, evidence in (
        ('hostile', '<img src="https://evil.test/pixel" onerror="alert(1)"> [fake](https://evil.test) **bold** | `tick`',
         '```text\n# fake heading\n```'),
        ('bounded', 'x' * 400 + 'HIDDEN_DETAIL', 'y' * 400 + 'HIDDEN_EVIDENCE'),
        ('backticks', '`' * 400 + 'HIDDEN_DETAIL', '~~~~\r\nLiteral fence candidate')):
        # The Markdown report includes its URL in an H1. Keep an unbroken long
        # path so wrapping is tested independently of platform font metrics.
        url = 'https://example.test/' + ('x' * 180 if name == 'bounded' else name)
        report = Report(url, fetched_status=200)
        report.add('technical', 'low', 'Synthetic preview check', detail,
                   'Review this fixture only.', evidence=evidence)
        expected = [' '.join(value.split())[:400] + ('…' if len(' '.join(value.split())) > 400 else '')
                    for value in (detail, evidence)]
        yield name, report, expected


def main(argv=None):
    """Inspect native HTML and actual Markdown-rendered output at screen/print sizes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--html', type=Path, help='also verify an installed-CLI heading report')
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
            documents = []
            for name, report, expected in cases():
                before = report.to_json()
                documents += [(name + '-native', report.to_html(), expected),
                              (name + '-markdown', html_document('Preview QA', '', md_to_html(report.to_markdown())), expected)]
                assert before == report.to_json(), name
            if args.html:
                documents.append(('installed-cli', args.html.read_text(encoding='utf-8'), ['An H1 is followed by an H4.']))
            for name, output, expected in documents:
                page.set_content(output)
                for mode, width in (('screen', 320), ('screen', 390), ('screen', 1100), ('print', 794)):
                    page.emulate_media(media=mode)
                    page.set_viewport_size({'width': width, 'height': 1000})
                    text = page.inner_text('body')
                    for value in expected:
                        assert value in text, (name, mode, width, value)
                    assert 'Observed (preview)' in text, name
                    assert 'whitespace-normalized' in text and 'not independent verification' in text
                    assert 'HIDDEN_DETAIL' not in text and 'HIDDEN_EVIDENCE' not in text
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (name, mode, width)
                    assert page.locator('img[src^="https://evil.test"], a[href^="https://evil.test"]').count() == 0
                    assert page.get_by_role('heading', name='fake heading', exact=True).count() == 0
                    if args.artifacts and width == 390:
                        page.screenshot(path=str(args.artifacts / (name + '-390.png')), full_page=True)
                if args.artifacts and (name.startswith('heading') or name == 'installed-cli'):
                    page.pdf(path=str(args.artifacts / (name + '.pdf')), format='A4', print_background=True)
            assert not requests, requests
        finally:
            browser.close()
    print('OK: quick-win observations/evidence remain literal and bounded in native/Markdown HTML, mobile/desktop/print; JSON unchanged and no external requests.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
