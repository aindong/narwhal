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
except ImportError:  # when imported as a package
    from .lib import text as textlib  # type: ignore

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

    _word_count(wc, report)
    _readability(text, report)
    _keywords(doc, text, report)
    _authorship(doc, text, report)
    _freshness(doc, text, report)
    _og_social(doc, report)


def _word_count(wc, report):
    if wc < 300:
        report.add(CAT, "high", "Thin content",
                   f"~{wc} words of main text.",
                   "Expand to cover the topic fully; thin pages struggle to rank "
                   "and are rarely cited by AI answers.")
    elif wc < 600:
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
