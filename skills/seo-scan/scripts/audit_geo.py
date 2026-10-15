"""GEO / LLMO auditor — visibility in AI answers (ChatGPT, Claude, Perplexity,
Google AI Overviews).

Content heuristics and documented search/retrieval robots directives inform
this audit. Training/data-use choices are separate policy observations, not
proof of search visibility or live crawler access.
"""

from __future__ import annotations

import re
import math
from decimal import Decimal
from fractions import Fraction

try:
    from lib.robots import RobotsTxt
    from lib import htmlx
    from lib import jsdiff
    from lib import llms_resource
except ImportError:  # when imported as a package
    from .lib.robots import RobotsTxt  # type: ignore
    from .lib import htmlx  # type: ignore
    from .lib import jsdiff  # type: ignore
    from .lib import llms_resource  # type: ignore

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
    # Editorial pattern counts are not engine/citation measurements. Keep them
    # low priority, including on articles; article classification stays available
    # to callers of the individual helpers for compatibility.
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


def _record_text_cue(report, name, counts):
    """Expose bounded literal observations, not a semantic or engine verdict."""
    receipt = report.meta.setdefault('geo_text_cues', {
        'version': 1, 'basis': 'configured_english_oriented_patterns',
        'interpretation': 'editorial_review_only',
        'limits': 'Not language understanding, paragraph segmentation, source validation, '
                  'answer assessment or measured engine/ranking/citation behavior.',
        'checks': {},
    })
    receipt['checks'][name] = counts


def _bound_receipt(value):
    """Serialize bounds without rounding or changing their comparison behavior."""
    if type(value) is int:
        return value
    if type(value) is float:
        return value if math.isfinite(value) else {'kind': 'nonfinite_float', 'value': str(value)}
    if type(value) is Decimal:
        return {'kind': 'decimal', 'value': str(value)}
    if type(value) is Fraction:
        return {'kind': 'fraction', 'value': str(value)}
    # Other programmatic numeric types may support comparisons. Keep that
    # behavior, but do not serialize the object, call its conversion hooks or
    # imply an exact numeric snapshot that we cannot represent.
    return {'kind': 'unrecorded_numeric_type'}


def _question_headings(doc, report, article=False):
    subs = [t for lvl, t in doc.headings if lvl >= 2 and t]
    q = [t for t in subs if t.lower().split()[:1] and
         t.lower().split()[0] in _QUESTION_WORDS or t.rstrip().endswith("?")]
    _record_text_cue(report, 'question_headings', {
        'matched': len(q), 'examined': len(subs), 'advisory_below_fraction': 0.2,
        'match_rule': 'english_first_token_or_terminal_ascii_question_mark',
    })
    if not subs:
        return
    observed = (f"{len(q)}/{len(subs)} subheadings match configured English starters "
                "or a terminal ASCII question mark.")
    ratio = len(q) / len(subs)
    if ratio < 0.2:
        report.add(CAT, "low", "Few configured question-heading cues",
                   observed + " Question relevance and engine matching are not measured.",
                   observed + " Use descriptive headings suited to the audience; questions "
                   "are optional when useful. Do not rewrite solely to satisfy these "
                   "English-oriented cues; citation impact is not measured.",
                   rule_id="geo.few.question.based.headings")
    else:
        report.add(CAT, "good", "Configured question-heading cues present",
                   observed + " Question relevance and engine matching are not measured.",
                   rule_id="geo.question.based.headings.present")


def _passage_citability(doc, report, th=None):
    """Count synthetic sentence groups in a configured ASCII-word size range.

    This does not segment real paragraphs or measure self-containment/citability.
    The default 40–120 range is a heuristic, not an engine requirement.
    """
    th = th or {}
    lo, hi = th.get("passage_min", 40), th.get("passage_max", 120)
    text = doc.body_text or ""
    chunks = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    # Historical grouping algorithm, not actual paragraph segmentation.
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
    citable = [p for p in passages if lo <= p <= hi]
    _record_text_cue(report, 'sentence_groups', {
        'in_range': len(citable), 'examined': len(passages),
        'word_min': _bound_receipt(lo), 'word_max': _bound_receipt(hi),
        'advisory_below_fraction': 0.3,
        'match_rule': 'ascii_word_counts_in_accumulated_sentence_fragments',
    })
    if not passages:
        return
    observed = (f"{len(citable)}/{len(passages)} synthetic sentence groups contain "
                f"{lo}–{hi} counted ASCII-word matches.")
    ratio = len(citable) / len(passages)
    if ratio < 0.3:
        report.add(CAT, "low", "Few sentence groups in the configured word range",
                   observed + " Actual paragraphs, self-containment and engine citability are not measured.",
                   observed + " Review readability and completeness in context. This configured "
                   "range is not an engine requirement; do not pad or split useful text "
                   "just to match it. Citation impact is not measured.",
                   rule_id="geo.few.self.contained.citable.passages")
    else:
        report.add(CAT, "good", "Sentence groups in the configured word range",
                   observed + " Actual paragraphs, self-containment and engine citability are not measured.",
                   rule_id="geo.citable.passage.structure")


def _evidence_density(doc, report, article=False):
    text = doc.body_text or ""
    stats = len(_STAT.findall(text))
    cites = len(_CITE_HINT.findall(text))
    _record_text_cue(report, 'evidence_cues', {
        'statistic_matches': stats, 'citation_cue_matches': cites,
        'source_validity_checked': False,
    })
    observed = f"{stats} configured statistic-pattern matches; {cites} citation-cue matches."
    if stats + cites == 0:
        report.add(CAT, "low", "No configured statistics/citation cues",
                   observed + " Other numbers, links or references may exist; source validity is not checked.",
                   observed + " Review factual claims and relevant primary sources in context. "
                   "Do not invent statistics or citations to satisfy this check. Cue absence "
                   "does not prove missing evidence; citation impact is not measured.",
                   rule_id="geo.no.statistics.or.citations")
    else:
        report.add(CAT, "good", "Configured statistics/citation cues present",
                   observed + " Lexical cues only; factual support and source validity are not checked.",
                   rule_id="geo.evidence.signals.present")


def _direct_answer(doc, report):
    """Observe English lexical cues in the first 80 whitespace-separated tokens."""
    text = doc.body_text or ""
    tokens = text.split()[:80]
    intro = " ".join(tokens)
    matched = bool(re.search(r"\b(is|are|means|refers to|allows|helps|provides)\b", intro, re.I))
    _record_text_cue(report, 'intro_cues', {
        'inspected_tokens': len(tokens), 'token_limit': 80, 'matched': matched,
        'match_rule': 'configured_english_answer_terms',
    })
    if not intro:
        return
    if not matched:
        report.add(CAT, "low", "No configured introductory answer cues",
                   "No configured English answer term matched in the first 80 whitespace-separated tokens. "
                   "This does not establish whether the opening answers a question.",
                   "Review whether the opening serves the reader's intent and language. "
                   "Add a concise answer only when useful; English cue absence does not "
                   "prove a missing answer. Answer accuracy and citation impact are not measured.",
                   rule_id="geo.no.direct.answer.up.top")
    else:
        report.add(CAT, "good", "Configured introductory answer cue present",
                   "A configured English term matched in the first 80 whitespace-separated tokens. "
                   "Answer directness, accuracy and citation impact are not measured.",
                   rule_id="geo.direct.answer.near.the.top")


def _llms_txt(ctx, report):
    supplied = ctx.get('llms_txt_receipt')
    receipt = llms_resource.recorded(supplied)
    if receipt is None:
        receipt = {'version': 1, 'checked_path': '/llms.txt', 'state': 'unverified',
                   'basis': 'legacy_context' if type(ctx.get('llms_txt')) is bool and supplied is None else 'not_recorded'}
        if receipt['basis'] == 'legacy_context':
            receipt['reported_present'] = ctx['llms_txt']
    report.meta['llms_txt'] = dict(receipt)
    legacy = receipt['basis'] == 'legacy_context'
    if receipt['state'] == 'observed' or (legacy and receipt['reported_present']):
        report.add(CAT, 'good', 'Root llms.txt text candidate observed' if not legacy else 'llms.txt presence reported (legacy context)',
                   llms_resource.note(report.meta), rule_id='geo.llms.txt.published', scope='site')
    elif receipt['state'] == 'absent' or (legacy and not receipt['reported_present']):
        report.add(CAT, 'low', 'No root llms.txt observed' if not legacy else 'No root llms.txt recorded (legacy context)',
                   llms_resource.note(report.meta),
                   'Optionally publish a curated llms.txt if useful; this is not a required ranking or access control.',
                   rule_id='geo.no.llms.txt', scope='site')


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
