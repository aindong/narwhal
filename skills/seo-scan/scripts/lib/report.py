"""Findings model and report renderers (Markdown + JSON).

Every auditor emits :class:`Finding` objects into a :class:`Report`. Severity
drives ordering and the headline score so the output is action-first: the reader
sees what to fix and why, not a wall of raw data.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Optional

# Ordered worst -> best. Weights feed the 0-100 health score.
SEVERITY = ("critical", "high", "medium", "low", "good")
_WEIGHT = {"critical": 12, "high": 6, "medium": 3, "low": 1, "good": 0}
_ICON = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "good": "🟢"}
CATEGORY_LABELS = {
    "technical": "Technical SEO",
    "content": "Content & E-E-A-T",
    "schema": "Structured data",
    "geo": "GEO / LLMO",
}


@dataclass
class Finding:
    category: str            # technical | content | schema | geo
    severity: str            # one of SEVERITY
    title: str               # short problem statement
    detail: str = ""         # what was observed
    recommendation: str = "" # concrete fix
    evidence: Optional[str] = None  # snippet / value

    def __post_init__(self):
        if self.severity not in SEVERITY:
            raise ValueError(f"bad severity: {self.severity}")


@dataclass
class Report:
    url: str
    final_url: str = ""
    fetched_status: int = 0
    rendered: bool = False
    findings: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    weights: dict = None          # override severity penalties (from config)
    ignore: object = None         # callable(category, title) -> bool

    def add(self, *args, **kwargs) -> None:
        finding = Finding(*args, **kwargs)
        if self.ignore and self.ignore(finding.category, finding.title):
            return  # suppressed by config ignore rules
        self.findings.append(finding)

    def ok(self, category: str, title: str, detail: str = "") -> None:
        self.add(category, "good", title, detail)

    def by_severity(self) -> dict:
        buckets = {s: [] for s in SEVERITY}
        for f in self.findings:
            buckets[f.severity].append(f)
        return buckets

    def by_category(self) -> dict:
        cats = {}
        for f in self.findings:
            cats.setdefault(f.category, []).append(f)
        return cats

    def _penalty(self, findings) -> int:
        weights = self.weights or _WEIGHT
        return sum(weights.get(f.severity, _WEIGHT[f.severity]) for f in findings)

    def score(self) -> int:
        return max(0, 100 - self._penalty(self.findings))

    def category_score(self, findings) -> int:
        return max(0, 100 - self._penalty(findings))

    def counts(self) -> dict:
        b = self.by_severity()
        return {s: len(b[s]) for s in SEVERITY}

    # ---- renderers -------------------------------------------------------
    def to_json(self) -> str:
        return json.dumps(
            {
                "url": self.url,
                "final_url": self.final_url,
                "status": self.fetched_status,
                "rendered": self.rendered,
                "score": self.score(),
                "counts": self.counts(),
                "meta": self.meta,
                "findings": [asdict(f) for f in self.findings],
            },
            indent=2,
            ensure_ascii=False,
        )

    def to_markdown(self, title: str = "SEO & GEO Audit") -> str:
        score = self.score()
        grade = _grade(score)
        counts = self.counts()
        buckets = self.by_severity()
        lines = [
            f"# {title} — {self.final_url or self.url}",
            "",
            f"**Health score: {score}/100 ({grade})**  ·  "
            f"status {self.fetched_status}"
            + ("  ·  JS-rendered" if self.rendered else ""),
            "",
            "| Critical | High | Medium | Low | Passed |",
            "|:--:|:--:|:--:|:--:|:--:|",
            f"| {counts['critical']} | {counts['high']} | {counts['medium']} "
            f"| {counts['low']} | {counts['good']} |",
            "",
        ]

        # --- Executive summary ---------------------------------------------
        lines.append("## Summary")
        lines.append("")
        lines.append(self._summary_text(score, grade, counts))
        lines.append("")
        priorities = buckets["critical"] + buckets["high"]
        if priorities:
            lines.append("**Top priorities:**")
            for f in priorities[:3]:
                lines.append(f"- {_ICON[f.severity]} {f.title} "
                             f"({CATEGORY_LABELS.get(f.category, f.category)})")
            lines.append("")

        # --- Breakdown by area ---------------------------------------------
        cats = self.by_category()
        if cats:
            lines.append("## Breakdown by area")
            lines.append("")
            lines.append("| Area | Score | 🔴 | 🟠 | 🟡 | 🔵 | 🟢 |")
            lines.append("|:--|:--:|:--:|:--:|:--:|:--:|:--:|")
            for key in ("technical", "content", "schema", "geo"):
                fs = cats.get(key)
                if not fs:
                    continue
                c = {s: sum(1 for f in fs if f.severity == s) for s in SEVERITY}
                lines.append(
                    f"| {CATEGORY_LABELS.get(key, key)} | {self.category_score(fs)} "
                    f"| {c['critical']} | {c['high']} | {c['medium']} | {c['low']} "
                    f"| {c['good']} |")
            lines.append("")

        # --- Priority fixes (critical + high + medium) ---------------------
        priority = buckets["critical"] + buckets["high"] + buckets["medium"]
        if priority:
            lines.append("## Priority fixes")
            lines.append("")
            for n, f in enumerate(priority, 1):
                lines.append(f"### {n}. {_ICON[f.severity]} {f.title}  ")
                lines.append(f"*{CATEGORY_LABELS.get(f.category, f.category)} · "
                             f"{f.severity}*")
                lines.append("")
                if f.detail:
                    lines.append(f"- **Observed:** {f.detail}")
                if f.evidence:
                    lines.append(f"- **Evidence:** `{_trim(f.evidence)}`")
                if f.recommendation:
                    lines.append(f"- **Fix:** {f.recommendation}")
                lines.append("")

        # --- Quick wins (low severity) -------------------------------------
        if buckets["low"]:
            lines.append("## Quick wins")
            lines.append("")
            for f in buckets["low"]:
                fix = f" — {f.recommendation}" if f.recommendation else ""
                lines.append(f"- 🔵 **{f.title}**{fix}")
            lines.append("")

        # --- Passing checks ------------------------------------------------
        if buckets["good"]:
            lines.append("## Passing checks")
            lines.append("")
            for f in buckets["good"]:
                extra = f" — {f.detail}" if f.detail else ""
                lines.append(f"- 🟢 **{f.title}**{extra}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def _summary_text(self, score, grade, counts) -> str:
        crit, high = counts["critical"], counts["high"]
        med, low = counts["medium"], counts["low"]
        prio = crit + high
        target = self.final_url or self.url
        if prio == 0 and med == 0:
            lead = (f"This page is in **{grade}** shape ({score}/100) — no critical, "
                    f"high, or medium issues found.")
        else:
            bits = []
            if crit:
                bits.append(f"{crit} critical")
            if high:
                bits.append(f"{high} high")
            if med:
                bits.append(f"{med} medium")
            lead = (f"This page scores **{score}/100 ({grade})**. "
                    f"{', '.join(bits)} issue(s) need attention"
                    + (f", plus {low} quick win(s)." if low else "."))
        return lead


def below_threshold(score, threshold) -> bool:
    """True when a `--fail-under` gate should fail the run.

    ``threshold`` of None means no gate (always passes). Used by scan.py and
    crawl_site.py to drive a non-zero exit code for CI quality gating.
    """
    return threshold is not None and score < threshold


def _grade(score: int) -> str:
    if score >= 90:
        return "excellent"
    if score >= 75:
        return "good"
    if score >= 55:
        return "needs work"
    if score >= 35:
        return "poor"
    return "critical"


def _trim(text: str, limit: int = 160) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
