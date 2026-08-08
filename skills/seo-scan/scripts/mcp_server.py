#!/usr/bin/env python3
"""narwhal MCP server — expose the auditors as Model Context Protocol tools.

This wraps the same deterministic scripts (scan / crawl / audit / sitemap / llms /
schema / diff) as MCP tools so any MCP client (Claude Desktop, IDEs, other agents)
can call them natively over stdio. It adds no new analysis — it's a thin, typed
adapter over the existing functions, so results match the CLI exactly.

MCP is an **optional** dependency (the core toolkit stays zero-dependency). Both
the MCP Python SDK 1.x and 2.x high-level server APIs are supported. Install it
with the `mcp` extra:

    pip install "narwhal-seo[mcp]"     # or: pip install "mcp>=1.12"

Run the server (stdio transport):

    narwhal mcp
    python mcp_server.py

Register it with a client, e.g. Claude Desktop's config:

    {
      "mcpServers": {
        "narwhal": { "command": "narwhal", "args": ["mcp"] }
      }
    }
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# The sibling tools are imported lazily inside each tool so this module loads
# (e.g. for a friendly "mcp not installed" message) even in odd environments.


def _scan(url: str, render: bool = False, only: str = "", timeout: int = 20,
          max_bytes: int = 5_000_000) -> dict:
    """Audit a single page for SEO + GEO/LLMO and return the full report as JSON.

    Args:
        url: The page URL to audit (must be public; private/loopback hosts are blocked).
        render: Render JavaScript with Playwright first (for SPAs). Requires the
            optional playwright extra.
        only: Comma-separated subset of auditors to run: technical,content,schema,geo.
            Empty runs all four.
        timeout: Per-request timeout in seconds (1–120).
        max_bytes: Maximum HTML bytes retained (64KB–20MB).

    Returns a dict with score, per-severity counts, and every finding
    (category, severity, title, detail, recommendation, evidence).
    """
    import scan as scan_mod
    subset = [s.strip() for s in only.split(",") if s.strip()] or None
    timeout = max(1, min(int(timeout), 120))
    max_bytes = max(64_000, min(int(max_bytes), 20_000_000))
    report = scan_mod.scan(url, render=render, only=subset, timeout=timeout,
                           max_bytes=max_bytes)
    return json.loads(report.to_json())


def _crawl(url: str, max_pages: int = 15, check_links: bool = False,
           timeout: int = 20, concurrency: int = 4) -> dict:
    """Crawl a whole site and roll up the recurring, highest-leverage issues.

    Args:
        url: The site URL to start from.
        max_pages: Maximum pages to scan (polite crawler; honors robots.txt).
        check_links: Also HEAD-check outbound links for 4xx/5xx/dead.
        timeout: Per-request timeout in seconds (1–120).
        concurrency: Concurrent page requests (1–8).

    Returns weakest pages, most-common issues, broken links, and near-duplicate
    clusters, plus the average score.
    """
    import crawl_site as crawl_mod
    max_pages = max(1, min(int(max_pages), 100))
    timeout = max(1, min(int(timeout), 120))
    concurrency = max(1, min(int(concurrency), 8))
    result = crawl_mod.crawl(url, max_pages=max_pages, check_links=check_links,
                             timeout=timeout, concurrency=concurrency)
    return json.loads(crawl_mod.render_json(result))


def _audit(url: str, max_pages: int = 15, render: bool = False,
           timeout: int = 20, concurrency: int = 4) -> dict:
    """Run the comprehensive audit: homepage + site crawl + sitemap in one report.

    Args:
        url: The site URL to audit.
        max_pages: Maximum pages for the crawl portion.
        render: Render JavaScript with Playwright (expensive; use for SPAs).
        timeout: Per-request timeout in seconds (1–120).
        concurrency: Concurrent crawl requests (1–8).

    Returns the overall score plus the homepage, crawl, and sitemap sub-reports.
    """
    import audit as audit_mod
    max_pages = max(1, min(int(max_pages), 100))
    timeout = max(1, min(int(timeout), 120))
    concurrency = max(1, min(int(concurrency), 8))
    data = audit_mod.run(url, max_pages=max_pages, render=render,
                         timeout=timeout, concurrency=concurrency)
    return json.loads(audit_mod.render_json(data))


def _sitemap(url: str) -> dict:
    """Validate a site's XML sitemap(s): loc/lastmod checks, index recursion, 404 sampling.

    Args:
        url: The site URL (or a direct sitemap URL).
    """
    import validate_sitemap as sm_mod
    return json.loads(sm_mod.render_json(sm_mod.analyze(url)))


def _llms(url: str, max_pages: int = 40) -> str:
    """Generate a starter ``llms.txt`` for a site (a curation starting point).

    Args:
        url: The site URL to seed from.
        max_pages: Maximum pages to include as candidate links.

    Returns the llms.txt content as text.
    """
    import generate_llms as llms_mod
    d = llms_mod.build(url, max_pages=max_pages)
    return llms_mod.render_llms_txt(d["site_name"], d["description"], d["sections"])


def _schema(type: str, fields: dict) -> dict:
    """Generate valid schema.org JSON-LD for a type, filling gaps with TODO placeholders.

    Args:
        type: A schema.org type — e.g. Article, Product, Organization, FAQPage,
            LocalBusiness, Event, Recipe, BreadcrumbList (see the supported list).
        fields: Key/value pairs to populate (e.g. {"headline": "…", "author": "…"}).

    Returns the JSON-LD object.
    """
    import generate_schema as schema_mod
    return schema_mod.build(type, {k: str(v) for k, v in (fields or {}).items()})


def _compare(your_url: str, competitor_urls: list, render: bool = False) -> dict:
    """Compare YOUR page against 1–3 competitor pages (local-first gap analysis).

    Args:
        your_url: The page you own/optimize.
        competitor_urls: 1–3 competitor page URLs to compare against.
        render: Render JavaScript with Playwright first (for SPAs).

    Returns per-page facts (scores, schema types, meta strategy, depth,
    structure, evidence, social packaging), the gaps competitors have that you
    don't, and where you lead. On-page differences only — no rank/keyword data.
    """
    import compare as compare_mod
    urls = [your_url] + list(competitor_urls)[: compare_mod.MAX_COMPETITORS]
    return compare_mod.run(urls, render=render)


def _brief(your_url: str = "", competitor_urls: list = None, topic: str = "",
           use_gsc: bool = True) -> dict:
    """Build a data-driven content brief: your real GSC queries (if credentials
    are set) + gaps vs the competitor pages that currently win.

    Args:
        your_url: The page you're rewriting (omit when planning a new page).
        competitor_urls: 1–3 competitor page URLs to learn structure/gaps from.
        topic: When ``your_url`` is empty — the topic of the page to plan.
        use_gsc: Pull striking-distance queries from Search Console (needs GSC
            credentials in the environment; degrades to a labeled
            structure-only brief without them).

    Returns target queries (real GSC data only — never invented), competitor
    gaps, missing subtopics, questions to answer, schema and structure targets.
    """
    import brief as brief_mod
    return brief_mod.run(your_url or None, list(competitor_urls or []),
                         topic=topic or None, use_gsc=use_gsc)


def _diff(old_json: str, new_json: str) -> dict:
    """Diff two JSON reports (from scan or audit) to track regressions over time.

    Args:
        old_json: The earlier report as a JSON string.
        new_json: The later report as a JSON string.

    Returns the score delta and new / resolved / worsened / improved findings,
    plus a ``regression`` flag (score dropped or a new critical/high finding).
    """
    import diff_scan as diff_mod
    return diff_mod.diff_reports(json.loads(old_json), json.loads(new_json))


def _plan(report: dict, repo: str = ".", max_files: int = 5000) -> dict:
    """Build a read-only remediation plan for a report and repository.

    Args:
        report: A parsed Narwhal scan/audit JSON object (not a filesystem path).
        repo: Repository directory relative to the MCP server's working directory.
            Absolute paths and parent traversal are rejected.
        max_files: Repository inventory cap (1–5000).

    Returns stable rule-linked actions, likely owning files, framework evidence,
    safety classifications, grouped fixes, conflicts, coverage, and verification
    commands. This tool never edits repository files.
    """
    from pathlib import Path
    import plan as plan_mod

    workspace = Path.cwd().resolve()
    requested = Path(repo)
    if requested.is_absolute():
        raise ValueError("MCP repo must be relative to the server working directory")
    candidate = (workspace / requested).resolve()
    try:
        candidate.relative_to(workspace)
    except ValueError as exc:
        raise ValueError("MCP repo cannot escape the server working directory") from exc
    max_files = max(1, min(int(max_files), plan_mod.MAX_REPO_FILES))
    return plan_mod.build_plan(report, str(candidate), report_source="<mcp-object>",
                               max_files=max_files)


# (function, public tool name) — names are what MCP clients see.
_TOOLS = [
    (_scan, "scan_page"),
    (_compare, "compare_pages"),
    (_brief, "content_brief"),
    (_crawl, "crawl_site"),
    (_audit, "audit_site"),
    (_sitemap, "validate_sitemap"),
    (_llms, "generate_llms"),
    (_schema, "generate_schema"),
    (_diff, "diff_reports"),
    (_plan, "plan_remediation"),
]


def build_server():
    """Construct the FastMCP server with all tools registered.

    Imported here (not at module top) so the module still loads without the
    optional ``mcp`` package — ``main`` turns the ImportError into guidance.
    """
    try:
        # MCP Python SDK 1.x
        from mcp.server.fastmcp import FastMCP as ServerClass  # noqa: PLC0415
    except ImportError:
        # MCP Python SDK 2.x renamed the high-level server while retaining the
        # add_tool/list_tools/run surface used by this adapter.
        from mcp.server.mcpserver import MCPServer as ServerClass  # noqa: PLC0415

    mcp = ServerClass("narwhal")
    for fn, name in _TOOLS:
        mcp.add_tool(fn, name=name)
    return mcp


def main(argv=None) -> int:
    try:
        server = build_server()
    except ImportError:
        print(
            "The MCP server needs the optional `mcp` package.\n"
            "Install it:  pip install \"narwhal-seo[mcp]\"   (or: pip install \"mcp>=1.12\")",
            file=sys.stderr,
        )
        return 1
    server.run()  # stdio transport; blocks for the server's lifetime
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
