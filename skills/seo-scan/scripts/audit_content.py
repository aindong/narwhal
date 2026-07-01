"""Content quality & E-E-A-T auditor.

Approximates the signals Google's Search Quality Rater Guidelines reward:
sufficient main content, readability, evidence of experience/authorship, and
freshness. These are heuristics, not verdicts — they surface pages that read as
thin, anonymous, or hard to parse.
"""

from __future__ import annotations

import re

CAT = "content"

_SENTENCE = re.compile(r"[.!?]+")
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
    _readability(text, words, report)
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


def _readability(text, words, report):
    sentences = [s for s in _SENTENCE.split(text) if s.strip()]
    if not sentences or not words:
        return
    avg = len(words) / len(sentences)
    if avg > 25:
        report.add(CAT, "low", "Long average sentence length",
                   f"~{avg:.0f} words per sentence.",
                   "Break up long sentences; short, scannable prose is easier to "
                   "quote and rank.")
    else:
        report.ok(CAT, "Readable sentence length", f"~{avg:.0f} words/sentence")


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
