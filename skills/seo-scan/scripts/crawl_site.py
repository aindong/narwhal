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
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import http, htmlx, links, simhash  # noqa: E402
from lib import config as configlib  # noqa: E402
from lib.report import below_threshold  # noqa: E402
from lib.robots import RobotsTxt  # noqa: E402
import scan as scanner  # noqa: E402


def _norm_canonical(url):
    if not url:
        return None
    p = urlparse(url)
    return f"{p.netloc}{p.path}".rstrip("/").lower()


def find_duplicates(page_fps: list, threshold_pct: float) -> list:
    """Cluster near-duplicate pages and check their canonicalization.

    ``page_fps`` is a list of ``{url, fingerprint, canonical}``. Returns clusters
    with the minimum pairwise similarity and whether the near-dupes point to a
    single, consistent canonical (``canonical_ok``).
    """
    items = [(i, p["fingerprint"]) for i, p in enumerate(page_fps)
             if p.get("fingerprint")]
    clusters = []
    for idxs in simhash.cluster(items, threshold_pct):
        pages = [page_fps[i] for i in idxs]
        sims = [simhash.similarity(pages[a]["fingerprint"], pages[b]["fingerprint"])
                for a in range(len(pages)) for b in range(a + 1, len(pages))]
        canon_targets = {_norm_canonical(p["canonical"]) for p in pages}
        canonical_ok = all(p["canonical"] for p in pages) and len(canon_targets) == 1
        clusters.append({
            "urls": [p["url"] for p in pages],
            "canonicals": [p["canonical"] for p in pages],
            "min_similarity": min(sims) if sims else 100.0,
            "canonical_ok": canonical_ok,
        })
    clusters.sort(key=lambda c: (c["canonical_ok"], -c["min_similarity"]))
    return clusters

# Product token a site would match us on (from http.DEFAULT_UA).
CRAWLER_AGENT = "seo-scan"

SITEMAP_CANDIDATES = ("/sitemap.xml", "/sitemap_index.xml")
_LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.I | re.S)


def discover(base: str, *, allow_private: bool, timeout: int, limit: int,
             robots_txt=None) -> list:
    root = f"{urlparse(base).scheme}://{urlparse(base).netloc}"
    urls: list = []

    # 1) sitemap(s), including a one-level sitemap index. Reuse an already-fetched
    # robots.txt when the caller provides one (avoids a redundant request).
    if robots_txt is None:
        robots_txt = http.fetch_text(urljoin(root + "/", "robots.txt"),
                                     allow_private=allow_private, timeout=timeout) or ""
    robots = robots_txt
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

    # de-dupe, keep order, drop obvious non-HTML assets. Normalize the dedupe key
    # so "…/page" and "…/page/" (and #fragments) count as one URL.
    seen, out = set(), []
    for u in [base] + urls:
        u = u.split("#")[0]
        key = u.rstrip("/") or u
        if key in seen or re.search(r"\.(jpg|png|gif|svg|pdf|css|js|xml|zip)$", u, re.I):
            continue
        seen.add(key)
        out.append(u)
        if len(out) >= limit:
            break
    return out


def select_urls(candidates, base, rt, obey_robots, max_pages,
                agent=CRAWLER_AGENT):
    """Filter discovered URLs by robots.txt and cap to ``max_pages``.

    The explicitly-provided ``base`` is always kept. Returns ``(urls, skipped)``.
    """
    urls, skipped = [], 0
    for u in candidates:
        if obey_robots and u != base and rt.disallowed(u, agent):
            skipped += 1
            continue
        urls.append(u)
        if len(urls) >= max_pages:
            break
    return urls, skipped


def check_broken_links(pages_links: dict, *, allow_private, timeout,
                       concurrency, max_links, link_timeout=8) -> dict:
    """Check unique links found across scanned pages; report broken ones.

    ``pages_links`` maps page_url -> list of {url, internal}. Returns a summary
    with each broken link's status and the source pages that link to it.

    Link checks are HEAD requests, so they use a **shorter per-link timeout** and
    **more workers** than page scanning — otherwise a handful of slow external
    links on a link-heavy page can serialize into a multi-minute stall.
    """
    registry: dict = {}   # link url -> {internal, sources:set}
    order: list = []
    for page, page_links in pages_links.items():
        for l in page_links:
            u = l["url"]
            if u not in registry:
                registry[u] = {"internal": l["internal"], "sources": set()}
                order.append(u)
            registry[u]["sources"].add(page)

    targets = order[:max_links]
    t = min(timeout, link_timeout)
    workers = min(16, max(concurrency, 10))

    def check(u):
        return u, http.head(u, timeout=t, allow_private=allow_private)

    statuses: dict = {}
    if targets:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for u, (status, err) in ex.map(check, targets):
                statuses[u] = (status, err)

    broken = []
    for u in targets:
        status, err = statuses[u]
        if links.is_broken(status):
            broken.append({
                "url": u,
                "status": status,
                "error": err,
                "internal": registry[u]["internal"],
                "sources": sorted(registry[u]["sources"]),
            })
    broken.sort(key=lambda b: (not b["internal"], b["url"]))  # internal first
    return {"unique_links": len(order), "checked": len(targets),
            "skipped_over_cap": max(0, len(order) - len(targets)),
            "broken": broken}


def crawl(base: str, *, max_pages=15, render=False, allow_private=False,
          timeout=20, delay=0.0, concurrency=4, obey_robots=True,
          check_links=False, max_links=200, detect_dupes=True,
          dup_threshold=90.0, config=None) -> dict:
    config = config or configlib.Config()
    # Fetch site-level signals (robots/sitemap/llms) ONCE and reuse for every
    # page — polite and much faster than re-fetching per page.
    ctx = scanner.gather_context(base, allow_private=allow_private, timeout=timeout)
    robots_txt = ctx.get("robots_txt") or ""
    rt = RobotsTxt.parse(robots_txt)

    # Over-fetch candidates so we still reach max_pages after robots filtering.
    candidates = discover(base, allow_private=allow_private, timeout=timeout,
                          limit=max_pages * 3 if obey_robots else max_pages,
                          robots_txt=robots_txt)

    urls, skipped = select_urls(candidates, base, rt, obey_robots, max_pages)

    def scan_one(u):
        return u, scanner.scan(u, render=render, allow_private=allow_private,
                               timeout=timeout, ctx=ctx, collect_links=check_links,
                               collect_fingerprint=detect_dupes, config=config)

    results = []
    if concurrency <= 1:
        for u in urls:
            results.append(scan_one(u))
            if delay > 0:
                time.sleep(delay)
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            results = list(ex.map(scan_one, urls))

    pages, issue_counter, pages_links, page_fps = [], Counter(), {}, []
    for u, rep in results:
        pages.append({"url": u, "score": rep.score(), "counts": rep.counts()})
        for f in rep.findings:
            if f.severity in ("critical", "high", "medium"):
                issue_counter[(f.category, f.severity, f.title)] += 1
        if check_links:
            pages_links[u] = rep.meta.get("links", [])
        if detect_dupes and rep.meta.get("fingerprint"):
            page_fps.append({"url": u, "fingerprint": rep.meta["fingerprint"],
                             "canonical": rep.meta.get("canonical")})
    avg = round(sum(p["score"] for p in pages) / len(pages), 1) if pages else 0

    result = {"base": base, "pages_scanned": len(pages), "avg_score": avg,
              "skipped_robots": skipped, "pages": pages, "recurring": issue_counter}
    if check_links:
        result["links"] = check_broken_links(
            pages_links, allow_private=allow_private, timeout=timeout,
            concurrency=concurrency, max_links=max_links)
    if detect_dupes:
        result["duplicates"] = find_duplicates(page_fps, dup_threshold)
    return result


def render_markdown(result: dict) -> str:
    skipped = result.get("skipped_robots", 0)
    skip_note = f"  ·  {skipped} skipped (robots.txt)" if skipped else ""
    lines = [f"# Site SEO & GEO Scan — {result['base']}", "",
             f"**Pages scanned:** {result['pages_scanned']}  ·  "
             f"**Average score:** {result['avg_score']}/100{skip_note}", ""]
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

    link_info = result.get("links")
    if link_info is not None:
        broken = link_info["broken"]
        header = (f"## Broken links ({len(broken)} of {link_info['checked']} checked"
                  + (f", {link_info['skipped_over_cap']} over cap" if link_info["skipped_over_cap"] else "")
                  + ")")
        lines.append(header)
        lines.append("")
        if not broken:
            lines.append("No broken links found. 🟢")
            lines.append("")
        else:
            lines += ["| Status | Type | Broken URL | Linked from |",
                      "|:--:|:--|:--|:--|"]
            for b in broken:
                status = b["status"] or (b["error"] or "unreachable")
                kind = "internal" if b["internal"] else "external"
                src = b["sources"][0]
                more = f" (+{len(b['sources']) - 1})" if len(b["sources"]) > 1 else ""
                lines.append(f"| {status} | {kind} | {b['url']} | {src}{more} |")
            lines.append("")

    dupes = result.get("duplicates")
    if dupes is not None:
        problem = [c for c in dupes if not c["canonical_ok"]]
        lines.append(f"## Duplicate content ({len(dupes)} near-duplicate cluster(s))")
        lines.append("")
        if not dupes:
            lines.append("No near-duplicate pages detected. 🟢")
            lines.append("")
        else:
            for i, c in enumerate(dupes, 1):
                flag = "✅ canonical consistent" if c["canonical_ok"] \
                    else "⚠️ missing/inconsistent canonical"
                lines.append(f"**Cluster {i}** — ~{c['min_similarity']}% similar · {flag}")
                for url, can in zip(c["urls"], c["canonicals"]):
                    canon = f" → canonical: {can}" if can else " → no canonical"
                    lines.append(f"- {url}{canon}")
                lines.append("")
            if problem:
                lines.append(f"> {len(problem)} cluster(s) of near-duplicate pages "
                             "lack a single consistent canonical — pick one URL per "
                             "cluster and point the rest at it with rel=canonical.")
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
    cfg = configlib.load_from_args(argv)
    d = cfg.defaults
    ap = argparse.ArgumentParser(description="Site-level SEO + GEO/LLMO scan",
                                 parents=[configlib.config_arg_parser()])
    ap.add_argument("url", help="base URL of the site")
    ap.add_argument("--max-pages", type=int, default=d["max_pages"])
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--format", choices=("markdown", "json"), default="markdown")
    ap.add_argument("-o", "--output")
    ap.add_argument("--timeout", type=int, default=d["timeout"])
    ap.add_argument("--allow-private", action="store_true")
    ap.add_argument("--delay", type=float, default=d["delay"], metavar="SECONDS",
                    help="pause between requests (sequential mode); be a polite bot")
    ap.add_argument("--concurrency", type=int, default=d["concurrency"], metavar="N",
                    help="number of pages to scan in parallel (default 4)")
    ap.add_argument("--ignore-robots", action="store_true",
                    help="do NOT skip URLs disallowed by robots.txt (off by default)")
    ap.add_argument("--check-links", action="store_true",
                    help="check outbound links (internal + external) for 4xx/5xx/dead")
    ap.add_argument("--max-links", type=int, default=d["max_links"], metavar="N",
                    help="cap the number of unique links checked (default 200)")
    ap.add_argument("--no-dupes", action="store_true",
                    help="skip near-duplicate content detection (on by default)")
    ap.add_argument("--dup-threshold", type=float,
                    default=d.get("dup_threshold", 90.0), metavar="PCT",
                    help="similarity %% at/above which pages are near-duplicates (default 90)")
    ap.add_argument("--fail-under", type=int, metavar="N", default=d.get("fail_under"),
                    help="exit non-zero if the average score is below N (for CI gating)")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    result = crawl(args.url, max_pages=args.max_pages, render=args.render,
                   allow_private=args.allow_private, timeout=args.timeout,
                   delay=args.delay, concurrency=args.concurrency,
                   obey_robots=not args.ignore_robots,
                   check_links=args.check_links, max_links=args.max_links,
                   detect_dupes=not args.no_dupes, dup_threshold=args.dup_threshold,
                   config=cfg)
    out = render_json(result) if args.format == "json" else render_markdown(result)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"Wrote {args.format} report to {args.output} "
              f"({result['pages_scanned']} pages, avg {result['avg_score']}/100)")
    else:
        print(out)

    if below_threshold(result["avg_score"], args.fail_under):
        print(f"FAIL: average score {result['avg_score']}/100 is below the "
              f"--fail-under threshold of {args.fail_under}.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
