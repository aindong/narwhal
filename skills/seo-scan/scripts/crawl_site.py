#!/usr/bin/env python3
"""Site-level SEO + GEO scan.

Discovers URLs from the sitemap (falling back to on-page internal links), audits
up to ``--max-pages`` of them, and prints a rollup: per-page scores plus the
issues that recur across the site (the highest-leverage fixes).

Usage:
    python crawl_site.py https://example.com
    python crawl_site.py https://example.com --max-pages 25 --format json
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from urllib.parse import urljoin, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import http, htmlx  # noqa: E402
import scan as scanner  # noqa: E402

SITEMAP_CANDIDATES = ("/sitemap.xml", "/sitemap_index.xml")
_LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.I | re.S)


def discover(base: str, *, allow_private: bool, timeout: int, limit: int) -> list:
    root = f"{urlparse(base).scheme}://{urlparse(base).netloc}"
    urls: list = []

    # 1) sitemap(s), including a one-level sitemap index
    robots = http.fetch_text(urljoin(root + "/", "robots.txt"),
                             allow_private=allow_private, timeout=timeout) or ""
    sm_urls = [ln.split(":", 1)[1].strip() for ln in robots.splitlines()
               if ln.lower().strip().startswith("sitemap:")]
    sm_urls += [urljoin(root + "/", p.lstrip("/")) for p in SITEMAP_CANDIDATES]
    for sm in sm_urls:
        body = http.fetch_text(sm, allow_private=allow_private, timeout=timeout)
        if not body:
            continue
        locs = _LOC.findall(body)
        if "<sitemapindex" in body:
            for child in locs[:5]:
                child_body = http.fetch_text(child, allow_private=allow_private,
                                             timeout=timeout) or ""
                urls += _LOC.findall(child_body)
        else:
            urls += locs
        if urls:
            break

    # 2) fallback: internal links on the entry page
    if not urls:
        resp = http.fetch(base, allow_private=allow_private, timeout=timeout)
        if resp.ok:
            doc = htmlx.parse(resp.text, base_url=resp.final_url or base)
            host = urlparse(resp.final_url or base).netloc
            for a in doc.links:
                href = a.get("href") or ""
                full = urljoin(resp.final_url or base, href)
                if urlparse(full).netloc == host and full.startswith("http"):
                    urls.append(full.split("#")[0])

    # de-dupe, keep order, drop obvious non-HTML assets
    seen, out = set(), []
    for u in [base] + urls:
        u = u.split("#")[0]
        if u in seen or re.search(r"\.(jpg|png|gif|svg|pdf|css|js|xml|zip)$", u, re.I):
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= limit:
            break
    return out


def crawl(base: str, *, max_pages=15, render=False, allow_private=False,
          timeout=20) -> dict:
    urls = discover(base, allow_private=allow_private, timeout=timeout, limit=max_pages)
    pages = []
    issue_counter = Counter()
    for u in urls:
        rep = scanner.scan(u, render=render, allow_private=allow_private,
                           timeout=timeout)
        pages.append({"url": u, "score": rep.score(), "counts": rep.counts()})
        for f in rep.findings:
            if f.severity in ("critical", "high", "medium"):
                issue_counter[(f.category, f.severity, f.title)] += 1
    avg = round(sum(p["score"] for p in pages) / len(pages), 1) if pages else 0
    return {"base": base, "pages_scanned": len(pages), "avg_score": avg,
            "pages": pages, "recurring": issue_counter}


def render_markdown(result: dict) -> str:
    lines = [f"# Site SEO & GEO Scan — {result['base']}", "",
             f"**Pages scanned:** {result['pages_scanned']}  ·  "
             f"**Average score:** {result['avg_score']}/100", ""]
    ranked = sorted(result["pages"], key=lambda p: p["score"])
    lines += ["## Weakest pages", "", "| Score | URL |", "|:--:|:--|"]
    for p in ranked[:10]:
        lines.append(f"| {p['score']} | {p['url']} |")
    lines.append("")
    recurring = result["recurring"].most_common(12)
    if recurring:
        lines += ["## Most common issues (fix these first)", "",
                  "| Count | Severity | Category | Issue |", "|:--:|:--|:--|:--|"]
        for (cat, sev, title), n in recurring:
            lines.append(f"| {n} | {sev} | {cat} | {title} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_json(result: dict) -> str:
    import json
    payload = dict(result)
    payload["recurring"] = [
        {"category": c, "severity": s, "title": t, "count": n}
        for (c, s, t), n in result["recurring"].most_common()
    ]
    return json.dumps(payload, indent=2, ensure_ascii=False)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Site-level SEO + GEO/LLMO scan")
    ap.add_argument("url", help="base URL of the site")
    ap.add_argument("--max-pages", type=int, default=15)
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--format", choices=("markdown", "json"), default="markdown")
    ap.add_argument("-o", "--output")
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--allow-private", action="store_true")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    result = crawl(args.url, max_pages=args.max_pages, render=args.render,
                   allow_private=args.allow_private, timeout=args.timeout)
    out = render_json(result) if args.format == "json" else render_markdown(result)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"Wrote {args.format} report to {args.output} "
              f"({result['pages_scanned']} pages, avg {result['avg_score']}/100)")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
