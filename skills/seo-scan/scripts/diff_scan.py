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

from lib.report import recorded_scan_scope  # noqa: E402

# Ordered worst -> best; lower index == more severe.
SEVERITY = ("critical", "high", "medium", "low", "good")
_RANK = {s: i for i, s in enumerate(SEVERITY)}
_ICON = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "good": "🟢"}
_CATS = {"technical": "Technical SEO", "content": "Content & E-E-A-T",
         "schema": "Structured data", "geo": "GEO / LLMO"}


def _normalize(data: dict) -> dict:
    """Keep score/findings and recorded execution provenance for comparisons."""
    if "findings" in data:  # single-page scan report
        return {"url": data.get("final_url") or data.get("url", ""),
                "score": data.get("score", 0),
                "findings": data.get("findings", []),
                "kind": "scan", "meta": data.get("meta", {}), "crawl": None,
                "rendered": data.get("rendered")}
    if "homepage" in data:  # comprehensive audit report
        hp = data.get("homepage", {})
        return {"url": data.get("site") or hp.get("url", ""),
                "score": data.get("overall_score", hp.get("score", 0)),
                "findings": hp.get("findings", []),
                "kind": "audit", "meta": hp.get("meta", {}), "crawl": data.get("crawl"),
                "rendered": hp.get("rendered")}
    raise ValueError(
        "Unrecognized report JSON — expected `narwhal scan` or `narwhal audit` "
        "output produced with `--format json`.")


def _comparison(o: dict, n: dict) -> dict:
    """Compare known execution/settings, not exhaustive environmental equality."""
    scopes = [recorded_scan_scope(item["meta"]) for item in (o, n)]
    settings = [_recorded_settings(item["meta"], item["rendered"]) for item in (o, n)]
    reasons = []
    if o["kind"] != n["kind"]:
        reasons.append("Report kinds differ: page score and audit overall score are not comparable.")
    for label, item, scope in zip(("Earlier", "Later"), (o, n), scopes):
        if scope is not None and (not scope[1] or set(scope[0]) != set(scope[1])):
            reasons.append(label + " report did not complete all requested auditor groups.")
        crawl = item["crawl"]
        pages = crawl.get("pages") if isinstance(crawl, dict) else None
        if isinstance(pages, list) and any(isinstance(page, dict) and page.get("hard_fail") is True
                                           for page in pages):
            reasons.append(label + " audit contains a hard-failed crawl page; its overall score is not comparable.")
        if isinstance(pages, list) and any(isinstance(page, dict) and page.get("response_truncated") is True
                                           for page in pages):
            reasons.append(label + " audit contains a truncated crawl page; its overall score is not comparable.")
        meta = item["meta"] if isinstance(item["meta"], dict) else {}
        coverage = meta.get("coverage")
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
        for key in ("render_requested", "rendered", "image_checks", "rule_config"):
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
        "basis": "Recorded auditor execution, known rendering/image-check settings and rule-configuration fingerprints, response truncation and explicit crawl failures only; not proof of "
                 "identical URLs, other configuration, tool rules or site-wide samples. Missing settings are not inferred or certified.",
    }


def _recorded_settings(meta, rendered=None):
    """Only explicit booleans prove a known setting; legacy data stays unknown."""
    raw = meta.get("scan_settings") if isinstance(meta, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    result = {key: raw[key] for key in ("render_requested", "rendered", "image_checks")
            if type(raw.get(key)) is bool}
    if "rendered" not in result and type(rendered) is bool:
        result["rendered"] = rendered
    fingerprint = raw.get("rule_config")
    if isinstance(fingerprint, str) and re.fullmatch(r"[0-9a-fA-F]{64}", fingerprint):
        result["rule_config"] = fingerprint.lower()
    return result


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


def diff_reports(old: dict, new: dict) -> dict:
    o, n = _normalize(old), _normalize(new)
    comparison = _comparison(o, n)
    if comparison["status"] == "incomparable":
        # Absence from a narrower/unmeasured run is not evidence of resolution.
        return {"url": n["url"], "old_score": o["score"], "new_score": n["score"],
                "score_delta": None, "added": [], "resolved": [], "worsened": [],
                "improved": [], "unchanged": 0, "regression": None,
                "new_critical_high": [], "comparison": comparison,
                "not_compared": {"old_findings": len(o["findings"]), "new_findings": len(n["findings"])}}
    oi = {_key(f): f for f in o["findings"]}
    ni = {_key(f): f for f in n["findings"]}
    okeys, nkeys = set(oi), set(ni)

    added = [ni[k] for k in nkeys - okeys]
    resolved = [oi[k] for k in okeys - nkeys]
    worsened, improved = [], []
    for k in okeys & nkeys:
        a, b = oi[k], ni[k]
        if a.get("severity") != b.get("severity"):
            entry = {"category": b.get("category"), "title": b.get("title"),
                     "from": a.get("severity"), "to": b.get("severity")}
            (worsened if _worse(b.get("severity"), a.get("severity"))
             else improved).append(entry)

    added.sort(key=lambda f: _RANK.get(f.get("severity"), 99))
    resolved.sort(key=lambda f: _RANK.get(f.get("severity"), 99))
    new_bad = [f for f in added if f.get("severity") in ("critical", "high")]
    score_dropped = n["score"] < o["score"]

    return {
        "url": n["url"],
        "old_score": o["score"],
        "new_score": n["score"],
        "score_delta": n["score"] - o["score"],
        "added": added,
        "resolved": resolved,
        "worsened": worsened,
        "improved": improved,
        "unchanged": len(okeys & nkeys) - len(worsened) - len(improved),
        # a regression = score dropped, or a brand-new critical/high finding
        "regression": score_dropped or bool(new_bad),
        "new_critical_high": new_bad,
        "comparison": comparison,
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
        return "**Regressed** — " + ", ".join(why) + "."
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


def _load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Diff two narwhal JSON reports (regression tracking)")
    ap.add_argument("old", help="earlier report (scan/audit --format json)")
    ap.add_argument("new", help="later report to compare against it")
    ap.add_argument("--format", choices=("markdown", "json"), default="markdown")
    ap.add_argument("-o", "--output")
    ap.add_argument("--fail-on-regression", action="store_true",
                    help="exit non-zero if the score dropped or a new "
                         "critical/high finding appeared; exit 2 for known "
                         "incomparable coverage (for CI gating)")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    try:
        d = diff_reports(_load(args.old), _load(args.new))
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    out = render_json(d) if args.format == "json" else render_markdown(d)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"Wrote {args.format} diff to {args.output} "
              f"(score {d['old_score']} → {d['new_score']})")
    else:
        print(out)

    status = d["comparison"]["status"]
    if status == "unknown":
        print("WARNING: auditor coverage is unverified; legacy finding/score comparison "
              "does not prove matching checks.", file=sys.stderr)
    if args.fail_on_regression and status == "incomparable":
        print("FAIL: report coverage is not comparable; re-scan with matching completed "
              "auditor selections, successful page fetches and full HTML coverage.", file=sys.stderr)
        return 2
    if args.fail_on_regression and d["regression"]:
        print("FAIL: regression detected (score dropped or new high-severity "
              "finding).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
