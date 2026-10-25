#!/usr/bin/env python3
"""narwhal brief — a data-driven content brief (local-first, no keyword APIs).

Auditing tells you what's broken; a brief tells you what to *write*. This tool
grounds that plan in data Narwhal already has instead of fabricated search
volumes:

  - **Your real queries** (optional, GSC): the striking-distance queries this
    page already earns impressions for at positions 8-20 — demand you nearly
    satisfy — plus CTR-laggard / decay status for the page.
  - **Compared pages** (compare, #21): scan 1-3 supplied competitor pages
    with the same auditors and report on-page gaps, not verified ranking wins.
  - **Heading-review candidates**: compared H2/H3 labels below a lexical
    term-match cutoff, not verified missing semantic coverage or required sections.
  - **Question-shaped candidates**: compared headings selected by that filter,
    plus your own recorded question-shaped striking queries; review relevance.

Honesty rules: without explicit GSC opt-in and usable credentials this is a clearly labeled
**structure-only** brief (no target queries are invented). Gaps are on-page
differences, never presented as proof of why anyone ranks.

Usage:
    narwhal brief https://you.com/page https://rival.com/page
    narwhal brief https://you.com/page https://rival.com/page --gsc
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

from lib.report_output import save_output  # noqa: E402

from lib import config as configlib  # noqa: E402
from lib.report import TRUNCATED_HTML_ERROR, recorded_response_truncated  # noqa: E402
from lib.report import PARTIAL_HTML_ERROR, recorded_response_partial  # noqa: E402
from lib.report import UNVERIFIED_JS_COMPARISON_ERROR, recorded_js_comparison_problem  # noqa: E402
from lib.report import UNVERIFIED_SITEMAP_DISCOVERY_ERROR, recorded_sitemap_discovery_problem  # noqa: E402
from lib.report import UNVERIFIED_LLMS_ERROR, recorded_llms_problem  # noqa: E402
from lib.report import recorded_image_weight_problem  # noqa: E402
from lib import text as textlib  # noqa: E402
from lib import length_observation, evidence_observation, question_observation  # noqa: E402
from lib import schema_appearance, schema_coverage, subtopic_observation  # noqa: E402
from lib import date_cues  # noqa: E402
from lib import canonical, links as linklib, hreflang  # noqa: E402
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
    """Compared H2/H3 labels below a lexical match cutoff, not semantic gaps.

    ``you``/``rivals`` are page dicts: ``{"url", "headings": [(lvl, text)],
    "text": body_text}``; ``you`` may be None (topic mode → every substantive
    rival heading is a candidate to review). A label is filtered out when at
    least half its eligible terms match own-page inputs. Pure; not coverage proof."""
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
            matched = _overlap(terms, have) if you else None
            at_cutoff = matched >= max(1, (len(terms) + 1) // 2) if you else False
            if not at_cutoff:
                seen.add(norm)
                out.append({"heading": h.strip(), "who": r["url"],
                            "question": _is_question(h),
                            'term_match': subtopic_observation.observe(h.strip(), lvl, len(terms), matched, bool(you))})
    return out


def questions_to_answer(subtopics: list, striking: list) -> list:
    """Review candidates from filtered compared headings and recorded queries.

    Deduped by terms; heading non-matches do not prove missing coverage. Pure."""
    out, seen = [], []
    for s in subtopics:
        if s["question"]:
            out.append({"question": s["heading"], "source": s["who"], 'source_kind': 'compared_heading'})
            seen.append(_terms(s["heading"]))
    for q in striking:
        if _is_question(q["query"]):
            t = _terms(q["query"])
            if not any(t and _overlap(t, prior) == len(t) for prior in seen):
                out.append({"question": q["query"], 'source_kind': 'gsc_query',
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
    for candidate in out:
        candidate['google_search_appearance'] = schema_appearance.observe([candidate['type']])
        candidate['existing_markup_status'] = ('not_applicable' if you is None else
            'not_observed_in_supported_subset' if schema_coverage.absence_review(you['facts']) else 'unverified')
        if candidate['existing_markup_status'] == 'unverified':
            candidate['reason'] += '; existing own-page markup is unverified, inspect before adding or duplicating it'
    return out


def structure_targets(you: dict | None, rivals: list) -> dict:
    """Existing question-heading heuristic on non-hubs, not length/evidence targets."""
    t: dict = {}
    content = [r["facts"] for r in rivals if r["facts"]["page_kind"] != "hub"]
    if question_observation.review_difference(you['facts'] if you else None, content):
        t['question_headings'] = True
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
            # Questions appear under structure targets; legacy length/evidence
            # verdicts are not recommendations either.
            structural = {"Content depth", "Question-based headings", question_observation.REVIEW_LABEL,
                          "Evidence density (stats/citations)"}
            brief["gaps"] = [g for g in ga["gaps"] if g["what"] not in structural]
            brief["leads"] = ga["leads"]
    subtopics = subtopic_gaps(you, rivals)
    brief["missing_subtopics"] = subtopics
    brief['subtopic_review'] = subtopic_observation.context(bool(you))
    brief["questions"] = questions_to_answer(subtopics, striking)
    brief["schema"] = schema_suggestions(you, rivals, brief["questions"])
    brief["structure"] = structure_targets(you, rivals)
    brief['text_length'] = length_observation.comparison(you['facts'] if you else None,
                                                       [r['facts'] for r in rivals])
    brief['schema_comparison'] = schema_coverage.comparison(you['facts'] if you else None, [r['facts'] for r in rivals])
    return brief


def _page(url: str, *, timeout=20, allow_private=False, render=False,
          config=None, max_bytes=5_000_000) -> dict:
    """Scan one URL into the page dict the pure functions consume."""
    rep = scanner.scan(url, timeout=timeout, allow_private=allow_private,
                       render=render, config=config, max_bytes=max_bytes)
    doc = getattr(rep, "_doc", None)
    if recorded_response_partial(rep.meta):
        raise RuntimeError(PARTIAL_HTML_ERROR)
    if rep.fetched_status != 200 or doc is None:
        raise RuntimeError(f"HTTP {rep.fetched_status}")
    if recorded_response_truncated(rep.meta):
        raise RuntimeError(TRUNCATED_HTML_ERROR)
    problem = recorded_js_comparison_problem(rep.meta, for_score=True)
    if problem:
        raise RuntimeError(UNVERIFIED_JS_COMPARISON_ERROR + " " + problem + ".")
    if recorded_sitemap_discovery_problem(rep.meta, for_score=True):
        raise RuntimeError(UNVERIFIED_SITEMAP_DISCOVERY_ERROR)
    if recorded_llms_problem(rep.meta, for_score=True):
        raise RuntimeError(UNVERIFIED_LLMS_ERROR)
    image_problem = recorded_image_weight_problem(rep.meta, for_score=True)
    if image_problem:
        raise RuntimeError(image_problem)
    if canonical.unverified(rep.meta):
        raise RuntimeError(canonical.ERROR)
    if linklib.unassessed_base(rep.meta):
        raise RuntimeError(linklib.BASE_ERROR)
    if hreflang.unverified(rep.meta, for_score=True):
        raise RuntimeError(hreflang.ERROR)
    return {"url": rep.final_url or url, "facts": compare.facts(rep, doc),
            "headings": list(doc.headings), "text": doc.body_text or ""}


def run(your_url: str = None, competitor_urls: list = None, *, topic: str = None,
        use_gsc: bool = False, days: int = 28, min_impressions: int = 50,
        timeout: int = 20, allow_private: bool = False, render: bool = False,
        config=None, max_bytes: int = 5_000_000) -> dict:
    """Fetch everything and build the brief. Failed competitor fetches are
    reported and skipped; a failed own-page fetch is an error. ``max_bytes`` is
    the per-snapshot HTML limit (64KB–20MB), shared by all pages."""
    max_bytes = max(64_000, min(int(max_bytes), 20_000_000))
    config = config or configlib.Config()
    config, _ = configlib.snapshot_rules(config)
    competitor_urls = list(competitor_urls or [])[:MAX_COMPETITORS]

    you = None
    if your_url:
        try:
            you = _page(your_url, timeout=timeout, allow_private=allow_private,
                        render=render, config=config, max_bytes=max_bytes)
        except Exception as exc:  # noqa: BLE001
            return {"error": f"could not scan your page {your_url}: {exc}"}

    rivals, failed = [], []
    for u in competitor_urls:
        try:
            rivals.append(_page(u, timeout=timeout, allow_private=allow_private,
                                render=render, config=config, max_bytes=max_bytes))
        except Exception as exc:  # noqa: BLE001
            failed.append({"url": u, "error": str(exc)})

    if not your_url and not rivals:
        return {"topic": topic, "failed": failed,
                "error": "brief needs an own page or at least one usable competitor page; "
                         "no page-grounded brief was measured."}

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
        lines = ["# Narwhal Brief", "", b["error"]]
        for failure in b.get("failed", []):
            lines.append(f"- failed: {failure['url']}: {failure['error']}")
        return "\n".join(lines) + "\n"

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
                  "compared pages' HTML snapshots._", ""]
    elif gsc.get("found"):
        lines += [f"_Search Console is connected (`{gsc.get('property', '?')}`)"
                  " but has no striking-distance queries for this page yet — "
                  "the plan below is grounded in the compared pages' HTML "
                  "snapshots. No queries are invented._", ""]
    else:
        guidance = ("pass `--gsc` to opt in to real GSC queries"
                    if gsc.get("note") == "GSC skipped" else
                    "connect GSC (`narwhal gsc --auth`) to ground the brief in real demand")
        lines += ["_**Structure-only brief** — no Search Console data was "
                  "available"
                  + (f" ({gsc['note']})" if gsc.get("note") else "")
                  + ". Target queries are omitted rather than invented; "
                  + guidance + "._", ""]
    for f in b.get("failed", []):
        detail = f" — {f['error']}" if f.get("error") else ""
        lines.append(f"_Skipped competitor: {f['url']}{detail}_")
    if b.get("failed"):
        lines.append("")

    pages = ([b["you"]] if b.get("you") else []) + b.get("competitors", [])
    if pages:
        lines += ["## Page snapshots", "", "| Page | HTML source |", "|:--|:--|"]
        for page in pages:
            label = page['url'].replace('|', '%7C').replace('\n', ' ').replace('\r', ' ')
            lines.append(f"| {label} | {compare.html_source(page)} |")
        lines.append("")
    lines += ['## Structured-data extraction coverage', '',
              *schema_coverage.summary(b.get('you'), b.get('competitors', [])), '']

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
        lines += ["## Gaps vs compared pages", ""]
        gaps = [g for g in b['gaps'] if g.get('what') not in
                ('Content depth', 'Evidence density (stats/citations)', 'Question-based headings', 'Publish/update date') and not (
                    g.get('what', '').startswith('Schema types:') and not schema_coverage.absence_review(b.get('you')))]
        if gaps:
            for g in gaps:
                who = ", ".join(_short(w, 30) for w in g["who"])
                lines.append(f"- **{g['what']}** — seen on {who}. {g['action']}")
        else:
            lines.append('No other assessed feature gaps; schema absence checks are unverified.'
                         if schema_coverage.comparison(b.get('you'), b.get('competitors', []))['status'] != 'no_known_problem'
                         else "No on-page feature gaps against the compared pages. 🟢")
        lines.append("")

    lines += ['## Date-related candidates (not freshness)', '',
              *date_cues.summary(b.get('you'), b.get('competitors', [])), '']
    lines += ['## Compared-heading candidates (review, not coverage gaps)', '', subtopic_observation.LIMITS, '']
    known_context = subtopic_observation.recorded(b.get('subtopic_review'), bool(b.get('you')))
    if not known_context:
        lines += ['Legacy candidate-selection basis is unrecorded or unsupported; no semantic absence is inferred.', '']
    if b["missing_subtopics"]:
        for s in b["missing_subtopics"]:
            lines.append(f"- **{s['heading']}** (on {_short(s['who'], 30)})")
            lines.append('  ' + subtopic_observation.candidate_note(s, bool(b.get('you')), known_context))
        lines.append("")
    else:
        lines += [('No additional candidates from this recorded filter' if known_context else 'No candidate records supplied')
                  + '; this does not establish complete topic coverage.', '']

    if b["questions"]:
        lines += ["## Question-shaped candidates to review", ""]
        for q in b["questions"]:
            kind = ('Recorded GSC query' if q.get('source_kind') == 'gsc_query' else
                    'Compared-page heading; not verified query data' if q.get('source_kind') == 'compared_heading' else
                    'Source kind unrecorded; query grounding unverified')
            lines.append(f"- **{q['question']}** — {kind}; from {_short(q['source'], 60)}")
        lines += ['', 'Review relevance and existing coverage for the actual audience. Add a concise '
                  'answer only when useful; candidate headings do not establish query demand. '
                  'Citation impact is not measured.', '']

    st = b["structure"]
    length = (b['text_length'] if 'text_length' in b else
              length_observation.comparison(b.get('you'), b.get('competitors', [])))
    lines += ['## Extracted-text length (not a target)', '',
              *length_observation.summary(length), '']
    if 'target_words' in st or 'your_words' in st:
        lines += ['Legacy length-target fields have an unrecorded measurement basis. '
                  'They do not establish a measured word-count requirement. Keep deliberate '
                  'user/editorial length goals separate from these observations.', '']
    lines += ['## Statistics/citation cues (not verified evidence)', '',
              *evidence_observation.summary(b.get('you'), b.get('competitors', [])), '']
    if 'evidence_target' in st or 'your_evidence' in st:
        lines += ['Legacy evidence-target fields have an unrecorded measurement basis. '
                  'They do not establish verified evidence or a required source count. '
                  'Review real claims and sources; do not invent statistics or citations.', '']
    lines += ['## Question-heading cues (contextual review)', '',
              *question_observation.summary(b.get('you'), b.get('competitors', [])), '']
    if st.get('question_headings') is True:
        content = [facts for facts in b.get('competitors', []) if facts.get('page_kind') != 'hub']
        if question_observation.review_difference(b.get('you'), content):
            lines += ['## Structure review (optional)', '',
                      'The exact heading-pattern counts trigger a contextual review heuristic. '
                      'Keep useful descriptive headings; questions are optional when helpful, '
                      'not required to match real queries or AI engines.', '']
        else:
            lines += ['The supplied question-heading flag is unverified for the recorded counts/basis. '
                      'It is not a requirement to rewrite headings or proof of real query demand.', '']

    if b["schema"]:
        lines += ["## Semantic schema candidates (review)", '', schema_appearance.LIMITS, '']
        for s in b["schema"]:
            who = (" (seen on " + ", ".join(_short(w, 30) for w in s["who"]) + ")"
                   if s["who"] else "")
            lines.append(f"- **{s['type']}** — {s['reason']}{who}. Generate it: "
                         f"`narwhal schema {s['type']}`; only add types that "
                         "match the page's real visible content and intended consumer.")
            own = b.get('you')
            expected = 'not_applicable' if own is None else 'not_observed_in_supported_subset'
            if (s.get('existing_markup_status') != expected
                    or own is not None and (not schema_coverage.absence_review(own) or s['type'] in own.get('schema_types', []))):
                lines.append('  Existing own-page markup is unverified; inspect it before adding or duplicating this type.')
            lines += ['  ' + line for line in schema_appearance.lines(s.get('google_search_appearance'), [s['type']])]
        lines.append("")

    leads = [lead for lead in b.get('leads', []) if lead.get('what') not in
             ('Content depth', 'Evidence density (stats/citations)', 'Question-based headings', 'Publish/update date') and not (
                 lead.get('what', '').startswith('Schema types only you have:')
                 and not all(schema_coverage.absence_review(facts) for facts in pages))]
    if leads:
        lines += ["## Keep (where you already lead)", ""]
        for l in leads:
            detail = f" — {l['detail']}" if l["detail"] else ""
            lines.append(f"- 🟢 **{l['what']}**{detail}")
        lines.append("")

    lines += ["_No search volumes are estimated or invented — any queries "
              "above are real Search Console data for your property. Page "
              "gaps are on-page differences from HTML snapshots — useful targets, "
              "not proof of why anyone ranks._"]
    return "\n".join(lines).rstrip() + "\n"


def render_json(b: dict) -> str:
    return json.dumps(b, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    cfg = configlib.load_from_args(argv)
    ap = argparse.ArgumentParser(
        description="Content brief from compared pages, with optional GSC "
                    "queries via --gsc (local-first; no keyword APIs)",
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
    service = ap.add_mutually_exclusive_group()
    service.add_argument("--gsc", action="store_true",
                        help="opt in to Search Console queries for your page (needs OAuth credentials)")
    service.add_argument("--no-gsc", action="store_true",
                    help="skip Search Console (structure-only brief)")
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--min-impressions", type=int, default=50)
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

    b = run(your_url, competitors, topic=args.topic, use_gsc=args.gsc,
            days=args.days, min_impressions=args.min_impressions,
            timeout=args.timeout, allow_private=args.allow_private,
            render=args.render, config=cfg, max_bytes=args.max_bytes)
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
        if not save_output(args.output, out, label='brief'):
            return 2
        print(f"Wrote {args.format} brief to {args.output}")
    else:
        print(out)
    return 0 if not b.get("error") else 2


if __name__ == "__main__":
    raise SystemExit(main())
