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
import math
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from urllib.parse import urljoin, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.report_output import save_output  # noqa: E402
from lib.budgets import nonnegative_integer  # noqa: E402

from lib import hreflang, http, htmlx, links, simhash, sitegraph, sitemap as sm  # noqa: E402
from lib import config as configlib  # noqa: E402
from lib.cli_errors import url_errors  # noqa: E402
from lib.markdown_text import TABLE_TEXT_MARKER, table_text  # noqa: E402
from lib.report import SEVERITY, below_threshold  # noqa: E402
from lib.report import recorded_js_comparison_problem, recorded_sitemap_discovery_problem  # noqa: E402
from lib.report import recorded_llms_problem, recorded_schema_extraction_problem  # noqa: E402
from lib.report import recorded_response_partial  # noqa: E402
from lib import llms_resource  # noqa: E402
from lib import canonical  # noqa: E402
from lib.report import _crawler_meta_notes, _http_robots_notes  # noqa: E402
from lib.sitemap_discovery import COMMON_PATHS, Discovery, MAX_INDEX_CHILDREN  # noqa: E402
from lib.robots import RobotsTxt  # noqa: E402
import scan as scanner  # noqa: E402


def _norm_canonical(url):
    return canonical.key(url)


def find_duplicates(page_fps: list, threshold_pct: float) -> list:
    """Cluster near-duplicate pages and compare their first canonical targets.

    ``page_fps`` is a list of ``{url, fingerprint, canonical}``. Returns clusters
    with the minimum pairwise similarity and whether the near-dupes point to a
    single supported component key (``canonical_ok``). This does not verify
    consolidation, target access/content or a search engine's selected URL.
    """
    items = [(i, p["fingerprint"]) for i, p in enumerate(page_fps)
             if p.get("fingerprint")]
    clusters = []
    for idxs in simhash.cluster(items, threshold_pct):
        pages = [page_fps[i] for i in idxs]
        sims = [simhash.similarity(pages[a]["fingerprint"], pages[b]["fingerprint"])
                for a in range(len(pages)) for b in range(a + 1, len(pages))]
        canon_targets = {_norm_canonical(p["canonical"]) for p in pages}
        canonical_ok = None not in canon_targets and len(canon_targets) == 1
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

SITEMAP_CANDIDATES = COMMON_PATHS


def discover(base: str, *, allow_private: bool, timeout: int, limit: int,
             robots_txt=None, diagnostics=None, coverage=None, discovered_sitemap=None) -> list:
    root = f"{urlparse(base).scheme}://{urlparse(base).netloc}"
    urls: list = []

    # 1) sitemap(s), including a one-level sitemap index. Reuse an already-fetched
    # robots.txt when the caller provides one (avoids a redundant request).
    if robots_txt is None:
        robots_txt = http.fetch_text(urljoin(root + "/", "robots.txt"),
                                     allow_private=allow_private, timeout=timeout) or ""
    robots = robots_txt
    sm_urls = sm.robots_sitemaps(robots, diagnostics=diagnostics)
    declared = set(sm_urls)
    sm_urls += [urljoin(root + "/", p.lstrip("/")) for p in SITEMAP_CANDIDATES]
    discovery = Discovery('crawl_candidates')
    for sitemap_url in sm_urls:
        parsed = discovery.read(sitemap_url, allow_private=allow_private, timeout=timeout, declared=sitemap_url in declared)
        if not parsed:
            if 'file_attempt_budget' in discovery.limits:
                break
            continue
        kind, entries = parsed
        locs = [entry['loc'] for entry in entries]
        if kind == 'index':
            children = list(dict.fromkeys(sm.file_url(child) for child in
                                         sm.usable_locations(locs, diagnostics=diagnostics, source='index_locations')))
            if len(children) > MAX_INDEX_CHILDREN:
                discovery.limit('index_child_budget')
            for child in children[:MAX_INDEX_CHILDREN]:
                child_data = discovery.read(child, allow_private=allow_private, timeout=timeout, declared=True)
                if not child_data:
                    continue
                if child_data[0] == 'index':
                    if child_data[1]:
                        discovery.limit('nested_index_depth')
                    continue
                urls += sm.usable_locations([entry['loc'] for entry in child_data[1]], diagnostics=diagnostics)
        else:
            urls += sm.usable_locations(locs, diagnostics=diagnostics)
        if urls:
            break
    if coverage is not None:
        coverage.update(discovery.receipt())
    sitemap_keys = {sitegraph.norm(url) for url in urls} if discovered_sitemap is not None else set()

    # 2) fallback: internal links on the entry page
    if not urls:
        resp = http.fetch(base, allow_private=allow_private, timeout=timeout)
        if resp.ok and not http.has_range_evidence(resp):
            doc = htmlx.parse(resp.text, base_url=resp.final_url or base)
            for observation in links.extract_links(doc, resp.final_url or base,
                                                   csp=resp.headers.get('content-security-policy', '')):
                if observation['internal']:
                    urls.append(observation['url'])

    # De-dupe observed URL identities, keep order and drop obvious non-HTML assets.
    # Only fragments/case-insensitive scheme+host group; path/query literals stay.
    seen, out = set(), []
    for u in [base] + urls:
        u = u.split("#")[0]
        key = sitegraph.norm(u)
        if key in seen or re.search(r"\.(jpg|png|gif|svg|pdf|css|js|xml|zip)$", u, re.I):
            continue
        seen.add(key)
        out.append(u)
        if len(out) >= limit:
            break
    if discovered_sitemap is not None:
        discovered_sitemap.extend(url for url in out if sitegraph.norm(url) in sitemap_keys)
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
    nonnegative_integer(max_links, 'max_links')
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

    broken, unverified = [], []
    counts = {'successful_2xx': 0, 'broken': 0, 'unverified': 0}
    request_failures = 0
    for u in targets:
        status, err = statuses[u]
        state = links.http_check_state(status, err)
        counts[state] += 1
        if type(status) is int and status == 0:
            request_failures += 1
        observation = {"url": u, "status": status, "error": err,
                       "internal": registry[u]["internal"], "sources": sorted(registry[u]["sources"])}
        if type(status) is int and links.is_broken(status):
            broken.append(observation)  # preserve the legacy problem-target list
        if state == 'unverified':
            unverified.append(observation)
    broken.sort(key=lambda b: (not b["internal"], b["url"]))  # internal first
    return {"unique_links": len(order), "checked": len(targets),
            "skipped_over_cap": max(0, len(order) - len(targets)),
            "broken": broken, "unverified": unverified,
            "coverage": {"basis": "head_responses", "scope": "checked_targets",
                         **counts, "request_failures": request_failures}}


def _link_coverage(info):
    receipt = info.get('coverage')
    if (not isinstance(receipt, dict) or receipt.get('basis') != 'head_responses'
            or receipt.get('scope') != 'checked_targets'):
        return None
    records = info.get('broken', [])
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        return None
    values = [receipt.get(key) for key in ('successful_2xx', 'broken', 'unverified')]
    request_failures = receipt.get('request_failures')
    if (any(type(value) is not int or value < 0 for value in values)
            or type(request_failures) is not int or not 0 <= request_failures <= receipt['unverified']
            or type(info.get('checked')) is not int or sum(values) != info['checked']
            or request_failures != sum(type(row.get('status')) is int and row['status'] == 0 for row in records)
            or receipt['broken'] != sum(links.http_check_state(row.get('status'), row.get('error')) == 'broken'
                                        for row in records)):
        return None
    if 'unverified' in info:
        rows = info['unverified']
        if (not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows)
                or len(rows) != receipt['unverified']
                or any(links.http_check_state(row.get('status'), row.get('error')) != 'unverified' for row in rows)
                or any(not isinstance(row.get('url'), str) or not row['url'].strip() for row in rows)):
            return None
        by_url = {row['url']: row for row in rows}
        if len(by_url) != len(rows):
            return None
        for row in records:
            if links.http_check_state(row.get('status'), row.get('error')) != 'unverified':
                continue
            url = row.get('url')
            retained = by_url.get(url) if isinstance(url, str) else None
            if retained is None or any(retained.get(key) != row.get(key)
                                       for key in ('status', 'error', 'internal', 'sources')):
                return None
    return receipt


def _duplicate_coverage(result):
    receipt = result.get('duplicate_coverage')
    if (not isinstance(receipt, dict) or receipt.get('basis') != 'simhash_fingerprints'
            or receipt.get('scope') != 'scanned_pages'):
        return None
    eligible, scanned = receipt.get('eligible_pages'), receipt.get('scanned_pages')
    if (type(eligible) is not int or type(scanned) is not int
            or type(result.get('pages_scanned')) is not int
            or not 0 <= eligible <= scanned or scanned != result['pages_scanned']):
        return None
    return receipt


def link_summary(info):
    """Scoped observations for audit headlines; missing execution is not zero."""
    if info is None:
        return 'not run'
    receipt = _link_coverage(info)
    if receipt is None:
        return (f"{len(info.get('broken', []))} reported / {info.get('checked', 0)} checked"
                ' (response coverage unrecorded)')
    summary = f"{receipt['broken']} observed / {info['checked']} checked"
    if receipt['request_failures']:
        return summary + f" ({receipt['unverified']} unverified; {receipt['request_failures']} no HTTP response)"
    return summary + (f" ({receipt['unverified']} unverified)" if receipt['unverified'] else '')


def duplicate_summary(result):
    if result.get('duplicates') is None:
        return 'not run'
    receipt = _duplicate_coverage(result)
    count = len(result['duplicates'])
    if receipt is None:
        return f'{count} observed (comparison coverage unrecorded)'
    eligible = receipt['eligible_pages']
    if eligible < 2:
        return f'insufficient data ({eligible} eligible fingerprints)'
    return f'{count} observed ({eligible} eligible fingerprints)'


def summarize_ecommerce(pages: list) -> dict:
    """Bounded, serializable product/store scope for conditional specialists."""
    product_pages = [p["url"] for p in pages if p.get("is_product")]
    # Fail closed for contradictory imported/older page metadata too.
    merchant_pages = [p["url"] for p in pages if p.get("is_product") and p.get("is_merchant")]
    return {"detected": bool(merchant_pages),
            "product_pages": product_pages,
            "product_pages_count": len(product_pages),
            "merchant_pages": merchant_pages,
            "merchant_pages_count": len(merchant_pages)}


def validate_budgets(*, max_pages, concurrency):
    """Require usable crawl limits before standalone or composite audit I/O."""
    for name, value in (('max_pages', max_pages), ('concurrency', concurrency)):
        if type(value) is not int or value < 1:
            raise ValueError(f'{name} must be a positive integer.')


def _delay_seconds(value):
    """Validate pacing before discovery or HTTP, including configured defaults."""
    try:
        if type(value) not in (int, float):
            raise ValueError
        seconds = float(value)
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError
    except (ValueError, OverflowError):
        raise ValueError('delay must be a finite, nonnegative number of seconds.') from None
    return seconds


def crawl(base: str, *, max_pages=15, render=False, allow_private=False,
          timeout=20, delay=0.0, concurrency=4, obey_robots=True,
          check_links=False, max_links=200, detect_dupes=True,
          dup_threshold=90.0, config=None) -> dict:
    validate_budgets(max_pages=max_pages, concurrency=concurrency)
    nonnegative_integer(max_links, 'max_links')
    delay = _delay_seconds(delay)
    base = http.normalize_url(base)
    config = config or configlib.Config()
    config, _ = configlib.snapshot_rules(config)
    # Fetch site-level signals (robots/sitemap/llms) ONCE and reuse for every
    # page — polite and much faster than re-fetching per page.
    ctx = scanner.gather_context(base, allow_private=allow_private, timeout=timeout)
    ctx = dict(ctx)
    if "thresholds" in ctx:
        ctx["thresholds"], _ = configlib.owned_value(ctx["thresholds"])
    robots_txt = ctx.get("robots_txt") or ""
    rt = RobotsTxt.parse(robots_txt)

    # Over-fetch candidates so we still reach max_pages after robots filtering.
    source_diagnostics = {}
    discovery_coverage = {}
    sitemap_urls = []
    candidates = discover(base, allow_private=allow_private, timeout=timeout,
                          limit=max_pages * 3 if obey_robots else max_pages,
                          robots_txt=robots_txt, diagnostics=source_diagnostics, coverage=discovery_coverage,
                          discovered_sitemap=sitemap_urls)
    gathered = sm.recorded_reference_diagnostics(ctx.get('sitemap_references'))
    if gathered:
        for key, value in gathered['rejected'].items():
            source_diagnostics[key] = max(value, source_diagnostics.get(key, 0))

    urls, skipped = select_urls(candidates, base, rt, obey_robots, max_pages)

    pace_lock = Lock()
    next_scan_at = None

    def scan_one(u):
        nonlocal next_scan_at
        if concurrency > 1 and delay > 0:
            with pace_lock:
                remaining = 0 if next_scan_at is None else next_scan_at - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)
                # Schedule from the actual wakeup so late workers cannot burst.
                next_scan_at = time.monotonic() + delay
        # collect_links is always on: link extraction is pure parsing (no extra
        # requests) and feeds the site-graph analysis even without --check-links.
        return u, scanner.scan(u, render=render, allow_private=allow_private,
                               timeout=timeout, ctx=ctx, collect_links=True,
                               collect_fingerprint=detect_dupes, config=config,
                               check_images=False)

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
    rule_counter = Counter()
    pages_hreflang: dict = {}
    hreflang_coverage, partial_hreflang, sampled_hreflang_observations = {}, set(), []
    for u, rep in results:
        ecommerce = rep.meta.get("ecommerce", {})
        coverage = rep.meta.get("coverage")
        truncated = rep.meta.get("response_truncated") is True or (
            isinstance(coverage, dict) and coverage.get("response_truncated") is True)
        pages.append({"url": u, "score": rep.score(), "hard_fail": bool(rep.hard_fail),
                      "response_truncated": truncated,
                      "js_comparison_unverified": bool(recorded_js_comparison_problem(rep.meta, for_score=True)),
                      "sitemap_discovery_unverified": bool(recorded_sitemap_discovery_problem(rep.meta, for_score=True)),
                      "llms_txt_unverified": bool(recorded_llms_problem(rep.meta, for_score=True)),
                      'schema_extraction_unverified': bool(recorded_schema_extraction_problem(rep.meta, for_score=True)),
                      'canonical_comparison_unverified': canonical.unverified(rep.meta),
                      'hreflang_comparison_unverified': hreflang.unverified(rep.meta, for_score=True),
                      "scan_settings": rep.meta.get("scan_settings", {}),
                      "counts": rep.counts(),
                      "is_product": bool(ecommerce.get("is_product")),
                      "is_merchant": bool(ecommerce.get("is_merchant")),
                      "product_confidence": ecommerce.get("confidence", 0.0)})
        if rep.meta.get("link_extraction"):
            pages[-1]["link_extraction"] = dict(rep.meta["link_extraction"])
        if isinstance(rep.meta.get('anchor_base'), dict):
            pages[-1]['anchor_base'] = dict(rep.meta['anchor_base'])
        if recorded_response_partial(rep.meta):
            pages[-1]['response_partial'] = True
        hreflang_receipt = hreflang.recorded(rep.meta)
        if hreflang_receipt is not None:
            pages[-1]['hreflang_extraction'] = hreflang_receipt
            hreflang_coverage[u] = hreflang_receipt
        source_observation = hreflang.recorded_observation(rep.meta)
        if source_observation is not None:
            pages[-1]['hreflang_source_observation'] = dict(source_observation)
        sampled_hreflang_observations.append({'target': u, **(source_observation or {'status': 'unrecorded'})})
        if rep.hard_fail or truncated or source_observation is None or source_observation['status'] != 'source_observed':
            partial_hreflang.add(u)
        for key in ('crawler_meta_robots', 'http_robots', 'llms_txt'):
            if not rep.hard_fail and isinstance(rep.meta.get(key), dict):
                pages[-1][key] = rep.meta[key]
        for f in rep.findings:
            if f.severity in ("critical", "high", "medium"):
                issue_counter[(f.category, f.severity, f.title)] += 1
                rule_counter[(f.category, f.severity, f.title, f.rule_id)] += 1
        pages_links[u] = rep.meta.get("links", [])
        pages_hreflang[u] = rep.meta.get('hreflang', []) if u not in partial_hreflang else []
        if detect_dupes and not rep.hard_fail and not truncated and rep.meta.get("fingerprint"):
            page_fps.append({"url": u, "fingerprint": rep.meta["fingerprint"],
                             "canonical": rep.meta.get("canonical")})
    avg = round(sum(p["score"] for p in pages) / len(pages), 1) if pages else 0

    ecommerce_scope = summarize_ecommerce(pages)
    result = {"base": base, "pages_scanned": len(pages), "avg_score": avg,
              "skipped_robots": skipped, "pages": pages, "recurring": issue_counter,
              "recurring_rule_counts": rule_counter,
              "ecommerce": ecommerce_scope}
    llms = llms_resource.recorded(ctx.get('llms_txt_receipt'))
    if llms:
        result['llms_txt'] = dict(llms)
    if discovery_coverage:
        result['sitemap_discovery'] = discovery_coverage
    if source_diagnostics:
        result['sitemap_references'] = sm.reference_diagnostics(source_diagnostics)
    omitted = [p["link_extraction"].get("invalid_url_occurrences", 0)
               for p in pages if p.get("link_extraction", {}).get('invalid_url_occurrences')]
    if omitted:
        result["link_extraction"] = {"invalid_url_occurrences": sum(omitted),
                                     "affected_pages": len(omitted), "basis": "url_syntax_only"}
    # Site structure (click depth, orphans, link equity) — pure computation on
    # data already in hand; orphan detection only makes sense sitemap-sourced.
    result["graph"] = sitegraph.analyze(
        base, [u for u, _ in results], pages_links,
        sitemap_urls, bool(sitemap_urls))
    result['link_resolution_basis'] = links.RESOLUTION_BASIS
    result['hreflang_policy_basis'] = hreflang.EXTRACTION_BASIS
    result['hreflang_acquisition_basis'] = hreflang.SNAPSHOT_BASIS
    result["sitemap_candidates"] = len(sitemap_urls)
    # Hreflang reciprocity — only when the site actually uses hreflang. Probe a
    # few same-host alternates (capped) so return tags are verifiable instead of
    # all "unverified".
    if any(pages_hreflang.values()) or any(receipt['declared'] for receipt in hreflang_coverage.values()):
        probe_coverage = {}
        probe_observations = []
        probed = hreflang.probe(pages_hreflang, allow_private=allow_private,
                                timeout=min(timeout, 8), diagnostics=probe_coverage, observations=probe_observations)
        result["hreflang"] = hreflang.analyze({**pages_hreflang, **probed},
                                             coverage={**hreflang_coverage, **probe_coverage}, partial_sources=partial_hreflang)
        result["hreflang"]["probed"] = len(probed)
        result['hreflang']['probe_observations'] = probe_observations
        result['hreflang']['sampled_source_observations'] = sampled_hreflang_observations
    if check_links:
        result["links"] = check_broken_links(
            pages_links, allow_private=allow_private, timeout=timeout,
            concurrency=concurrency, max_links=max_links)
    if detect_dupes:
        result["duplicates"] = find_duplicates(page_fps, dup_threshold)
        result['duplicate_coverage'] = {'basis': 'simhash_fingerprints', 'scope': 'scanned_pages',
                                        'eligible_pages': len(page_fps), 'scanned_pages': len(pages)}
    return result


def _observation_literal(value, limit, prose=False):
    """Keep bounded page/receipt text literal in Markdown and branded HTML."""
    value = ' '.join(str(value).split())
    if len(value) > limit:
        value = value[:limit] + '…'
    if prose and re.fullmatch(r'''[A-Za-z0-9 .,:;/()'"%+!?-]*''', value) and '://' not in value:
        return value  # readable prose with no Markdown/HTML syntax or autolinks
    delimiter = '`' * (1 + max((len(run) for run in re.findall(r'`+', value)), default=0))
    return delimiter + ' ' + value + ' ' + delimiter


def _page_indexing_notes(page):
    """Read known receipts only; failed/legacy pages cannot establish policy."""
    if page.get('hard_fail'):
        return []
    notes = _crawler_meta_notes(page)
    header_notes = _http_robots_notes(page)
    if header_notes:
        generic = page['http_robots'].get('generic')
        if (isinstance(generic, list) and generic
                and all(rule in ('noindex', 'nofollow') for rule in generic)):
            notes.append('Unprefixed HTTP X-Robots-Tag declares ' + ', '.join(sorted(set(generic)))
                         + '; corresponding findings remain in the score/issue rollup.')
        notes.extend('HTTP: ' + note for note in header_notes)
    return notes


def schema_extraction_note(result: dict) -> str:
    """Qualify aggregate scores only for explicitly recorded extraction gaps."""
    affected = sum(1 for page in result.get('pages', []) if isinstance(page, dict) and (
        page.get('schema_extraction_unverified') is True
        or recorded_schema_extraction_problem({'scan_settings': page.get('scan_settings')}, for_score=True)))
    if not affected:
        return ''
    return (f'Structured-data extraction needs verification on {affected} scanned page(s); '
            'schema/overall score comparisons, including the site average, are unverified. '
            'Raw scores are retained, not proof of improvement.')


def canonical_comparison_note(result: dict) -> str:
    """Qualify the site average only for explicitly recorded comparison gaps."""
    affected = sum(1 for page in result.get('pages', []) if isinstance(page, dict)
                   and page.get('canonical_comparison_unverified') is True)
    return (f'HTML canonical comparison needs verification on {affected} scanned page(s); '
            'technical/overall score comparisons, including the site average, are unverified.') if affected else ''


def anchor_base_note(result: dict) -> str:
    """Expose known sampled base gaps even when per-page displays are capped."""
    affected = sum(1 for page in result.get('pages', []) if isinstance(page, dict) and links.unassessed_base(page))
    return (f'Declared anchor-base coverage is unassessed on {affected} scanned page(s); '
            'technical/overall score comparisons and graph completeness are unverified. '
            'Raw counts and scores are retained, not proof of site improvement.') if affected else ''


def partial_response_note(result: dict) -> str:
    """Do not silently mix full-page scores with unassessed range responses."""
    affected = sum(recorded_response_partial(page) for page in result.get('pages', []))
    return (f'{affected} sampled page(s) have partial/ranged HTML coverage; full-page health is unassessed. '
            'Fail-safe zeros and raw scores are retained, not a comparable site-health measurement or SEO change.') if affected else ''


def hreflang_source_note(result: dict) -> str:
    """Keep known source gaps visible even if a sampled cluster has no usable URLs."""
    affected = sum(hreflang.unverified(page) for page in result.get('pages', []))
    scored = any(page.get('hreflang_comparison_unverified') is True for page in result.get('pages', []))
    return ((f'HTML hreflang source URL coverage has omissions on {affected} scanned page(s); '
             'relationship checks involving omitted/partial sources are unassessed, not broken URLs. '
             + ('Technical/overall score comparisons are unverified. ' if scored else '')
             + 'Raw observations and scores are retained, not proof of site improvement.') if affected else '')


def render_markdown(result: dict) -> str:
    skipped = result.get("skipped_robots", 0)
    skip_note = f"  ·  {skipped} skipped (robots.txt)" if skipped else ""
    lines = [f"# Site SEO & GEO Scan — {result['base']}", "",
             f"**Pages scanned:** {result['pages_scanned']}  ·  "
             f"**Average score:** {result['avg_score']}/100{skip_note}", ""]
    if result.get('link_resolution_basis') == links.RESOLUTION_BASIS:
        lines += ['Relative anchor paths preserve repeated separators while resolving literal dot segments. '
                  'Supported targets use the first declared non-template base href when present. '
                  'This is not full browser URL conformance or server equivalence; fetch guards and budgets remain separate.', '']
    else:
        lines += ['Anchor link-resolution policy was not recorded; historical path merging is unverified.', '']
    schema_note = schema_extraction_note(result)
    if schema_note:
        lines += ['> ' + schema_note, '']
    canonical_note = canonical_comparison_note(result)
    if canonical_note:
        lines += ['> ' + canonical_note, '']
    base_scope_note = anchor_base_note(result)
    if base_scope_note:
        lines += ['> ' + base_scope_note, '']
    hreflang_scope_note = hreflang_source_note(result)
    if hreflang_scope_note:
        lines += ['> ' + hreflang_scope_note, '']
    partial_note = partial_response_note(result)
    if partial_note:
        lines += ['> ' + partial_note, '']
    sitemap_note = sm.reference_note(result.get('sitemap_references'))
    if sitemap_note:
        lines += ['> ' + sitemap_note, '']
    discovery_note = sm.discovery_note(result.get('sitemap_discovery'))
    if discovery_note:
        lines += ['> ' + discovery_note, '']
    omission = result.get("link_extraction")
    if omission:
        lines += [f"> {omission['invalid_url_occurrences']} malformed HTTP href occurrence(s) "
                  f"in {omission['affected_pages']} scanned page(s) were omitted from HTTP link collection. "
                  "These are source syntax issues, not network failures; they were not HTTP-checked.", ""]
    base_pages = [(page.get('url', ''), links.base_note(page)) for page in result['pages']
                  if not page.get('hard_fail') and links.base_note(page)]
    unassessed_urls = {page.get('url', '') for page in result['pages'] if links.unassessed_base(page)}
    base_pages.sort(key=lambda item: item[0] not in unassessed_urls)
    if base_pages:
        lines += ['## Declared anchor-base observations (not scored)', '']
        for url, note in base_pages[:5]:
            lines += ['- ' + _observation_literal(url, 400) + ': ' + note]
        if len(base_pages) > 5:
            lines += [f'- … +{len(base_pages) - 5} more sampled pages (see JSON)']
        lines += ['']
    ranked = sorted(result["pages"], key=lambda p: p["score"])
    llms_note = llms_resource.note(result)
    if llms_note:
        lines += ['## Root llms.txt response evidence', '', llms_note, '']
    lines += ["## Weakest pages", "", TABLE_TEXT_MARKER, "| Score | URL |", "|:--:|:--|"]
    for p in ranked[:10]:
        lines.append(f"| {p['score']} | {table_text(p['url'])} |")
    lines.append("")
    recurring = sorted(result["recurring"].items(), key=lambda item: (
        SEVERITY.index(item[0][1]) if item[0][1] in SEVERITY else len(SEVERITY),
        -item[1], item[0]))[:12]
    if recurring:
        lines += ["## Priority issues (severity first, then frequency)", "",
                  "| Count | Severity | Category | Issue |", "|:--:|:--|:--|:--|"]
        for (cat, sev, title), n in recurring:
            lines.append(f"| {n} | {sev} | {cat} | {title} |")
        lines.append("")
        omitted = len(result["recurring"]) - len(recurring)
        if omitted:
            lines += [f"> {omitted} additional issue type(s) not shown; "
                      "the JSON report retains the full rollup.", ""]

    observations = []
    for page in result['pages']:
        notes = _page_indexing_notes(page)
        if notes:
            observations.append((page.get('url', ''), notes))
    if observations:
        lines += ['## Sampled-page indexing observations (not scored)', '',
                  'Recorded declarations and transport notes on scanned pages only; not effective cross-source policy, '
                  'whole-site coverage or proof of live crawling/indexing. These notes add no score penalties. '
                  'Partial snapshots establish observed declarations only. Review intended policy manually.', '']
        for url, notes in observations[:10]:
            lines += ['### ' + _observation_literal(url, 600), '']
            lines += ['- ' + _observation_literal(note, 600, prose=True) for note in notes[:8]]
            if len(notes) > 8:
                lines.append(f'- {len(notes) - 8} more notes for this page are not displayed; inspect its JSON receipts.')
            lines.append('')
        if len(observations) > 10:
            lines += [f'> {len(observations) - 10} more sampled page(s) with observations are retained in JSON.', '']

    hl = result.get("hreflang")
    if hl and hl.get("used"):
        lines += hreflang.render_markdown(hl)

    graph = result.get("graph")
    if graph is not None:
        lines += sitegraph.render_markdown(
            graph, sitemap_total=result.get("sitemap_candidates", 0))

    link_info = result.get("links")
    if link_info is not None:
        broken = link_info["broken"]
        header = (f"## Broken or unreachable targets ({len(broken)} of {link_info['checked']} checked"
                  + (f", {link_info['skipped_over_cap']} over cap" if link_info["skipped_over_cap"] else "")
                  + ")")
        lines.append(header)
        lines.append("")
        receipt = _link_coverage(link_info)
        if receipt is None:
            lines += ['> HTTP response coverage was not recorded; reachability remains unverified.', '']
        else:
            lines += [f"{receipt['successful_2xx']} successful 2xx response(s); "
                      f"{receipt['broken']} broken response(s); "
                      f"{receipt['unverified']} response(s) leave reachability unverified. "
                      'Counts cover HTTP-checked targets only, not all site links.', '']
            if receipt['request_failures']:
                lines += [f"{receipt['request_failures']} request(s) produced no HTTP response "
                          '(included in unverified, not broken HTTP responses).', '']
        if not broken:
            if not link_info['checked']:
                lines.append('No HTTP link targets were checked; reachability unverified.')
            else:
                lines.append('No broken links observed among HTTP-checked targets.'
                             + (' Malformed hrefs were omitted, not verified.' if omission else ''))
            lines.append("")
        else:
            lines += [TABLE_TEXT_MARKER, "| Status / request error | Type | Target URL | Linked from |",
                      "|:--:|:--|:--|:--|"]
            for b in broken:
                status = b["status"] or (b["error"] or "unreachable")
                if b["status"] and links.http_check_state(b["status"], b.get("error")) == 'unverified':
                    status = f"{status} (unverified)"
                kind = "internal" if b["internal"] else "external"
                src = b["sources"][0]
                more = f" (+{len(b['sources']) - 1})" if len(b["sources"]) > 1 else ""
                lines.append(f"| {table_text(status)} | {kind} | {table_text(b['url'])} | {table_text(src)}{more} |")
            lines.append("")

    if link_info is not None and receipt is not None and link_info.get('unverified'):
        rows = link_info['unverified']
        lines += [f"### Unverified checked targets (first {min(20, len(rows))} of {len(rows)})", '',
                  'These responses do not establish dead destinations. Rows may overlap the problem table above; '
                  'they are the same checks. URL previews are bounded; full records remain in JSON.', '',
                  TABLE_TEXT_MARKER, '| Reported status | Target URL | Linked from |', '|:--|:--|:--|']
        for row in rows[:20]:
            status = row.get('status')
            label = f'{status} (unverified)' if type(status) is int and status else 'no HTTP response / unrecorded'
            target = row.get('url') if isinstance(row.get('url'), str) else '(unrecorded)'
            sources = row.get('sources')
            sources = [value for value in sources if isinstance(value, str)] if isinstance(sources, list) else []
            source = sources[0] if sources else '(unrecorded)'
            more = f' (+{len(sources) - 1})' if len(sources) > 1 else ''
            target = target[:240] + ('…' if len(target) > 240 else '')
            source = source[:240] + ('…' if len(source) > 240 else '')
            lines.append(f'| {table_text(label)} | {table_text(target)} | {table_text(source)}{more} |')
        lines.append('')

    dupes = result.get("duplicates")
    if dupes is not None:
        problem = [c for c in dupes if not c["canonical_ok"]]
        lines.append(f"## Duplicate content ({len(dupes)} near-duplicate cluster(s))")
        lines.append("")
        coverage = _duplicate_coverage(result)
        if coverage is None:
            lines += ['> Duplicate-comparison coverage was not recorded; absence of clusters is not a health verdict.', '']
        else:
            lines += [f"Comparison scope: {coverage['eligible_pages']} eligible page fingerprints "
                      f"from {coverage['scanned_pages']} scanned pages; sampled pages only.", '']
        if not dupes:
            if coverage is None:
                lines.append('No near-duplicate clusters reported; comparison coverage unverified.')
            elif coverage['eligible_pages'] < 2:
                lines.append('Duplicate comparison has insufficient data: fewer than two eligible fingerprints.')
            else:
                lines.append(f"No near-duplicate clusters detected among {coverage['eligible_pages']} eligible page fingerprints.")
            lines.append("")
        else:
            for i, c in enumerate(dupes, 1):
                flag = 'matching canonical target observations' if c['canonical_ok'] \
                    else 'review canonical targets (missing, different or unassessed)'
                lines.append(f"**Cluster {i}** — ~{c['min_similarity']}% similar · {flag}")
                for url, can in zip(c["urls"], c["canonicals"]):
                    canon = f" → canonical: {can}" if can else " → no canonical"
                    lines.append(f"- {url}{canon}")
                lines.append("")
            if problem:
                lines.append(f"> {len(problem)} cluster(s) of near-duplicate pages "
                             'need canonical-target review. Inspect actual duplication, variants and intended '
                             'consolidation before editing; preserve intentional distinct pages. Matching '
                             'component keys do not verify target access, equivalent content or search-engine selection.')
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_json(result: dict) -> str:
    import json
    payload = dict(result)
    rule_counts = payload.pop('recurring_rule_counts', None)
    if rule_counts is not None:
        totals = Counter()
        for (category, severity, title, rule_id), count in rule_counts.items():
            if type(count) is not int or count < 1:
                raise ValueError('Recurring rule counts must be positive integers.')
            totals[(category, severity, title)] += count
        if totals != result['recurring']:
            raise ValueError('Recurring rule counts disagree with the title rollup; regenerate the crawl before rendering.')
        payload['recurring'] = [
            {'category': c, 'severity': s, 'title': t, 'count': n, **({'rule_id': rid} if rid else {})}
            for (c, s, t, rid), n in rule_counts.most_common()]
    else:
        payload["recurring"] = [
            {"category": c, "severity": s, "title": t, "count": n}
            for (c, s, t), n in result["recurring"].most_common()
        ]
    return json.dumps(payload, indent=2, ensure_ascii=False)


@url_errors
def main(argv=None) -> int:
    cfg = configlib.load_from_args(argv)
    d = cfg.defaults
    ap = argparse.ArgumentParser(description="Site-level SEO + GEO/LLMO scan",
                                 parents=[configlib.config_arg_parser()])
    ap.add_argument("url", help="base URL of the site")
    ap.add_argument("--max-pages", type=int, default=d["max_pages"],
                    help="positive maximum pages to scan")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--format", choices=("markdown", "json"), default="markdown")
    ap.add_argument("-o", "--output")
    ap.add_argument("--timeout", type=int, default=d["timeout"])
    ap.add_argument("--allow-private", action="store_true")
    ap.add_argument("--delay", type=float, default=d["delay"], metavar="SECONDS",
                    help="seconds between parallel page-scan starts (post-scan pause in sequential mode); "
                         "does not pace discovery, site resources or optional probes")
    ap.add_argument("--concurrency", type=int, default=d["concurrency"], metavar="N",
                    help="positive number of pages to scan in parallel")
    ap.add_argument("--ignore-robots", action="store_true",
                    help="do NOT skip URLs disallowed by robots.txt (off by default)")
    ap.add_argument("--check-links", action="store_true",
                    help="check outbound links (internal + external) for 4xx/5xx/dead")
    ap.add_argument("--max-links", type=int, default=d["max_links"], metavar="N",
                    help="nonnegative cap on unique links checked (0 skips link requests)")
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

    try:
        validate_budgets(max_pages=args.max_pages, concurrency=args.concurrency)
        nonnegative_integer(args.max_links, 'max_links')
        delay = _delay_seconds(args.delay)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    result = crawl(args.url, max_pages=args.max_pages, render=args.render,
                   allow_private=args.allow_private, timeout=args.timeout,
                   delay=delay, concurrency=args.concurrency,
                   obey_robots=not args.ignore_robots,
                   check_links=args.check_links, max_links=args.max_links,
                   detect_dupes=not args.no_dupes, dup_threshold=args.dup_threshold,
                   config=cfg)
    out = render_json(result) if args.format == "json" else render_markdown(result)
    if args.output:
        if not save_output(args.output, out, label='crawl report'):
            return 2
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
