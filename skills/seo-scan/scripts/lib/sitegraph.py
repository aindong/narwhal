"""Site-structure analysis over a crawl: click depth, orphans, link equity.

Pure computation (no network) on data the crawler already collects — each
crawled page's internal links plus the sitemap URL set. Three questions:

- **Click depth** — how many clicks from the start URL is each page? Pages
  buried deeper than ~3 clicks get crawled less and rank worse.
- **Internal-link distribution** — which crawled pages receive no internal
  links from the other crawled pages (weak link equity)?
- **Orphan candidates** — sitemap URLs that no crawled page links to. With a
  capped crawl this is a *candidate* list, not proof; the report says so.

Honesty rule: every result is scoped to the crawled sample. The renderer must
state the sample size next to any claim.
"""

from __future__ import annotations

from collections import deque
from urllib.parse import urlparse, urlunparse

DEPTH_WARN = 3          # clicks from the start URL beyond which we flag
ORPHAN_SAMPLE = 8       # candidates listed in the report (full count still given)


def norm(url: str) -> str:
    """Normalize for graph identity: lowercase scheme/host, drop fragments and
    trailing slashes (``…/page`` and ``…/page/`` are one node)."""
    p = urlparse((url or "").split("#")[0])
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", p.query, ""))


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
                   if d > DEPTH_WARN), key=lambda x: -x["depth"])
    unreachable = sorted(display[n] for n in nodes - set(depths))

    # --- inbound internal links per crawled page ----------------------------
    inbound = {n: 0 for n in nodes}
    for src in nodes:
        for dst in edges[src]:
            inbound[dst] += 1
    zero_inbound = sorted(display[n] for n, c in inbound.items()
                          if c == 0 and n != base_n)
    top = sorted(((display[n], c) for n, c in inbound.items() if c),
                 key=lambda x: -x[1])[:5]

    # --- orphan candidates: in the sitemap, linked from no crawled page -----
    # Crawled pages are excluded — a crawled page with no inbound links is
    # already reported (with more certainty) in zero_inbound above.
    orphans = {"checked": bool(sitemap_found), "candidates": [], "total": 0}
    if sitemap_found:
        seen_linked = linked_anywhere | {base_n} | nodes
        cands = []
        for u in sitemap_urls or []:
            un = norm(u)
            if un != base_n and urlparse(un).netloc == urlparse(base_n).netloc \
                    and un not in seen_linked:
                cands.append(u)
        orphans["candidates"] = cands
        orphans["total"] = len(cands)

    max_depth = max(depths.values()) if depths else 0
    return {
        "pages_in_graph": len(nodes),
        "internal_edges": sum(len(v) for v in edges.values()),
        "max_depth": max_depth,
        "deep_pages": deep,
        "unreachable_from_start": unreachable,
        "zero_inbound": zero_inbound,
        "top_linked": [{"url": u, "inbound": c} for u, c in top],
        "orphans": orphans,
    }


def render_markdown(g: dict, *, sitemap_total: int = 0) -> list:
    """The 'Site structure' report section as Markdown lines (composed into the
    crawler's report). Sample-size honesty is part of the contract."""
    n = g["pages_in_graph"]
    lines = [f"## Site structure ({n} crawled pages, "
             f"{g['internal_edges']} internal links)", ""]
    if g["internal_edges"] == 0:
        lines += ["No internal links were observed between the crawled pages — "
                  "depth/link-equity analysis needs a larger crawl "
                  "(`--max-pages`).", ""]
        return lines

    lines.append(f"- **Max click depth from the start URL:** {g['max_depth']}"
                 + (" 🟢" if g["max_depth"] <= DEPTH_WARN else ""))
    if g["deep_pages"]:
        lines.append(f"- **Buried pages (deeper than {DEPTH_WARN} clicks):**")
        for p in g["deep_pages"][:5]:
            lines.append(f"  - depth {p['depth']}: {p['url']}")
    if g["unreachable_from_start"]:
        lines.append("- **Crawled but not reachable from the start URL** "
                     "(no internal path within the sample):")
        for u in g["unreachable_from_start"][:5]:
            lines.append(f"  - {u}")
    if g["zero_inbound"]:
        lines.append("- **No inbound internal links** (weak link equity within "
                     "the sample):")
        for u in g["zero_inbound"][:5]:
            lines.append(f"  - {u}")
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
            lines.append("- **Orphan candidates:** none — every checked sitemap "
                         "URL is linked from the crawled sample. 🟢")
    else:
        lines.append("- **Orphan check skipped** — no sitemap was found.")

    lines += ["", f"_Structure is computed from the {n}-page crawl sample"
              + (f" against {sitemap_total} discovered sitemap URLs"
                 if o["checked"] and sitemap_total else "")
              + "; a page 'unlinked' here may be linked from pages outside the "
                "sample. Raise `--max-pages` for a fuller graph._", ""]
    return lines
