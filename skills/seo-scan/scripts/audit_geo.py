"""GEO / LLMO auditor — visibility in AI answers (ChatGPT, Claude, Perplexity,
Google AI Overviews).

Content heuristics and documented search/retrieval robots directives inform
this audit. Training/data-use choices are separate policy observations, not
proof of search visibility or live crawler access.
"""

from __future__ import annotations

import re

try:
    from lib.robots import RobotsTxt
    from lib import htmlx
    from lib import jsdiff
except ImportError:  # when imported as a package
    from .lib.robots import RobotsTxt  # type: ignore
    from .lib import htmlx  # type: ignore
    from .lib import jsdiff  # type: ignore

CAT = "geo"

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]+")
_QUESTION_WORDS = ("how", "what", "why", "when", "where", "who", "which", "can",
                   "does", "is", "are", "should", "do")
_STAT = re.compile(r"\b\d+([.,]\d+)?\s?(%|percent|million|billion|k\b|x\b)", re.I)
_CITE_HINT = re.compile(r"\b(according to|source:|study|research|report|data from|"
                        r"survey|cited|\[\d+\])\b", re.I)

# Static, primary-source role guidance, checked 2026-10-15. No runtime policy I/O.
_OPENAI_BOTS = "https://developers.openai.com/api/docs/bots"
_CLAUDE_BOTS = ("https://support.claude.com/en/articles/8896518-"
                "does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler")
_PERPLEXITY_BOTS = "https://docs.perplexity.ai/docs/resources/perplexity-crawlers"
_GOOGLE_BOTS = "https://developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers#google-extended"
_GOOGLE_SEARCH = "https://developers.google.com/search/docs/appearance/ai-features#controlling-your-content-in-ai-features-in-search"

# agent, role, purpose, source, interpretation for non-scored restrictions.
_CRAWLER_POLICIES = (
    ("OAI-SearchBot", "search_retrieval", "ChatGPT Search", _OPENAI_BOTS, ""),
    ("Claude-SearchBot", "search_retrieval", "Claude search", _CLAUDE_BOTS, ""),
    ("Claude-User", "search_retrieval", "Claude user-directed retrieval", _CLAUDE_BOTS, ""),
    ("PerplexityBot", "search_retrieval", "Perplexity search", _PERPLEXITY_BOTS, ""),
    ("Googlebot", "search_retrieval", "Google Search, including AI features", _GOOGLE_SEARCH, ""),
    ("GPTBot", "training", "OpenAI training collection", _OPENAI_BOTS,
     "Training collection opt-out; independent of ChatGPT Search access."),
    ("ClaudeBot", "training", "Anthropic training collection", _CLAUDE_BOTS,
     "Training collection opt-out; distinct from Claude search and user-directed retrieval."),
    ("Google-Extended", "data_use", "Gemini training and grounding", _GOOGLE_BOTS,
     "Controls training and specified Gemini/Vertex grounding uses, not Google Search or AI Overviews access."),
    ("CCBot", "data_collection", "Common Crawl dataset", "https://commoncrawl.org/ccbot",
     "Dataset collection restriction; this alone does not establish a direct search-access failure."),
    ("ChatGPT-User", "user_triggered", "ChatGPT user-triggered fetches", _OPENAI_BOTS,
     "A user-triggered directive does not prove a fetch is blocked; robots.txt may not apply. Not a Search opt-out control."),
    ("Perplexity-User", "user_triggered", "Perplexity user-triggered fetches", _PERPLEXITY_BOTS,
     "A user-triggered directive does not prove a fetch is blocked; this fetcher generally ignores robots.txt."),
    ("Claude-Web", "unverified", "Legacy or unverified token", None,
     "Current role is unverified; a matching directive does not establish a search impact."),
    ("Bytespider", "unverified", "Unverified role", None,
     "Current role is unverified; a matching directive does not establish a search impact."),
)
AI_BOTS = {agent: purpose for agent, role, purpose, source, note in _CRAWLER_POLICIES}


def audit(doc, resp, report, ctx=None) -> None:
    ctx = ctx or {}
    # Question-heading and evidence advice is *article* advice. On homepages,
    # hubs, and product pages these checks fired on ~90% of real sites — a check
    # that flags everyone ranks nothing. Article pages keep the stronger severity.
    article = htmlx.looks_article(doc)
    _question_headings(doc, report, article=article)
    _passage_citability(doc, report, ctx.get("thresholds", {}))
    _evidence_density(doc, report, article=article)
    _direct_answer(doc, report)
    _llms_txt(ctx, report)
    _ai_crawler_access(ctx, report)
    _entity_clarity(doc, report)
    if ctx.get("jsdep"):   # only present when a --render scan measured it
        jsdiff.geo_finding(ctx["jsdep"], report)


def _question_headings(doc, report, article=False):
    subs = [t for lvl, t in doc.headings if lvl >= 2 and t]
    if not subs:
        return
    q = [t for t in subs if t.lower().split()[:1] and
         t.lower().split()[0] in _QUESTION_WORDS or t.rstrip().endswith("?")]
    ratio = len(q) / len(subs)
    if ratio < 0.2:
        report.add(CAT, "medium" if article else "low",
                   "Few question-based headings",
                   f"{len(q)} of {len(subs)} subheadings are phrased as questions.",
                   "Rewrite key H2/H3s as the questions users actually ask — AI "
                   "engines match answers to question-shaped headings."
                   + ("" if article else " (Most useful on article/guide pages; "
                      "lower priority here.)"))
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


def _evidence_density(doc, report, article=False):
    text = doc.body_text or ""
    stats = len(_STAT.findall(text))
    cites = len(_CITE_HINT.findall(text))
    if stats + cites == 0:
        report.add(CAT, "medium" if article else "low",
                   "No statistics or citations",
                   "No numbers, data points, or source references detected.",
                   "Add concrete stats and cite primary sources — AI answers "
                   "favor and attribute evidence-backed content."
                   + ("" if article else " (Weighs most on article/guide pages.)"))
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
    """Classify root directives by documented purpose, not live bot reachability."""
    robots = ctx.get("robots_txt")
    if robots is None:
        return
    rt = RobotsTxt.parse(robots)
    agents, notes = [], []
    for agent, role, purpose, source, note in _CRAWLER_POLICIES:
        disallowed = rt.disallowed("/", agent)
        agents.append({"agent": agent, "role": role, "purpose": purpose,
                       "source": source, "disallowed": disallowed})
        if disallowed and role != "search_retrieval":
            notes.append({"agent": agent, "text": note, "source": source})
    report.meta["ai_crawler_access"] = {
        "version": 1, "policy_checked": "2026-10-15", "checked_path": "/",
        "basis": "robots_txt_only", "agents": agents, "notes": notes,
    }
    blocked = [row["agent"] for row in agents
               if row["role"] == "search_retrieval" and row["disallowed"]]
    if blocked:
        names = ", ".join(f"{b} ({AI_BOTS[b]})" for b in blocked)
        report.add(CAT, "high", "AI crawlers are blocked in robots.txt",
                   f"robots.txt disallows / for these search/retrieval agents: {names}. "
                   "Only the site root was checked; live access, other paths, indexing and citations are not verified.",
                   "If these search or user-retrieval channels match your goals, review their / directives "
                   "and infrastructure access. Keep deliberate restrictions; do not enable training bots "
                   "as a search fix.", evidence=names, scope="site")
    else:
        report.add(CAT, "good", "Search/retrieval agents are not disallowed at site root",
                   "robots.txt only; live access, other paths, indexing and citations are not verified.",
                   scope="site")


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
