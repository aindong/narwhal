"""Bounded source-annotation and sampled relationship checks for HTML hreflang.

No language/translation equivalence, search acceptance or whole-site validity
is measured. Unsupported declarations and incomplete target snapshots stay
unassessed, not failed HTTP requests or evidence of missing return tags.
Optional same-host probes retain the existing request/redirect/SSRF budgets.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlsplit

from . import htmlx, http
from .sitegraph import norm

# BCP-47-ish subset Google accepts: lang(2-3) [-Script(4)] [-REGION(2)|-(3digit)]
CODE = re.compile(r"^[a-z]{2,3}(-[a-z]{4})?(-([a-z]{2}|\d{3}))?$", re.I)
PROBE_CAP = 5
EXTRACTION_BASIS = 'html_hreflang_absolute_http_source_v1'
ANALYSIS_BASIS = 'supported_html_hreflang_pairs_v1'
SNAPSHOT_BASIS = 'html_hreflang_response_snapshot_v1'
_SNAPSHOT_STATUSES = ('source_observed', 'unavailable', 'empty', 'partial', 'non_html', 'identity_changed')
_OBSERVATION_LABELS = {'source_observed': 'parsed source snapshot', 'unavailable': 'response unavailable/unassessed',
                       'empty': 'empty body/unassessed', 'partial': 'partial body/unassessed',
                       'non_html': 'HTML media type unverified/unassessed', 'identity_changed': 'final URL identity unverified/unassessed'}
ERROR = 'HTML hreflang URL coverage is unassessed; technical/overall score comparisons are unverified.'
_REASONS = ('missing_href', 'not_fully_qualified', 'non_http', 'syntax', 'unsupported_reference')


def valid_code(code: str) -> bool:
    c = (code or "").strip().lower()
    return c == "x-default" or bool(CODE.match(c))


def href_problem(value):
    """Bounded source URL classification, not fetch permission or Google acceptance.

    Language alternate annotations require fully-qualified HTTP(S) references;
    resolving a relative href would fabricate a different source declaration.
    """
    if not isinstance(value, str):
        return 'missing_href' if value is None else 'unsupported_reference'
    value = value.strip()
    if not value:
        return 'missing_href'
    if any(ord(c) <= 32 or ord(c) == 127 or c.isspace() for c in value) or '\\' in value:
        return 'unsupported_reference'
    try:
        parts = urlsplit(value)
        if parts.scheme and parts.scheme not in ('http', 'https'):
            return 'non_http'
        if not parts.scheme or not parts.netloc:
            return 'not_fully_qualified'
        if not parts.hostname:
            return 'syntax'
        parts.port
        if parts.username is not None:
            return 'unsupported_reference'
    except ValueError:
        return 'syntax'
    return None


def extract(doc, base_url: str, *, diagnostics=None) -> list:
    """Supported source annotations as ``[{lang, href}]``; no URI fabrication or I/O."""
    out, omitted, declared = [], {}, 0
    for l in doc.links_by_rel("alternate"):
        lang, href = l.get("hreflang"), l.get("href")
        if lang is None:
            continue
        declared += 1
        problem = href_problem(href)
        if problem:
            omitted[problem] = omitted.get(problem, 0) + 1
            continue
        out.append({"lang": lang.strip(), "href": href.strip()})
    if diagnostics is not None:
        diagnostics.update({'basis': EXTRACTION_BASIS, 'declared': declared, 'accepted': len(out), 'omitted': omitted})
    return out


def recorded(meta):
    """Accept only a supported, self-consistent supplied-tag receipt, not site coverage."""
    receipt = meta.get('hreflang_extraction') if isinstance(meta, dict) else None
    if not isinstance(receipt, dict) or receipt.get('basis') != EXTRACTION_BASIS:
        return None
    declared, accepted, omitted = receipt.get('declared'), receipt.get('accepted'), receipt.get('omitted')
    if any(type(value) is not int or value < 0 for value in (declared, accepted)) or not isinstance(omitted, dict):
        return None
    if any(key not in _REASONS or type(value) is not int or value < 0 for key, value in omitted.items()):
        return None
    return receipt if accepted + sum(omitted.values()) == declared else None


def unverified(meta, *, for_score=False):
    """Known URL omissions, not a verdict inferred from a missing legacy receipt."""
    if for_score:
        from .report import recorded_scan_scope
        scope = recorded_scan_scope(meta)
        if scope is not None and 'technical' not in scope[0]:
            return False
    receipt = recorded(meta)
    return bool(receipt and sum(receipt['omitted'].values()))


def note(meta):
    """Summarize counts without echoing rejected source URLs or exception messages."""
    receipt = recorded(meta)
    if receipt is None or not receipt['declared']:
        return ''
    omitted = sum(receipt['omitted'].values())
    detail = ', '.join(key + '=' + str(receipt['omitted'][key]) for key in _REASONS if receipt['omitted'].get(key))
    return (f"HTML hreflang source: {receipt['accepted']} of {receipt['declared']} declarations have supported "
            'fully-qualified HTTP(S) URLs. '
            + (f'{omitted} omitted from relationship/probe analysis ({detail}); these are not HTTP failures. '
               'Confirm intended language-page URLs before source edits. ' if omitted else '')
            + 'Parsed HTML declarations only; not full URI/code/head validation, translation equivalence, '
              'HTTP-header/sitemap coverage or search-engine acceptance.')


def source_observation(response, target):
    """Qualify a response for requested-identity relationship checks, not page health.

    A page scan can still audit a redirect's final page. This receipt only keeps
    its HTML from establishing annotations at an unobserved requested identity.
    No request, redirect permission, raw error or final URL is added here.
    """
    content_type = (response.headers.get('content-type') or '').split(';', 1)[0].strip().lower()
    status = ('unavailable' if not response.ok or not 200 <= response.status < 300 else
              'partial' if http.has_range_evidence(response) else 'empty' if not response.text else
              'partial' if response.headers.get('x-narwhal-truncated') == 'true' else
              'non_html' if content_type not in ('text/html', 'application/xhtml+xml') else
              'identity_changed' if href_problem(response.final_url) is not None or href_problem(target) is not None
              or norm(response.final_url) != norm(target) else 'source_observed')
    return {'basis': SNAPSHOT_BASIS, 'status': status,
            'acquisition': 'rendered_snapshot' if response.rendered else 'guarded_http', 'http_status': response.status}


def recorded_observation(meta):
    """Recognize a bounded response receipt, without authenticating imported data."""
    value = meta.get('hreflang_source_observation') if isinstance(meta, dict) else None
    if (not isinstance(value, dict) or value.get('basis') != SNAPSHOT_BASIS
            or value.get('status') not in _SNAPSHOT_STATUSES
            or value.get('acquisition') not in ('guarded_http', 'rendered_snapshot')
            or type(value.get('http_status')) is not int or not 0 <= value['http_status'] <= 599
            or (value.get('status') != 'unavailable' and not 200 <= value['http_status'] < 300)
            or (value.get('status') == 'source_observed' and value['http_status'] == 206)):
        return None
    return value


def probe(pages_alts: dict, *, allow_private=False, timeout=8, cap=PROBE_CAP,
          fetch_text=None, diagnostics=None, observations=None) -> dict:
    """Fetch up to ``cap`` same-host alternate URLs we didn't crawl and extract
    their clusters, so reciprocity can be verified instead of left unknown."""
    if cap <= 0:
        return {}
    known = {norm(u) for u in pages_alts if href_problem(u) is None}
    targets, seen = [], set()
    for page, alts in pages_alts.items():
        if href_problem(page) is not None:
            continue
        host = urlparse(page).netloc.lower()
        for a in alts:
            if href_problem(a.get('href')) is not None:
                continue
            tn = norm(a["href"])
            if tn in known or tn in seen:
                continue
            if urlparse(a["href"]).netloc.lower() != host:
                continue   # cross-host alternates are out of probe scope
            seen.add(tn)
            targets.append(a["href"])
            if len(targets) >= cap:
                break
        if len(targets) >= cap:
            break

    probed = {}
    for t in targets:
        observation = {'target': t, 'acquisition': 'supplied_body' if fetch_text is not None else 'guarded_http'}
        if fetch_text is None:
            from . import http
            try:
                response = http.fetch(t, allow_private=allow_private, timeout=timeout)
            except http.URLInputError:  # includes SSRFError; retain the guard, omit raw diagnostics
                observation['status'] = 'unavailable'
                if observations is not None: observations.append(observation)
                continue
            observation.update(source_observation(response, t))
            if observation['status'] != 'source_observed':
                if observations is not None: observations.append(observation)
                continue  # unavailable/partial/other-identity snapshots do not establish absent annotations
            body = response.text
        else:
            body = fetch_text(t)  # supplied-body hook is not HTTP identity/coverage verification
        observation['status'] = 'source_observed' if body else 'empty'
        if observations is not None: observations.append(observation)
        if body:
            receipt = {}
            probed[t] = extract(htmlx.parse(body, base_url=t), t, diagnostics=receipt)
            if diagnostics is not None:
                diagnostics[t] = receipt
    return probed


def analyze(pages_alts: dict, *, coverage=None, partial_sources=()) -> dict:
    """Validate hreflang relationships across ``{page_url: [{lang, href}]}``.

    Every page present in the mapping counts as "seen" (crawled or probed);
    alternate targets outside it are unverified, not broken."""
    coverage = coverage or {}
    supplied = {p: alts for p, alts in pages_alts.items() if href_problem(p) is None}
    unsupported_active = sum(bool(alts or (recorded({'hreflang_extraction': coverage.get(p)}) or {}).get('declared'))
                             for p, alts in pages_alts.items() if p not in supplied)
    supported = {p: [alt for alt in alts if href_problem(alt.get('href')) is None] for p, alts in supplied.items()}
    receipts = {p: recorded({'hreflang_extraction': coverage.get(p)}) for p in supplied}
    used = {p: alts for p, alts in supported.items() if supplied[p] or (receipts[p] and receipts[p]['declared'])}
    seen = {norm(p): p for p in supplied}
    incomplete = {norm(p) for p in partial_sources if href_problem(p) is None}
    incomplete.update(norm(p) for p in supplied if len(supported[p]) != len(supplied[p])
                      or (receipts[p] and sum(receipts[p]['omitted'].values())))

    invalid, missing_self, missing_return = [], [], []
    unverified = 0
    checked, unassessed_pairs, unassessed_self = 0, 0, []
    langs_seen = set()

    for page, alts in used.items():
        pn = norm(page)
        cluster = {norm(a["href"]) for a in alts}
        for a in alts:
            langs_seen.add(a["lang"].strip().lower())
            if not valid_code(a["lang"]):
                invalid.append({"page": page, "code": a["lang"]})
        if pn in incomplete:
            unassessed_self.append(page)
        elif pn not in cluster:
            missing_self.append(page)
        for a in alts:
            tn = norm(a["href"])
            if tn == pn:
                continue
            if tn not in seen:
                unverified += 1
                continue
            if pn in incomplete or tn in incomplete:
                unassessed_pairs += 1
                continue
            checked += 1
            target_cluster = {norm(x["href"]) for x in supported.get(seen[tn], [])}
            if pn not in target_cluster:
                missing_return.append({"page": page, "target": a["href"],
                                       "lang": a["lang"]})

    return {
        "used": bool(used) or bool(unsupported_active),
        "pages_with_hreflang": len(used) + unsupported_active,
        "invalid_codes": invalid,
        "missing_self": missing_self,
        "missing_return": missing_return,
        "unverified_targets": unverified,
        "has_x_default": "x-default" in langs_seen,
        'analysis_basis': ANALYSIS_BASIS,
        'checked_pairs': checked,
        'unassessed_pairs': unassessed_pairs,
        'unassessed_self': unassessed_self,
        'source_coverage': {'basis': EXTRACTION_BASIS,
                            'recorded_pages': sum(receipt is not None for receipt in receipts.values()),
                            'unrecorded_pages': sum(receipt is None for receipt in receipts.values()),
                            'pages_with_omissions': sum(bool(receipt and sum(receipt['omitted'].values())) for receipt in receipts.values()),
                            'omitted_declarations': sum(sum(receipt['omitted'].values()) for receipt in receipts.values() if receipt),
                            'unsupported_source_pages': len(pages_alts) - len(supplied),
                            'unsupported_supplied_targets': sum(len(supplied[p]) - len(supported[p]) for p in supplied)},
    }


def _literal(value, limit=400):
    """Bound display text and keep URL/code markup literal; JSON retains full values."""
    value = ' '.join(str(value).split())
    if len(value) > limit:
        value = value[:limit] + '… [truncated; see JSON]'
    fence = '`' * (1 + max((len(run) for run in re.findall(r'`+', value)), default=0))
    return fence + ' ' + value + ' ' + fence


def render_markdown(r: dict) -> list:
    """The 'Hreflang' report section (only rendered when hreflang is in use)."""
    lines = [f"## Hreflang / international ({r['pages_with_hreflang']} supplied pages "
             "with declarations)", ""]
    coverage = r.get('source_coverage')
    known = (r.get('analysis_basis') == ANALYSIS_BASIS and isinstance(coverage, dict)
             and coverage.get('basis') == EXTRACTION_BASIS
             and all(type(coverage.get(key)) is int and coverage[key] >= 0 for key in (
                 'recorded_pages', 'unrecorded_pages', 'pages_with_omissions', 'omitted_declarations', 'unsupported_supplied_targets', 'unsupported_source_pages')))
    if known:
        lines += [f"Source receipts recorded for {coverage['recorded_pages']} supplied pages; "
                  f"{coverage['unrecorded_pages']} have unrecorded source coverage. "
                  f"{coverage['unsupported_source_pages']} source-address key(s) are unsupported and unassessed. "
                  f"Recorded receipts list {coverage['omitted_declarations']} omitted declarations; "
                  f"{coverage['unsupported_supplied_targets']} unsupported supplied targets were omitted. "
                  'Omitted/partial sources do not prove missing return tags or dead URLs.', '']
        lines += [f"- **Supported directed declaration checks within the sample:** {r.get('checked_pairs', 0)}. "
                  'This is an input-snapshot relationship check, not language/translation or search-acceptance verification.']
    else:
        lines += ['Source/pair-analysis coverage was not recorded or is unsupported; reported relationships are not verified eligibility.', '']
    observations = r.get('probe_observations')
    if isinstance(observations, list):
        lines += [f"- **Probe observations:** {len(observations)} selected target(s); this is not a count of redirect/network hops."]
        for observation in observations[:5]:
            label = _OBSERVATION_LABELS.get(observation.get('status'), 'unrecorded/unsupported observation')
            code = observation.get('http_status')
            transport = 'guarded HTTP' if observation.get('acquisition') == 'guarded_http' else 'supplied body; not HTTP verification'
            lines += ['  - ' + _literal(observation.get('target', '')) + ': ' + label + '; ' + transport
                      + (f'; HTTP {code}' if type(code) is int else '')]
        if len(observations) > 5:
            lines += [f"  - … +{len(observations) - 5} more (see JSON)"]
    sampled = r.get('sampled_source_observations')
    if isinstance(sampled, list):
        usable = sum(bool(recorded_observation({'hreflang_source_observation': item}))
                     and item.get('status') == 'source_observed' for item in sampled)
        unassessed = [item for item in sampled if not recorded_observation({'hreflang_source_observation': item})
                      or item.get('status') != 'source_observed']
        lines += [f"- **Crawled source observations:** {usable} of {len(sampled)} supplied response(s) qualified "
                  f"for requested-identity relationship checks; {len(unassessed)} unassessed. "
                  'This is not page-health, translation or search-acceptance verification.']
        rendered = sum(bool(recorded_observation({'hreflang_source_observation': item}))
                       and item.get('acquisition') == 'rendered_snapshot' for item in sampled)
        if rendered:
            lines += [f"  - {rendered} rendered snapshot(s), not original served HTML; this does not prove search-crawler rendering."]
        for item in unassessed[:5]:
            value = item if isinstance(item, dict) else {}
            observation = recorded_observation({'hreflang_source_observation': value})
            label = _OBSERVATION_LABELS[observation['status']] if observation else 'unrecorded/unsupported observation'
            lines += ['  - ' + _literal(value.get('target', '')) + ': ' + label]
        if len(unassessed) > 5:
            lines += [f"  - … +{len(unassessed) - 5} more (see JSON)"]
    else:
        lines += ['- Crawled response acquisition coverage is unrecorded; source counts alone do not establish requested URL identity or a complete HTML response.']
    if r["missing_return"]:
        lines.append(f"- **Missing return tags ({len(r['missing_return'])})** — recorded "
                     'within supported supplied snapshots, not search-acceptance proof:')
        for m in r["missing_return"][:6]:
            lines.append(f"  - {_literal(m['page'])} → {_literal(m['target'])} ({_literal(m['lang'], 80)}) has "
                         "no link back")
        if len(r['missing_return']) > 6:
            lines.append(f"  - … +{len(r['missing_return']) - 6} more (see JSON)")
    if r["missing_self"]:
        lines.append(f"- **Missing self-reference ({len(r['missing_self'])})** — "
                     'within supported supplied snapshots:')
        for p in r["missing_self"][:5]:
            lines.append('  - ' + _literal(p))
        if len(r['missing_self']) > 5:
            lines.append(f"  - … +{len(r['missing_self']) - 5} more (see JSON)")
    if r.get('unassessed_pairs') or r.get('unassessed_self'):
        lines += [f"- **Unassessed due to source gaps/partial snapshots:** {r.get('unassessed_pairs', 0)} directed pair(s), "
                  f"{len(r.get('unassessed_self', []))} self-reference check(s). Inspect source and response coverage before edits."]
    if r["invalid_codes"]:
        codes = ", ".join(_literal(i['code'] or '[empty]', 80) for i in r["invalid_codes"][:6])
        lines.append(f"- **Outside the supported code pattern:** {codes}. "
                     'This is a bounded syntax check, not IANA/locale validation.')
        if len(r['invalid_codes']) > 6:
            lines.append(f"  - … +{len(r['invalid_codes']) - 6} more (see JSON)")
    if not r["has_x_default"]:
        lines.append('- **No supported x-default target observed** in the supplied annotations. '
                     'Review whether an unmatched-locale fallback is appropriate; this is not a universal requirement.')
    if r["unverified_targets"]:
        lines.append(f"- _{r['unverified_targets']} alternate target(s) point "
                     "outside the crawled/probed sample — **unverified**, not "
                     'broken. Broader sampling is optional and must remain within authorized crawl/probe limits._')
    lines += ['', 'Confirm intended language variants before editing annotations. HTML snapshots only: '
              'no HTTP-header/sitemap hreflang, head-placement, full URI/code validity or search acceptance is certified.']
    lines.append("")
    return lines
