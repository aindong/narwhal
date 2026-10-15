#!/usr/bin/env python3
"""Same-run rendered/served evidence capture against a controlled local server."""

import argparse
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from threading import Thread

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'skills/seo-scan/scripts'))
from lib import htmlx


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, help='optional NEW capture directory; otherwise temporary')
    args = parser.parse_args(argv)
    hits = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            if self.path == '/guide':
                body = ('<html lang="en"><title>Controlled capture QA</title><body>'
                        '<main id="copy"><h1>Capture QA</h1><p>Served witness.</p></main>'
                        '<script>document.querySelector("#copy").insertAdjacentHTML('
                        '"beforeend", "<p>Rendered witness.</p>");</script></body></html>')
                kind, status = 'text/html; charset=utf-8', 200
            elif self.path == '/robots.txt':
                body, kind, status = 'User-agent: *\nDisallow:\nSitemap: /sitemap.xml\n', 'text/plain', 200
            elif self.path == '/sitemap.xml':
                body, kind, status = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>', 'application/xml', 200
            else:
                body, kind, status = 'Not found', 'text/plain', 404
            raw = body.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(raw)))
            if self.path == '/guide':
                self.send_header('X-Robots-Tag', 'noindex')
                self.send_header('X-Robots-Tag', 'nofollow')
            self.end_headers()
            self.wfile.write(raw)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with ExitStack() as stack:
            target = args.output_dir or Path(stack.enter_context(tempfile.TemporaryDirectory())) / 'capture'
            capture, review = load('capture_review_case'), load('review_corpus')
            capture.capture('http://127.0.0.1:' + str(server.server_port) + '/guide', target,
                            case_id='synthetic-rendered', render=True, allow_private=True, check_images=False)
            metadata = json.loads((target / 'capture.json').read_text())
            assert metadata['primary_response']['rendered'] is True
            assert metadata['served_comparison_response']['rendered'] is False
            rendered = htmlx.parse((target / 'page-source.txt').read_text()).body_text
            served = htmlx.parse((target / 'served-source.txt').read_text()).body_text
            assert 'Rendered witness.' in rendered and 'Rendered witness.' not in served
            assert 'Served witness.' in rendered and 'Served witness.' in served
            assert hits.count('/guide') == 2, hits
            assert metadata['served_comparison_response']['robots_header_fields'] == ['noindex', 'nofollow']
            assert 'noindex' in ' '.join(metadata['primary_response']['robots_header_fields'] or [])
            packet = review.prepare(target / 'manifest.json')
            summary = review.summarize(target / 'manifest.json', packet)
            assert summary['case_count'] == summary['cases_with_attached_files'] == 1
            assert summary['review_status'] == 'pending'
            assert summary['accuracy_metrics'] is None and summary['recall_metrics'] is None
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    print('OK: same-run served/rendered sources and header evidence preserved without a third page fetch; review pending, accuracy/recall unmeasured.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
