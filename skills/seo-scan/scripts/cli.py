"""Unified ``narwhal`` command — dispatches to the scan/crawl/schema tools.

This is a thin router so the same code works three ways with no duplication:
  - ``narwhal scan|crawl|schema …``            (installed via uvx/pip)
  - ``python -m narwhal scan …``               (installed package)
  - ``python scan.py …`` / ``crawl_site.py``   (cloned repo / Claude Code plugin)

Each subcommand forwards the remaining args to that tool's own ``main()``.
"""

from __future__ import annotations

import sys

try:
    from . import __version__
except ImportError:  # running as loose scripts
    __version__ = "1.5.0"

USAGE = """narwhal — SEO & GEO/LLMO scanner

Usage:
  narwhal audit <url> [options]     Comprehensive site audit (page + crawl + sitemap)
  narwhal scan <url> [options]      Audit a single page
  narwhal crawl <url> [options]     Audit a whole site (sitemap/link discovery)
  narwhal schema <Type> [options]   Generate schema.org JSON-LD
  narwhal sitemap <url> [options]   Validate a site's XML sitemap(s)
  narwhal llms <url> [options]      Generate a starter llms.txt
  narwhal diff <old.json> <new.json>  Compare two JSON reports (regression tracking)
  narwhal --version

Run any subcommand with -h for its options, e.g. `narwhal scan -h`.
"""


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    if argv[0] in ("-V", "--version", "version"):
        print(f"narwhal {__version__}")
        return 0

    cmd, rest = argv[0], argv[1:]
    module = {
        "scan": "scan",
        "audit": "audit",
        "crawl": "crawl_site",
        "crawl_site": "crawl_site",
        "schema": "generate_schema",
        "sitemap": "validate_sitemap",
        "llms": "generate_llms",
        "diff": "diff_scan",
    }.get(cmd)
    if module is None:
        print(f"Unknown command: {cmd!r}\n", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2

    mod = _load(module)
    return mod.main(rest)


def _load(name):
    """Import a sibling tool module whether we're a package or loose scripts."""
    try:
        import importlib
        return importlib.import_module(f".{name}", __package__ or "")
    except (ImportError, TypeError):
        import importlib
        return importlib.import_module(name)


if __name__ == "__main__":
    raise SystemExit(main())
