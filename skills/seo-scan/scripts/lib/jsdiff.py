"""Observe paired served/rendered snapshots without certifying JS causation.

Counts compare selected extracted text, not the share of content requiring JS.
Separate responses, extraction choices and page state can differ. Computation
is offline and does not measure crawler behavior, visibility or indexability.
"""

from __future__ import annotations

from . import htmlx

# Historical positive net-count bands, not measured shares of JS-only content.
PCT_HIGH = 30
PCT_MEDIUM = 10
TEXT_LIMITS = (
    'Selected extracted text only, not full-page content or rendered visibility. '
    'Net token-count change is not a share of JS-only content or proof of JavaScript causation, '
    'server rendering, crawler access, indexing or citation impact. Separate responses/page state '
    'and extraction can differ; equal counts do not establish equal text.'
)
TEXT_REVIEW = (
    'Inspect the paired original HTML/DOM, extraction scope and intended page state. '
    'Verify whether essential content is unavailable in the intended served response before '
    'proposing SSR/prerendering; preserve useful client behavior. Do not rewrite source or '
    'claim crawler/ranking/citation effects from counts alone.'
)


def analyze(raw_html: str, rendered_html: str, base_url: str = "") -> dict:
    """Compare served HTML against the rendered DOM. Returns the delta facts."""
    raw = htmlx.parse(raw_html or "", base_url=base_url)
    ren = htmlx.parse(rendered_html or "", base_url=base_url)

    raw_words = len((raw.body_text or "").split())
    ren_words = len((ren.body_text or "").split())
    js_pct = 0
    if ren_words > raw_words and ren_words > 0:
        js_pct = round(100 * (ren_words - raw_words) / ren_words)

    raw_heads = {(lvl, t) for lvl, t in raw.headings if t}
    js_headings = [t for lvl, t in ren.headings if t and (lvl, t) not in raw_heads]

    meta_js_only = {
        "title": bool(ren.title) and not raw.title,
        "description": bool(ren.meta_by_name("description"))
                       and not raw.meta_by_name("description"),
        "canonical": bool(ren.canonical()) and not raw.canonical(),
        "jsonld": len(ren.scripts_ld) > len(raw.scripts_ld),
    }
    return {
        "words_raw": raw_words,
        "words_rendered": ren_words,
        "js_only_pct": js_pct,
        "js_only_headings": js_headings[:10],
        "js_only_heading_count": len(js_headings),
        "meta_js_only": meta_js_only,
        'text_comparison': {
            'version': 1, 'basis': 'selected_extracted_text_pair', 'unit': 'whitespace_tokens',
            'served_extraction': raw.extraction, 'rendered_extraction': ren.extraction,
            'served_tokens': raw_words, 'rendered_tokens': ren_words,
            'net_token_delta': ren_words - raw_words,
            'positive_net_increase_percent': js_pct,
            'selected_text_equal': (raw.body_text or '') == (ren.body_text or ''),
            'limits': TEXT_LIMITS,
        },
    }


def text_observation(dep):
    """Accept only coherent supported receipts; legacy counts are not parity proof."""
    if not isinstance(dep, dict):
        return None
    obs = dep.get('text_comparison')
    if not isinstance(obs, dict) or type(obs.get('version')) is not int or obs['version'] != 1:
        return None
    if obs.get('basis') != 'selected_extracted_text_pair' or obs.get('unit') != 'whitespace_tokens':
        return None
    for key in ('served_extraction', 'rendered_extraction'):
        if type(obs.get(key)) is not str or not obs[key].strip() or len(obs[key]) > 160:
            return None
    for key in ('served_tokens', 'rendered_tokens', 'positive_net_increase_percent'):
        if type(obs.get(key)) is not int or not 0 <= obs[key] <= 2 ** 53 - 1:
            return None
    raw, rendered = obs['served_tokens'], obs['rendered_tokens']
    pct = round(100 * (rendered - raw) / rendered) if rendered > raw else 0
    if (type(obs.get('net_token_delta')) is not int or obs['net_token_delta'] != rendered - raw
            or obs['positive_net_increase_percent'] != pct
            or type(obs.get('selected_text_equal')) is not bool
            or (obs['selected_text_equal'] and raw != rendered)):
        return None
    for key, value in (('words_raw', raw), ('words_rendered', rendered), ('js_only_pct', pct)):
        if type(dep.get(key)) is not int or dep[key] != value:
            return None
    return obs


def _text_detail(obs):
    if not obs['served_tokens'] and not obs['rendered_tokens']:
        state = 'No selected text was observed in either snapshot. '
    elif obs['selected_text_equal']:
        state = 'Selected extracted text matches in this pair. '
    else:
        state = 'Selected extracted text differs in this pair. '
    return (f"{obs['served_tokens']} served vs {obs['rendered_tokens']} rendered whitespace tokens; "
            f"net change {obs['net_token_delta']:+d}; positive net increase / rendered count "
            f"{obs['positive_net_increase_percent']}%. "
            + state + TEXT_LIMITS)


def technical_findings(dep: dict, report) -> None:
    """Report scoped differences, including equal-count replacements, for review."""
    cat = "technical"
    obs = text_observation(dep)
    if obs is None:
        report.add(cat, 'low', 'Rendered-text comparison needs verification',
                   'A supported coherent text-pair receipt was not recorded. Legacy counts/labels '
                   'do not establish content parity, JS-only content or server rendering.',
                   TEXT_REVIEW, rule_id='technical.rendered.text.comparison.unverified')
    elif not obs['selected_text_equal']:
        pct = obs['positive_net_increase_percent']
        if pct >= PCT_HIGH:
            title, rule = 'Review large rendered-text count increase', 'technical.most.content.requires.javascript'
        elif pct >= PCT_MEDIUM:
            title, rule = 'Review rendered-text count increase', 'technical.significant.content.requires.javascript'
        else:
            title, rule = 'Review served/rendered text difference', 'technical.rendered.text.changed'
        report.add(cat, 'low', title, _text_detail(obs), TEXT_REVIEW, rule_id=rule)
    elif not obs['served_tokens']:
        report.add(cat, 'low', 'No selected text observed in either snapshot', _text_detail(obs),
                   TEXT_REVIEW, rule_id='technical.rendered.text.unobserved')
    else:
        report.add(cat, 'good', 'Selected extracted text matches in paired snapshots',
                   _text_detail(obs), rule_id='technical.content.is.server.rendered')

    m = dep.get('meta_js_only')
    m = m if isinstance(m, dict) else {}
    js_meta = [name for name, only in
               (("title", m.get("title")), ("meta description", m.get("description")),
                ("canonical", m.get("canonical"))) if only is True]
    if js_meta:
        report.add(cat, 'low', 'Review head metadata observed only in rendered snapshot',
                   f"Present in rendered metadata but not the served snapshot: {', '.join(js_meta)}. "
                   'This observes the paired snapshots, not JavaScript causation or engine processing.',
                   'Inspect intended responses and metadata ownership. Emit essential metadata in served HTML '
                   'only if a real consumer need/source defect is confirmed; indexing behavior remains unverified.',
                   rule_id='technical.head.metadata.injected.by.javascript')
    if m.get('jsonld') is True:
        report.add(cat, 'low', 'Review increased JSON-LD block count in rendered snapshot',
                   'More JSON-LD script blocks were counted in the rendered snapshot than in served HTML. '
                   'Some may already exist in served HTML; block counts do not prove injection, validity, '
                   'semantic differences or engine behavior.',
                   'Inspect both snapshots and existing supported markup before changing delivery. '
                   'Preserve valid semantic data and do not duplicate or move markup solely to clear this note.',
                   rule_id='technical.json.ld.injected.by.javascript')


def geo_finding(dep: dict, report) -> None:
    """Keep a large-count consumer review without asserting AI access failure."""
    obs = text_observation(dep)
    if obs is not None and obs['positive_net_increase_percent'] >= PCT_HIGH:
        report.add('geo', 'low', 'Review served-text availability for intended consumers',
                   _text_detail(obs), TEXT_REVIEW,
                   rule_id='geo.ai.answer.engines.may.not.see.this.content')
