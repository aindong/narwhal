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


    # ---- HTML renderer ---------------------------------------------------
    def to_html(self, title: str = "SEO & GEO Audit") -> str:
        """A self-contained, styled HTML report (inline CSS, score gauge,
        severity-coloured finding cards). Reuses the same findings model as the
        Markdown/JSON renderers — no logic is duplicated, only presentation."""
        score = self.score()
        grade = _grade(score)
        counts = self.counts()
        target = self.final_url or self.url
        header = _score_header(score, grade, counts, self.fetched_status, self.rendered)
        return html_document(title, target, header + "\n".join(self._html_sections()))

    def _html_sections(self) -> list:
        """Findings rendered as HTML section cards (no document shell / hero).
        Shared by :meth:`to_html` and the combined audit's HTML renderer."""
        score = self.score()
        grade = _grade(score)
        counts = self.counts()
        buckets = self.by_severity()
        body = []

        # Summary + top priorities
        body.append('<section class="card"><h2>Summary</h2>')
        body.append(f"<p>{_inline_md(self._summary_text(score, grade, counts))}</p>")
        priorities = buckets["critical"] + buckets["high"]
        if priorities:
            items = "".join(
                f'<li>{_dot(f.severity)} {_esc(f.title)} '
                f'<span class="muted">({_esc(CATEGORY_LABELS.get(f.category, f.category))})</span></li>'
                for f in priorities[:3]
            )
            body.append(f"<p class=\"lead\">Top priorities</p><ul class=\"clean\">{items}</ul>")
        body.append("</section>")

        # Breakdown by area
        cats = self.by_category()
        if cats:
            rows = []
            for key in ("technical", "content", "schema", "geo"):
                fs = cats.get(key)
                if not fs:
                    continue
                c = {s: sum(1 for f in fs if f.severity == s) for s in SEVERITY}
                cs = self.category_score(fs)
                rows.append(
                    f'<tr><td>{_esc(CATEGORY_LABELS.get(key, key))}</td>'
                    f'<td class="score-cell">{_bar(cs)}<span>{cs}</span></td>'
                    f'<td>{c["critical"] or ""}</td><td>{c["high"] or ""}</td>'
                    f'<td>{c["medium"] or ""}</td><td>{c["low"] or ""}</td>'
                    f'<td>{c["good"] or ""}</td></tr>')
            body.append(
                '<section class="card"><h2>Breakdown by area</h2>'
                '<table class="areas"><thead><tr><th>Area</th><th>Score</th>'
                '<th>🔴</th><th>🟠</th><th>🟡</th><th>🔵</th><th>🟢</th></tr></thead>'
                f'<tbody>{"".join(rows)}</tbody></table></section>')

        # Priority fixes
        priority = buckets["critical"] + buckets["high"] + buckets["medium"]
        if priority:
            body.append('<section class="card"><h2>Priority fixes</h2>')
            for n, f in enumerate(priority, 1):
                body.append(_finding_card(n, f))
            body.append("</section>")

        # Quick wins
        if buckets["low"]:
            items = "".join(
                f'<li>{_dot("low")} <strong>{_esc(f.title)}</strong>'
                + (f' — {_esc(f.recommendation)}' if f.recommendation else "")
                + "</li>"
                for f in buckets["low"])
            body.append(f'<section class="card"><h2>Quick wins</h2>'
                        f'<ul class="clean">{items}</ul></section>')

        # Passing checks
        if buckets["good"]:
            items = "".join(
                f'<li>{_dot("good")} <strong>{_esc(f.title)}</strong>'
                + (f' — {_esc(f.detail)}' if f.detail else "")
                + "</li>"
                for f in buckets["good"])
            body.append(f'<section class="card pass"><h2>Passing checks</h2>'
                        f'<ul class="clean">{items}</ul></section>')

        return body


# --- HTML helpers (shared by Report.to_html and audit.render_html) --------

def _esc(text) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


_SEV_COLOR = {"critical": "#dc2626", "high": "#ea580c", "medium": "#ca8a04",
              "low": "#2563eb", "good": "#16a34a"}
_SEV_LABEL = {"critical": "Critical", "high": "High", "medium": "Medium",
              "low": "Low", "good": "Good"}


def _dot(sev: str) -> str:
    return f'<span class="dot" style="background:{_SEV_COLOR.get(sev, "#888")}"></span>'


def _grade_color(score: int) -> str:
    if score >= 90:
        return "#16a34a"
    if score >= 75:
        return "#65a30d"
    if score >= 55:
        return "#ca8a04"
    if score >= 35:
        return "#ea580c"
    return "#dc2626"


def _bar(score: int) -> str:
    return (f'<span class="bar"><span class="fill" style="width:{max(0, min(100, score))}%;'
            f'background:{_grade_color(score)}"></span></span>')


def score_gauge(score: int) -> str:
    """An SVG donut gauge coloured by grade, score centred."""
    r, cx = 54, 64
    import math
    circ = 2 * math.pi * r
    dash = circ * max(0, min(100, score)) / 100
    color = _grade_color(score)
    return (
        f'<svg viewBox="0 0 128 128" width="128" height="128" class="gauge" '
        f'role="img" aria-label="Health score {score} of 100">'
        f'<circle cx="{cx}" cy="{cx}" r="{r}" fill="none" stroke="#e5e7eb" stroke-width="12"/>'
        f'<circle cx="{cx}" cy="{cx}" r="{r}" fill="none" stroke="{color}" stroke-width="12" '
        f'stroke-linecap="round" stroke-dasharray="{dash:.1f} {circ:.1f}" '
        f'transform="rotate(-90 {cx} {cx})"/>'
        f'<text x="{cx}" y="{cx - 2}" text-anchor="middle" class="g-num">{score}</text>'
        f'<text x="{cx}" y="{cx + 18}" text-anchor="middle" class="g-den">/ 100</text>'
        f'</svg>')


def _score_header(score, grade, counts, status, rendered) -> str:
    chips = "".join(
        f'<span class="chip s-{s}">{counts[s]} {_SEV_LABEL[s]}</span>'
        for s in SEVERITY if counts[s])
    meta = f"status {status}" + ("  ·  JS-rendered" if rendered else "")
    return (
        '<header class="hero">'
        f'{score_gauge(score)}'
        '<div class="hero-txt">'
        f'<div class="grade" style="color:{_grade_color(score)}">{_esc(grade).title()}</div>'
        f'<div class="chips">{chips}</div>'
        f'<div class="muted">{_esc(meta)}</div>'
        '</div></header>')


def _finding_card(n, f) -> str:
    color = _SEV_COLOR.get(f.severity, "#888")
    parts = [
        f'<div class="finding" style="border-left-color:{color}">',
        f'<div class="f-head"><span class="f-num">{n}</span>'
        f'<span class="f-title">{_esc(f.title)}</span>'
        f'<span class="tag" style="background:{color}">{_SEV_LABEL.get(f.severity, f.severity)}</span></div>',
        f'<div class="muted f-cat">{_esc(CATEGORY_LABELS.get(f.category, f.category))}</div>',
    ]
    if f.detail:
        parts.append(f'<p><span class="k">Observed</span> {_esc(f.detail)}</p>')
    if f.evidence:
        parts.append(f'<p><span class="k">Evidence</span> <code>{_esc(_trim(f.evidence))}</code></p>')
    if f.recommendation:
        parts.append(f'<p><span class="k">Fix</span> {_esc(f.recommendation)}</p>')
    parts.append("</div>")
    return "".join(parts)


_HTML_CSS = """
:root{--fg:#1f2933;--muted:#6b7280;--bg:#f7f8fa;--card:#fff;--border:#e5e7eb;
--brand:#14b8a6;--radius:12px}
*{box-sizing:border-box}
body{margin:0;padding:32px 20px;background:var(--bg);color:var(--fg);
font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:820px;margin:0 auto}
h1{font-size:22px;margin:0 0 2px}
h2{font-size:16px;margin:0 0 14px;padding-bottom:8px;border-bottom:1px solid var(--border)}
.sub{color:var(--muted);margin:0 0 24px;word-break:break-all}
.brand{display:flex;align-items:center;gap:16px;margin:0 0 24px}
.brand-logo{display:block;width:auto;flex:0 0 auto}
.brand-txt h1{margin:0}
.brand-txt .sub{margin:2px 0 0}
.foot .brand-logo{vertical-align:middle;margin-right:6px}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
padding:20px 22px;margin:0 0 18px}
.card.pass h2{border-color:#dcfce7}
.hero{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
padding:22px;margin:0 0 18px;display:flex;gap:22px;align-items:center}
.gauge{flex:0 0 auto}
.g-num{font-size:30px;font-weight:700;fill:var(--fg)}
.g-den{font-size:12px;fill:var(--muted)}
.grade{font-size:24px;font-weight:700;text-transform:capitalize}
.chips{margin:8px 0;display:flex;flex-wrap:wrap;gap:6px}
.chip{font-size:12px;font-weight:600;padding:3px 9px;border-radius:20px;color:#fff}
.s-critical{background:#dc2626}.s-high{background:#ea580c}.s-medium{background:#ca8a04}
.s-low{background:#2563eb}.s-good{background:#16a34a}
.muted{color:var(--muted);font-size:13px}
.lead{font-weight:600;margin:14px 0 6px}
ul.clean{list-style:none;padding:0;margin:0}
ul.clean li{padding:5px 0;border-bottom:1px solid #f0f1f3}
ul.clean li:last-child{border-bottom:0}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px;vertical-align:middle}
table{width:100%;border-collapse:collapse;font-size:14px}
table.areas th,table.areas td{padding:8px 6px;text-align:center;border-bottom:1px solid var(--border)}
table.areas th:first-child,table.areas td:first-child{text-align:left}
.score-cell{white-space:nowrap}
.score-cell span{margin-left:8px;font-weight:600}
.bar{display:inline-block;width:70px;height:8px;background:#eef0f2;border-radius:4px;overflow:hidden;vertical-align:middle}
.bar .fill{display:block;height:100%}
.finding{background:#fbfcfd;border:1px solid var(--border);border-left-width:4px;
border-radius:8px;padding:14px 16px;margin:0 0 12px}
.f-head{display:flex;align-items:center;gap:10px}
.f-num{font-weight:700;color:var(--muted)}
.f-title{font-weight:600;flex:1}
.tag{color:#fff;font-size:11px;font-weight:600;padding:2px 8px;border-radius:6px;text-transform:uppercase;letter-spacing:.02em}
.f-cat{margin:2px 0 8px 24px}
.finding p{margin:6px 0}
.k{display:inline-block;min-width:70px;font-weight:600;color:var(--muted);font-size:12px;
text-transform:uppercase;letter-spacing:.03em}
code{background:#f0f1f3;padding:1px 5px;border-radius:4px;font-size:12.5px;word-break:break-all}
.section{font-size:18px;margin:28px 0 14px;border:0;padding:0}
.metrics{display:flex;flex-wrap:wrap;gap:18px 26px;margin-top:6px}
.metric{display:flex;flex-direction:column}
.m-num{font-size:20px;font-weight:700}
.m-lab{font-size:12px;color:var(--muted)}
.foot{color:var(--muted);font-size:12px;text-align:center;margin:24px 0 0}
.foot a{color:var(--brand);text-decoration:none}
@media print{body{background:#fff;padding:0}.card,.hero,.finding{break-inside:avoid}}
"""


def html_document(title: str, subtitle: str, body: str) -> str:
    """Wrap rendered body HTML in a self-contained, print-friendly document.

    The Narwhal mark is embedded inline (base64 data URI) so the report stays
    self-contained — no external image request, works offline and in PDF."""
    try:
        from lib import brand  # noqa: PLC0415
        header_logo = brand.logo_img(46)
        foot_logo = brand.logo_img(16)
    except Exception:  # noqa: BLE001 — branding is cosmetic; never fail a report over it
        header_logo = foot_logo = ""
    return (
        "<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{_esc(title)} — {_esc(subtitle)}</title>"
        f"<style>{_HTML_CSS}</style></head><body><div class=\"wrap\">"
        f'<header class="brand">{header_logo}<div class="brand-txt">'
        f'<h1>{_esc(title)}</h1><p class="sub">{_esc(subtitle)}</p></div></header>'
        f"{body}"
        f'<p class="foot">{foot_logo}Generated by '
        '<a href="https://github.com/aindong/narwhal">Narwhal</a> · '
        'local-first SEO &amp; GEO/LLMO scanning</p>'
        "</div></body></html>\n")


def _inline_md(text: str) -> str:
    """Inline Markdown -> HTML for the subset our renderers emit: `code`,
    **bold**, and bare URLs. Input is escaped first, so this is XSS-safe."""
    import re
    out = _esc(text)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    # [text](http…) links — before other spans; URL restricted to http(s).
    out = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
                 r'<a href="\2">\1</a>', out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    # _italic_ — only at word boundaries so snake_case / paths aren't matched.
    out = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"<em>\1</em>", out)
    return out


def md_to_html(md: str) -> str:
    """Convert the limited Markdown our sub-reports emit (headings, tables,
    lists, blockquotes, `---`, bold/code) into styled HTML. This is not a
    general Markdown engine — it only needs to cover what crawl_site and
    validate_sitemap produce, so the combined audit can render them as HTML
    without duplicating their logic."""
    lines = md.splitlines()
    out, i, n = [], 0, len(lines)

    def close_list(stack):
        while stack:
            out.append(f"</{stack.pop()}>")

    list_stack = []
    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Table: a header row followed by a |:--| separator row
        if (stripped.startswith("|") and i + 1 < n
                and set(lines[i + 1].strip()) <= set("|:- ")
                and "-" in lines[i + 1]):
            close_list(list_stack)
            headers = [c.strip() for c in stripped.strip("|").split("|")]
            out.append('<table><thead><tr>'
                       + "".join(f"<th>{_inline_md(h)}</th>" for h in headers)
                       + "</tr></thead><tbody>")
            i += 2
            while i < n and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                out.append("<tr>" + "".join(f"<td>{_inline_md(c)}</td>" for c in cells)
                           + "</tr>")
                i += 1
            out.append("</tbody></table>")
            continue

        if not stripped:
            close_list(list_stack)
            i += 1
            continue

        if stripped == "---":
            close_list(list_stack)
            out.append("<hr>")
        elif stripped.startswith("#"):
            close_list(list_stack)
            level = len(stripped) - len(stripped.lstrip("#"))
            level = min(max(level, 1), 6)
            out.append(f"<h{level}>{_inline_md(stripped[level:].strip())}</h{level}>")
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not list_stack:
                out.append("<ul>")
                list_stack.append("ul")
            out.append(f"<li>{_inline_md(stripped[2:])}</li>")
        elif stripped.startswith(">"):
            close_list(list_stack)
            out.append(f'<blockquote>{_inline_md(stripped.lstrip("> ").strip())}</blockquote>')
        else:
            close_list(list_stack)
            out.append(f"<p>{_inline_md(stripped)}</p>")
        i += 1
    close_list(list_stack)
    return "\n".join(out)


def pdf_from_html(html: str, path: str) -> bool:
    """Render ``html`` to a PDF at ``path`` using WeasyPrint if available.

    Returns True on success, False if WeasyPrint isn't installed (the caller
    then falls back to writing HTML — see the ``--format pdf`` handling). Any
    other WeasyPrint error propagates so the user sees the real cause.
    """
    try:
        from weasyprint import HTML  # type: ignore
    except (ImportError, OSError):
        # ImportError: package absent. OSError: package present but its native
        # libraries (pango/cairo/…) aren't — treat both as "no PDF, use HTML".
        return False
    HTML(string=html).write_pdf(path)
    return True


def deliver(fmt: str, output, content: str, *, label: str = "report",
            score=None) -> int:
    """Write or print a rendered report, handling the PDF path uniformly for
    both scan.py and audit.py. For ``fmt == 'pdf'``, ``content`` must be the
    HTML source; this converts it via WeasyPrint, or gracefully falls back to
    writing the HTML when WeasyPrint isn't installed. Returns a process exit
    contribution (0 = fine, 2 = usage error) so callers can bail early."""
    import sys
    score_txt = f" (score {score}/100)" if score is not None else ""
    if fmt == "pdf":
        if not output:
            print("--format pdf requires -o/--output (PDF is binary).",
                  file=sys.stderr)
            return 2
        if pdf_from_html(content, output):
            print(f"Wrote PDF {label} to {output}{score_txt}")
            return 0
        html_path = (output[:-4] + ".html"
                     if output.lower().endswith(".pdf") else output + ".html")
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        print(f"WeasyPrint not installed - wrote HTML {label} to {html_path}"
              f"{score_txt} instead.\nInstall it for PDF export: "
              f"pip install weasyprint", file=sys.stderr)
        return 0
    if output:
        with open(output, "w", encoding="utf-8") as fh:
            fh.write(content)
        print(f"Wrote {fmt} {label} to {output}{score_txt}")
    else:
        print(content)
    return 0


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
