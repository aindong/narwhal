#!/usr/bin/env python3
"""Generated JSON-LD stays literal data in an actual Chromium HTML document."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import generate_schema
from test_schema_script_embedding import generate, PAYLOADS


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--script', type=Path, action='append', default=[],
                        help='also verify a generated script block from an installed package')
    args = parser.parse_args(argv)
    cases = [({'headline': payload}, generate({'headline': payload})) for payload in PAYLOADS]
    nested = {'extra': json.dumps({'</script>': [PAYLOADS[0], PAYLOADS[1]]})}
    cases.append((nested, generate(nested)))
    cases += [(None, generate({'headline': 'Another headline'})),
              (None, generate({'name': 'Data without a headline'}))]
    cases += [(None, path.read_text(encoding='utf-8')) for path in args.script]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            requests = []
            for fields, script in cases:
                page = browser.new_page()
                try:
                    def deny(route):
                        requests.append(route.request.url)
                        route.abort()
                    page.route('http://**/*', deny)
                    page.route('https://**/*', deny)
                    page.set_content('<html><head>' + script + '</head><body><p id="after">After artifact</p></body></html>')
                    assert page.locator('script').count() == 1
                    assert page.locator('script[type="application/ld+json"]').count() == 1
                    assert page.locator('img').count() == 0
                    assert page.locator('#after').inner_text() == 'After artifact'
                    assert not page.evaluate('Object.hasOwn(globalThis, "narwhalProbe")')
                    node = json.loads(page.locator('script').text_content())
                    if fields is not None:
                        assert node == generate_schema.build('Article', fields, include_recommended=False)
                finally:
                    page.close()
            assert not requests, requests
        finally:
            browser.close()
    print('OK: generated JSON-LD round-trips as one inert script; no injected elements, execution or requests, and following HTML remains intact.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
