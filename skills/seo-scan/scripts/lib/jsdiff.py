"""Raw-vs-rendered content diff: how much of the page needs JavaScript?

Content that only exists after JS execution is invisible to crawlers that don't
render (most AI answer-engine fetchers, many search crawlers on their first
pass). When a scan runs with ``--render``, we have both documents anyway — the
served HTML and the rendered DOM — so we can measure the dependence instead of
guessing: word-count delta, headings that only exist post-JS, and head metadata
(title/description/canonical/JSON-LD) injected client-side.

Pure computation on two parsed documents; no network, fully offline-testable.
"""

from __future__ import annotations

from . import htmlx

# Share of the rendered text that is JS-only before each severity fires.
PCT_HIGH = 30
PCT_MEDIUM = 10


def analyze(raw_html: str, rendered_html: str, base_url: str = "") -> dict:
    """Compare served HTML against the rendered DOM. Returns the delta facts."""
    raw = htmlx.parse(raw_html or "", base_url=base_url)
    ren = htmlx.parse(rendered_html or "", base_url=base_url)

    raw_words = len((raw.body_text or "").split())
    ren_words = len((ren.body_text or "").split())
    js_pct = 0
    if ren_words > raw_words and ren_words > 0:
        js_pct = round(100 * (ren_words - raw_words) / ren_words)

    raw_heads = {(lvl, t) for lvl, t in raw.headings if t}
    js_headings = [t for lvl, t in ren.headings if t and (lvl, t) not in raw_heads]

    meta_js_only = {
        "title": bool(ren.title) and not raw.title,
        "description": bool(ren.meta_by_name("description"))
                       and not raw.meta_by_name("description"),
        "canonical": bool(ren.canonical()) and not raw.canonical(),
        "jsonld": len(ren.scripts_ld) > len(raw.scripts_ld),
    }
    return {
        "words_raw": raw_words,
        "words_rendered": ren_words,
        "js_only_pct": js_pct,
        "js_only_headings": js_headings[:10],
        "js_only_heading_count": len(js_headings),
        "meta_js_only": meta_js_only,
    }


def technical_findings(dep: dict, report) -> None:
    """Emit technical findings from a jsdiff result (tiered by JS-only share)."""
    cat = "technical"
    pct = dep["js_only_pct"]
    detail = (f"{dep['words_raw']} words served vs {dep['words_rendered']} after "
              f"JavaScript — {pct}% of the content is JS-only.")
    evidence = "; ".join(dep["js_only_headings"][:4]) or None
    if pct >= PCT_HIGH:
        report.add(cat, "high", "Most content requires JavaScript",
                   detail,
                   "Server-render or pre-render the main content (SSR/SSG). "
                   "Crawlers that don't execute JS — including most AI answer-"
                   "engine fetchers — see the served HTML only.",
                   evidence=evidence)
    elif pct >= PCT_MEDIUM:
        report.add(cat, "medium", "Significant content requires JavaScript",
                   detail,
                   "Consider server-rendering the affected sections; verify what "
                   "non-JS crawlers see.", evidence=evidence)
    else:
        report.ok(cat, "Content is server-rendered",
                  f"only {pct}% of text is JS-only")

    m = dep["meta_js_only"]
    js_meta = [name for name, only in
               (("title", m["title"]), ("meta description", m["description"]),
                ("canonical", m["canonical"])) if only]
    if js_meta:
        report.add(cat, "high", "Head metadata injected by JavaScript",
                   f"Only present after rendering: {', '.join(js_meta)}.",
                   "Emit title/description/canonical in the served HTML — "
                   "indexing pipelines may read them before (or without) "
                   "rendering.")
    if m["jsonld"]:
        report.add(cat, "medium", "JSON-LD injected by JavaScript",
                   "Structured data appears only in the rendered DOM (e.g. via a "
                   "tag manager).",
                   "Move JSON-LD into the served HTML; Google usually processes "
                   "rendered JSON-LD, but other consumers and AI fetchers often "
                   "don't.")


def geo_finding(dep: dict, report) -> None:
    """One GEO-side finding when the page is heavily JS-dependent."""
    if dep["js_only_pct"] >= PCT_HIGH:
        report.add("geo", "high", "AI answer engines may not see this content",
                   f"{dep['js_only_pct']}% of the text exists only after "
                   "JavaScript runs.",
                   "Most AI fetchers (and citation crawlers) read the served "
                   "HTML without executing JS — server-render the content you "
                   "want quoted.")
