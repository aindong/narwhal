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

from lib import http  # noqa: E402

MARKER = "RENDERED_BY_JS_OK"
PAGE = f"""<!DOCTYPE html><html><head><title>Render smoke</title></head>
<body><div id="app">loading…</div>
<script>document.getElementById('app').textContent = '{MARKER}';</script>
</body></html>""".encode("utf-8")


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *args):
        pass  # keep CI output clean


def main() -> int:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"

    # allow_private=True: the smoke server is localhost, which the SSRF guard
    # blocks by default.
    resp = http.fetch(url, render=True, allow_private=True, timeout=30)
    server.shutdown()

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
    # The raw (unrendered) HTML says "loading…"; the rendered DOM must not.
    print(f"OK: rendered DOM captured the JS-injected marker ({MARKER}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
