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
from lib import report as report_lib  # noqa: E402
from lib.report import below_threshold, deliver  # noqa: E402
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
        config=None, vitals=False, strategy="mobile", gsc=False) -> dict:
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
    data = {"site": site, "page": page, "site_result": site_result, "sitemap": sitemap}
    if vitals:
        data["vitals"] = gather_vitals(site, timeout=timeout, strategy=strategy)
    if gsc:
        import gsc as gsc_mod  # noqa: PLC0415
        data["gsc"] = gsc_mod.gather(site, timeout=timeout)
    return data


def gather_vitals(site: str, *, timeout=20, strategy="mobile") -> dict:
    """Core Web Vitals for the audit: real CrUX **field** data first (origin-level),
    then PageSpeed Insights **lab** data as a fallback when CrUX has none (most
    sites). Opt-in — only runs with ``--vitals`` because it makes external API
    calls. Honest about which is which; never fabricates numbers."""
    import crux  # noqa: PLC0415
    import psi  # noqa: PLC0415
    from lib import env as envlib  # noqa: PLC0415

    crux_key = envlib.resolve("CRUX_API_KEY")
    field = crux.analyze(site, crux_key, origin=True, timeout=timeout) if crux_key else None

    lab = None
    if not (field and field.get("found")):
        psi_key = envlib.resolve("PAGESPEED_API_KEY") or crux_key
        lab = psi.analyze(site, psi_key, strategy=strategy, timeout=max(timeout, 60))
    return {"field": field, "lab": lab}


def _vitals_markdown(v: dict) -> str:
    """The Core Web Vitals section body (Markdown), demoted to slot under an H2."""
    import crux  # noqa: PLC0415
    import psi  # noqa: PLC0415
    field, lab = v.get("field"), v.get("lab")
    if field and field.get("found"):
        return _demote(crux.render_markdown(field))
    if lab is not None:
        note = ("_CrUX has no real-user field data for this site (below its traffic "
                "floor), so this is PageSpeed Insights **lab** data instead._\n\n"
                if field is not None else "")
        return note + _demote(psi.render_markdown(lab))
    if field is not None:                       # CrUX tried, no data, no lab
        return _demote(crux.render_markdown(field))
    return ("_No Core Web Vitals collected. Set `CRUX_API_KEY` for real-user field "
            "data, or `PAGESPEED_API_KEY` for lab data, then re-run with `--vitals`._")


def _vitals_headline(v: dict) -> str:
    """A short one-liner for the header/metrics strip, or '' if nothing usable."""
    field, lab = v.get("field"), v.get("lab")
    if field and field.get("found"):
        verdict = {True: "pass", False: "fail"}.get(field.get("cwv_pass"), "partial")
        return f"CWV (field): {verdict}"
    if lab and lab.get("found") and lab.get("perf_score") is not None:
        return f"Perf (lab): {lab['perf_score']}/100"
    return ""


def _gsc_markdown(g: dict, site: str) -> str:
    """The Search-performance section body (Markdown), demoted under an H2."""
    import gsc as gsc_mod  # noqa: PLC0415
    if not g.get("found"):
        return (f"_No Search Console data: {g.get('error', 'unavailable')}_"
                if g.get("error") else "_No Search Console data collected._")
    return _demote(gsc_mod.render_markdown(g, site))


def _gsc_headline(g: dict) -> str:
    """Short header-strip metric, or '' when there's no data."""
    if not g.get("found"):
        return ""
    s = g["summary"]
    delta = ""
    if s.get("clicks_prev"):
        d = round(100 * (s["clicks"] - s["clicks_prev"]) / s["clicks_prev"])
        delta = f" ({'+' if d >= 0 else ''}{d}%)"
    return f"GSC clicks ({g.get('days', 28)}d): {s['clicks']}{delta}"


def _extra_sections(data: dict) -> list:
    """The conditional report sections after the three fixed ones, numbered in
    order of presence: (number, title, markdown-body)."""
    out, n = [], 4
    cwv = data.get("vitals")
    if cwv:
        out.append((n, "Core Web Vitals", _vitals_markdown(cwv)))
        n += 1
    g = data.get("gsc")
    if g:
        out.append((n, "Search performance (GSC)", _gsc_markdown(g, data["site"])))
        n += 1
    return out


def overall_score(data: dict) -> float:
    """The audit's headline score: the lower of homepage and site-average."""
    return min(data["page"].score(), data["site_result"]["avg_score"])


def render_markdown(data: dict) -> str:
    page = data["page"]
    site_res = data["site_result"]
    sm = data["sitemap"]
    broken = len(site_res.get("links", {}).get("broken", [])) if site_res.get("links") else 0
    dupes = len(site_res.get("duplicates", []))

    cwv = data.get("vitals")
    headlines = [h for h in
                 ((_vitals_headline(cwv) if cwv else ""),
                  (_gsc_headline(data["gsc"]) if data.get("gsc") else ""))
                 if h]
    headline = "  ·  ".join(f"**{h}**" for h in headlines)
    header = [
        f"# Narwhal Site Audit — {data['site']}",
        "",
        f"**Homepage:** {page.score()}/100  ·  "
        f"**Site average:** {site_res['avg_score']}/100  ·  "
        f"**Pages scanned:** {site_res['pages_scanned']}  ",
        f"**Broken links:** {broken}  ·  **Near-duplicate clusters:** {dupes}  ·  "
        f"**Sitemap URLs:** {sm.get('total_urls', 0)}"
        + (f"  ·  {headline}" if headline else ""),
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
    for n, title, body in _extra_sections(data):
        header += ["", f"## {n}. {title}", "", body]
    return "\n".join(header).rstrip() + "\n"


def render_html(data: dict) -> str:
    """A self-contained, styled HTML audit: overall score gauge, a metrics
    strip, the homepage findings (rich cards), then the site-wide and sitemap
    sections. Reuses the shared HTML helpers and the sub-reports' Markdown so no
    presentation logic is duplicated."""
    page = data["page"]
    site_res = data["site_result"]
    sm = data["sitemap"]
    broken = len(site_res.get("links", {}).get("broken", [])) if site_res.get("links") else 0
    dupes = len(site_res.get("duplicates", []))
    overall = int(round(overall_score(data)))

    cwv = data.get("vitals")
    metrics = [
        ("Homepage", f"{page.score()}/100"),
        ("Site average", f"{site_res['avg_score']}/100"),
        ("Pages scanned", site_res["pages_scanned"]),
        ("Broken links", broken),
        ("Near-dupe clusters", dupes),
        ("Sitemap URLs", sm.get("total_urls", 0)),
    ]
    for headline in ((_vitals_headline(cwv) if cwv else ""),
                     (_gsc_headline(data["gsc"]) if data.get("gsc") else "")):
        if headline:
            label, _, val = headline.partition(": ")
            metrics.append((label, val))
    cells = "".join(
        f'<div class="metric"><span class="m-num">{report_lib._esc(v)}</span>'
        f'<span class="m-lab">{report_lib._esc(k)}</span></div>'
        for k, v in metrics)
    hero = (
        '<header class="hero">'
        f'{report_lib.score_gauge(overall)}'
        '<div class="hero-txt"><div class="grade" '
        f'style="color:{report_lib._grade_color(overall)}">Overall</div>'
        f'<div class="metrics">{cells}</div></div></header>')

    homepage = ('<h2 class="section">1. Homepage audit</h2>'
                + "".join(page._html_sections()))
    sitewide = ('<h2 class="section">2. Site-wide</h2><section class="card">'
                + report_lib.md_to_html(_demote(crawl_site.render_markdown(site_res)))
                + "</section>")
    sitemap = ('<h2 class="section">3. Sitemap</h2><section class="card">'
               + report_lib.md_to_html(_demote(validate_sitemap.render_markdown(sm)))
               + "</section>")

    extra_html = "".join(
        f'<h2 class="section">{n}. {title}</h2><section class="card">'
        + report_lib.md_to_html(body) + "</section>"
        for n, title, body in _extra_sections(data))

    body = hero + homepage + sitewide + sitemap + extra_html
    return report_lib.html_document("Narwhal Site Audit", data["site"], body)


def render_json(data: dict) -> str:
    import json
    payload = {
        "site": data["site"],
        "overall_score": overall_score(data),
        "homepage": json.loads(data["page"].to_json()),
        "crawl": json.loads(crawl_site.render_json(data["site_result"])),
        "sitemap": json.loads(validate_sitemap.render_json(data["sitemap"])),
    }
    if "vitals" in data:
        payload["vitals"] = data["vitals"]   # {field: crux result, lab: psi result}
    if "gsc" in data:
        payload["gsc"] = data["gsc"]         # gsc.gather() result
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
    ap.add_argument("--vitals", action="store_true",
                    help="include real Core Web Vitals in the report — CrUX field "
                         "data (needs CRUX_API_KEY), falling back to PageSpeed "
                         "Insights lab data. Makes external API calls.")
    ap.add_argument("--strategy", choices=("mobile", "desktop"), default="mobile",
                    help="device for the lab (PSI) fallback (default: mobile)")
    ap.add_argument("--gsc", action="store_true",
                    help="include real Google Search Console query data "
                         "(striking distance, CTR laggards, decaying pages, "
                         "cannibalization). Needs GSC OAuth credentials — see "
                         "`narwhal gsc --auth`. Makes external API calls.")
    ap.add_argument("--format", choices=("markdown", "json", "html", "pdf"),
                    default="markdown",
                    help="output format; pdf needs WeasyPrint (falls back to html)")
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
               max_links=args.max_links, max_sitemaps=args.max_sitemaps, config=cfg,
               vitals=args.vitals, strategy=args.strategy, gsc=args.gsc)
    renderers = {
        "json": render_json,
        "markdown": render_markdown,
        "html": render_html,
        "pdf": render_html,  # PDF is produced by converting the HTML
    }
    content = renderers[args.format](data)
    rc = deliver(args.format, args.output, content, label="audit",
                 score=int(round(overall_score(data))))
    if rc:
        return rc

    if below_threshold(overall_score(data), args.fail_under):
        print(f"FAIL: overall score {overall_score(data)}/100 is below the "
              f"--fail-under threshold of {args.fail_under}.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
