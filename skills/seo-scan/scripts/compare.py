#!/usr/bin/env python3
"""narwhal compare — side-by-side competitor comparison (local-first).

Auditing one page answers "what's wrong here?"; the question users actually ask
is relative: *why does that page outrank mine?* This tool scans YOUR page and
1–3 competitor pages with the same auditors, extracts comparable facts from each
(schema types, meta strategy, depth, structure, evidence, social packaging), and
reports the **gaps** — what they have that you don't — plus where you lead.

Local-first like everything else: it only fetches the pages you name (SSRF-safe,
robots-respecting fetch), no rank/keyword APIs, no fabricated search volumes. It
compares on-page reality, and says so.

Usage:
    narwhal compare https://you.com/page https://rival.com/page
    narwhal compare <you> <rival1> <rival2> --format json -o gaps.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import config as configlib  # noqa: E402
from lib import htmlx  # noqa: E402
import audit_geo  # noqa: E402
import scan as scanner  # noqa: E402

MAX_COMPETITORS = 3   # keeps tables readable (you + 3 = 4 columns)

_QUESTION_WORDS = audit_geo._QUESTION_WORDS


def _schema_types(doc) -> list:
    """Every @type present in the page's JSON-LD blocks (deduped, sorted)."""
    types = set()

    def walk(node):
        if isinstance(node, dict):
            t = node.get("@type")
            if isinstance(t, str):
                types.add(t)
            elif isinstance(t, list):
                types.update(x for x in t if isinstance(x, str))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for blob in doc.scripts_ld:
        try:
            walk(json.loads(blob))
        except (ValueError, TypeError):
            continue
    return sorted(types)


def _question_ratio(doc) -> float:
    subs = [t for lvl, t in doc.headings if lvl >= 2 and t]
    if not subs:
        return 0.0
    q = [t for t in subs if (t.lower().split() or [""])[0] in _QUESTION_WORDS
         or t.rstrip().endswith("?")]
    return len(q) / len(subs)


def facts(report, doc) -> dict:
    """Comparable, deterministic facts for one scanned page (pure)."""
    text = doc.body_text or ""
    cats = report.by_category()
    desc = doc.meta_by_name("description") or ""
    kind = ("article" if htmlx.looks_article(doc)
            else "hub" if htmlx.is_hub_page(doc)
            else "home" if htmlx.is_homepage(doc) else "page")
    return {
        "url": report.final_url or report.url,
        "score": report.score(),
        "cat_scores": {k: report.category_score(v) for k, v in cats.items()},
        "page_kind": kind,
        "title": doc.title,
        "title_len": len(doc.title or ""),
        "meta_desc_len": len(desc),
        "words": len(text.split()),
        "extraction": doc.extraction,
        "h1": any(lvl == 1 for lvl, _ in doc.headings),
        "headings": len(doc.headings),
        "question_ratio": round(_question_ratio(doc), 2),
        "schema_types": _schema_types(doc),
        "og_complete": all(doc.meta_by_property(p)
                           for p in ("og:title", "og:description", "og:image")),
        "twitter_card": bool(doc.meta_by_name("twitter:card")),
        "canonical": bool(doc.canonical()),
        "author_signal": bool(doc.meta_by_name("author")
                              or doc.meta_by_property("article:author")),
        "date_signal": bool(doc.meta_by_property("article:published_time")
                            or doc.meta_by_name("date")),
        "stats_cites": len(audit_geo._STAT.findall(text))
                       + len(audit_geo._CITE_HINT.findall(text)),
    }


# Boolean facts framed as "having it is better" + the action closing that gap.
_BOOL_GAPS = [
    ("meta_desc", "Meta description", "Write a 140–160 char meta description."),
    ("h1", "H1 heading", "Add a single H1 stating the page topic."),
    ("og_complete", "Complete Open Graph tags",
     "Add og:title, og:description, og:image for link previews."),
    ("twitter_card", "Twitter/X card", "Add <meta name=\"twitter:card\">."),
    ("canonical", "Canonical URL", "Add <link rel=\"canonical\">."),
    ("author_signal", "Author metadata", "Add an author meta/byline (E-E-A-T)."),
    ("date_signal", "Publish/update date", "Expose a published/modified date."),
]


def _bool(f: dict, key: str) -> bool:
    if key == "meta_desc":
        return f["meta_desc_len"] > 0
    return bool(f[key])


def gap_analysis(you: dict, rivals: list) -> dict:
    """What rivals have that you don't (gaps) and where you lead (pure)."""
    gaps, leads = [], []

    for key, label, action in _BOOL_GAPS:
        have = _bool(you, key)
        who = [r["url"] for r in rivals if _bool(r, key)]
        if not have and who:
            gaps.append({"what": label, "who": who, "action": action})
        elif have and rivals and not who:
            leads.append({"what": label,
                          "detail": "you have it; no compared competitor does"})

    # Schema types any rival carries that you don't — grouped into one gap so a
    # rich competitor graph doesn't flood the list with one bullet per type.
    yours = set(you["schema_types"])
    missing: dict = {}
    for r in rivals:
        for t in r["schema_types"]:
            if t not in yours:
                missing.setdefault(t, []).append(r["url"])
    if missing:
        gaps.append({"what": "Schema types: " + ", ".join(sorted(missing)),
                     "who": sorted({u for who in missing.values() for u in who}),
                     "action": "Add the ones that match this page's real entity "
                               "(generate with `narwhal schema <Type>`); some may "
                               "belong nested inside your existing markup."})
    extra = yours - {t for r in rivals for t in r["schema_types"]}
    if extra and rivals:
        leads.append({"what": f"Schema types only you have: {', '.join(sorted(extra))}",
                      "detail": ""})

    # Depth: a rival with substantially deeper prose (both non-hub pages).
    if you["page_kind"] != "hub":
        deeper = [r for r in rivals if r["page_kind"] != "hub"
                  and r["words"] >= max(300, int(you["words"] * 1.5))]
        if deeper:
            gaps.append({
                "what": "Content depth",
                "who": [r["url"] for r in deeper],
                "action": f"They run {max(r['words'] for r in deeper)} words to "
                          f"your {you['words']} — cover the missing subtopics, "
                          "don't pad."})
        elif rivals and all(you["words"] >= max(300, int(r["words"] * 1.5))
                            for r in rivals if r["page_kind"] != "hub"):
            leads.append({"what": "Content depth",
                          "detail": f"{you['words']} words vs at most "
                                    f"{max((r['words'] for r in rivals), default=0)}"})

    # Question-shaped headings (AI-answer matching).
    ahead = [r for r in rivals if r["question_ratio"] >= 0.2]
    if you["question_ratio"] < 0.2 and ahead:
        gaps.append({"what": "Question-based headings", "who": [r["url"] for r in ahead],
                     "action": "Rephrase key H2/H3s as the questions users ask."})

    # Evidence density.
    evd = [r for r in rivals if r["stats_cites"] >= max(3, you["stats_cites"] * 2)]
    if evd:
        gaps.append({"what": "Evidence density (stats/citations)",
                     "who": [r["url"] for r in evd],
                     "action": "Add concrete numbers and cited sources — AI answers "
                               "attribute evidence-backed pages."})

    return {"gaps": gaps, "leads": leads}


def run(urls: list, *, timeout=20, allow_private=False, render=False,
        config=None) -> dict:
    """Scan every URL and build the comparison. Failed fetches are reported and
    skipped; fewer than two successful scans is an error."""
    config = config or configlib.Config()
    results, failed = [], []
    for u in urls:
        try:
            rep = scanner.scan(u, timeout=timeout, allow_private=allow_private,
                               render=render, config=config)
        except Exception as exc:  # noqa: BLE001 — unresolvable host, SSRF guard…
            # One dead competitor URL must not sink the whole comparison.
            failed.append({"url": u, "status": 0, "error": str(exc)})
            continue
        doc = getattr(rep, "_doc", None)
        if rep.fetched_status != 200 or doc is None:
            failed.append({"url": u, "status": rep.fetched_status})
            continue
        results.append(facts(rep, doc))
    out = {"failed": failed}
    if len(results) >= 2:
        you, rivals = results[0], results[1:]
        out.update({"you": you, "competitors": rivals,
                    **gap_analysis(you, rivals)})
    else:
        out["error"] = ("compare needs at least 2 reachable pages; got "
                        f"{len(results)}.")
    return out


# ---------------------------------------------------------------- rendering

def _yn(v) -> str:
    return "✅" if v else "—"


def _short(url: str, limit: int = 40) -> str:
    u = url.split("://", 1)[-1].rstrip("/")
    return u if len(u) <= limit else u[: limit - 1] + "…"


def render_markdown(r: dict) -> str:
    if r.get("error"):
        lines = [f"# Narwhal Compare", "", r["error"]]
        for f in r.get("failed", []):
            lines.append(f"- failed: {f['url']} (status {f['status']})")
        return "\n".join(lines) + "\n"

    you, rivals = r["you"], r["competitors"]
    cols = [you] + rivals
    lines = [f"# Narwhal Compare — {_short(you['url'])} vs "
             + ", ".join(_short(c["url"]) for c in rivals), ""]
    for f in r.get("failed", []):
        lines.append(f"_Skipped (status {f['status']}): {f['url']}_")
    if r.get("failed"):
        lines.append("")

    header = "| | **You** | " + " | ".join(_short(c["url"], 24) for c in rivals) + " |"
    sep = "|:--|" + "--:|" * len(cols)
    lines += ["## Scoreboard", "", header, sep,
              "| Overall | " + " | ".join(f"**{c['score']}**" for c in cols) + " |"]
    for key, label in (("technical", "Technical"), ("content", "Content"),
                       ("schema", "Schema"), ("geo", "GEO")):
        row = [str(c["cat_scores"].get(key, "–")) for c in cols]
        lines.append(f"| {label} | " + " | ".join(row) + " |")
    lines.append("")

    rows = [
        ("Page type", [c["page_kind"] for c in cols]),
        ("Title length", [str(c["title_len"]) for c in cols]),
        ("Meta description", [f"{c['meta_desc_len']} ch" if c["meta_desc_len"]
                              else "—" for c in cols]),
        ("Words", [str(c["words"]) for c in cols]),
        ("H1", [_yn(c["h1"]) for c in cols]),
        ("Question headings", [f"{int(c['question_ratio'] * 100)}%" for c in cols]),
        ("Stats/citations", [str(c["stats_cites"]) for c in cols]),
        ("Schema types", [str(len(c["schema_types"])) or "0" for c in cols]),
        ("Open Graph complete", [_yn(c["og_complete"]) for c in cols]),
        ("Twitter card", [_yn(c["twitter_card"]) for c in cols]),
        ("Canonical", [_yn(c["canonical"]) for c in cols]),
        ("Author signal", [_yn(c["author_signal"]) for c in cols]),
        ("Date signal", [_yn(c["date_signal"]) for c in cols]),
    ]
    lines += ["## Side by side", "", header, sep]
    lines += [f"| {label} | " + " | ".join(vals) + " |" for label, vals in rows]
    lines.append("")

    lines += ["## Gaps to close (they have it — you don't)", ""]
    if r["gaps"]:
        for g in r["gaps"]:
            who = ", ".join(_short(w, 30) for w in g["who"])
            lines.append(f"- **{g['what']}** — seen on {who}. {g['action']}")
    else:
        lines.append("No feature gaps detected against these competitors. 🟢")
    lines.append("")

    if r["leads"]:
        lines += ["## Where you lead", ""]
        for l in r["leads"]:
            detail = f" — {l['detail']}" if l["detail"] else ""
            lines.append(f"- 🟢 **{l['what']}**{detail}")
        lines.append("")

    lines += ["_Compared from the pages' own served HTML (same auditors for every "
              "URL). No rank or traffic data is used or implied — a gap here is an "
              "on-page difference, not proof of why anyone ranks._"]
    return "\n".join(lines).rstrip() + "\n"


def render_json(r: dict) -> str:
    return json.dumps(r, indent=2, ensure_ascii=False)


def main(argv=None) -> int:
    cfg = configlib.load_from_args(argv)
    ap = argparse.ArgumentParser(
        description="Side-by-side competitor comparison (local-first)",
        parents=[configlib.config_arg_parser()])
    ap.add_argument("urls", nargs="+",
                    help="YOUR page first, then 1–3 competitor pages")
    ap.add_argument("--format", choices=("markdown", "json"), default="markdown")
    ap.add_argument("-o", "--output")
    ap.add_argument("--timeout", type=int, default=cfg.default("timeout"))
    ap.add_argument("--render", action="store_true",
                    help="render JS with Playwright if installed")
    ap.add_argument("--allow-private", action="store_true")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    if len(args.urls) < 2:
        print("compare needs your URL plus at least one competitor URL.",
              file=sys.stderr)
        return 2
    urls = args.urls[: 1 + MAX_COMPETITORS]
    if len(args.urls) > len(urls):
        print(f"Note: comparing against the first {MAX_COMPETITORS} competitors "
              f"(got {len(args.urls) - 1}).", file=sys.stderr)

    r = run(urls, timeout=args.timeout, allow_private=args.allow_private,
            render=args.render, config=cfg)
    out = render_json(r) if args.format == "json" else render_markdown(r)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"Wrote {args.format} comparison to {args.output}")
    else:
        print(out)
    return 0 if not r.get("error") else 2


if __name__ == "__main__":
    raise SystemExit(main())
