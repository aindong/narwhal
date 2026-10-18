"""Content quality & E-E-A-T auditor.

Observes extracted-text counts, English-oriented readability/style patterns,
attribution/date candidates and social metadata. These are scoped heuristics,
not measurements of content depth, expertise, quality or search outcomes.
"""

from __future__ import annotations

try:
    from lib import text as textlib
    from lib import content_quality
    from lib import htmlx
    from lib import authorship
    from lib import content_length
    from lib import date_cues
    from lib import readability_observation
    from lib import lexical_focus
except ImportError:  # when imported as a package
    from .lib import text as textlib  # type: ignore
    from .lib import content_quality  # type: ignore
    from .lib import htmlx  # type: ignore
    from .lib import authorship  # type: ignore
    from .lib import content_length  # type: ignore
    from .lib import date_cues  # type: ignore
    from .lib import readability_observation  # type: ignore
    from .lib import lexical_focus  # type: ignore

CAT = "content"

_WORD = content_length.WORD_PATTERN  # historical private matcher alias


def audit(doc, resp, report, ctx=None) -> None:
    text = doc.body_text or ""

    # Page-type awareness: prose checks misfire on link-hub pages (index,
    # category, front pages), and byline checks misfire on non-articles.
    hub = htmlx.is_hub_page(doc)
    article = htmlx.looks_article(doc)
    # Flesch and the filler/common-phrase lists are English-calibrated. Running
    # them on a declared non-English page measures nothing real — skip them
    # (and claim nothing) rather than mislabel French prose "hard to read".
    english = not doc.lang or doc.lang.strip().lower().startswith("en")

    th = (ctx or {}).get("thresholds", {})
    receipt = content_length.observe(text, language=doc.lang, basis=doc.extraction, thresholds=th)
    report.meta['content_length'] = receipt
    _word_count(receipt, report, hub=hub)
    _readability(text, report, hub=hub, article=article, language=doc.lang, basis=doc.extraction)
    if english:
        _quality(text, report)
    _keywords(doc, text, report)
    _authorship(doc, text, report, article=article)
    _freshness(doc, text, report)
    _og_social(doc, report)


def _word_count(receipt, report, hub=False):
    """Keep length cues contextual; a count cannot certify thinness or depth."""
    status = receipt['threshold_status']
    if status == 'uninterpreted':
        return  # no false zero-word defect or passing depth claim
    observed = (f"{receipt['ascii_pattern_matches']} matches of the configured ASCII-only pattern "
                f"in selected extracted text ({receipt['source_basis']}). ")
    advice = ('Review whether the captured text serves the reader and page intent. Keep useful '
              'concise text; edit only confirmed coverage gaps. Do not pad content to reach '
              'a configured count. Ranking and citation impact are not measured.')
    if status == 'below_lower':
        detail = observed + 'Below the configured lower bound. ' + content_length.LIMITS
        if hub:
            report.add(CAT, 'low', 'Review limited ASCII-token count on a hub', detail,
                       advice, rule_id='content.link.hub.page.with.little.prose')
        else:
            report.add(CAT, 'low', 'Review limited ASCII-token count', detail,
                       advice, rule_id='content.thin.content')
    elif status == 'below_upper':
        report.add(CAT, 'low', 'Review ASCII-token count in the configured middle range',
                   observed + content_length.LIMITS, advice,
                   rule_id='content.content.is.on.the.short.side')
    else:
        report.add(CAT, 'good', 'No below-range ASCII-token flag',
                   observed + content_length.LIMITS, rule_id='content.sufficient.content.depth')


def _readability(text, report, hub=False, article=False, *, language='', basis='visible text'):
    receipt = readability_observation.observe(text, language=language, basis=basis, hub=hub)
    report.meta['readability'] = receipt
    if receipt['formula_status'] != 'computed':
        return
    fre, grade = receipt['flesch_reading_ease'], receipt['flesch_kincaid_grade']
    detail = (f'Flesch reading ease estimate {fre}; FK grade formula estimate {grade}. '
              + readability_observation.LIMITS)
    advice = ('Review actual audience, language and the captured prose in context. Simplify only where useful; '
              'preserve necessary technical terms, factual precision and useful concise text. Do not pad or '
              'rewrite solely to reach a formula target. Reader comprehension and engine outcomes are unmeasured.')
    if fre < 30:
        report.add(CAT, 'low', 'Review below-30 readability formula estimate', detail, advice,
                   rule_id='content.content.is.very.hard.to.read')
    elif fre < 50:
        report.add(CAT, 'low', 'Review below-50 readability formula estimate', detail, advice,
                   rule_id='content.content.is.fairly.hard.to.read')
    else:
        report.add(CAT, 'good', 'No below-range readability formula flag', detail,
                   rule_id='content.readable.prose')


def _keywords(doc, text, report):
    receipt = lexical_focus.observe(doc, text)
    report.meta['lexical_focus'] = receipt
    keywords = receipt['body_terms']
    if not keywords:
        return
    display = lambda item: item['term'] + (' [clipped]' if item['clipped'] else '') + f" ({item['count']})"
    summary = ', '.join(display(item) for item in keywords[:6])
    bigrams = receipt['phrases']
    if bigrams:
        summary += '  ·  phrases: ' + ', '.join(item['term'] + (' [clipped]' if item['clipped'] else '') for item in bigrams)
    report.add(CAT, 'good', 'Frequent extracted-text terms observed', summary + '. ' + lexical_focus.LIMITS,
               rule_id='content.dominant.topics.detected')
    if receipt['status'] == 'zero_overlap':
        report.add(CAT, 'low', 'Review literal title/H1 term overlap',
                   f"0 exact shared title/first-H1 terms among {len(keywords)} retained frequent body terms. " + lexical_focus.LIMITS,
                   'Review actual page purpose and wording in context, including synonyms and extraction. '
                   'Edit only confirmed misleading labels or missing useful content; keep accurate wording. '
                   'Do not repeat keywords or rewrite solely to force overlap with the top-8 list. '
                   'Ranking and AI-citation effects are unmeasured.',
                   evidence=lexical_focus.witnesses(receipt),
                   rule_id='content.body.may.not.reinforce.the.title.topic')


def _quality(text, report):
    """Surface phrase matches for editorial review, not authorship detection."""
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

    # Keep examples/limits in advice too: legacy/third-party compact renderers
    # may omit the reported detail and evidence previews.
    phrase_advice = (f"Example matches: {'; '.join(q['ai_examples'])}. Review in context. "
                     "Edit only if wording is vague or unnecessary for the intended "
                     "audience; keep useful wording. Matches do not determine "
                     "authorship, originality, helpfulness or ranking impact.")
    if q["ai_distinct"] >= 4:
        report.add(CAT, "low", "Common phrases worth reviewing",
                   f"{q['ai_distinct']} distinct configured phrase matches "
                   f"({q['ai_pattern_count']} total). Phrase matches do not determine "
                   "authorship, originality, helpfulness or ranking impact.",
                   phrase_advice,
                   evidence="; ".join(q["ai_examples"]),
                   rule_id="content.reads.as.ai.generated.generic")
    elif q["ai_distinct"] >= 2:
        report.add(CAT, "low", "Some common phrases worth reviewing",
                   f"{q['ai_distinct']} distinct configured phrase matches "
                   f"({q['ai_pattern_count']} total). Phrase matches do not determine "
                   "authorship, originality, helpfulness or ranking impact.",
                   phrase_advice,
                   evidence="; ".join(q["ai_examples"]),
                   rule_id="content.some.generic.ai.sounding.phrasing")

    if q["word_count"] >= 400 and q["lexical_diversity"] < 0.35:
        report.add(CAT, "low", "Repetitive vocabulary",
                   f"Lexical diversity {q['lexical_diversity']} (unique/total words).",
                   "Vary wording and add substance; heavy repetition signals thin or "
                   "spun content.")
    if (q["filler_per_100w"] < 1.0 and q["ai_distinct"] < 2
            and q["lexical_diversity"] >= 0.35):
        report.add(CAT, "good", "Few configured style-pattern matches",
                   f"{q['filler_count']} filler matches; {q['ai_distinct']} distinct "
                   f"common-phrase matches; lexical diversity {q['lexical_diversity']}. "
                   "This does not establish authorship, originality or content quality.",
                   rule_id="content.clean.specific.writing")


def _authorship(doc, text, report, article=False):
    receipt = authorship.observe(doc, text)
    receipt['article_hint'] = bool(article)
    report.meta['authorship_cues'] = receipt
    if receipt['candidates']:
        report.add(CAT, 'good', 'Attribution cue candidate observed',
                   f"{len(receipt['candidates'])} captured metadata/link/byline candidate(s). "
                   + authorship.LIMITS_NOTE,
                   rule_id='content.authorship.signal.present')
    elif article:
        report.add(CAT, 'low', 'Review article attribution cues',
                   'No attribution candidate was observed in the bounded metadata, author-link '
                   'and leading source-block checks. This does not prove anonymity.',
                   'Review the real byline, profile links and editorial ownership in context. '
                   'Identify actual creators/reviewers where appropriate; do not invent people '
                   'or credentials. Missing cues do not establish anonymity or poor quality.',
                   rule_id='content.no.visible.author.byline')
    # Homepages, hubs, and product pages don't carry bylines — flagging them
    # there was noise, so non-article pages are simply not judged on this.


def _freshness(doc, text, report):
    receipt = date_cues.observe(doc, text)
    report.meta['date_cues'] = receipt
    if receipt['candidates']:
        report.add(CAT, 'good', 'Date-related candidate observed',
                   f"{receipt['candidate_count']} captured metadata/text candidate(s). " + date_cues.LIMITS,
                   rule_id='content.date.freshness.signal.present')
    elif htmlx.looks_article(doc):
        report.add(CAT, 'low', 'Review article date cues',
                   'No candidate observed in the checked metadata and selected-text prefix. ' + date_cues.LIMITS,
                   'Review actual page purpose and original date evidence. Add accurate publication/update '
                   'information only when useful and known; do not invent dates, relabel events as publication '
                   'or refresh a date without substantive change. Ranking/citation effects are not measured.',
                   rule_id='content.no.visible.date.signal')


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
