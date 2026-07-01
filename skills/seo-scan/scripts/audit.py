#!/usr/bin/env python3
"""Comprehensive site audit — one report combining:

  1. A full single-page audit of the entry URL (all four auditors)
  2. A site-wide crawl (weakest pages, recurring issues, broken links, duplicates)
  3. XML sitemap validation

This is the flagship ``narwhal audit <site>`` deliverable: a stakeholder-ready
overview that a single-page scan can't give on its own.

Usage:
    python audit.py https://example.com
    python audit.py https://example.com --max-pages 30 --format json -o audit.json
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import config as configlib  # noqa: E402
from lib.report import below_threshold  # noqa: E402
import scan as scanner  # noqa: E402
import crawl_site  # noqa: E402
import validate_sitemap  # noqa: E402


def _demote(md: str) -> str:
    """Drop a sub-report's top H1 and push every other heading down one level."""
    out, seen_h1 = [], False
    for line in md.splitlines():
        if line.startswith("# ") and not seen_h1:
            seen_h1 = True
            continue
        out.append("#" + line if line.startswith("#") else line)
    return "\n".join(out).strip()


def run(site: str, *, max_pages=15, concurrency=4, timeout=20, allow_private=False,
        obey_robots=True, render=False, max_links=100, max_sitemaps=12,
        config=None) -> dict:
    """Run the three sub-audits. The link and sitemap caps default lower than the
    standalone tools' — an audit is an overview, so it favors speed over an
    exhaustive link/sitemap sweep (the dedicated commands go deeper)."""
    config = config or configlib.Config()
    page = scanner.scan(site, timeout=timeout, allow_private=allow_private,
                        render=render, config=config)
    site_result = crawl_site.crawl(
        site, max_pages=max_pages, concurrency=concurrency, timeout=timeout,
        allow_private=allow_private, obey_robots=obey_robots, render=render,
        check_links=True, max_links=max_links, detect_dupes=True, config=config)
    sitemap = validate_sitemap.analyze(
        site, allow_private=allow_private, timeout=timeout,
        sample=config.default("sample"), max_sitemaps=max_sitemaps)
    return {"site": site, "page": page, "site_result": site_result, "sitemap": sitemap}


def overall_score(data: dict) -> float:
    """The audit's headline score: the lower of homepage and site-average."""
    return min(data["page"].score(), data["site_result"]["avg_score"])


def render_markdown(data: dict) -> str:
    page = data["page"]
    site_res = data["site_result"]
    sm = data["sitemap"]
    broken = len(site_res.get("links", {}).get("broken", [])) if site_res.get("links") else 0
    dupes = len(site_res.get("duplicates", []))

    header = [
        f"# Narwhal Site Audit — {data['site']}",
        "",
        f"**Homepage:** {page.score()}/100  ·  "
        f"**Site average:** {site_res['avg_score']}/100  ·  "
        f"**Pages scanned:** {site_res['pages_scanned']}  ",
        f"**Broken links:** {broken}  ·  **Near-duplicate clusters:** {dupes}  ·  "
        f"**Sitemap URLs:** {sm.get('total_urls', 0)}",
        "",
        "---",
        "",
        "## 1. Homepage audit",
        "",
        _demote(page.to_markdown()),
        "",
        "## 2. Site-wide",
        "",
        _demote(crawl_site.render_markdown(site_res)),
        "",
        "## 3. Sitemap",
        "",
        _demote(validate_sitemap.render_markdown(sm)),
    ]
    return "\n".join(header).rstrip() + "\n"


def render_json(data: dict) -> str:
    import json
    payload = {
        "site": data["site"],
        "overall_score": overall_score(data),
        "homepage": json.loads(data["page"].to_json()),
        "crawl": json.loads(crawl_site.render_json(data["site_result"])),
        "sitemap": json.loads(validate_sitemap.render_json(data["sitemap"])),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def main(argv=None) -> int:
    cfg = configlib.load_from_args(argv)
    d = cfg.defaults
    ap = argparse.ArgumentParser(description="Comprehensive site audit (page + crawl + sitemap)",
                                 parents=[configlib.config_arg_parser()])
    ap.add_argument("url", help="site URL")
    ap.add_argument("--max-pages", type=int, default=d["max_pages"])
    ap.add_argument("--concurrency", type=int, default=d["concurrency"])
    ap.add_argument("--max-links", type=int, default=100,
                    help="cap on outbound links checked (default 100)")
    ap.add_argument("--max-sitemaps", type=int, default=12,
                    help="cap on sitemap files fetched (default 12)")
    ap.add_argument("--timeout", type=int, default=d["timeout"])
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--ignore-robots", action="store_true")
    ap.add_argument("--allow-private", action="store_true")
    ap.add_argument("--format", choices=("markdown", "json"), default="markdown")
    ap.add_argument("-o", "--output")
    ap.add_argument("--fail-under", type=int, metavar="N", default=d.get("fail_under"),
                    help="exit non-zero if the overall score (min of homepage & "
                         "site-average) is below N")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    data = run(args.url, max_pages=args.max_pages, concurrency=args.concurrency,
               timeout=args.timeout, allow_private=args.allow_private,
               obey_robots=not args.ignore_robots, render=args.render,
               max_links=args.max_links, max_sitemaps=args.max_sitemaps, config=cfg)
    out = render_json(data) if args.format == "json" else render_markdown(data)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"Wrote {args.format} audit to {args.output} "
              f"(overall {overall_score(data)}/100)")
    else:
        print(out)

    if below_threshold(overall_score(data), args.fail_under):
        print(f"FAIL: overall score {overall_score(data)}/100 is below the "
              f"--fail-under threshold of {args.fail_under}.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
