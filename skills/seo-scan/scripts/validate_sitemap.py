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

from lib.report_output import save_output  # noqa: E402
from lib.budgets import nonnegative_integer  # noqa: E402

from lib import http, links, sitemap as sm  # noqa: E402
from lib import config as configlib  # noqa: E402
from lib.cli_errors import url_errors  # noqa: E402
from lib.sitemap_discovery import COMMON_PATHS, Discovery  # noqa: E402

COMMON = COMMON_PATHS


def _looks_like_sitemap(url: str) -> bool:
    low = url.lower()
    return low.endswith((".xml", ".xml.gz")) or "sitemap" in low


def discover(base: str, *, allow_private, timeout, diagnostics=None, coverage=None) -> list:
    root = f"{urlparse(base).scheme}://{urlparse(base).netloc}"
    robots = http.fetch_text(urljoin(root + "/", "robots.txt"),
                             allow_private=allow_private, timeout=timeout) or ""
    found = sm.robots_sitemaps(robots, diagnostics=diagnostics)
    if found:
        return found
    discovery = Discovery('validator_candidates')
    for cand in COMMON:
        u = urljoin(root + "/", cand.lstrip("/"))
        if discovery.read(u, allow_private=allow_private, timeout=timeout):
            if coverage is not None:
                coverage.update(discovery.receipt())
            return [u]
    if coverage is not None:
        coverage.update(discovery.receipt())
    return discovery.uncertain_urls[:1]  # candidate only; validator must verify its body


def analyze(start: str, *, allow_private=False, timeout=20, sample=10,
            max_sitemaps=50) -> dict:
    nonnegative_integer(sample, 'sample')
    nonnegative_integer(max_sitemaps, 'max_sitemaps')
    start = http.normalize_url(start)
    http.assert_public_host(start, allow_private=allow_private)
    host = urlparse(start).netloc
    source_diagnostics = {}
    discovery_coverage = {}
    seeds = [start] if _looks_like_sitemap(start) else discover(
        start, allow_private=allow_private, timeout=timeout, diagnostics=source_diagnostics,
        coverage=discovery_coverage)
    seeds = list(dict.fromkeys(sm.file_url(url) for url in seeds))

    result = {
        "start": start, "seeds": seeds, "sitemaps_fetched": 0, "sitemaps_attempted": 0, "indexes": 0,
        "total_urls": 0, "errors": [], "problems": {}, "fetch_failures": 0,
        "invalid_lastmod": 0, "missing_lastmod": 0, "gzip": 0,
        "sample": [], "broken_sample": [],
        "parse_coverage": {"basis": "bounded_xml_parse", "scope": "fetched_files",
                           "verified_files": 0, "unverified_files": 0, "reasons": {},
                           "decoded_byte_limit": sm.MAX_DECODED_BYTES},
    }
    if discovery_coverage:
        result['sitemap_discovery'] = discovery_coverage
    if source_diagnostics:
        result['sitemap_references'] = sm.reference_diagnostics(source_diagnostics)
    if not seeds:
        result["errors"].append("No sitemap found (robots.txt or common paths).")
        return result

    queue = list(seeds)
    visited = set()
    url_entries = []  # {loc, lastmod}
    problems = {"not-absolute": 0, "cross-host": 0}

    while queue and len(visited) < max_sitemaps:
        smap = queue.pop(0)
        if smap in visited:
            continue
        visited.add(smap)
        result['sitemaps_attempted'] += 1
        raw, err = http.fetch_bytes(smap, allow_private=allow_private, timeout=timeout)
        if raw is None or err:
            result['fetch_failures'] += 1
            result["errors"].append(f"{smap} -> {err}")
            continue
        if raw[:2] == b"\x1f\x8b":
            result["gzip"] += 1
        result["sitemaps_fetched"] += 1
        text, parse_problem = sm.decode_checked(raw)
        if not parse_problem:
            kind, entries, parse_problem = sm.parse_checked(text)
        coverage = result['parse_coverage']
        if parse_problem:
            coverage['unverified_files'] += 1
            coverage['reasons'][parse_problem] = coverage['reasons'].get(parse_problem, 0) + 1
            continue  # a parsed prefix is not complete file evidence
        coverage['verified_files'] += 1
        if kind == "index":
            result["indexes"] += 1
            for loc in sm.usable_locations([e['loc'] for e in entries], diagnostics=source_diagnostics,
                                            source='index_locations'):
                loc = sm.file_url(loc)
                if loc not in visited:
                    queue.append(loc)
        else:
            for e in entries:
                url_entries.append(e)
                prob = sm.loc_problem(e["loc"], host)
                if prob:
                    problems[prob] = problems.get(prob, 0) + 1
                    if prob in ('invalid-url', 'not-absolute'):
                        source_diagnostics['page_locations'] = source_diagnostics.get('page_locations', 0) + 1
                if e["lastmod"] is None:
                    result["missing_lastmod"] += 1
                elif not sm.valid_lastmod(e["lastmod"]):
                    result["invalid_lastmod"] += 1

    result["total_urls"] = len(url_entries)
    result["problems"] = {k: v for k, v in problems.items() if v}
    if source_diagnostics:
        result['sitemap_references'] = sm.reference_diagnostics(source_diagnostics)
    remaining = set(queue) - visited
    if remaining:  # cap reached with distinct unattempted files still queued
        result["truncated"] = len(remaining)
        result["errors"].append(
            f"Reached --max-sitemaps ({max_sitemaps}); {len(remaining)} more sitemap "
            f"file(s) not fetched, so total URLs is a partial count.")

    # Sample exact URL identities once, preserving parsed order and both ends.
    valid_locs = list(dict.fromkeys(e["loc"] for e in url_entries
                                   if not sm.loc_problem(e["loc"], host)))
    result['sample_selection'] = {'basis': 'unique_exact_urls_evenly_spaced_v1',
                                  'eligible_unique_urls': len(valid_locs), 'requested': sample}
    response_counts = {'successful_2xx': 0, 'broken': 0, 'unverified': 0}
    if valid_locs and sample > 0:
        count = min(sample, len(valid_locs))
        indices = [0] if count == 1 else [i * (len(valid_locs) - 1) // (count - 1)
                                         for i in range(count)]
        picked = [valid_locs[i] for i in indices]
        for loc in picked:
            status, err = http.head(loc, allow_private=allow_private, timeout=timeout)
            response_counts[links.http_check_state(status, err)] += 1
            entry = {"url": loc, "status": status, "error": err}
            result["sample"].append(entry)
            if links.is_broken(status):
                result["broken_sample"].append(entry)
    result['sample_response_coverage'] = {'basis': 'shared_http_check_state_v1',
                                           'scope': 'selected_targets', **response_counts}
    return result


def _sample_succeeded(entry: dict) -> bool:
    return links.http_check_state(entry.get('status'), entry.get('error')) == 'successful_2xx'


def render_markdown(r: dict) -> str:
    lines = [f"# Sitemap validation — {r['start']}", ""]
    note = sm.reference_note(r.get('sitemap_references'))
    if note:
        lines += ['> ' + note, '']
    discovery_note = sm.discovery_note(r.get('sitemap_discovery'))
    if discovery_note:
        lines += ['> ' + discovery_note, '']
    if not r["seeds"]:
        lines += ["**No sitemap found.** Publish an XML sitemap and reference it "
                  "from robots.txt.", ""]
        return "\n".join(lines) + "\n"
    coverage = sm.recorded_parse_coverage(r.get('parse_coverage'), r['sitemaps_fetched'])
    parse_note = sm.parse_coverage_note(r.get('parse_coverage'), r['sitemaps_fetched'])
    if parse_note:
        lines += ['> ' + parse_note, '']
    fetch_failures = r.get('fetch_failures')
    fetch_incomplete = type(fetch_failures) is int and fetch_failures > 0
    lines += [
        f"- **Sitemaps fetched:** {r['sitemaps_fetched']} "
        f"({r['indexes']} index file(s){', ' + str(r['gzip']) + ' gzipped' if r['gzip'] else ''})",
        f"- **Total URLs:** {r['total_urls']}"
        + (" (verified files only; XML extraction is incomplete)" if coverage and coverage['unverified_files'] else "")
        + (" (verified fetched files only; fetch failures leave total incomplete)" if fetch_incomplete else "")
        + ("+ (partial — --max-sitemaps cap reached)" if r.get("truncated") else ""),
        f"- **Missing lastmod:** {r['missing_lastmod']}  ·  "
        f"**Invalid lastmod:** {r['invalid_lastmod']}",
    ]
    if fetch_incomplete:
        lines.append(f'- **Fetch failures:** {fetch_failures} sitemap file(s); see notes below.')
    if r["problems"]:
        probs = ", ".join(f"{k}: {v}" for k, v in r["problems"].items())
        lines.append(f"- **`<loc>` problems:** {probs}")
    selection = r.get('sample_selection')
    if (isinstance(selection, dict) and selection.get('basis') == 'unique_exact_urls_evenly_spaced_v1'
            and type(selection.get('eligible_unique_urls')) is int
            and type(selection.get('requested')) is int
            and min(selection['eligible_unique_urls'], selection['requested']) >= 0
            and len(r['sample']) == min(selection['eligible_unique_urls'], selection['requested'])):
        lines.append(f"- **Sampling policy:** {selection['eligible_unique_urls']} distinct eligible URL strings from parsed files; "
                     "deterministic evenly spaced positions (first/last when at least two are picked). "
                     "Not random or statistically representative.")
    if r["sample"]:
        ok = sum(_sample_succeeded(entry) for entry in r['sample'])
        unverified = sum(links.http_check_state(entry.get('status'), entry.get('error')) == 'unverified'
                         for entry in r['sample'])
        lines.append(f"- **Sample check:** {ok}/{len(r['sample'])} URLs returned successful 2xx"
                     + (f"; {unverified} response(s) leave reachability unverified" if unverified else ""))
    elif r['total_urls']:
        lines.append('- **Sample check:** not run; URL reachability unverified.')
    lines.append("")

    if r["broken_sample"]:
        lines += ["## Reported problem samples", "", "| Status | URL |", "|:--:|:--|"]
        for b in r["broken_sample"]:
            status = b['status'] or b['error'] or 'unrecorded response'
            if links.http_check_state(b.get('status'), b.get('error')) == 'unverified':
                status = f'{status} (unverified)'
            lines.append(f"| {status} | {b['url']} |")
        lines.append("")
    if r["errors"]:
        lines += ["## Notes", ""] + [f"- {e}" for e in r["errors"]] + [""]
    if (coverage and coverage['verified_files'] and not coverage['unverified_files']
            and r['total_urls'] and not r['errors'] and not note and not fetch_incomplete and not discovery_note
            and all(_sample_succeeded(entry) for entry in r['sample'])
            and not r["broken_sample"] and not r["problems"] and not r["invalid_lastmod"]):
        lines.append("Sitemap looks healthy for the checks performed. 🟢")
    return "\n".join(lines).rstrip() + "\n"


def render_json(r: dict) -> str:
    import json
    return json.dumps(r, indent=2, ensure_ascii=False)


@url_errors
def main(argv=None) -> int:
    cfg = configlib.load_from_args(argv)
    d = cfg.defaults
    ap = argparse.ArgumentParser(description="Validate a site's XML sitemap(s)",
                                 parents=[configlib.config_arg_parser()])
    ap.add_argument("url", help="site URL or a sitemap URL")
    ap.add_argument("--sample", type=int, default=d["sample"],
                    help="nonnegative URL sample size (0 skips URL probes)")
    ap.add_argument("--max-sitemaps", type=int, default=d["max_sitemaps"],
                    help="nonnegative sitemap validation file-attempt cap (0 skips validation fetches)")
    ap.add_argument("--format", choices=("markdown", "json"), default="markdown")
    ap.add_argument("-o", "--output")
    ap.add_argument("--timeout", type=int, default=d["timeout"])
    ap.add_argument("--allow-private", action="store_true")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    try:
        nonnegative_integer(args.sample, 'sample')
        nonnegative_integer(args.max_sitemaps, 'max_sitemaps')
    except ValueError as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2

    result = analyze(args.url, allow_private=args.allow_private, timeout=args.timeout,
                     sample=args.sample, max_sitemaps=args.max_sitemaps)
    out = render_json(result) if args.format == "json" else render_markdown(result)
    if args.output:
        if not save_output(args.output, out, label='sitemap report'):
            return 2
        print(f"Wrote {args.format} report to {args.output}")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
