#!/usr/bin/env python3
"""narwhal brief — a data-driven content brief (local-first, no keyword APIs).

Auditing tells you what's broken; a brief tells you what to *write*. This tool
grounds that plan in data Narwhal already has instead of fabricated search
volumes:

  - **Your real queries** (optional, GSC): the striking-distance queries this
    page already earns impressions for at positions 8-20 — demand you nearly
    satisfy — plus CTR-laggard / decay status for the page.
  - **The pages that currently win** (compare, #21): scan 1-3 competitor pages
    with the same auditors and report the on-page gaps.
  - **Missing subtopics**: competitor H2/H3 sections whose topic words don't
    appear anywhere in your page text — coverage to add, not padding.
  - **Questions to answer**: competitors' question-shaped headings you don't
    cover, plus your own question-shaped striking queries.

Honesty rules: without GSC credentials this degrades to a clearly labeled
**structure-only** brief (no target queries are invented). Gaps are on-page
differences, never presented as proof of why anyone ranks.

Usage:
    narwhal brief https://you.com/page https://rival.com/page
    narwhal brief https://you.com/page rival1 rival2 --format json -o brief.json
    narwhal brief --topic "widget calibration" https://rival.com/guide
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import config as configlib  # noqa: E402
from lib import text as textlib  # noqa: E402
import audit_geo  # noqa: E402
import compare  # noqa: E402
import scan as scanner  # noqa: E402

MAX_COMPETITORS = compare.MAX_COMPETITORS
_QUESTION_WORDS = audit_geo._QUESTION_WORDS

# Boilerplate headings that aren't subtopics — suggesting "cover: Comments"
# would be noise. Matched against the whole heading, lowercased.
_NOISE_HEADINGS = {
    "introduction", "intro", "overview", "conclusion", "summary", "contents",
    "table of contents", "faq", "faqs", "comments", "related", "related posts",
    "related articles", "related content", "see also", "further reading",
    "references",
    "resources", "share", "share this", "newsletter", "subscribe", "sign up",
    "about", "about the author", "contact", "tags", "categories", "archive",
    "search", "menu", "navigation", "footer", "leave a comment", "leave a reply",
}


def _terms(s: str) -> set:
    """Meaningful lowercased terms of a phrase (stopwords/short words out)."""
    return {w.lower() for w in textlib.words(s or "")
            if len(w) >= 3 and w.lower() not in textlib.STOPWORDS}


def _match(a: str, b: str) -> bool:
    """Crude inflection-tolerant term match ("widgets"~"widget",
    "calibration"~"calibrate") — a labeled heuristic, not linguistics."""
    return (a == b
            or (len(a) >= 4 and len(b) >= 4
                and (a.startswith(b) or b.startswith(a)))
            or (len(a) >= 7 and len(b) >= 7 and a[:6] == b[:6]))


def _overlap(terms: set, other: set) -> int:
    """How many of ``terms`` have a match in ``other``."""
    return sum(1 for t in terms if any(_match(t, o) for o in other))


def _is_question(s: str) -> bool:
    s = (s or "").strip()
    first = (s.lower().split() or [""])[0]
    return s.endswith("?") or first in _QUESTION_WORDS


def norm_page(url: str) -> str:
    """URL comparison key: scheme/www/trailing-slash/fragment-insensitive."""
    p = urlparse((url or "").strip())
    host = (p.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (p.path or "/").rstrip("/") or "/"
    return f"{host}{path}" + (f"?{p.query}" if p.query else "")


# ---------------------------------------------------------------- GSC slice

def page_queries(gsc: dict, url: str) -> dict:
    """Slice an analyzed GSC result (gsc.gather / gsc.analyze shape) down to
    one page: its striking-distance queries and laggard/decay status. Pure."""
    key = norm_page(url)
    striking = [s for s in gsc.get("striking", []) if norm_page(s["page"]) == key]
    laggard = next((l for l in gsc.get("laggards", [])
                    if norm_page(l["page"]) == key), None)
    decaying = next((d for d in gsc.get("decaying", [])
                     if norm_page(d["page"]) == key), None)
    cannibalized = [c["query"] for c in gsc.get("cannibalization", [])
                    if any(norm_page(p["page"]) == key for p in c["pages"])]
    return {"striking": striking, "laggard": laggard, "decaying": decaying,
            "cannibalized": cannibalized}


def topic_queries(gsc: dict, topic: str, *, top: int = 15) -> list:
    """Site-wide striking-distance queries that share a term with the topic —
    real demand adjacent to a page that doesn't exist yet. Pure."""
    want = _terms(topic)
    if not want:
        return []
    return [s for s in gsc.get("striking", [])
            if _overlap(_terms(s["query"]), want)][:top]


# ---------------------------------------------------------------- coverage

def subtopic_gaps(you: dict, rivals: list) -> list:
    """Competitor H2/H3 sections your page text doesn't cover.

    ``you``/``rivals`` are page dicts: ``{"url", "headings": [(lvl, text)],
    "text": body_text}``; ``you`` may be None (topic mode → every substantive
    rival section is a subtopic to cover). A rival heading counts as *covered*
    when at least half of its meaningful terms appear in your page text. Pure."""
    have = _terms(you["text"]) | {t for _, h in you["headings"] for t in _terms(h)} \
        if you else set()
    out, seen = [], set()
    for r in rivals:
        for lvl, h in r["headings"]:
            if lvl not in (2, 3) or not h:
                continue
            norm = " ".join(h.lower().split())
            terms = _terms(h)
            if norm in _NOISE_HEADINGS or not terms or norm in seen:
                continue
            # One-word headings are usually nav/footer column labels
            # ("Tools", "Company"), not subtopics — unless question-shaped.
            if len(terms) < 2 and not _is_question(h):
                continue
            covered = _overlap(terms, have) >= max(1, (len(terms) + 1) // 2) \
                if you else False
            if not covered:
                seen.add(norm)
                out.append({"heading": h.strip(), "who": r["url"],
                            "question": _is_question(h)})
    return out


def questions_to_answer(subtopics: list, striking: list) -> list:
    """Question-shaped work items: rival question headings you don't cover
    plus your own question-shaped striking queries. Deduped by terms. Pure."""
    out, seen = [], []
    for s in subtopics:
        if s["question"]:
            out.append({"question": s["heading"], "source": s["who"]})
            seen.append(_terms(s["heading"]))
    for q in striking:
        if _is_question(q["query"]):
            t = _terms(q["query"])
            if not any(t and _overlap(t, prior) == len(t) for prior in seen):
                out.append({"question": q["query"],
                            "source": f"your own striking-distance query "
                                      f"({q['impressions']} impressions)"})
                seen.append(t)
    return out


def schema_suggestions(you: dict | None, rivals: list, questions: list) -> list:
    """Schema types worth adding: what rivals mark up that you don't, plus
    FAQPage when there's question content to mark up. Pure."""
    yours = set(you["facts"]["schema_types"]) if you else set()
    out = []
    for t in sorted({t for r in rivals for t in r["facts"]["schema_types"]}
                    - yours):
        who = sorted({r["url"] for r in rivals
                      if t in r["facts"]["schema_types"]})
        out.append({"type": t, "reason": "competitors mark this up",
                    "who": who})
    if questions and "FAQPage" not in yours \
            and not any(s["type"] == "FAQPage" for s in out):
        out.append({"type": "FAQPage",
                    "reason": "the brief includes questions to answer",
                    "who": []})
    return out


def structure_targets(you: dict | None, rivals: list) -> dict:
    """Deterministic structure benchmarks vs the compared pages. Hub pages
    (link lists) aren't content benchmarks, so they're excluded. Pure."""
    t: dict = {}
    content = [r["facts"] for r in rivals if r["facts"]["page_kind"] != "hub"]
    if content:
        deepest = max(f["words"] for f in content)
        if you is None or deepest >= max(300, int(you["facts"]["words"] * 1.5)):
            t["target_words"] = deepest
            t["your_words"] = you["facts"]["words"] if you else 0
        qr = max(f["question_ratio"] for f in content)
        if qr >= 0.2 and (you is None or you["facts"]["question_ratio"] < 0.2):
            t["question_headings"] = True
        ev = max(f["stats_cites"] for f in content)
        if you is None or ev >= max(3, you["facts"]["stats_cites"] * 2):
            t["evidence_target"] = ev
            t["your_evidence"] = you["facts"]["stats_cites"] if you else 0
    return t


# ---------------------------------------------------------------- assembly

def synthesize(you: dict | None, rivals: list, gsc: dict | None,
               *, topic: str = None, failed: list = None) -> dict:
    """Assemble the brief from scanned-page dicts + an analyzed GSC result.

    ``you``/rival page dicts: ``{"url", "facts", "headings", "text"}``.
    ``gsc`` is the gsc.gather result (or None when skipped). Pure."""
    brief: dict = {"topic": topic, "failed": failed or []}

    gsc_ok = bool(gsc and gsc.get("found"))
    if gsc_ok:
        full = page_queries(gsc, you["url"]) if you else \
            {"striking": topic_queries(gsc, topic), "laggard": None,
             "decaying": None, "cannibalized": []}
        brief["gsc"] = {"found": True, "property": gsc.get("property"),
                        "window": gsc.get("window"), **full}
        striking = full["striking"]
    else:
        brief["gsc"] = {"found": False,
                        "note": (gsc or {}).get("error") or "GSC skipped"}
        striking = []
    brief["grounding"] = ("queries+pages" if gsc_ok and striking
                          else "pages-only" if rivals else "page-only")

    if you:
        brief["you"] = you["facts"]
    if rivals:
        brief["competitors"] = [r["facts"] for r in rivals]
        if you:
            ga = compare.gap_analysis(you["facts"], [r["facts"] for r in rivals])
            # Depth/questions/evidence gaps re-appear under "structure targets"
            # with concrete numbers — keep them there only.
            structural = {"Content depth", "Question-based headings",
                          "Evidence density (stats/citations)"}
            brief["gaps"] = [g for g in ga["gaps"] if g["what"] not in structural]
            brief["leads"] = ga["leads"]
    subtopics = subtopic_gaps(you, rivals)
    brief["missing_subtopics"] = subtopics
    brief["questions"] = questions_to_answer(subtopics, striking)
    brief["schema"] = schema_suggestions(you, rivals, brief["questions"])
    brief["structure"] = structure_targets(you, rivals)
    return brief


def _page(url: str, *, timeout=20, allow_private=False, render=False,
          config=None) -> dict:
    """Scan one URL into the page dict the pure functions consume."""
    rep = scanner.scan(url, timeout=timeout, allow_private=allow_private,
                       render=render, config=config)
    doc = getattr(rep, "_doc", None)
    if rep.fetched_status != 200 or doc is None:
        raise RuntimeError(f"HTTP {rep.fetched_status}")
    return {"url": rep.final_url or url, "facts": compare.facts(rep, doc),
            "headings": list(doc.headings), "text": doc.body_text or ""}


def run(your_url: str = None, competitor_urls: list = None, *, topic: str = None,
        use_gsc: bool = True, days: int = 28, min_impressions: int = 50,
        timeout: int = 20, allow_private: bool = False, render: bool = False,
        config=None) -> dict:
    """Fetch everything and build the brief. Failed competitor fetches are
    reported and skipped; a failed own-page fetch is an error."""
    config = config or configlib.Config()
    competitor_urls = list(competitor_urls or [])[:MAX_COMPETITORS]

    you = None
    if your_url:
        try:
            you = _page(your_url, timeout=timeout, allow_private=allow_private,
                        render=render, config=config)
        except Exception as exc:  # noqa: BLE001
            return {"error": f"could not scan your page {your_url}: {exc}"}

    rivals, failed = [], []
    for u in competitor_urls:
        try:
            rivals.append(_page(u, timeout=timeout, allow_private=allow_private,
                                render=render, config=config))
        except Exception as exc:  # noqa: BLE001
            failed.append({"url": u, "error": str(exc)})

    gsc_data = None
    if use_gsc:
        if your_url:  # GSC only knows *your* property — never query rivals'
            import gsc as gsclib  # noqa: PLC0415
            gsc_data = gsclib.gather(your_url, days=days, timeout=timeout,
                                     min_impressions=min_impressions)
        elif topic:
            gsc_data = {"found": False,
                        "error": "topic mode has no page URL to resolve a GSC "
                                 "property from — pass your site URL as "
                                 "--gsc-site to ground the topic in real queries"}
    return synthesize(you, rivals, gsc_data, topic=topic, failed=failed)


def run_topic_gsc(site: str, *, days=28, min_impressions=50, timeout=30):
    """Fetch GSC for an explicit site in topic mode (``--gsc-site``)."""
    import gsc as gsclib  # noqa: PLC0415
    return gsclib.gather(site, days=days, timeout=timeout,
                         min_impressions=min_impressions)


# ---------------------------------------------------------------- rendering

def _short(url: str, limit: int = 40) -> str:
    u = url.split("://", 1)[-1].rstrip("/")
    return u if len(u) <= limit else u[: limit - 1] + "…"


def render_markdown(b: dict) -> str:
    if b.get("error"):
        return f"# Narwhal Brief\n\n{b['error']}\n"

    subject = b.get("topic") or (_short(b["you"]["url"]) if b.get("you")
                                 else "content brief")
    lines = [f"# Content brief — {subject}", ""]

    gsc = b["gsc"]
    striking = gsc.get("striking", []) if gsc.get("found") else []
    if striking:
        w = gsc.get("window") or {}
        lines += [f"_Grounded in **your real Search Console queries** "
                  f"(`{gsc.get('property', '?')}`, "
                  f"{w.get('start', '?')} → {w.get('end', '?')}) plus the "
                  "compared pages' served HTML._", ""]
    elif gsc.get("found"):
        lines += [f"_Search Console is connected (`{gsc.get('property', '?')}`)"
                  " but has no striking-distance queries for this page yet — "
                  "the plan below is grounded in the compared pages' served "
                  "HTML. No queries are invented._", ""]
    else:
        lines += ["_**Structure-only brief** — no Search Console data was "
                  "available"
                  + (f" ({gsc['note']})" if gsc.get("note") else "")
                  + ". Target queries are omitted rather than invented; "
                  "connect GSC (`narwhal gsc --auth`) to ground the brief in "
                  "real demand._", ""]
    for f in b.get("failed", []):
        lines.append(f"_Skipped competitor (fetch failed): {f['url']}_")
    if b.get("failed"):
        lines.append("")

    # Target queries (only ever real ones).
    if striking:
        label = ("Real demand adjacent to this topic (site-wide)"
                 if b.get("topic") else "Queries this page nearly ranks for")
        lines += ["## Target queries — real, from your Search Console", "",
                  f"{label} — positions 8–20 with impressions; landing these "
                  "on page 1 is the point of the rewrite:", "",
                  "| Query | Position | Impressions |", "|:--|--:|--:|"]
        lines += [f"| {s['query']} | {s['position']} | {s['impressions']} |"
                  for s in striking]
        lines.append("")
    if gsc.get("laggard"):
        l = gsc["laggard"]
        lines += [f"**CTR laggard:** this page ranks at position "
                  f"{l['position']} but converts only {l['ctr'] * 100:.1f}% of "
                  f"{l['impressions']} impressions — rewrite the title/meta "
                  "first; it's the cheapest win here.", ""]
    if gsc.get("decaying"):
        d = gsc["decaying"]
        lines += [f"**Decaying:** clicks fell {d['drop_pct']}% vs the prior "
                  f"period ({d['clicks_prev']} → {d['clicks_now']}) — treat "
                  "this refresh as time-sensitive.", ""]
    if gsc.get("cannibalized"):
        lines += ["**Cannibalization:** this page splits these queries with "
                  "other pages of yours — decide which page owns each before "
                  "adding content: " + ", ".join(gsc["cannibalized"]), ""]

    if b.get("gaps") is not None:
        lines += ["## Gaps vs the pages that win", ""]
        if b["gaps"]:
            for g in b["gaps"]:
                who = ", ".join(_short(w, 30) for w in g["who"])
                lines.append(f"- **{g['what']}** — seen on {who}. {g['action']}")
        else:
            lines.append("No on-page feature gaps against the compared pages. 🟢")
        lines.append("")

    if b["missing_subtopics"]:
        title = ("Subtopics the winning pages cover"
                 if not b.get("you") else
                 "Missing subtopics — sections they have, your text doesn't")
        lines += [f"## {title}", ""]
        for s in b["missing_subtopics"]:
            lines.append(f"- **{s['heading']}** (on {_short(s['who'], 30)})")
        lines.append("")

    if b["questions"]:
        lines += ["## Questions to answer on the page", ""]
        for q in b["questions"]:
            lines.append(f"- **{q['question']}** — from {_short(q['source'], 60)}")
        lines += ["", "Answer each in the first sentence under its heading — "
                  "citable passages are what AI answer engines lift.", ""]

    st = b["structure"]
    if st:
        lines += ["## Structure targets", ""]
        if st.get("target_words"):
            lines.append(f"- **Depth:** the deepest compared page runs "
                         f"~{st['target_words']} words"
                         + (f" to your {st['your_words']}" if b.get("you") else "")
                         + " — close the gap by covering the missing subtopics "
                           "above, not by padding.")
        if st.get("question_headings"):
            lines.append("- **Question-shaped H2/H3s:** the winning pages "
                         "phrase key headings as the questions users ask — "
                         "do the same where it's natural.")
        if "evidence_target" in st:
            lines.append(f"- **Evidence:** they carry ~{st['evidence_target']} "
                         "stats/citations"
                         + (f" to your {st['your_evidence']}" if b.get("you") else "")
                         + " — add concrete numbers with named sources.")
        lines.append("")

    if b["schema"]:
        lines += ["## Schema to add", ""]
        for s in b["schema"]:
            who = (" (seen on " + ", ".join(_short(w, 30) for w in s["who"]) + ")"
                   if s["who"] else "")
            lines.append(f"- **{s['type']}** — {s['reason']}{who}. Generate it: "
                         f"`narwhal schema {s['type']}`; only add types that "
                         "match the page's real entity.")
        lines.append("")

    if b.get("leads"):
        lines += ["## Keep (where you already lead)", ""]
        for l in b["leads"]:
            detail = f" — {l['detail']}" if l["detail"] else ""
            lines.append(f"- 🟢 **{l['what']}**{detail}")
        lines.append("")

    lines += ["_No search volumes are estimated or invented — any queries "
              "above are real Search Console data for your property. Page "
              "gaps are on-page differences from served HTML — useful targets, "
              "not proof of why anyone ranks._"]
    return "\n".join(lines).rstrip() + "\n"


def render_json(b: dict) -> str:
    return json.dumps(b, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    cfg = configlib.load_from_args(argv)
    ap = argparse.ArgumentParser(
        description="Data-driven content brief from your GSC queries + the "
                    "pages that win (local-first; no keyword APIs)",
        parents=[configlib.config_arg_parser()])
    ap.add_argument("urls", nargs="*",
                    help="YOUR page first, then 1-3 competitor pages "
                         "(with --topic: competitor pages only)")
    ap.add_argument("--topic", default=None,
                    help="plan a page that doesn't exist yet — the positional "
                         "URLs are all competitors")
    ap.add_argument("--gsc-site", default=None,
                    help="with --topic: your site URL, to pull site-wide "
                         "striking-distance queries near the topic")
    ap.add_argument("--no-gsc", action="store_true",
                    help="skip Search Console (structure-only brief)")
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--min-impressions", type=int, default=50)
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

    if args.topic:
        your_url, competitors = None, args.urls
        if not competitors:
            print("--topic needs at least one competitor URL to learn the "
                  "topic's structure from.", file=sys.stderr)
            return 2
    else:
        if not args.urls:
            print("brief needs your page URL (plus competitor URLs), or "
                  "--topic <phrase> with competitor URLs.", file=sys.stderr)
            return 2
        your_url, competitors = args.urls[0], args.urls[1:]
    if len(competitors) > MAX_COMPETITORS:
        print(f"Note: using the first {MAX_COMPETITORS} competitors "
              f"(got {len(competitors)}).", file=sys.stderr)

    b = run(your_url, competitors, topic=args.topic, use_gsc=not args.no_gsc,
            days=args.days, min_impressions=args.min_impressions,
            timeout=args.timeout, allow_private=args.allow_private,
            render=args.render, config=cfg)
    # Topic mode with an explicit GSC site: fold real adjacent demand in.
    if args.topic and args.gsc_site and not args.no_gsc and not b.get("error"):
        g = run_topic_gsc(args.gsc_site, days=args.days,
                          min_impressions=args.min_impressions,
                          timeout=args.timeout)
        if g.get("found"):
            b["gsc"] = {"found": True, "property": g.get("property"),
                        "window": g.get("window"),
                        "striking": topic_queries(g, args.topic),
                        "laggard": None, "decaying": None, "cannibalized": []}
            if b["gsc"]["striking"]:
                b["grounding"] = "queries+pages"
        else:
            b["gsc"] = {"found": False, "note": g.get("error")}

    out = render_json(b) if args.format == "json" else render_markdown(b)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"Wrote {args.format} brief to {args.output}")
    else:
        print(out)
    return 0 if not b.get("error") else 2


if __name__ == "__main__":
    raise SystemExit(main())
