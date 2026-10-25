#!/usr/bin/env python3
"""narwhal diff — compare two JSON reports to track SEO/GEO health over time.

Narwhal stays deliberately stateless: instead of a database, you save a scan as
JSON (`--format json -o before.json`), re-scan later (`-o after.json`), and diff
the two files. The output shows the score delta and which findings are **new**,
**resolved**, **worsened**, or **improved** — human-readable, git-friendly, and
readable by the agent itself.

Usage:
    python diff_scan.py before.json after.json
    python diff_scan.py before.json after.json --format json -o diff.json
    python diff_scan.py before.json after.json --fail-on-regression   # CI gate

Accepts either `scan`/`audit --format json` output (the audit's homepage findings
and overall score are used). Known mismatched/incomplete auditor scope or
truncated HTML does not yield improvement/resolution verdicts; CI gates exit 2.
Legacy scope stays explicitly unknown, with compatible finding comparisons.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.report import recorded_scan_scope, recorded_js_comparison_problem, recorded_sitemap_discovery_problem  # noqa: E402
from lib.report import recorded_llms_problem, recorded_schema_extraction_problem  # noqa: E402
from lib.report import recorded_response_partial  # noqa: E402
from lib import canonical  # noqa: E402
from lib import sitegraph, links, hreflang  # noqa: E402
from lib.report_output import write_output as _write_output  # noqa: E402

# Ordered worst -> best; lower index == more severe.
SEVERITY = ("critical", "high", "medium", "low", "good")
_RANK = {s: i for i, s in enumerate(SEVERITY)}
_ICON = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "good": "🟢"}
_CATS = {"technical": "Technical SEO", "content": "Content & E-E-A-T",
         "schema": "Structured data", "geo": "GEO / LLMO"}


def _normalize(data: dict, label='Report') -> dict:
    """Validate consumed evidence without repairing it or inferring missing metrics."""
    if not isinstance(data, dict):
        raise ValueError(label + ' must be a JSON object.')
    if 'findings' in data and 'homepage' in data:
        raise ValueError(label + ' has ambiguous scan/audit fields; supply one report kind.')
    if 'findings' in data:
        page, kind, score_field, finding_field = data, 'scan', 'score', 'findings'
        target = data.get('final_url') or data.get('url', '')
    elif 'homepage' in data:
        page = data['homepage']
        if not isinstance(page, dict):
            raise ValueError(label + '.homepage must be a JSON object.')
        kind, score_field, finding_field = 'audit', 'overall_score', 'homepage.findings'
        target = data.get('site') or page.get('url', '')
    else:
        raise ValueError(label + ' is unrecognized; expected scan/audit --format json output.')
    score = data.get(score_field)
    # A bounded numeric interval also excludes NaN/infinity without converting
    # huge JSON integers to floats. Booleans are not measured numeric scores.
    if type(score) not in (int, float) or not 0 <= score <= 100:
        raise ValueError(label + '.' + score_field + ' must be a finite number between 0 and 100.')
    findings = page.get('findings')
    if not isinstance(findings, list):
        raise ValueError(label + '.' + finding_field + ' must be a list.')
    for index, finding in enumerate(findings):
        location = f'{label}.{finding_field}[{index}]'
        if not isinstance(finding, dict):
            raise ValueError(location + ' must be an object.')
        category, title = finding.get('category'), finding.get('title')
        if not isinstance(category, str) or not category.strip():
            raise ValueError(location + '.category must be a non-empty string.')
        if not isinstance(title, str):
            raise ValueError(location + '.title must be a string.')
        if not isinstance(finding.get('severity'), str) or finding['severity'] not in SEVERITY:
            raise ValueError(location + '.severity must be critical, high, medium, low or good.')
        rule = finding.get('rule_id')
        if rule is not None and (not isinstance(rule, str) or (rule and not rule.strip())):
            raise ValueError(location + '.rule_id must be a string or null; blank whitespace is unsupported.')
        if not rule and not _key(finding)[1]:
            raise ValueError(location + ' needs a non-empty rule_id or usable normalized legacy title.')
    if not isinstance(target, str):
        raise ValueError(label + ' URL label must be a string.')
    return {'url': target, 'score': score, 'findings': findings, 'kind': kind,
            'meta': page.get('meta', {}), 'crawl': data.get('crawl') if kind == 'audit' else None,
            'rendered': page.get('rendered'), 'status': page.get('status')}


def _comparison(o: dict, n: dict) -> dict:
    """Compare known execution/settings, not exhaustive environmental equality."""
    scopes = [recorded_scan_scope(item["meta"]) for item in (o, n)]
    settings = [_recorded_settings(item["meta"], item["rendered"]) for item in (o, n)]
    reasons = []
    if o["kind"] != n["kind"]:
        reasons.append("Report kinds differ: page score and audit overall score are not comparable.")
    samples = [_crawl_sample(item["crawl"]) for item in (o, n)]
    if all(sample is not None for sample in samples) and samples[0] != samples[1]:
        reasons.append("Recorded audit crawl page samples differ (exact URLs or multiplicities); "
                       "a changed page mix is not site-fix evidence.")
    graph_bases = []
    for item in (o, n):
        crawl = item['crawl'] if isinstance(item['crawl'], dict) else {}
        graph = crawl.get('graph') if isinstance(crawl.get('graph'), dict) else {}
        graph_bases.append(graph.get('url_identity_basis'))
    if sitegraph.URL_IDENTITY_BASIS in graph_bases and any(
            basis != sitegraph.URL_IDENTITY_BASIS for basis in graph_bases):
        reasons.append('Crawl URL-identity policy differs or is unrecorded; changed page selection/graph grouping is not fix evidence.')
    link_bases = [item['crawl'].get('link_resolution_basis') if isinstance(item['crawl'], dict) else None for item in (o, n)]
    if any(basis in links.KNOWN_RESOLUTION_BASES for basis in link_bases) and link_bases[0] != link_bases[1]:
        reasons.append('Crawl link-resolution policy differs or is unrecorded; changed discovered targets are not site-fix evidence.')
    page_link_bases = [item['meta'].get('anchor_resolution_basis') if isinstance(item['meta'], dict) else None for item in (o, n)]
    if links.RESOLUTION_BASIS in page_link_bases and any(basis != links.RESOLUTION_BASIS for basis in page_link_bases):
        reasons.append('Page anchor-resolution policy differs or is unrecorded; changed source-link checks are not site-fix evidence.')
    if any(scope is None or 'technical' in scope[0] for scope in scopes):
        for source in ('meta', 'crawl'):
            bases = [item[source].get('hreflang_policy_basis') if isinstance(item[source], dict) else None for item in (o, n)]
            if hreflang.EXTRACTION_BASIS in bases and any(basis != hreflang.EXTRACTION_BASIS for basis in bases):
                reasons.append('HTML hreflang source policy differs or is unrecorded; changed technical observations are not site-fix evidence.')
        acquisition_bases = [item['crawl'].get('hreflang_acquisition_basis') if isinstance(item['crawl'], dict) else None for item in (o, n)]
        if hreflang.SNAPSHOT_BASIS in acquisition_bases and any(basis != hreflang.SNAPSHOT_BASIS for basis in acquisition_bases):
            reasons.append('Crawled hreflang response-acquisition policy differs or is unrecorded; changed relationships are not site-fix evidence.')
    for label, item, scope in zip(("Earlier", "Later"), (o, n), scopes):
        if scope is not None and (not scope[1] or set(scope[0]) != set(scope[1])):
            reasons.append(label + " report did not complete all requested auditor groups.")
        crawl = item["crawl"]
        meta_base = item['meta'] if isinstance(item['meta'], dict) else {}
        if links.unassessed_base(meta_base):
            reasons.append(label + ' page has unassessed declared anchor-base coverage.')
        if hreflang.unverified(meta_base, for_score=True):
            reasons.append(label + ' page has unassessed HTML hreflang URL coverage.')
        if recorded_response_partial(meta_base) or (type(item.get('status')) is int and item['status'] == 206):
            reasons.append(label + ' report has partial/ranged HTML coverage; full-page comparisons are unverified.')
        pages = crawl.get("pages") if isinstance(crawl, dict) else None
        if isinstance(pages, list) and any(links.unassessed_base(page)
                                           for page in pages if isinstance(page, dict)):
            reasons.append(label + ' audit contains unassessed declared anchor-base coverage; the sampled site score is not comparable.')
        if isinstance(pages, list) and any(isinstance(page, dict) and (
                page.get('hreflang_comparison_unverified') is True or (
                    'hreflang_comparison_unverified' not in page and hreflang.unverified(page))) for page in pages):
            reasons.append(label + ' audit contains unassessed HTML hreflang URL coverage; the sampled site score is not comparable.')
        if isinstance(pages, list) and any(isinstance(page, dict) and page.get("hard_fail") is True
                                           for page in pages):
            reasons.append(label + " audit contains a hard-failed crawl page; its overall score is not comparable.")
        if isinstance(pages, list) and any(recorded_response_partial(page) for page in pages):
            reasons.append(label + ' audit contains partial/ranged HTML coverage; its overall score is not comparable.')
        if isinstance(pages, list) and any(isinstance(page, dict) and page.get("response_truncated") is True
                                           for page in pages):
            reasons.append(label + " audit contains a truncated crawl page; its overall score is not comparable.")
        if isinstance(pages, list) and any(isinstance(page, dict) and page.get("js_comparison_unverified") is True
                                           for page in pages):
            reasons.append(label + " audit contains an unverified JS-dependence comparison; its overall score is not comparable.")
        if isinstance(pages, list) and any(isinstance(page, dict) and page.get('sitemap_discovery_unverified') is True
                                         for page in pages):
            reasons.append(label + ' audit contains unverified sitemap availability; its overall score is not comparable.')
        if isinstance(pages, list) and any(isinstance(page, dict) and page.get('llms_txt_unverified') is True for page in pages):
            reasons.append(label + ' audit contains unverified root llms.txt availability; its overall score is not comparable.')
        if isinstance(pages, list) and any(isinstance(page, dict) and page.get('canonical_comparison_unverified') is True for page in pages):
            reasons.append(label + ' audit contains an unverified HTML canonical comparison; its overall score is not comparable.')
        if isinstance(pages, list) and any(isinstance(page, dict) and (
                page.get('schema_extraction_unverified') is True or recorded_schema_extraction_problem(
                    {'scan_settings': page.get('scan_settings')}, for_score=True)) for page in pages):
            reasons.append(label + ' audit contains unverified structured-data extraction; its overall score is not comparable.')
        meta = item["meta"] if isinstance(item["meta"], dict) else {}
        coverage = meta.get("coverage")
        if canonical.unverified(meta):
            reasons.append(label + ' report has an unverified HTML canonical comparison; technical/overall score comparison is unverified.')
        js_problem = recorded_js_comparison_problem(meta, for_score=True)
        if js_problem:
            reasons.append(label + " report did not measure JS-dependence: " + js_problem + ".")
        if recorded_sitemap_discovery_problem(meta, for_score=True):
            reasons.append(label + ' report did not verify supported sitemap availability; technical-score comparison is unverified.')
        if recorded_llms_problem(meta, for_score=True):
            reasons.append(label + ' report did not verify root llms.txt availability; GEO-score comparison is unverified.')
        if recorded_schema_extraction_problem(meta, for_score=True):
            reasons.append(label + ' report has unverified structured-data extraction; schema/overall score comparison is unverified.')
        if meta.get("response_truncated") is True or (
                isinstance(coverage, dict) and coverage.get("response_truncated") is True):
            reasons.append(label + " report used truncated HTML coverage.")
    if all(scope is not None for scope in scopes):
        if set(scopes[0][0]) != set(scopes[1][0]):
            reasons.append("Requested auditor groups differ between reports.")
        if set(scopes[0][1]) != set(scopes[1][1]):
            reasons.append("Completed auditor groups differ between reports.")
    for key, label in (("render_requested", "Requested rendering"),
                       ("rendered", "Actual rendered/raw mode"),
                       ("image_checks", "Image-check setting"),
                       ("content_length_reviewed", "Content-length threshold coverage"),
                       ('readability_reviewed', 'Readability formula coverage'),
                       ('schema_extraction_reviewed', 'Schema-extraction coverage'),
                       ("rule_config", "Rule/scoring configuration")):
        if all(key in item for item in settings) and settings[0][key] != settings[1][key]:
            reasons.append(label + " differs between reports; changed checks or page representations are not fix evidence.")
    crawls = [_crawl_settings(item["crawl"]) for item in (o, n)]
    for label, crawl in zip(("Earlier", "Later"), crawls):
        for url, modes in crawl.items():
            for key, values in modes.items():
                if len(values) > 1:
                    reasons.append(f"{label} crawl contains contradictory {key} settings for {url}; its overall score is not comparable.")
    for url in sorted(crawls[0].keys() & crawls[1].keys()):
        for key in ("render_requested", "rendered", "image_checks", "content_length_reviewed", 'readability_reviewed', 'schema_extraction_reviewed', "rule_config"):
            values = [item[url].get(key, set()) for item in crawls]
            if all(values) and values[0] != values[1]:
                reasons.append(f"Crawl setting {key} differs for {url}; its contribution to the overall score is not comparable.")
    status = "incomparable" if reasons else (
        "comparable" if all(scope is not None for scope in scopes) else "unknown")
    if status == "unknown":
        reasons.append("Valid execution scope is missing; coverage cannot be inferred from findings.")
    return {
        "status": status,
        "reasons": reasons,
        "old_scope": {"requested": scopes[0][0], "completed": scopes[0][1]} if scopes[0] else None,
        "new_scope": {"requested": scopes[1][0], "completed": scopes[1][1]} if scopes[1] else None,
        "old_settings": settings[0], "new_settings": settings[1],
        "basis": "Recorded auditor execution, known rendering/image-check/content-length threshold/readability formula settings and rule-configuration fingerprints, response truncation/range evidence, known JS/sitemap/root-llms/structured-data extraction/HTML canonical/declared anchor-base/HTML hreflang gaps, complete recorded audit crawl samples (exact URL multiplicities), page anchor-resolution and crawl URL-identity/link-resolution/hreflang policy and explicit crawl failures only; not proof of "
                 "identical response destinations, other configuration, tool rules or unrecorded site-wide samples. Missing settings are not inferred or certified. Incomplete/malformed crawl samples are not inferred or certified.",
    }


def _recorded_settings(meta, rendered=None):
    """Only explicit booleans prove a known setting; legacy data stays unknown."""
    raw = meta.get("scan_settings") if isinstance(meta, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    result = {key: raw[key] for key in ("render_requested", "rendered", "image_checks", "content_length_reviewed", 'readability_reviewed', 'schema_extraction_reviewed')
            if type(raw.get(key)) is bool}
    if "rendered" not in result and type(rendered) is bool:
        result["rendered"] = rendered
    fingerprint = raw.get("rule_config")
    if isinstance(fingerprint, str) and re.fullmatch(r"[0-9a-fA-F]{64}", fingerprint):
        result["rule_config"] = fingerprint.lower()
    return result


def _crawl_sample(crawl):
    """Keep exact URL multiplicities; incomplete legacy lists certify no sample."""
    pages = crawl.get('pages') if isinstance(crawl, dict) else None
    if not isinstance(pages, list) or any(
            not isinstance(page, dict) or not isinstance(page.get('url'), str)
            or not page['url'].strip() for page in pages):
        return None
    return sorted(page['url'] for page in pages)


def _crawl_settings(crawl):
    """Join explicit page settings by URL, retaining contradictory duplicates."""
    pages = crawl.get("pages") if isinstance(crawl, dict) else None
    result = {}
    for page in pages if isinstance(pages, list) else []:
        if not isinstance(page, dict) or not isinstance(page.get("url"), str) or not page["url"]:
            continue
        for key, value in _recorded_settings(page, page.get("rendered")).items():
            result.setdefault(page["url"], {}).setdefault(key, set()).add(value)
    return result


def _key(finding: dict):
    """Stable identity for a finding across runs.

    Titles can carry a dynamic suffix (e.g. "Thin content (210 words)"); we
    strip a trailing parenthetical so the same issue matches run-to-run even as
    the measured number changes."""
    if finding.get("rule_id"):
        return (finding.get("category", ""), finding["rule_id"])
    title = str(finding.get("title", ""))
    base = title.split(" (")[0].strip().lower()
    return (finding.get("category", ""), base)


def _worse(a: str, b: str) -> bool:
    """True if severity ``a`` is more severe than ``b``."""
    return _RANK.get(a, 99) < _RANK.get(b, 99)


def _index_findings(findings: list) -> dict:
    """Select worst-severity evidence per identity, with an order-independent tie."""
    indexed = {}
    for finding in findings:
        key = _key(finding)
        previous = indexed.get(key)
        if previous is None or _worse(finding.get('severity'), previous.get('severity')):
            indexed[key] = finding
        elif finding.get('severity') == previous.get('severity') and (
                json.dumps(finding, sort_keys=True) < json.dumps(previous, sort_keys=True)):
            indexed[key] = finding
    return indexed


def diff_reports(old: dict, new: dict) -> dict:
    o, n = _normalize(old, 'Earlier report'), _normalize(new, 'Later report')
    comparison = _comparison(o, n)
    if comparison["status"] == "incomparable":
        # Absence from a narrower/unmeasured run is not evidence of resolution.
        return {"url": n["url"], "old_url": o["url"], "old_score": o["score"], "new_score": n["score"],
                "score_delta": None, "added": [], "resolved": [], "worsened": [],
                "improved": [], "unchanged": 0, "regression": None,
                "new_critical_high": [], "comparison": comparison,
                "not_compared": {"old_findings": len(o["findings"]), "new_findings": len(n["findings"])}}
    oi = _index_findings(o['findings'])
    ni = _index_findings(n['findings'])
    okeys, nkeys = set(oi), set(ni)

    added = [ni[k] for k in nkeys - okeys]
    resolved = [oi[k] for k in okeys - nkeys]
    worsened, improved = [], []
    for k in sorted(okeys & nkeys, key=json.dumps):
        a, b = oi[k], ni[k]
        if a.get("severity") != b.get("severity"):
            entry = {"category": b.get("category"), "title": b.get("title"),
                     "from": a.get("severity"), "to": b.get("severity")}
            if b.get('rule_id'):
                entry['rule_id'] = b['rule_id']
            (worsened if _worse(b.get("severity"), a.get("severity"))
             else improved).append(entry)

    added.sort(key=lambda f: (_RANK.get(f.get("severity"), 99), json.dumps(_key(f))))
    resolved.sort(key=lambda f: (_RANK.get(f.get("severity"), 99), json.dumps(_key(f))))
    new_bad = [f for f in added if f.get("severity") in ("critical", "high")]
    score_dropped = n["score"] < o["score"]
    severe_escalation = any(f["to"] in ("critical", "high") for f in worsened)

    return {
        "url": n["url"],
        "old_url": o["url"],
        "old_score": o["score"],
        "new_score": n["score"],
        "score_delta": n["score"] - o["score"],
        "added": added,
        "resolved": resolved,
        "worsened": worsened,
        "improved": improved,
        "unchanged": len(okeys & nkeys) - len(worsened) - len(improved),
        # Severe escalation matters even when other fixes offset its score cost.
        "regression": score_dropped or bool(new_bad) or severe_escalation,
        "new_critical_high": new_bad,
        "comparison": comparison,
        'finding_identity': {
            'basis': 'category_rule_or_legacy_title_worst_severity_v1',
            'representative': 'Worst observed severity; equal-severity ties use sorted-key JSON lexical order.',
            'scope': 'Rule-level identities; individual instances are not matched. Scores retain input values.',
            **{label: {'raw_findings': len(item['findings']), 'distinct_identities': len(index),
                       'repeated_entries': len(item['findings']) - len(index)}
               for label, item, index in (('old', o, oi), ('new', n, ni))},
        },
    }


def _verdict(d: dict) -> str:
    status = d.get("comparison", {}).get("status", "unknown")
    if status == "incomparable":
        return "**Not comparable** — no improvement, resolution or regression verdict was measured."
    delta = d["score_delta"]
    if d["regression"]:
        why = []
        if delta < 0:
            why.append(f"score dropped {abs(delta)}")
        if d["new_critical_high"]:
            why.append(f"{len(d['new_critical_high'])} new high-severity issue(s)")
        escalated = sum(f['to'] in ('critical', 'high') for f in d['worsened'])
        if escalated:
            why.append(f"{escalated} existing finding(s) escalated to critical/high severity")
        return "**Regressed** — " + ", ".join(why) + "."
    if d['worsened']:
        if delta > 0 or d['resolved'] or d['improved']:
            return ('**Mixed reported finding changes** — severity worsened alongside other '
                    'reported improvements; inspect both before claiming a fix.')
        return ('**Worsened reported severity** — review the changes below. The regression flag '
                'also catches score drops, new critical/high findings and escalations to critical/high; '
                'this lower-severity change alone does not trigger it.')
    if delta > 0 or d["resolved"] or d["improved"]:
        return "**Improved reported findings** — not proof of improved overall page health."
    return "**No material change** since the previous run."


def render_markdown(d: dict) -> str:
    delta = d["score_delta"]
    sign = "not compared" if delta is None else (
        f"+{delta}" if delta > 0 else (str(delta) if delta < 0 else "±0"))
    lines = [
        f"# Narwhal Scan Diff — {d['url']}",
        "",
        f"**{'Recorded scores' if delta is None else 'Score'}: {d['old_score']} → {d['new_score']} ({sign})**",
        "",
        _verdict(d),
        "",
    ]
    if 'old_url' in d and d['old_url'] != d['url']:
        labels = json.dumps({'earlier': d['old_url'], 'later': d['url']}, indent=2, ensure_ascii=True)
        # Encode backticks so recorded labels cannot close this JSON code block.
        labels = labels.replace('`', '\\u0060')
        lines += ['## Target labels differ', '',
                  'Verify that these recorded labels represent the intended before/after page or site. '
                  'Local preview mappings are not inferred; matching labels do not prove identical response destinations.', '',
                  '```json', labels, '```', '']
    comparison = d.get("comparison", {})
    status = comparison.get("status", "unknown")
    lines.append("**Auditor coverage: " + {"comparable": "matching recorded scope",
                 "incomparable": "not comparable", "unknown": "unverified"}.get(status, "unverified") + ".**")
    for label, key in (("Earlier", "old_scope"), ("Later", "new_scope")):
        scope = comparison.get(key)
        if scope:
            requested = ", ".join(scope['requested'])
            completed = ", ".join(scope['completed']) or "none"
            lines.append(f"- {label}: requested {requested}; completed {completed}.")
        else:
            lines.append(f"- {label}: valid auditor scope not recorded.")
    for label, key in (("Earlier", "old_settings"), ("Later", "new_settings")):
        settings = comparison.get(key, {})
        facts = []
        for name, description in (("render_requested", "render requested"),
                                  ("rendered", "actual rendering"), ("image_checks", "image resource checks")):
            if name in settings:
                facts.append(description + ": " + ("enabled" if settings[name] else "disabled"))
        if settings:
            facts.append("rule configuration: " + ("fingerprint recorded" if "rule_config" in settings else "unverified"))
        lines.append(f"- {label} settings: " + ("; ".join(facts) if facts else "not recorded") + ".")
    lines.extend("- " + reason for reason in comparison.get("reasons", []))
    lines.extend([comparison.get("basis", "Coverage was not recorded."), ""])
    if status == "incomparable":
        counts = d["not_compared"]
        lines.append(f"_Not compared: {counts['old_findings']} earlier and {counts['new_findings']} later findings. "
                     "Re-scan with successful page fetches, matching completed auditor selections, rendering/image settings and full HTML coverage._")
        return "\n".join(lines).rstrip() + "\n"

    identity = d.get('finding_identity', {})
    if any(identity.get(label, {}).get('repeated_entries', 0) for label in ('old', 'new')):
        old, new = identity['old'], identity['new']
        lines += [f"Repeated finding identities: earlier {old['raw_findings']} entries → "
                  f"{old['distinct_identities']} identities; later {new['raw_findings']} entries → "
                  f"{new['distinct_identities']} identities. Comparisons use the worst observed severity "
                  'and a stable representative; individual instances are not matched. '
                  'Scores retain the input reports\' values.', '']

    def _bullets(items):
        for f in items:
            lines.append(f"- {_ICON.get(f.get('severity'), '•')} **{f.get('title')}** "
                         f"({_CATS.get(f.get('category'), f.get('category'))})")

    if d["added"]:
        lines.append(f"## 🔺 New findings ({len(d['added'])})")
        lines.append("")
        _bullets(d["added"])
        lines.append("")
    if d["worsened"]:
        lines.append(f"## ⚠️ Worsened ({len(d['worsened'])})")
        lines.append("")
        for c in d["worsened"]:
            lines.append(f"- **{c['title']}** ({_CATS.get(c['category'], c['category'])}): "
                         f"{c['from']} → {c['to']}")
        lines.append("")
    if d["resolved"]:
        lines.append(f"## ✅ Resolved ({len(d['resolved'])})")
        lines.append("")
        _bullets(d["resolved"])
        lines.append("")
    if d["improved"]:
        lines.append(f"## 🟢 Improved severity ({len(d['improved'])})")
        lines.append("")
        for c in d["improved"]:
            lines.append(f"- **{c['title']}** ({_CATS.get(c['category'], c['category'])}): "
                         f"{c['from']} → {c['to']}")
        lines.append("")

    lines.append(f"_Unchanged: {d['unchanged']} finding(s) present in both runs._")
    return "\n".join(lines).rstrip() + "\n"


def render_json(d: dict) -> str:
    return json.dumps(d, indent=2, ensure_ascii=False)


def _decode_report_json(text: str, label='Report') -> dict:
    """Turn known decoder failures into bounded diagnostics without body excerpts."""
    if not isinstance(text, str):
        raise ValueError(label + ' JSON input must be a string.')
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f'{label} JSON is invalid at line {exc.lineno}, column {exc.colno}.') from None
    except (ValueError, RecursionError):
        raise ValueError(label + ' JSON could not be decoded within supported parser limits.') from None


def _load(path: str, label='Report', input_stats=None) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        if input_stats is not None:
            input_stats.append(os.fstat(fh.fileno()))
        try:
            text = fh.read()
        except UnicodeError:
            raise ValueError(label + ' file must contain UTF-8 JSON.') from None
    return _decode_report_json(text, label)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Diff two narwhal JSON reports (regression tracking)")
    ap.add_argument("old", help="earlier report (scan/audit --format json)")
    ap.add_argument("new", help="later report to compare against it")
    ap.add_argument("--format", choices=("markdown", "json"), default="markdown")
    ap.add_argument("-o", "--output", help='save to a regular file distinct from both input snapshots')
    ap.add_argument("--fail-on-regression", action="store_true",
                    help="exit non-zero for a score drop, new critical/high finding, "
                         "or existing finding escalated to critical/high; exit 2 for known "
                         "incomparable coverage (for CI gating)")
    ap.add_argument("--require-comparable", action="store_true",
                    help="exit 2 unless recorded report coverage is comparable; "
                         "combine with --fail-on-regression to gate regression and recorded comparability")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    input_stats = [] if args.output else None
    try:
        d = diff_reports(_load(args.old, 'Earlier report', input_stats),
                         _load(args.new, 'Later report', input_stats))
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    out = render_json(d) if args.format == "json" else render_markdown(d)
    if args.output:
        try:
            _write_output(args.output, out, input_stats, label='Diff output')
        except ValueError as exc:
            print(f'Error: {exc}', file=sys.stderr)
            return 2
        except OSError as exc:
            print(f'Error: Could not write diff output ({type(exc).__name__}); check target path and permissions.',
                  file=sys.stderr)
            return 2
        print(f"Wrote {args.format} diff to {args.output} "
              f"(score {d['old_score']} → {d['new_score']})")
    else:
        print(out)

    status = d["comparison"]["status"]
    if status == "unknown":
        print("WARNING: auditor coverage is unverified; legacy finding/score comparison "
              "does not prove matching checks.", file=sys.stderr)
    if args.require_comparable and status != "comparable":
        print("FAIL: comparable recorded report coverage is required; restore matching completed "
              "auditor execution and verify the comparison reasons before accepting a fix.", file=sys.stderr)
        return 2
    if args.fail_on_regression and status == "incomparable":
        print("FAIL: report coverage is not comparable; re-scan with matching completed "
              "auditor selections, successful page fetches and full HTML coverage.", file=sys.stderr)
        return 2
    if args.fail_on_regression and d["regression"]:
        print("FAIL: regression detected (score dropped, new high-severity finding, "
              "or existing finding escalated to critical/high).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
