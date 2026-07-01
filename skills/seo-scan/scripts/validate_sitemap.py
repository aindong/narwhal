#!/usr/bin/env python3
"""Validate a site's XML sitemap(s).

Discovers the sitemap (from robots.txt or common paths) or takes a sitemap URL
directly, recurses one or more levels of sitemap indexes, validates every
``<loc>`` and ``<lastmod>``, and samples a few URLs to catch stale sitemaps
(links that 404). Supports gzipped sitemaps.

Usage:
    python validate_sitemap.py https://example.com
    python validate_sitemap.py https://example.com/sitemap_index.xml --sample 20
    python validate_sitemap.py https://example.com --format json
"""

from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urljoin, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import http, links, sitemap as sm  # noqa: E402
from lib import config as configlib  # noqa: E402

COMMON = ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml")


def _looks_like_sitemap(url: str) -> bool:
    low = url.lower()
    return low.endswith((".xml", ".xml.gz")) or "sitemap" in low


def discover(base: str, *, allow_private, timeout) -> list:
    root = f"{urlparse(base).scheme}://{urlparse(base).netloc}"
    robots = http.fetch_text(urljoin(root + "/", "robots.txt"),
                             allow_private=allow_private, timeout=timeout) or ""
    found = [ln.split(":", 1)[1].strip() for ln in robots.splitlines()
             if ln.lower().strip().startswith("sitemap:")]
    if found:
        return found
    for cand in COMMON:
        u = urljoin(root + "/", cand.lstrip("/"))
        body = http.fetch_text(u, allow_private=allow_private, timeout=timeout)
        if body and ("<urlset" in body or "<sitemapindex" in body):
            return [u]
    return []


def analyze(start: str, *, allow_private=False, timeout=20, sample=10,
            max_sitemaps=50) -> dict:
    host = urlparse(start).netloc
    seeds = [start] if _looks_like_sitemap(start) else discover(
        start, allow_private=allow_private, timeout=timeout)

    result = {
        "start": start, "seeds": seeds, "sitemaps_fetched": 0, "indexes": 0,
        "total_urls": 0, "errors": [], "problems": {},
        "invalid_lastmod": 0, "missing_lastmod": 0, "gzip": 0,
        "sample": [], "broken_sample": [],
    }
    if not seeds:
        result["errors"].append("No sitemap found (robots.txt or common paths).")
        return result

    queue = list(seeds)
    visited = set()
    url_entries = []  # {loc, lastmod}
    problems = {"not-absolute": 0, "cross-host": 0}

    while queue and result["sitemaps_fetched"] < max_sitemaps:
        smap = queue.pop(0)
        if smap in visited:
            continue
        visited.add(smap)
        raw, err = http.fetch_bytes(smap, allow_private=allow_private, timeout=timeout)
        if raw is None:
            result["errors"].append(f"{smap} -> {err}")
            continue
        if raw[:2] == b"\x1f\x8b":
            result["gzip"] += 1
        text = sm.decode(raw)
        result["sitemaps_fetched"] += 1
        kind, entries = sm.parse(text)
        if kind == "index":
            result["indexes"] += 1
            for e in entries:
                if e["loc"] not in visited:
                    queue.append(e["loc"])
        else:
            for e in entries:
                url_entries.append(e)
                prob = sm.loc_problem(e["loc"], host)
                if prob:
                    problems[prob] = problems.get(prob, 0) + 1
                if e["lastmod"] is None:
                    result["missing_lastmod"] += 1
                elif not sm.valid_lastmod(e["lastmod"]):
                    result["invalid_lastmod"] += 1

    result["total_urls"] = len(url_entries)
    result["problems"] = {k: v for k, v in problems.items() if v}
    if queue:  # cap reached with sitemaps still queued
        result["truncated"] = len(queue)
        result["errors"].append(
            f"Reached --max-sitemaps ({max_sitemaps}); {len(queue)} more sitemap "
            f"file(s) not fetched, so total URLs is a partial count.")

    # 404 sampling: spread the sample across the URL list
    valid_locs = [e["loc"] for e in url_entries if not sm.loc_problem(e["loc"], host)]
    if valid_locs and sample > 0:
        step = max(1, len(valid_locs) // sample)
        picked = valid_locs[::step][:sample]
        for loc in picked:
            status, err = http.head(loc, allow_private=allow_private, timeout=timeout)
            entry = {"url": loc, "status": status, "error": err}
            result["sample"].append(entry)
            if links.is_broken(status):
                result["broken_sample"].append(entry)
    return result


def render_markdown(r: dict) -> str:
    lines = [f"# Sitemap validation — {r['start']}", ""]
    if not r["seeds"]:
        lines += ["**No sitemap found.** Publish an XML sitemap and reference it "
                  "from robots.txt.", ""]
        return "\n".join(lines) + "\n"
    lines += [
        f"- **Sitemaps fetched:** {r['sitemaps_fetched']} "
        f"({r['indexes']} index file(s){', ' + str(r['gzip']) + ' gzipped' if r['gzip'] else ''})",
        f"- **Total URLs:** {r['total_urls']}"
        + ("+ (partial — --max-sitemaps cap reached)" if r.get("truncated") else ""),
        f"- **Missing lastmod:** {r['missing_lastmod']}  ·  "
        f"**Invalid lastmod:** {r['invalid_lastmod']}",
    ]
    if r["problems"]:
        probs = ", ".join(f"{k}: {v}" for k, v in r["problems"].items())
        lines.append(f"- **`<loc>` problems:** {probs}")
    if r["sample"]:
        ok = len(r["sample"]) - len(r["broken_sample"])
        lines.append(f"- **Sample check:** {ok}/{len(r['sample'])} URLs returned OK")
    lines.append("")

    if r["broken_sample"]:
        lines += ["## Broken sampled URLs", "", "| Status | URL |", "|:--:|:--|"]
        for b in r["broken_sample"]:
            lines.append(f"| {b['status'] or b['error']} | {b['url']} |")
        lines.append("")
    if r["errors"]:
        lines += ["## Notes", ""] + [f"- {e}" for e in r["errors"]] + [""]
    if not r["broken_sample"] and not r["problems"] and not r["invalid_lastmod"]:
        lines.append("Sitemap looks healthy. 🟢")
    return "\n".join(lines).rstrip() + "\n"


def render_json(r: dict) -> str:
    import json
    return json.dumps(r, indent=2, ensure_ascii=False)


def main(argv=None) -> int:
    cfg = configlib.load_from_args(argv)
    d = cfg.defaults
    ap = argparse.ArgumentParser(description="Validate a site's XML sitemap(s)",
                                 parents=[configlib.config_arg_parser()])
    ap.add_argument("url", help="site URL or a sitemap URL")
    ap.add_argument("--sample", type=int, default=d["sample"],
                    help="number of URLs to spot-check for 404 (default 10)")
    ap.add_argument("--max-sitemaps", type=int, default=d["max_sitemaps"],
                    help="cap on sitemap files fetched (default 50)")
    ap.add_argument("--format", choices=("markdown", "json"), default="markdown")
    ap.add_argument("-o", "--output")
    ap.add_argument("--timeout", type=int, default=d["timeout"])
    ap.add_argument("--allow-private", action="store_true")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    result = analyze(args.url, allow_private=args.allow_private, timeout=args.timeout,
                     sample=args.sample, max_sitemaps=args.max_sitemaps)
    out = render_json(result) if args.format == "json" else render_markdown(result)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"Wrote {args.format} report to {args.output}")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
