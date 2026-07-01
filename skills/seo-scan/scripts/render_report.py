#!/usr/bin/env python3
"""narwhal render — wrap a Markdown report in Narwhal's branded HTML/PDF shell.

Turns any Markdown into a self-contained, **branded** HTML or PDF report — the
same styling, logo, and layout as the scan/audit reports. This is how the
multi-agent `/narwhal audit` turns its *synthesized* report into a shareable PDF:
the synthesis lives in Markdown, and this renders it. Reuses the report renderer,
so there's no new presentation logic.

Usage:
    narwhal render audit.md -o audit.html
    narwhal render audit.md --format pdf -o audit.pdf --title "Site Audit"
    narwhal audit example.com | narwhal render - -o report.html        # from stdin

PDF needs WeasyPrint (falls back to writing HTML if it isn't installed).
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import report as report_lib  # noqa: E402
from lib.report import deliver  # noqa: E402


def _split_title(md: str):
    """Return (first-H1-text-or-None, body-without-that-H1). Prevents the report
    from showing the title twice — once in the branded header, once in the body."""
    lines = md.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# "):
            return line[2:].strip(), "\n".join(lines[:i] + lines[i + 1:])
    return None, md


def render(md_text: str, *, title=None, subtitle: str = "") -> str:
    """Markdown -> a self-contained, branded HTML document."""
    extracted, body = _split_title(md_text)
    doc_title = title or extracted or "Narwhal Report"
    return report_lib.html_document(doc_title, subtitle,
                                    report_lib.md_to_html(body))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Render a Markdown report as branded HTML/PDF")
    ap.add_argument("input", help="Markdown file to render, or - for stdin")
    ap.add_argument("--title", default=None,
                    help="report title (default: the first # heading)")
    ap.add_argument("--subtitle", default="",
                    help="subtitle under the title (e.g. the site URL)")
    ap.add_argument("--format", choices=("html", "pdf"), default="html")
    ap.add_argument("-o", "--output")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    try:
        if args.input == "-":
            md = sys.stdin.read()
        else:
            with open(args.input, "r", encoding="utf-8") as fh:
                md = fh.read()
    except OSError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    html = render(md, title=args.title, subtitle=args.subtitle)
    return deliver(args.format, args.output, html, label="report")


if __name__ == "__main__":
    raise SystemExit(main())
