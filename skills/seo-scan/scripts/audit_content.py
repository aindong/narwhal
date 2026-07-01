"""Content quality & E-E-A-T auditor.

Approximates the signals Google's Search Quality Rater Guidelines reward:
sufficient main content, readability, evidence of experience/authorship, and
freshness. These are heuristics, not verdicts — they surface pages that read as
thin, anonymous, or hard to parse.
"""

from __future__ import annotations

import re

try:
    from lib import text as textlib
    from lib import content_quality
except ImportError:  # when imported as a package
    from .lib import text as textlib  # type: ignore
    from .lib import content_quality  # type: ignore

CAT = "content"

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]+")
_DATE_HINT = re.compile(
    r"\b(20\d{2})\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}",
    re.I,
)
_AUTHOR_HINT = re.compile(r"\b(by|author|written by|reviewed by)\b", re.I)


def audit(doc, resp, report, ctx=None) -> None:
    text = doc.body_text or ""
    words = _WORD.findall(text)
    wc = len(words)

    th = (ctx or {}).get("thresholds", {})
    _word_count(wc, report, th)
    _readability(text, report)
    _keywords(doc, text, report)
    _quality(text, report)
    _authorship(doc, text, report)
    _freshness(doc, text, report)
    _og_social(doc, report)


def _word_count(wc, report, th=None):
    th = th or {}
    thin, short = th.get("thin_content", 300), th.get("short_content", 600)
    if wc < thin:
        report.add(CAT, "high", "Thin content",
                   f"~{wc} words of main text.",
                   "Expand to cover the topic fully; thin pages struggle to rank "
                   "and are rarely cited by AI answers.")
    elif wc < short:
        report.add(CAT, "low", "Content is on the short side",
                   f"~{wc} words.",
                   "Consider deepening coverage if this is a primary landing page.")
    else:
        report.ok(CAT, "Sufficient content depth", f"~{wc} words")


def _readability(text, report):
    fre = textlib.flesch_reading_ease(text)
    if fre is None:
        return
    grade = textlib.flesch_kincaid_grade(text)
    label = textlib.reading_ease_label(fre)
    detail = f"Flesch reading ease {fre} ({label}); ~grade {grade}"
    if fre < 30:
        report.add(CAT, "medium", "Content is very hard to read",
                   detail + ".",
                   "Shorten sentences and prefer plainer words. Dense prose is "
                   "harder for readers and for AI engines to quote cleanly.")
    elif fre < 50:
        report.add(CAT, "low", "Content is fairly hard to read",
                   detail + ".",
                   "Consider shorter sentences/simpler words unless the audience "
                   "is specialist.")
    else:
        report.ok(CAT, "Readable prose", detail)


def _keywords(doc, text, report):
    keywords = textlib.top_keywords(text, 8)
    if not keywords:
        return
    top_terms = {k for k, _ in keywords}
    summary = ", ".join(f"{k} ({c})" for k, c in keywords[:6])
    bigrams = textlib.top_bigrams(text, 3)
    if bigrams:
        summary += "  ·  phrases: " + ", ".join(k for k, _ in bigrams)
    report.ok(CAT, "Dominant topics detected", summary)

    # Topical focus: do the title/H1 terms show up in the body's top keywords?
    focus_words = set(textlib.words((doc.title or "").lower()))
    h1s = [t for lvl, t in doc.headings if lvl == 1]
    if h1s:
        focus_words |= set(textlib.words(h1s[0].lower()))
    focus_words = {w for w in focus_words if len(w) >= 3
                   and w not in textlib.STOPWORDS}
    if focus_words and not (focus_words & top_terms):
        report.add(CAT, "low", "Body may not reinforce the title topic",
                   "None of the title/H1 keywords appear among the page's most "
                   "frequent body terms.",
                   "Make sure the main content actually develops the topic promised "
                   "by the title and H1 (helps ranking and AI topical grounding).")


def _quality(text, report):
    """Flag filler/padding language, AI-writing patterns, and low diversity."""
    q = content_quality.analyze(text)
    if q["word_count"] < 100:
        return  # too short to judge reliably

    if q["filler_per_100w"] >= 1.0:
        report.add(CAT, "medium", "Filler / padding language",
                   f"{q['filler_count']} filler phrases "
                   f"(~{q['filler_per_100w']} per 100 words).",
                   "Cut hollow phrasing and lead with substance; padding dilutes the "
                   "content for readers and AI extraction.",
                   evidence="; ".join(q["filler_examples"]))
    elif q["filler_count"] >= 2:
        report.add(CAT, "low", "Some filler phrasing",
                   f"{q['filler_count']} filler phrases detected.",
                   "Tighten wording; prefer specifics over padding.",
                   evidence="; ".join(q["filler_examples"]))

    if q["ai_distinct"] >= 4:
        report.add(CAT, "medium", "Reads as AI-generated / generic",
                   f"{q['ai_distinct']} distinct AI-writing patterns "
                   f"({q['ai_pattern_count']} total).",
                   "Rewrite in an original voice with first-hand specifics and "
                   "examples — generic AI-sounding prose is a helpful-content risk.",
                   evidence="; ".join(q["ai_examples"]))
    elif q["ai_distinct"] >= 2:
        report.add(CAT, "low", "Some generic/AI-sounding phrasing",
                   f"{q['ai_distinct']} AI-writing patterns detected.",
                   "Replace cliché phrasing with concrete, experience-backed detail.",
                   evidence="; ".join(q["ai_examples"]))

    if q["word_count"] >= 400 and q["lexical_diversity"] < 0.35:
        report.add(CAT, "low", "Repetitive vocabulary",
                   f"Lexical diversity {q['lexical_diversity']} (unique/total words).",
                   "Vary wording and add substance; heavy repetition signals thin or "
                   "spun content.")
    if (q["filler_per_100w"] < 1.0 and q["ai_distinct"] < 2
            and q["lexical_diversity"] >= 0.35):
        report.ok(CAT, "Clean, specific writing",
                  f"low filler, diverse vocabulary ({q['lexical_diversity']})")


def _authorship(doc, text, report):
    head = text[:1500]
    has_author = bool(_AUTHOR_HINT.search(head)) or bool(
        doc.meta_by_name("author") or doc.meta_by_property("article:author")
    )
    if not has_author:
        report.add(CAT, "medium", "No visible author/byline",
                   "No author meta tag or byline detected near the top.",
                   "Add a named author with credentials — a core E-E-A-T "
                   "(experience/expertise) signal.")
    else:
        report.ok(CAT, "Authorship signal present")


def _freshness(doc, text, report):
    published = (
        doc.meta_by_property("article:published_time")
        or doc.meta_by_name("date")
        or doc.meta_by_property("article:modified_time")
    )
    if not published and not _DATE_HINT.search(text[:2000]):
        report.add(CAT, "low", "No visible date signal",
                   "No published/modified date in metadata or near the top.",
                   "Expose a publish or last-updated date to signal freshness.")
    else:
        report.ok(CAT, "Date/freshness signal present")


def _og_social(doc, report):
    missing = [
        p for p in ("og:title", "og:description", "og:image")
        if not doc.meta_by_property(p)
    ]
    if missing:
        report.add(CAT, "low", "Incomplete Open Graph tags",
                   f"Missing: {', '.join(missing)}.",
                   "Add og:title, og:description and og:image for rich social and "
                   "chat-app link previews.")
    else:
        report.ok(CAT, "Open Graph preview tags complete")
    if not doc.meta_by_name("twitter:card"):
        report.add(CAT, "low", "No Twitter/X card type",
                   "Missing <meta name=\"twitter:card\">.",
                   "Add twitter:card (e.g. summary_large_image) for X previews.")
