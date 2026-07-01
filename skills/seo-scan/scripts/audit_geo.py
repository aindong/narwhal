"""GEO / LLMO auditor — visibility in AI answers (ChatGPT, Claude, Perplexity,
Google AI Overviews).

AI answer engines lift self-contained passages, prefer question-shaped headings,
reward clear entities and citable evidence, and — critically — can only quote a
page their crawler is allowed to fetch. This auditor scores those signals.
"""

from __future__ import annotations

import re

try:
    from lib.robots import RobotsTxt
except ImportError:  # when imported as a package
    from .lib.robots import RobotsTxt  # type: ignore

CAT = "geo"

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]+")
_QUESTION_WORDS = ("how", "what", "why", "when", "where", "who", "which", "can",
                   "does", "is", "are", "should", "do")
_STAT = re.compile(r"\b\d+([.,]\d+)?\s?(%|percent|million|billion|k\b|x\b)", re.I)
_CITE_HINT = re.compile(r"\b(according to|source:|study|research|report|data from|"
                        r"survey|cited|\[\d+\])\b", re.I)

# AI crawler user-agents worth checking in robots.txt.
AI_BOTS = {
    "GPTBot": "OpenAI (ChatGPT training/browse)",
    "OAI-SearchBot": "OpenAI (ChatGPT search)",
    "ChatGPT-User": "OpenAI (ChatGPT on-demand fetch)",
    "ClaudeBot": "Anthropic (Claude)",
    "Claude-Web": "Anthropic (Claude on-demand)",
    "PerplexityBot": "Perplexity",
    "Google-Extended": "Google (Gemini / AI Overviews training)",
    "CCBot": "Common Crawl (feeds many LLMs)",
    "Bytespider": "ByteDance",
}


def audit(doc, resp, report, ctx=None) -> None:
    ctx = ctx or {}
    _question_headings(doc, report)
    _passage_citability(doc, report, ctx.get("thresholds", {}))
    _evidence_density(doc, report)
    _direct_answer(doc, report)
    _llms_txt(ctx, report)
    _ai_crawler_access(ctx, report)
    _entity_clarity(doc, report)


def _question_headings(doc, report):
    subs = [t for lvl, t in doc.headings if lvl >= 2 and t]
    if not subs:
        return
    q = [t for t in subs if t.lower().split()[:1] and
         t.lower().split()[0] in _QUESTION_WORDS or t.rstrip().endswith("?")]
    ratio = len(q) / len(subs)
    if ratio < 0.2:
        report.add(CAT, "medium", "Few question-based headings",
                   f"{len(q)} of {len(subs)} subheadings are phrased as questions.",
                   "Rewrite key H2/H3s as the questions users actually ask — AI "
                   "engines match answers to question-shaped headings.")
    else:
        report.ok(CAT, "Question-based headings present",
                  f"{len(q)}/{len(subs)} subheadings")


def _passage_citability(doc, report, th=None):
    """AI engines quote self-contained passages best when they're ~40–120 words.

    We approximate passages by splitting visible text on sentence groups. Very
    long unbroken blocks are hard to lift cleanly; a page of only tiny fragments
    lacks quotable substance.
    """
    th = th or {}
    lo, hi = th.get("passage_min", 40), th.get("passage_max", 120)
    text = doc.body_text or ""
    chunks = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    # group sentences into ~paragraph-sized passages
    passages, buf, count = [], [], 0
    for s in chunks:
        w = len(_WORD.findall(s))
        buf.append(s)
        count += w
        if count >= lo:
            passages.append(count)
            buf, count = [], 0
    if buf and count:
        passages.append(count)
    if not passages:
        return
    citable = [p for p in passages if lo <= p <= hi]
    ratio = len(citable) / len(passages)
    if ratio < 0.3:
        report.add(CAT, "medium", "Few self-contained, citable passages",
                   f"Most passages are outside the ~{lo}–{hi} word range that AI "
                   "engines quote cleanly.",
                   "Structure answers as standalone paragraphs that make sense "
                   "without surrounding context.")
    else:
        report.ok(CAT, "Citable passage structure",
                  f"{len(citable)}/{len(passages)} passages in range")


def _evidence_density(doc, report):
    text = doc.body_text or ""
    stats = len(_STAT.findall(text))
    cites = len(_CITE_HINT.findall(text))
    if stats + cites == 0:
        report.add(CAT, "medium", "No statistics or citations",
                   "No numbers, data points, or source references detected.",
                   "Add concrete stats and cite primary sources — AI answers "
                   "favor and attribute evidence-backed content.")
    else:
        report.ok(CAT, "Evidence signals present",
                  f"{stats} stats, {cites} citation cues")


def _direct_answer(doc, report):
    """Reward a concise answer near the top (the 'inverted pyramid')."""
    text = doc.body_text or ""
    intro = " ".join(text.split()[:80])
    if not intro:
        return
    # A definitional/answer intro tends to contain 'is/are/means' early.
    if not re.search(r"\b(is|are|means|refers to|allows|helps|provides)\b", intro, re.I):
        report.add(CAT, "low", "No direct answer up top",
                   "The opening doesn't state a concise answer/definition.",
                   "Lead with a 1–2 sentence direct answer before the details; "
                   "AI overviews lift the top summary.")
    else:
        report.ok(CAT, "Direct answer near the top")


def _llms_txt(ctx, report):
    if ctx.get("llms_txt"):
        report.ok(CAT, "llms.txt published", ctx.get("llms_txt_url", ""))
    else:
        report.add(CAT, "low", "No llms.txt",
                   "No /llms.txt found.",
                   "Optionally publish /llms.txt to guide AI crawlers to your key "
                   "content. Evidence for ranking impact is still thin — treat as "
                   "low-cost, low-certainty.")


def _ai_crawler_access(ctx, report):
    robots = ctx.get("robots_txt")
    if robots is None:
        return
    rt = RobotsTxt.parse(robots)
    # A bot is effectively blocked when it can't fetch the site root.
    blocked = [b for b in AI_BOTS if rt.disallowed("/", b)]
    if blocked:
        names = ", ".join(f"{b} ({AI_BOTS[b]})" for b in blocked)
        report.add(CAT, "high", "AI crawlers are blocked in robots.txt",
                   f"Disallowed from the site root: {names}.",
                   "If you want visibility in AI answers, allow these agents. If "
                   "the block is intentional (content protection), ignore this.",
                   evidence=names)
    else:
        report.ok(CAT, "AI crawlers are not blocked")


def _entity_clarity(doc, report):
    """A clear subject entity helps AI ground the page. Approximate by checking
    the H1/title share a consistent noun phrase and the page names an org."""
    title = (doc.title or "").lower()
    h1s = [t.lower() for lvl, t in doc.headings if lvl == 1]
    if title and h1s:
        t_words = set(_WORD.findall(title))
        h_words = set(_WORD.findall(h1s[0]))
        if t_words and not (t_words & h_words):
            report.add(CAT, "low", "Title and H1 don't share terms",
                       "The <title> and <h1> have no words in common.",
                       "Align them on the core entity so engines get one clear "
                       "topic signal.")
