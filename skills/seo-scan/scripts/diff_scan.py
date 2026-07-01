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
and overall score are used).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Ordered worst -> best; lower index == more severe.
SEVERITY = ("critical", "high", "medium", "low", "good")
_RANK = {s: i for i, s in enumerate(SEVERITY)}
_ICON = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "good": "🟢"}
_CATS = {"technical": "Technical SEO", "content": "Content & E-E-A-T",
         "schema": "Structured data", "geo": "GEO / LLMO"}


def _normalize(data: dict) -> dict:
    """Reduce a scan or audit JSON payload to {url, score, findings}."""
    if "findings" in data:  # single-page scan report
        return {"url": data.get("final_url") or data.get("url", ""),
                "score": data.get("score", 0),
                "findings": data.get("findings", [])}
    if "homepage" in data:  # comprehensive audit report
        hp = data.get("homepage", {})
        return {"url": data.get("site") or hp.get("url", ""),
                "score": data.get("overall_score", hp.get("score", 0)),
                "findings": hp.get("findings", [])}
    raise ValueError(
        "Unrecognized report JSON — expected `narwhal scan` or `narwhal audit` "
        "output produced with `--format json`.")


def _key(finding: dict):
    """Stable identity for a finding across runs.

    Titles can carry a dynamic suffix (e.g. "Thin content (210 words)"); we
    strip a trailing parenthetical so the same issue matches run-to-run even as
    the measured number changes."""
    title = str(finding.get("title", ""))
    base = title.split(" (")[0].strip().lower()
    return (finding.get("category", ""), base)


def _worse(a: str, b: str) -> bool:
    """True if severity ``a`` is more severe than ``b``."""
    return _RANK.get(a, 99) < _RANK.get(b, 99)


def diff_reports(old: dict, new: dict) -> dict:
    o, n = _normalize(old), _normalize(new)
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
    }


def _verdict(d: dict) -> str:
    delta = d["score_delta"]
    if d["regression"]:
        why = []
        if delta < 0:
            why.append(f"score dropped {abs(delta)}")
        if d["new_critical_high"]:
            why.append(f"{len(d['new_critical_high'])} new high-severity issue(s)")
        return "**Regressed** — " + ", ".join(why) + "."
    if delta > 0 or d["resolved"] or d["improved"]:
        return "**Improved** — health is better than the previous run."
    return "**No material change** since the previous run."


def render_markdown(d: dict) -> str:
    delta = d["score_delta"]
    sign = f"+{delta}" if delta > 0 else (str(delta) if delta < 0 else "±0")
    lines = [
        f"# Narwhal Scan Diff — {d['url']}",
        "",
        f"**Score: {d['old_score']} → {d['new_score']} ({sign})**",
        "",
        _verdict(d),
        "",
    ]

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
                         "critical/high finding appeared (for CI gating)")
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

    if args.fail_on_regression and d["regression"]:
        print("FAIL: regression detected (score dropped or new high-severity "
              "finding).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
