#!/usr/bin/env python3
"""seo-scan — single-page SEO + GEO/LLMO auditor.

Fetches a URL (optionally JS-rendered), gathers site-level signals (robots.txt,
sitemap, llms.txt), runs the technical / content / schema / geo auditors, and
prints a prioritized report.

Usage:
    python scan.py https://example.com/page
    python scan.py https://example.com --render --format json -o report.json
    python scan.py https://example.com --only technical,geo

Runs local-only with zero external accounts. Works on a bare Python install and
uses requests/lxml/bs4/playwright automatically when they are present.
"""

from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urljoin, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import http, htmlx, links  # noqa: E402
from lib import config as configlib  # noqa: E402
from lib.report import Report, below_threshold  # noqa: E402

import audit_content  # noqa: E402
import audit_geo  # noqa: E402
import audit_schema  # noqa: E402
import audit_technical  # noqa: E402

AUDITORS = {
    "technical": audit_technical.audit,
    "content": audit_content.audit,
    "schema": audit_schema.audit,
    "geo": audit_geo.audit,
}

SITEMAP_CANDIDATES = ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml")


def gather_context(base: str, *, allow_private: bool, timeout: int) -> dict:
    """Fetch site-level resources shared across auditors."""
    root = f"{urlparse(base).scheme}://{urlparse(base).netloc}"
    ctx: dict = {}

    ctx["robots_txt"] = http.fetch_text(
        urljoin(root + "/", "robots.txt"),
        allow_private=allow_private, timeout=timeout,
    )

    llms = http.fetch_text(
        urljoin(root + "/", "llms.txt"), allow_private=allow_private, timeout=timeout
    )
    ctx["llms_txt"] = bool(llms)
    ctx["llms_txt_url"] = f"{root}/llms.txt" if llms else ""

    ctx["sitemap_found"] = False
    robots = ctx.get("robots_txt") or ""
    sitemap_urls = [
        ln.split(":", 1)[1].strip()
        for ln in robots.splitlines()
        if ln.lower().strip().startswith("sitemap:")
    ]
    for cand in list(sitemap_urls) + [urljoin(root + "/", p.lstrip("/")) for p in SITEMAP_CANDIDATES]:
        body = http.fetch_text(cand, allow_private=allow_private, timeout=timeout)
        if body and ("<urlset" in body or "<sitemapindex" in body):
            ctx["sitemap_found"] = True
            ctx["sitemap_url"] = cand
            break
    return ctx


def scan(url: str, *, render=False, allow_private=False, timeout=20,
         only=None, ctx=None, collect_links=False, config=None) -> Report:
    """Audit a single page. Pass ``ctx`` (from :func:`gather_context`) to reuse
    site-level signals across many pages — the crawler does this so robots.txt,
    sitemap, and llms.txt are fetched once per site rather than once per page.
    Set ``collect_links=True`` to record outbound links in ``report.meta['links']``
    (used by the crawler's broken-link checker). ``config`` (a Config) tunes
    scoring weights, ignore rules, and check thresholds."""
    config = config or configlib.Config()
    resp = http.fetch(url, render=render, allow_private=allow_private, timeout=timeout)
    report = Report(url=url, final_url=resp.final_url, fetched_status=resp.status,
                    rendered=resp.rendered, weights=config.weights,
                    ignore=config.is_ignored)
    report.meta["elapsed_ms"] = resp.elapsed_ms

    if not resp.ok:
        report.add("technical", "critical", "Page could not be fetched",
                   f"Status {resp.status}" + (f": {resp.error}" if resp.error else ""),
                   "Verify the URL is public and returns 200 before auditing.")
        return report

    doc = htmlx.parse(resp.text, base_url=resp.final_url or url)
    if collect_links:
        report.meta["links"] = links.extract_links(doc, resp.final_url or url)
    if ctx is None:
        ctx = gather_context(resp.final_url or url,
                             allow_private=allow_private, timeout=timeout)
    # expose tunable thresholds to auditors without mutating a shared ctx
    ctx = {**ctx, "thresholds": ctx.get("thresholds", config.thresholds)}

    selected = only or list(AUDITORS)
    for name in selected:
        fn = AUDITORS.get(name)
        if fn:
            fn(doc, resp, report, ctx)
    return report


def main(argv=None) -> int:
    cfg = configlib.load_from_args(argv)
    ap = argparse.ArgumentParser(description="SEO + GEO/LLMO single-page auditor",
                                 parents=[configlib.config_arg_parser()])
    ap.add_argument("url", help="URL to audit")
    ap.add_argument("--render", action="store_true",
                    help="render JS with Playwright if installed")
    ap.add_argument("--format", choices=("markdown", "json"), default="markdown")
    ap.add_argument("--only", help="comma-separated subset: technical,content,schema,geo")
    ap.add_argument("-o", "--output", help="write report to a file")
    ap.add_argument("--timeout", type=int, default=cfg.default("timeout"))
    ap.add_argument("--allow-private", action="store_true",
                    help="permit private/localhost hosts (off by default for SSRF safety)")
    ap.add_argument("--fail-under", type=int, metavar="N",
                    default=cfg.defaults.get("fail_under"),
                    help="exit non-zero if the health score is below N (for CI gating)")
    args = ap.parse_args(argv)

    # Windows consoles default to cp1252 and choke on the severity icons; force
    # UTF-8 so the report prints cleanly everywhere.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    only = [s.strip() for s in args.only.split(",")] if args.only else None
    report = scan(args.url, render=args.render, allow_private=args.allow_private,
                  timeout=args.timeout, only=only, config=cfg)

    out = report.to_json() if args.format == "json" else report.to_markdown()
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"Wrote {args.format} report to {args.output} "
              f"(score {report.score()}/100)")
    else:
        print(out)

    if below_threshold(report.score(), args.fail_under):
        print(f"FAIL: health score {report.score()}/100 is below the "
              f"--fail-under threshold of {args.fail_under}.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
