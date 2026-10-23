"""Site-structure analysis over a crawl: depth, inbound counts, orphan candidates.

Pure computation (no network) on data the crawler already collects — each
crawled page's internal links plus the sitemap URL set. Three questions:

- **Click depth** — shortest paths from the supplied start node over input edges.
  Depth is not a measurement of crawler access or ranking.
- **Internal-link distribution** — which crawled pages receive no internal
  links from the other crawled pages? Counts do not measure link equity.
- **Orphan candidates** — sitemap URLs that no crawled page links to. With a
  capped crawl this is a *candidate* list, not proof; the report says so.

Honesty rule: every result is scoped to the crawled sample. The renderer must
state the sample size next to any claim.
"""

from __future__ import annotations

from collections import deque
from urllib.parse import urlparse, urlsplit, urlunsplit

DEPTH_WARN = 3          # clicks from the start URL beyond which we flag
ORPHAN_SAMPLE = 8       # candidates listed in the report (full count still given)
URL_IDENTITY_BASIS = 'fragment_free_scheme_host_case_preserve_path_query_v1'
DEPTH_BASIS = 'breadth_first_over_supplied_graph_edges_v1'


def norm(url: str) -> str:
    """Observed-address key, not canonical/redirect or server equivalence.

    Ignore fragments and scheme/host case; preserve non-root separators,
    semicolon path data, query case/order/empty delimiter and userinfo case.
    This pure grouping helper never grants permission to fetch a URL.
    """
    address = (url or '').split('#', 1)[0]
    p = urlsplit(address)
    userinfo, separator, authority = p.netloc.rpartition('@')
    netloc = (userinfo + separator if separator else '') + authority.lower()
    output = urlunsplit((p.scheme.lower(), netloc, p.path or '/', p.query, ''))
    return output + ('?' if '?' in address and not p.query else '')


def analyze(base: str, crawled: list, pages_links: dict,
            sitemap_urls: list, sitemap_found: bool) -> dict:
    """Build the internal-link graph from crawled pages and analyze it.

    ``crawled`` — URLs actually scanned; ``pages_links`` — per-page
    ``[{url, internal}]`` from the scans; ``sitemap_urls`` — discovered sitemap
    candidates (used for orphan detection only when ``sitemap_found``).
    """
    base_n = norm(base)
    nodes = {norm(u) for u in crawled}
    display = {norm(u): u for u in crawled}   # keep the original spelling

    # Adjacency over crawled pages; also remember EVERY internal target seen
    # (crawled or not) — that's the "linked from somewhere" set orphans need.
    edges: dict = {n: set() for n in nodes}
    linked_anywhere: set = set()
    for page, page_links in (pages_links or {}).items():
        src = norm(page)
        for l in page_links or []:
            if not l.get("internal"):
                continue
            dst = norm(l["url"])
            if dst == src:
                continue
            linked_anywhere.add(dst)
            if src in edges and dst in nodes:
                edges[src].add(dst)

    # --- click depth: BFS from the start URL over crawled-page edges --------
    depths: dict = {}
    if base_n in nodes:
        depths[base_n] = 0
        q = deque([base_n])
        while q:
            cur = q.popleft()
            for nxt in sorted(edges.get(cur, ())):
                if nxt not in depths:
                    depths[nxt] = depths[cur] + 1
                    q.append(nxt)
    deep = sorted(({"url": display[n], "depth": d} for n, d in depths.items()
                   if d > DEPTH_WARN), key=lambda x: (-x["depth"], x["url"]))
    unreachable = sorted(display[n] for n in nodes - set(depths))

    # --- inbound internal links per crawled page ----------------------------
    inbound = {n: 0 for n in nodes}
    for src in nodes:
        for dst in edges[src]:
            inbound[dst] += 1
    zero_inbound = sorted(display[n] for n, c in inbound.items()
                          if c == 0 and n != base_n)
    # Break equal ranks before capping, so process/set order cannot change
    # which tied pages enter the JSON top five or Markdown top three.
    top = sorted(((display[n], c) for n, c in inbound.items() if c),
                 key=lambda x: (-x[1], x[0]))[:5]

    # --- orphan candidates: in the sitemap, linked from no crawled page -----
    # Crawled pages are excluded — a crawled page with no inbound links is
    # already reported (with more certainty) in zero_inbound above.
    orphans = {"checked": bool(sitemap_found), "candidates": [], "total": 0}
    if sitemap_found:
        seen_linked = linked_anywhere | {base_n} | nodes
        cands, seen_candidates = [], set()
        for u in sitemap_urls or []:
            un = norm(u)
            if un != base_n and urlparse(un).netloc == urlparse(base_n).netloc \
                    and un not in seen_linked and un not in seen_candidates:
                cands.append(u)
                seen_candidates.add(un)
        orphans["candidates"] = cands
        orphans["total"] = len(cands)

    max_depth = max(depths.values()) if depths else 0
    return {
        'url_identity_basis': URL_IDENTITY_BASIS,
        'depth_coverage': {'basis': DEPTH_BASIS, 'start_present': base_n in nodes,
                           'reachable_nodes': len(depths), 'unreachable_nodes': len(unreachable)},
        "pages_in_graph": len(nodes),
        "internal_edges": sum(len(v) for v in edges.values()),
        "max_depth": max_depth,
        "deep_pages": deep,
        "unreachable_from_start": unreachable,
        "zero_inbound": zero_inbound,
        "top_linked": [{"url": u, "inbound": c} for u, c in top],
        "orphans": orphans,
    }


def recorded_depth(g):
    """Accept a self-consistent recorded BFS scope, not fetch or site coverage."""
    value = g.get('depth_coverage')
    if not isinstance(value, dict) or value.get('basis') != DEPTH_BASIS:
        return None
    start = value.get('start_present')
    reached, other = value.get('reachable_nodes'), value.get('unreachable_nodes')
    count, depth, edges = g.get('pages_in_graph'), g.get('max_depth'), g.get('internal_edges')
    if type(start) is not bool or any(type(item) is not int or item < 0 for item in (reached, other, count, depth, edges)):
        return None
    if reached + other != count or (not start and reached != 0) or (start and reached < 1):
        return None
    if (reached == 0 and depth != 0) or (reached and depth >= reached):
        return None
    if (reached > 1 and depth == 0) or edges < max(0, reached - 1):
        return None
    if edges > count * max(0, count - 1):
        return None
    if not isinstance(g.get('unreachable_from_start'), list) or len(g['unreachable_from_start']) != other:
        return None
    return value


def _url_sample(lines, urls, cap=5):
    """Keep the existing URL display budget while making omissions explicit."""
    for url in urls[:cap]:
        lines.append(f'  - {url}')
    if len(urls) > cap:
        lines.append(f'  - … +{len(urls) - cap} more (see JSON)')


def render_markdown(g: dict, *, sitemap_total: int = 0) -> list:
    """The 'Site structure' report section as Markdown lines (composed into the
    crawler's report). Sample-size honesty is part of the contract."""
    n = g["pages_in_graph"]
    lines = [f"## Site structure ({n} crawled pages, "
             f"{g['internal_edges']} internal links)", ""]
    if g.get('url_identity_basis') == URL_IDENTITY_BASIS:
        lines += ['URL identity groups fragments and scheme/host case only (empty roots use `/`). '
                  'Other path/query literals remain distinct; canonical tags, redirects and '
                  'server equivalence are not inferred.', '']
    else:
        lines += ['URL identity policy was not recorded; historical alias handling is unverified.', '']
    if g["internal_edges"] == 0:
        lines += ['No inter-page edges were recorded in this sample. Inspect captured links, '
                  'extraction and sampling limits before editing the site or increasing the crawl; '
                  'zero recorded edges does not prove the site has no links.', '']

    coverage = recorded_depth(g)
    if coverage is None:
        lines += [f"- **Reported max depth:** {g['max_depth']} — start/BFS coverage is unrecorded or unsupported; "
                  'this is not a verified reachability or health verdict.']
    elif coverage['start_present']:
        lines += [f"- **Max measured click depth from the start URL:** {g['max_depth']} "
                  f"among {coverage['reachable_nodes']} reachable of {n} supplied graph nodes. "
                  'Reachability is computed from input edges only, not verified crawler access or ranking.']
    else:
        lines += ['- **Depth from the start URL is unassessed:** the start address is absent from the supplied '
                  'graph. Raw `max_depth=0` is a placeholder, not a measured zero-hop site.']
    if g["deep_pages"]:
        lines.append(f"- **Recorded pages deeper than {DEPTH_WARN} clicks ({len(g['deep_pages'])}):**")
        for p in g["deep_pages"][:5]:
            lines.append(f"  - depth {p['depth']}: {p['url']}")
        if len(g['deep_pages']) > 5:
            lines.append(f"  - … +{len(g['deep_pages']) - 5} more (see JSON)")
    if g["unreachable_from_start"]:
        if coverage is None:
            label = 'Recorded URLs listed as unreachable (start/BFS scope unverified)'
        elif not coverage['start_present']:
            label = 'Recorded URLs with unassessed start reachability'
        else:
            label = 'Crawled but not reachable from the start URL within the supplied graph'
        lines.append(f"- **{label} ({len(g['unreachable_from_start'])}):**")
        _url_sample(lines, g['unreachable_from_start'])
    if g["zero_inbound"]:
        lines.append(f"- **No inbound internal links observed in the sample ({len(g['zero_inbound'])}):** "
                     'A count, not measured link equity or ranking impact.')
        _url_sample(lines, g['zero_inbound'])
    if g["top_linked"]:
        best = ", ".join(f"{t['url']} ({t['inbound']})" for t in g["top_linked"][:3])
        lines.append(f"- **Most-linked pages:** {best}")

    o = g["orphans"]
    if o["checked"]:
        if o["total"]:
            lines.append(f"- **Orphan candidates** ({o['total']} sitemap URLs "
                         "linked from none of the crawled pages):")
            for u in o["candidates"][:ORPHAN_SAMPLE]:
                lines.append(f"  - {u}")
            if o["total"] > ORPHAN_SAMPLE:
                lines.append(f"  - … +{o['total'] - ORPHAN_SAMPLE} more (see JSON)")
        else:
            lines.append('- **Orphan candidates:** no additional candidates in this sample. '
                         'Crawled/start URL identities and observed link targets are excluded; '
                         'this does not prove every sitemap URL is linked.')
    else:
        lines.append("- **Orphan check skipped** — no verified sitemap URL sample was available.")

    lines += ["", f"_Structure is computed from the {n}-page crawl sample"
              + (f" against {sitemap_total} discovered sitemap URLs"
                 if o["checked"] and sitemap_total else "")
              + "; a page 'unlinked' here may be linked from pages outside the "
                "sample. Raise `--max-pages` only when broader authorized sampling is useful; "
                "a larger cap does not itself repair missing edges._", ""]
    return lines
