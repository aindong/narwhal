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

    def score(self) -> int:
        weights = self.weights or _WEIGHT
        penalty = sum(weights.get(f.severity, _WEIGHT[f.severity])
                      for f in self.findings)
        return max(0, 100 - penalty)

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

    def to_markdown(self) -> str:
        score = self.score()
        grade = _grade(score)
        counts = self.counts()
        lines = [
            f"# SEO & GEO Scan — {self.final_url or self.url}",
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
        buckets = self.by_severity()
        issue_order = ("critical", "high", "medium", "low")
        if any(buckets[s] for s in issue_order):
            lines.append("## Prioritized fixes")
            lines.append("")
            n = 1
            for sev in issue_order:
                for f in buckets[sev]:
                    lines.append(f"### {n}. {_ICON[sev]} {f.title}  ")
                    lines.append(f"*{f.category} · {sev}*")
                    lines.append("")
                    if f.detail:
                        lines.append(f"- **Observed:** {f.detail}")
                    if f.evidence:
                        lines.append(f"- **Evidence:** `{_trim(f.evidence)}`")
                    if f.recommendation:
                        lines.append(f"- **Fix:** {f.recommendation}")
                    lines.append("")
                    n += 1
        if buckets["good"]:
            lines.append("## Passing checks")
            lines.append("")
            for f in buckets["good"]:
                extra = f" — {f.detail}" if f.detail else ""
                lines.append(f"- 🟢 **{f.title}**{extra}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"


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
