#!/usr/bin/env python3
"""Playwright render smoke test — run by the CI `render-smoke` job (not the
offline unittest suite, which never touches the network or a browser).

It serves a tiny page whose real content is injected by JavaScript, renders it
through ``http.fetch(..., render=True)``, and asserts the post-JS text is
captured. This proves the hardened `_try_render` path actually executes JS end
to end. Exit 0 on success, 1 on failure.
"""

from __future__ import annotations

import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

from lib import htmlx, http  # noqa: E402
import scan  # noqa: E402

MARKER = "RENDERED_BY_JS_OK"
PAGE = f"""<!DOCTYPE html><html><head><title>Render smoke</title></head>
<body><div id="app">loading…</div>
<template id="example"><h1>Template product</h1>
<script type="application/ld+json">{{"@type":"Product","name":"Template product"}}</script>
</template>
<script>document.getElementById('app').textContent = '{MARKER}';</script>
</body></html>""".encode("utf-8")
ACTIVATED_PAGE = PAGE.replace(
    b"</body>",
    b"<script>document.body.append(document.getElementById('example').content.cloneNode(true));</script></body>",
)
BUDGET_PAGE = """<!DOCTYPE html><html><head><title>DOM budget fixture</title></head>
<body><div id="app"></div><script>
document.getElementById('app').textContent = '😀'.repeat(20000);
let heading = document.createElement('h1');
heading.textContent = 'AFTER_BUDGET'; document.body.append(heading);
</script></body></html>""".encode("utf-8")
BASELINE_PAGE = ("""<!DOCTYPE html><html><head><title>Paired HTML fixture</title>
<script>window.addEventListener('DOMContentLoaded',()=>document.getElementById('padding').remove());</script>
</head><body><div id="padding">""" + " " * 120_000
                 + '</div><h1>Always served heading</h1><p>' + 'word ' * 350
                 + '</p></body></html>').encode('utf-8')


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/http-redirect':
            self.send_response(302)
            self.send_header('Location', '/http-robots')
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if self.path == "/spoofed":
            self.send_header("X-Narwhal-Truncated", "true")
        if self.path == '/http-robots':
            self.send_header('X-Robots-Tag', 'none')
            self.send_header('X-Robots-Tag', 'googlebot: nofollow')
        if self.path == '/js-navigation':
            self.send_header('X-Robots-Tag', 'none')
        self.end_headers()
        if self.path == '/js-navigation':
            self.wfile.write(b'<html><body><script>setTimeout(()=>location.href="/",100)</script></body></html>')
            return
        if self.path == '/same-document':
            self.wfile.write(b'<html><body><script>history.pushState({}, "", "/virtual");</script>History API</body></html>')
            return
        if self.path == '/js-reload':
            self.wfile.write(b'<html><body><script>if(!sessionStorage.reloaded){sessionStorage.reloaded="1";setTimeout(()=>location.reload(),100)}</script>Reload</body></html>')
            return
        if self.path == '/crawler-meta':
            self.wfile.write(b'<html><head><meta name="googlebot" content="index"></head><body>'
                             b'<template><meta name="googlebot-news" content="none"></template>'
                             b'<script>document.querySelector("meta").content="noindex";</script></body></html>')
            return
        self.wfile.write(BASELINE_PAGE if self.path == "/baseline" else
                         BUDGET_PAGE if self.path == "/budget" else
                         ACTIVATED_PAGE if self.path == "/activated" else PAGE)

    def log_message(self, *args):
        pass  # keep CI output clean


def main() -> int:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"

    # allow_private=True: the smoke server is localhost, which the SSRF guard
    # blocks by default.
    try:
        resp = http.fetch(url, render=True, allow_private=True, timeout=30)
        activated = http.fetch(url + "activated", render=True, allow_private=True, timeout=30)
        bounded = http.fetch(url + "budget", render=True, allow_private=True,
                             timeout=30, max_bytes=64_000)
        partial = scan.scan(url + "budget", render=True, allow_private=True,
                             timeout=30, max_bytes=64_000, only=["technical"],
                             ctx={}, check_images=False)
        spoofed = scan.scan(url + "spoofed", render=True, allow_private=True,
                             timeout=30, max_bytes=64_000, only=["technical"],
                             ctx={}, check_images=False)
        unverified = scan.scan(url + "baseline", render=True, allow_private=True,
                                timeout=30, max_bytes=64_000, only=["technical"],
                                ctx={}, check_images=False)
        recovered = scan.scan(url + "baseline", render=True, allow_private=True,
                               timeout=30, max_bytes=256_000, only=["technical"],
                               ctx={}, check_images=False)
        header_scan = scan.scan(url + 'http-robots', render=True, allow_private=True,
                                timeout=30, only=['technical'], ctx={}, check_images=False)
        redirected = http.fetch(url + 'http-redirect', render=True, allow_private=True, timeout=30)
        navigated = scan.scan(url + 'js-navigation', render=True, allow_private=True,
                              timeout=30, only=['technical'], ctx={}, check_images=False)
        same_document = http.fetch(url + 'same-document', render=True, allow_private=True, timeout=30)
        reloaded = http.fetch(url + 'js-reload', render=True, allow_private=True, timeout=30)
        crawler_meta = scan.scan(url + 'crawler-meta', render=True, allow_private=True,
                                 timeout=30, only=['technical'], ctx={}, check_images=False)
    finally:
        server.shutdown()
        server.server_close()

    if resp.error:
        print(f"FAIL: render returned an error: {resp.error}", file=sys.stderr)
        return 1
    if not resp.rendered:
        print("FAIL: response was not rendered (Playwright not used).", file=sys.stderr)
        return 1
    if MARKER not in resp.text:
        print("FAIL: JS-injected marker missing — DOM was not executed.\n"
              f"Got: {resp.text[:200]!r}", file=sys.stderr)
        return 1
    inert_doc = htmlx.parse(resp.text, url)
    if htmlx.looks_product(inert_doc) or inert_doc.scripts_ld:
        print("FAIL: an inert template supplied Product schema to the document.", file=sys.stderr)
        return 1
    if activated.error or not activated.rendered:
        print(f"FAIL: template activation render failed: {activated.error}", file=sys.stderr)
        return 1
    active_doc = htmlx.parse(activated.text, url)
    if not htmlx.looks_product(active_doc) or len(active_doc.scripts_ld) != 1:
        print("FAIL: activated template Product schema was not detected exactly once.", file=sys.stderr)
        return 1
    if (bounded.error or not bounded.rendered
            or len(bounded.text.encode("utf-8")) > 64_000
            or bounded.headers.get("x-narwhal-truncated") != "true"
            or "\ufffd" in bounded.text):
        print("FAIL: rendered UTF-8 snapshot did not obey its byte budget cleanly.", file=sys.stderr)
        return 1
    if (not partial.rendered or partial.hard_fail
            or not partial.meta["coverage"]["response_truncated"]
            or "js_dependence" in partial.meta
            or not any(f.rule_id == "technical.response.truncated" for f in partial.findings)):
        print("FAIL: partial rendered snapshot lost coverage or produced a JS-dependence measurement.", file=sys.stderr)
        return 1
    if (not spoofed.rendered or spoofed.hard_fail
            or spoofed.meta["coverage"]["response_truncated"]
            or "js_dependence" not in spoofed.meta):
        print("FAIL: origin header forged partial DOM coverage or skipped a valid JS comparison.", file=sys.stderr)
        return 1
    if (unverified.hard_fail or unverified.meta['coverage']['response_truncated']
            or unverified.meta['coverage']['js_comparison'].get('reason') != 'served_html_truncated'
            or 'js_dependence' in unverified.meta):
        print('FAIL: truncated served HTML became JS-dependence evidence.', file=sys.stderr)
        return 1
    if (recovered.hard_fail or recovered.meta['coverage']['js_comparison']['status'] != 'measured'
            or recovered.meta.get('js_dependence', {}).get('js_only_pct') != 0):
        print('FAIL: larger paired budget did not restore the complete HTML comparison.', file=sys.stderr)
        return 1
    # The raw (unrendered) HTML says "loading…"; the rendered DOM must not.
    header_rules = {finding.rule_id for finding in header_scan.findings}
    if (crawler_meta.hard_fail or not crawler_meta.rendered
            or crawler_meta.meta.get('crawler_meta_robots', {}).get('observations') !=
               [{'agent': 'googlebot', 'directives': ['noindex'], 'tag_positions': [1]}]
            or any(f.rule_id == 'technical.page.is.set.to.noindex' for f in crawler_meta.findings)):
        print('FAIL: rendered named-meta observation lost JS changes, template exclusion or crawler scope.', file=sys.stderr)
        return 1
    if (redirected.error or not redirected.final_url.endswith('/http-robots')
            or redirected.robots_header_fields != ['none', 'googlebot: nofollow']):
        print('FAIL: ordinary HTTP redirect lost the final response header pairing.', file=sys.stderr)
        return 1
    if (not navigated.hard_fail
            or any(f.rule_id.startswith('technical.http.robots.') for f in navigated.findings)
            or not any('response headers and DOM cannot be safely paired' in f.detail for f in navigated.findings)):
        print('FAIL: cross-document JS navigation scored an earlier response header.', file=sys.stderr)
        return 1
    if same_document.error or not same_document.final_url.endswith('/virtual'):
        print('FAIL: same-document History API navigation was treated as a document replacement.', file=sys.stderr)
        return 1
    if not reloaded.error or 'response headers and DOM cannot be safely paired' not in reloaded.error:
        print('FAIL: same-URL document reload escaped response/DOM pairing validation.', file=sys.stderr)
        return 1
    if (header_scan.hard_fail or not header_scan.rendered
            or not {'technical.http.robots.noindex', 'technical.http.robots.nofollow'} <= header_rules
            or header_scan.meta.get('http_robots', {}).get('basis') != 'browser_reported_fields'
            or {'agent': 'googlebot', 'directives': ['nofollow']} not in header_scan.meta.get('http_robots', {}).get('scoped', [])):
        print('FAIL: rendered scan lost the observed generic HTTP robots restrictions or provenance.', file=sys.stderr)
        return 1
    print(f"OK: rendered DOM captured the JS-injected marker ({MARKER}).")
    print("OK: inert template Product ignored; JS-activated Product detected exactly once.")
    print("OK: rendered UTF-8 byte budget enforced; partial scan flagged without JS-dependence metrics.")
    print("OK: origin cannot forge the internally calculated truncation marker.")
    print('OK: paired byte budget enforced; truncated baseline unverified; complete pair recovers 0% JS-only.')
    print('OK: rendered HTTP robots declarations retained with browser-reported field provenance.')
    print('OK: JS document replacement fails explicitly; HTTP redirects and History API remain supported.')
    print('OK: rendered Googlebot meta observed without generic scoring; inert named-meta template ignored.')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
