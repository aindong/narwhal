#!/usr/bin/env python3
"""narwhal compare — side-by-side competitor comparison (local-first).

Auditing one page answers "what's wrong here?"; the question users actually ask
is relative: *why does that page outrank mine?* This tool scans YOUR page and
1–3 competitor pages with the same auditors, extracts comparable facts from each
(schema types, meta strategy, structure, social packaging), and reports the
**gaps** — what they have that you don't — plus where you lead. Length and
statistic/citation-pattern counts are separate, neutral observations.

Local-first: it fetches supplied pages and related site resources with SSRF
guards, no rank/keyword APIs and no fabricated search volumes. On-page
differences do not establish why anyone ranks.

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
from lib import authorship, htmlx, structured_data, length_observation, evidence_observation  # noqa: E402
from lib import question_observation, schema_appearance  # noqa: E402
from lib.report import TRUNCATED_HTML_ERROR, recorded_response_truncated  # noqa: E402
from lib.report import UNVERIFIED_JS_COMPARISON_ERROR, recorded_js_comparison_problem  # noqa: E402
from lib.report import UNVERIFIED_SITEMAP_DISCOVERY_ERROR, recorded_sitemap_discovery_problem  # noqa: E402
from lib.report import UNVERIFIED_LLMS_ERROR, recorded_llms_problem  # noqa: E402
import audit_geo  # noqa: E402
import scan as scanner  # noqa: E402

MAX_COMPETITORS = 3   # keeps tables readable (you + 3 = 4 columns)

_QUESTION_WORDS = audit_geo._QUESTION_WORDS


def _schema_types(doc) -> list:
    """Every supported structured-data type (deduped, sorted)."""
    records, _ = structured_data.collect(doc)
    return sorted({typ for record in records for typ in structured_data.types(record["node"])})


def _question_ratio(doc) -> float:
    return question_observation.fraction(question_observation.observe(doc.headings, _QUESTION_WORDS))


def facts(report, doc) -> dict:
    """Comparable, deterministic facts for one scanned page (pure)."""
    text = doc.body_text or ""
    cats = report.by_category()
    desc = doc.meta_by_name("description") or ""
    kind = ("article" if htmlx.looks_article(doc)
            else "hub" if htmlx.is_hub_page(doc)
            else "home" if htmlx.is_homepage(doc) else "page")
    attribution = authorship.observe(doc, text)
    length = length_observation.observe(text, doc.extraction)
    questions = question_observation.observe(doc.headings, _QUESTION_WORDS)
    evidence = evidence_observation.observe(len(audit_geo._STAT.findall(text)),
                                            len(audit_geo._CITE_HINT.findall(text)), doc.extraction)
    settings = report.meta.get('scan_settings', {})
    reviewed = settings.get('content_length_reviewed') if isinstance(settings, dict) else None
    schema_types = _schema_types(doc)
    return {
        "url": report.final_url or report.url,
        "rendered": report.rendered,
        "score": report.score(),
        "cat_scores": {k: report.category_score(v) for k, v in cats.items()},
        "page_kind": kind,
        "title": doc.title,
        "title_len": len(doc.title or ""),
        "meta_desc_len": len(desc),
        "words": length['whitespace_tokens'],  # legacy alias, not a linguistic word count
        "text_length": length,
        "content_length_reviewed": reviewed if type(reviewed) is bool else None,
        "extraction": doc.extraction,
        "h1": any(lvl == 1 for lvl, _ in doc.headings),
        "headings": len(doc.headings),
        "question_ratio": round(question_observation.fraction(questions), 2),  # legacy rounded alias
        "question_cues": questions,
        "schema_types": schema_types,
        'schema_search_features': schema_appearance.observe(schema_types),
        "og_complete": all(doc.meta_by_property(p)
                           for p in ("og:title", "og:description", "og:image")),
        "twitter_card": bool(doc.meta_by_name("twitter:card")),
        "canonical": bool(doc.canonical()),
        "author_signal": bool(attribution['candidates']),
        "authorship_cues": attribution,
        "date_signal": bool(doc.meta_by_property("article:published_time")
                            or doc.meta_by_name("date")),
        "stats_cites": evidence['total_matches'],  # legacy alias; not verified sources
        "evidence_cues": evidence,
    }


# Boolean facts framed as "having it is better" + the action closing that gap.
_BOOL_GAPS = [
    ("meta_desc", "Meta description", "Write a 140–160 char meta description."),
    ("h1", "H1 heading", "Add a single H1 stating the page topic."),
    ("og_complete", "Complete Open Graph tags",
     "Add og:title, og:description, og:image for link previews."),
    ("twitter_card", "Twitter/X card", "Add <meta name=\"twitter:card\">."),
    ("canonical", "Canonical URL", "Add <link rel=\"canonical\">."),
    ("author_signal", "Attribution cues",
     "Review actual attribution and page intent; observed cue differences do not verify writers "
     "or require matching a competitor. Do not invent people or credentials."),
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
                     "action": "Review these types; add only those matching real visible content and the intended consumer "
                               "(generate with `narwhal schema <Type>`). Review the dated Google "
                               "appearance notes separately; presence is not proof of eligibility "
                               "or ranking benefit. Some types belong nested in existing markup."})
    extra = yours - {t for r in rivals for t in r["schema_types"]}
    if extra and rivals:
        leads.append({"what": f"Schema types only you have: {', '.join(sorted(extra))}",
                      "detail": ""})

    # Exact lexical cue counts support optional review, not inferred query demand.
    if question_observation.review_difference(you, rivals):
        ahead = [r for r in rivals if question_observation.at_threshold(r) is True]
        gaps.append({'what': question_observation.REVIEW_LABEL, 'who': [r['url'] for r in ahead],
                     'action': 'Review actual headings and reader intent. Questions are optional '
                               'when helpful; do not rewrite solely to satisfy a cue fraction. '
                               'Real queries, engine matching and citation impact are not measured.'})

    return {"gaps": gaps, "leads": leads,
            "text_length": length_observation.comparison(you, rivals)}


def run(urls: list, *, timeout=20, allow_private=False, render=False,
        config=None, max_bytes=5_000_000) -> dict:
    """Scan every URL; the first URL must supply the user's page.

    Failed competitors are reported and skipped. A failed target or fewer than
    two successful scans is an error, never a comparison between rivals.
    ``max_bytes`` is the per-snapshot HTML limit (64KB–20MB), shared by all pages.
    """
    max_bytes = max(64_000, min(int(max_bytes), 20_000_000))
    config = config or configlib.Config()
    config, _ = configlib.snapshot_rules(config)
    results, failed, target = [], [], None
    for index, u in enumerate(urls):
        try:
            rep = scanner.scan(u, timeout=timeout, allow_private=allow_private,
                               render=render, config=config, max_bytes=max_bytes)
        except Exception as exc:  # noqa: BLE001 — unresolvable host, SSRF guard…
            # One dead competitor URL must not sink the whole comparison.
            failed.append({"url": u, "status": 0, "error": str(exc)})
            continue
        doc = getattr(rep, "_doc", None)
        if rep.fetched_status != 200 or doc is None:
            failed.append({"url": u, "status": rep.fetched_status})
            continue
        if recorded_response_truncated(rep.meta):
            failed.append({"url": u, "status": rep.fetched_status,
                           "response_truncated": True, "error": TRUNCATED_HTML_ERROR})
            continue
        problem = recorded_js_comparison_problem(rep.meta, for_score=True)
        if problem:
            failed.append({"url": u, "status": rep.fetched_status,
                           "js_comparison_unverified": True,
                           "error": UNVERIFIED_JS_COMPARISON_ERROR + " " + problem + "."})
            continue
        if recorded_sitemap_discovery_problem(rep.meta, for_score=True):
            failed.append({'url': u, 'status': rep.fetched_status,
                           'sitemap_discovery_unverified': True, 'error': UNVERIFIED_SITEMAP_DISCOVERY_ERROR})
            continue
        if recorded_llms_problem(rep.meta, for_score=True):
            failed.append({'url': u, 'status': rep.fetched_status,
                           'llms_txt_unverified': True, 'error': UNVERIFIED_LLMS_ERROR})
            continue
        results.append(facts(rep, doc))
        if index == 0:
            target = results[-1]
    out = {"failed": failed}
    if target is None and failed:
        out["error"] = ("compare could not scan your page (the first URL); "
                        "no target/competitor verdict was measured.")
    elif len(results) >= 2:
        you, rivals = target, results[1:]
        out.update({"you": you, "competitors": rivals,
                    **gap_analysis(you, rivals)})
    else:
        out["error"] = ("compare needs at least 2 reachable pages; got "
                        f"{len(results)}.")
    return out


# ---------------------------------------------------------------- rendering

def _yn(v) -> str:
    return "✅" if v else "—"


def html_source(page: dict) -> str:
    """Label actual snapshot provenance; missing legacy flags stay unknown."""
    if page.get("rendered") is True:
        return "JavaScript-rendered DOM"
    if page.get("rendered") is False:
        return "Served HTML"
    return "Unknown (not recorded)"


def _short(url: str, limit: int = 40) -> str:
    u = url.split("://", 1)[-1].rstrip("/")
    return u if len(u) <= limit else u[: limit - 1] + "…"


def render_markdown(r: dict) -> str:
    if r.get("error"):
        lines = [f"# Narwhal Compare", "", r["error"]]
        for f in r.get("failed", []):
            detail = f": {f['error']}" if f.get("error") else ""
            lines.append(f"- failed: {f['url']} (status {f['status']}){detail}")
        return "\n".join(lines) + "\n"

    you, rivals = r["you"], r["competitors"]
    cols = [you] + rivals
    lines = [f"# Narwhal Compare — {_short(you['url'])} vs "
             + ", ".join(_short(c["url"]) for c in rivals), ""]
    for f in r.get("failed", []):
        detail = f" — {f['error']}" if f.get("error") else ""
        lines.append(f"_Skipped (status {f['status']}): {f['url']}{detail}_")
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
        ("HTML snapshot", [html_source(c) for c in cols]),
        ("Page type", [c["page_kind"] for c in cols]),
        ("Title length", [str(c["title_len"]) for c in cols]),
        ("Meta description", [f"{c['meta_desc_len']} ch" if c["meta_desc_len"]
                              else "—" for c in cols]),
        ("Extracted-text count", [length_observation.cell(c) for c in cols]),
        ("Selected text (code points)", [length_observation.cell(c, code_points=True) for c in cols]),
        ("Page length-threshold review", [
            'Reviewed' if c.get('content_length_reviewed') is True else
            'Uninterpreted' if c.get('content_length_reviewed') is False else 'Unrecorded' for c in cols]),
        ("H1", [_yn(c["h1"]) for c in cols]),
        ("Question-heading cues", [question_observation.cell(c) for c in cols]),
        ("Statistics/citation pattern matches", [evidence_observation.cell(c) for c in cols]),
        ("Schema types", [str(len(c["schema_types"])) or "0" for c in cols]),
        ("Open Graph complete", [_yn(c["og_complete"]) for c in cols]),
        ("Twitter card", [_yn(c["twitter_card"]) for c in cols]),
        ("Canonical", [_yn(c["canonical"]) for c in cols]),
        ("Attribution cues (not verified writers)", [_yn(c["author_signal"]) for c in cols]),
        ("Date signal", [_yn(c["date_signal"]) for c in cols]),
    ]
    lines += ["## Side by side", "", header, sep]
    lines += [f"| {label} | " + " | ".join(vals) + " |" for label, vals in rows]
    lines.append("")

    length = (r['text_length'] if 'text_length' in r else
              length_observation.comparison(you, rivals))
    lines += ['## Extracted-text length (not a target)', '',
              *length_observation.summary(length), '']
    lines += ['## Statistics/citation cues (not verified evidence)', '',
              *evidence_observation.summary(you, rivals), '']
    lines += ['## Question-heading cues (contextual review)', '',
              *question_observation.summary(you, rivals), '']
    lines += ['## Google schema appearances (dated snapshot)', '',
              *schema_appearance.summary(you, rivals), '']
    unsupported = {'Content depth', 'Evidence density (stats/citations)', 'Question-based headings'}
    gaps = [g for g in r['gaps'] if g.get('what') not in unsupported]
    leads = [g for g in r['leads'] if g.get('what') not in unsupported]
    if len(gaps) != len(r['gaps']) or len(leads) != len(r['leads']):
        lines += ['A legacy content-depth gap/lead, evidence-density verdict or question-heading '
                  'prescription is not repeated as a recommendation; counts alone do not establish '
                  'content depth, factual support or real user queries.', '']
    lines += ["## Gaps to close (they have it — you don't)", ""]
    if gaps:
        for g in gaps:
            who = ", ".join(_short(w, 30) for w in g["who"])
            lines.append(f"- **{g['what']}** — seen on {who}. {g['action']}")
    else:
        lines.append("No feature gaps detected against these competitors. 🟢")
    lines.append("")

    if leads:
        lines += ["## Where you lead", ""]
        for l in leads:
            detail = f" — {l['detail']}" if l["detail"] else ""
            lines.append(f"- 🟢 **{l['what']}**{detail}")
        lines.append("")

    lines += ["_Compared from the pages' own HTML snapshots (same auditors for every "
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
    ap.add_argument("--max-bytes", type=int, default=5_000_000, metavar="N",
                    help="HTML bytes per page/snapshot (64KB–20MB; default 5MB)")
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
            render=args.render, config=cfg, max_bytes=args.max_bytes)
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
