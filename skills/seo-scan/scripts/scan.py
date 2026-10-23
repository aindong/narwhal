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

from lib import hreflang, http, htmlx, images, jsdiff, links, simhash, sitemap as sm  # noqa: E402
from lib.sitemap_discovery import COMMON_PATHS, Discovery  # noqa: E402
from lib import config as configlib  # noqa: E402
from lib import llms_resource, content_length, schema_coverage, readability_observation  # noqa: E402
from lib.cli_errors import url_errors  # noqa: E402
from lib.report import Report, below_threshold, deliver  # noqa: E402

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

SITEMAP_CANDIDATES = COMMON_PATHS


def gather_context(base: str, *, allow_private: bool, timeout: int) -> dict:
    """Fetch site-level resources shared across auditors."""
    root = f"{urlparse(base).scheme}://{urlparse(base).netloc}"
    ctx: dict = {}

    ctx["robots_txt"] = http.fetch_text(
        urljoin(root + "/", "robots.txt"),
        allow_private=allow_private, timeout=timeout,
    )

    llms = llms_resource.probe(
        urljoin(root + "/", "llms.txt"), allow_private=allow_private, timeout=timeout
    )
    ctx['llms_txt_receipt'] = llms
    ctx["llms_txt"] = llms['state'] == 'observed'  # legacy caller compatibility only
    ctx["llms_txt_url"] = f"{root}/llms.txt" if ctx['llms_txt'] else ""

    ctx["sitemap_found"] = False
    robots = ctx.get("robots_txt") or ""
    rejected_references = {}
    sitemap_urls = sm.robots_sitemaps(robots, diagnostics=rejected_references)
    declared = set(sitemap_urls)
    discovery = Discovery('context_candidates')
    for cand in list(sitemap_urls) + [urljoin(root + "/", p.lstrip("/")) for p in SITEMAP_CANDIDATES]:
        parsed = discovery.read(cand, allow_private=allow_private, timeout=timeout, declared=cand in declared)
        if parsed:
            ctx["sitemap_found"] = True
            ctx["sitemap_url"] = cand
            break
        if discovery.limits:
            break
    ctx['sitemap_discovery'] = discovery.receipt()
    if rejected_references:
        ctx['sitemap_references'] = sm.reference_diagnostics(rejected_references)
    return ctx


def scan(url: str, *, render=False, allow_private=False, timeout=20,
         only=None, ctx=None, collect_links=False, collect_fingerprint=False,
         config=None, check_images=True, max_bytes=5_000_000,
         retain_evidence=False) -> Report:
    """Audit a single page. Pass ``ctx`` (from :func:`gather_context`) to reuse
    site-level signals across many pages — the crawler does this so robots.txt,
    sitemap, and llms.txt are fetched once per site rather than once per page.
    Set ``collect_links=True`` to record outbound links in ``report.meta['links']``
    (used by the crawler's broken-link checker). ``config`` (a Config) tunes
    scoring weights, ignore rules, and check thresholds. Opt-in
    ``retain_evidence`` keeps response/context objects on the non-serialized
    ``_capture_inputs`` handle for maintainer review captures. They can contain
    sensitive source/headers; ordinary callers retain nothing extra."""
    config = config or configlib.Config()
    config, owned_rules = configlib.snapshot_rules(config)
    owned_context_rules = True
    if ctx is not None:
        ctx = dict(ctx)
        if "thresholds" in ctx:
            ctx["thresholds"], owned_context_rules = configlib.owned_value(ctx["thresholds"])
    selected = list(dict.fromkeys(only or list(AUDITORS)))
    unknown = sorted(set(selected) - set(AUDITORS))
    if unknown:
        raise ValueError("Unknown auditor(s): " + ", ".join(unknown))
    max_bytes = max(64_000, min(int(max_bytes), 20_000_000))
    resp = http.fetch(url, render=render, allow_private=allow_private, timeout=timeout,
                      max_bytes=max_bytes)
    report = Report(url=url, final_url=resp.final_url, fetched_status=resp.status,
                    rendered=resp.rendered,
                    weights=dict(config.weights) if isinstance(config.weights, dict) else config.weights,
                    ignore=config.is_ignored)
    if retain_evidence:
        report._capture_inputs = {'primary_response': resp, 'site_context': None,
                                  'served_response': None}
    report.meta["elapsed_ms"] = resp.elapsed_ms
    report.meta["redirects"] = resp.redirects
    report.meta["coverage"] = {
        "response_byte_limit": max_bytes,
        "response_truncated": resp.headers.get("x-narwhal-truncated") == "true",
    }
    report.meta["scan_scope"] = {
        "requested": list(selected), "completed": [],
        "not_selected": [name for name in AUDITORS if name not in selected],
    }
    report.meta["scan_settings"] = {
        "render_requested": bool(render), "rendered": bool(resp.rendered),
        "image_checks": bool(check_images and "technical" in selected),
    }

    if not resp.ok:
        report.hard_fail = True   # no measurable health; score is 0, not 88
        report.add("technical", "critical", "Page could not be fetched",
                   f"Status {resp.status}" + (f": {resp.error}" if resp.error else ""),
                   "Verify the URL is public and returns 200 before auditing.")
        return report

    content_type = resp.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type and content_type not in ("text/html", "application/xhtml+xml"):
        report.hard_fail = True
        report.add("technical", "critical", "URL did not return an HTML page",
                   f"Content-Type was {content_type!r}.",
                   "Scan a public HTML page URL, or use the dedicated sitemap/schema tool.",
                   rule_id="technical.response.non_html")
        return report

    if resp.headers.get("x-narwhal-truncated") == "true":
        report.meta["response_truncated"] = True
        report.add("technical", "medium", "Response exceeded scan byte limit",
                   f"Only the first {max_bytes / 1_000_000:g} MB of the response was analyzed.",
                   "Reduce the HTML response size or raise the explicit scan budget; "
                   "treat other findings as based on partial coverage.",
                   rule_id="technical.response.truncated", scope="page")

    doc = htmlx.parse(resp.text, base_url=resp.final_url or url)
    report._doc = doc   # non-serialized handle for tools that need the parse (compare)
    report.meta["extraction"] = doc.extraction
    alts = hreflang.extract(doc, resp.final_url or url)
    if alts:   # only when in use — keeps most reports free of empty keys
        report.meta["hreflang"] = alts
    if collect_links:
        link_diagnostics = {}
        report.meta["links"] = links.extract_links(doc, resp.final_url or url,
                                                   diagnostics=link_diagnostics,
                                                   csp=resp.headers.get('content-security-policy', ''))
        report.meta['anchor_resolution_basis'] = links.RESOLUTION_BASIS
        base_receipt = link_diagnostics.pop('anchor_base', None)
        if base_receipt is not None:
            report.meta['anchor_base'] = base_receipt
        if link_diagnostics:
            report.meta["link_extraction"] = {**link_diagnostics, "basis": (
                'url_syntax_and_declared_base_scope' if link_diagnostics.get('unassessed_base_occurrences') else 'url_syntax_only')}
    if collect_fingerprint:
        report.meta["fingerprint"] = simhash.simhash(doc.body_text)
        report.meta["canonical"] = doc.canonical()
    if ctx is None:
        ctx = gather_context(resp.final_url or url,
                             allow_private=allow_private, timeout=timeout)
    receipt = sm.recorded_reference_diagnostics(ctx.get('sitemap_references'))
    reference_counts = dict(receipt['rejected']) if receipt else {}
    observed = {}
    sm.robots_sitemaps(ctx.get('robots_txt') or '', diagnostics=observed)
    if observed:
        reference_counts['robots_directives'] = max(observed['robots_directives'],
                                                    reference_counts.get('robots_directives', 0))
    if reference_counts:
        report.meta['sitemap_references'] = sm.reference_diagnostics(reference_counts)
    # expose tunable thresholds to auditors without mutating a shared ctx
    effective_thresholds, owned_effective_rules = configlib.owned_value(ctx.get("thresholds", config.thresholds))
    ctx = {**ctx, "thresholds": effective_thresholds}
    fingerprint = (configlib.comparison_fingerprint(config, ctx["thresholds"], weights=report.weights)
                   if owned_rules and owned_context_rules and owned_effective_rules else None)
    if fingerprint is not None:
        report.meta["scan_settings"]["rule_config"] = fingerprint

    # JS-dependence: when we actually rendered, fetch the served HTML too and
    # diff — content that only exists post-JS is invisible to non-rendering
    # crawlers (incl. most AI fetchers). Without Playwright there is no rendered
    # DOM, so nothing is measured and nothing is said (never guess).
    if resp.headers.get("x-narwhal-truncated") == "true":
        ctx.pop("jsdep", None)  # a cached value is not evidence for this partial snapshot
    if resp.rendered and not resp.error:
        ctx.pop("jsdep", None)
        receipt = {"status": "unverified", "byte_limit": max_bytes}
        report.meta["coverage"]["js_comparison"] = receipt
        if resp.headers.get("x-narwhal-truncated") == "true":
            receipt["reason"] = "rendered_html_truncated"
        else:
            try:
                raw_resp = http.fetch(url, allow_private=allow_private, timeout=timeout,
                                      max_bytes=max_bytes)
                if retain_evidence:
                    report._capture_inputs['served_response'] = raw_resp
            except (OSError, http.URLInputError):
                raw_resp = None
            if raw_resp is None or not raw_resp.ok or raw_resp.status != 200:
                receipt["reason"] = "served_html_unavailable"
            elif raw_resp.headers.get("x-narwhal-truncated") == "true":
                receipt["reason"] = "served_html_truncated"
            elif raw_resp.headers.get("content-type", "").split(";", 1)[0].strip().lower() not in (
                    "", "text/html", "application/xhtml+xml"):
                receipt["reason"] = "served_non_html"
            else:
                dep = jsdiff.analyze(raw_resp.text, resp.text, resp.final_url or url)
                ctx["jsdep"] = dep
                report.meta["js_dependence"] = {
                    k: dep[k] for k in ("words_raw", "words_rendered", "js_only_pct")}
                if isinstance(dep.get('text_comparison'), dict):
                    report.meta['js_dependence']['text_comparison'] = dict(dep['text_comparison'])
                receipt["status"] = "measured"

    if retain_evidence:
        report._capture_inputs['site_context'] = ctx

    for name in selected:
        fn = AUDITORS.get(name)
        if fn:
            fn(doc, resp, report, ctx)
            report.meta["scan_scope"]["completed"].append(name)

    if content_length.note(report.meta) is not None:
        report.meta['scan_settings']['content_length_reviewed'] = (
            report.meta['content_length']['threshold_status'] != 'uninterpreted')
    if readability_observation.recorded(report.meta.get('readability')) is not None:
        report.meta['scan_settings']['readability_reviewed'] = (
            report.meta['readability']['formula_status'] == 'computed')
    schema_state = schema_coverage.state(schema_coverage.meta_receipt(report.meta))
    if 'schema' in report.meta['scan_scope']['completed'] and schema_state != 'unknown':
        report.meta['scan_settings']['schema_extraction_reviewed'] = schema_state == 'no_known_problem'

    # Image weight/format + og:image checks: a few HEADs and one ranged GET per
    # page, so they're on for single-page scans but skipped during crawls
    # (which would multiply the requests by every crawled page).
    if check_images and "technical" in selected:
        facts = images.audit_images(doc, resp.final_url or url,
                                    allow_private=allow_private,
                                    timeout=min(timeout, 8))
        report.meta["images"] = {k: facts[k] for k in
                                 ("checked", "unchecked", "missing_dims")}
        images.findings(facts, report)
    return report


@url_errors
def main(argv=None) -> int:
    cfg = configlib.load_from_args(argv)
    ap = argparse.ArgumentParser(description="SEO + GEO/LLMO single-page auditor",
                                 parents=[configlib.config_arg_parser()])
    ap.add_argument("url", help="URL to audit")
    ap.add_argument("--render", action="store_true",
                    help="render JS with Playwright if installed")
    ap.add_argument("--format", choices=("markdown", "json", "html", "pdf"),
                    default="markdown",
                    help="output format; pdf needs WeasyPrint (falls back to html)")
    ap.add_argument("--only", help="comma-separated subset: technical,content,schema,geo")
    ap.add_argument("-o", "--output", help="write report to a file")
    ap.add_argument("--timeout", type=int, default=cfg.default("timeout"))
    ap.add_argument("--max-bytes", type=int, default=5_000_000, metavar="N",
                    help="maximum HTML response bytes to analyze (64KB–20MB; default 5MB)")
    ap.add_argument("--allow-private", action="store_true",
                    help="permit private/localhost hosts (off by default for SSRF safety)")
    ap.add_argument("--no-image-checks", action="store_true",
                    help="skip image weight/og:image checks (a few HEAD requests)")
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
                  timeout=args.timeout, only=only, config=cfg,
                  check_images=not args.no_image_checks, max_bytes=args.max_bytes)

    renderers = {
        "json": report.to_json,
        "markdown": report.to_markdown,
        "html": report.to_html,
        "pdf": report.to_html,  # PDF is produced by converting the HTML
    }
    content = renderers[args.format]()
    rc = deliver(args.format, args.output, content, score=report.score())
    if rc:
        return rc

    if below_threshold(report.score(), args.fail_under):
        print(f"FAIL: {report.score_label().lower()} {report.score()}/100 is below the "
              f"--fail-under threshold of {args.fail_under}.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
