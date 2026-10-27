"""Findings model and report renderers (Markdown + JSON).

Every auditor emits :class:`Finding` objects into a :class:`Report`. Severity
drives ordering and the headline score so the output is action-first: the reader
sees what to fix and why, not a wall of raw data.
"""

from __future__ import annotations

import json
import re
import string
from dataclasses import asdict, dataclass, field
from typing import Optional

from .guides import reference_url
from . import sitemap as sitemaplib
from . import llms_resource
from . import authorship
from . import content_length
from . import schema_coverage
from . import canonical
from . import links as linklib
from . import hreflang as hreflanglib
from . import date_cues
from . import readability_observation
from .code_fences import closes_fence, markdown_lines, opening_fence
from .markdown_text import TABLE_TEXT_MARKER

REPORT_SCHEMA_VERSION = "2.0"

if __package__ and "." in __package__:
    from .._version import __version__ as TOOL_VERSION
else:  # loose-script/plugin execution (``lib.report``)
    from _version import __version__ as TOOL_VERSION

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

_QUICK_PREVIEW_LIMIT = 400
_QUICK_PREVIEW_NOTE = (
    'Observations below are bounded, whitespace-normalized previews of reported fields, '
    'not independent verification. Full fields remain in JSON.'
)

TRUNCATED_HTML_ERROR = (
    "HTML response was truncated; complete HTML is required for comparisons and briefs."
)
PARTIAL_HTML_ERROR = 'HTML response was partial/ranged; full-page observations and comparisons are unverified.'
UNVERIFIED_JS_COMPARISON_ERROR = (
    "JS-dependence is unverified; complete paired HTML is required for page-score comparisons."
)
UNVERIFIED_SITEMAP_DISCOVERY_ERROR = 'Sitemap availability was not verified from a supported XML root; technical-score comparison is unverified.'
UNVERIFIED_LLMS_ERROR = 'Root llms.txt availability is unverified; GEO-score comparison is unverified.'
UNVERIFIED_IMAGE_WEIGHT_ERROR = 'Image weights need verification; technical/overall score comparisons are unverified.'
_JS_COMPARISON_PROBLEMS = {
    "rendered_html_truncated": "rendered HTML was truncated",
    "served_html_truncated": "served HTML was truncated",
    "served_html_partial": "served HTML had range evidence and was partial/unassessed",
    "served_html_unavailable": "served HTML was unavailable",
    "served_non_html": "the served baseline was not HTML",
}


def recorded_js_comparison_problem(meta, *, for_score=False):
    """Describe a recorded missing JS measurement, without guessing legacy data."""
    coverage = meta.get("coverage") if isinstance(meta, dict) else None
    receipt = coverage.get("js_comparison") if isinstance(coverage, dict) else None
    if not isinstance(receipt, dict) or receipt.get("status") != "unverified":
        return None
    if for_score:
        scope = recorded_scan_scope(meta)
        if scope is not None and not set(scope[0]) & {"technical", "geo"}:
            return None
    reason = receipt.get("reason")
    return (_JS_COMPARISON_PROBLEMS.get(reason, "a required HTML snapshot was not measured")
            if isinstance(reason, str) else "a required HTML snapshot was not measured")


def recorded_response_truncated(meta):
    """Recognize explicit truncation, not certify missing/legacy coverage."""
    if not isinstance(meta, dict):
        return False
    coverage = meta.get("coverage")
    return meta.get("response_truncated") is True or (
        isinstance(coverage, dict) and coverage.get("response_truncated") is True)


def recorded_execution_problem(page):
    """Acquisition failures or malformed execution data; absence is not completeness.

    Callers retain their separate measured partial/truncation coverage checks.
    """
    if not isinstance(page, dict):
        return 'has unsupported page execution evidence.'
    if page.get('hard_fail') is True:
        return 'records a hard-failed page acquisition.'
    if 'hard_fail' in page and type(page['hard_fail']) is not bool:
        return 'has a malformed acquisition failure flag.'
    status = page.get('status')
    if 'status' in page and (type(status) is not int or status == 206 or not 200 <= status < 300):
        return 'records an unusable acquisition status.'
    contexts = [page]
    if isinstance(page.get('meta'), dict):
        contexts.append(page['meta'])
    for meta in contexts:
        settings = meta.get('scan_settings')
        if (type(page.get('rendered')) is bool and isinstance(settings, dict)
                and type(settings.get('rendered')) is bool and page['rendered'] != settings['rendered']):
            return 'records contradictory actual rendering flags.'
        flags = [meta[key] for key in ('response_truncated', 'response_partial') if key in meta]
        coverage = meta.get('coverage')
        if isinstance(coverage, dict) and 'response_truncated' in coverage:
            flags.append(coverage['response_truncated'])
        if any(type(value) is not bool for value in flags):
            return 'has malformed response-completeness flags.'
        if recorded_response_partial(meta):
            return 'records partial/ranged HTML coverage.'
        if recorded_response_truncated(meta):
            return 'records truncated HTML coverage.'
    return None


def recorded_response_partial(meta):
    """Known range/partial evidence, not an absence-of-receipt completeness pass.

    Current receipts contain counts/flags, not raw Content-Range. Historical
    snapshot receipts can expose partial evidence even if old auditors ran.
    A contradictory known HTTP 206 receipt stays unassessed, never certified.
    """
    if not isinstance(meta, dict):
        return False
    from .http import SERVER_RANGE_BASIS
    coverage = meta.get('coverage')
    receipt = coverage.get('server_range') if isinstance(coverage, dict) else None
    if meta.get('response_partial') is True or (isinstance(receipt, dict)
            and receipt.get('basis') == SERVER_RANGE_BASIS and receipt.get('observed') is True):
        return True
    supplied = meta.get('hreflang_source_observation')
    if (isinstance(supplied, dict) and supplied.get('basis') == hreflanglib.SNAPSHOT_BASIS
            and type(supplied.get('http_status')) is int and supplied['http_status'] == 206):
        return True
    snapshot = hreflanglib.recorded_observation(meta)
    return bool(snapshot and snapshot['status'] == 'partial' and not recorded_response_truncated(meta))


def recorded_sitemap_discovery_problem(meta, *, for_score=False):
    """Keep site-discovery gaps visible without inferring absent legacy receipts."""
    value = meta.get('sitemap_discovery') if isinstance(meta, dict) else None
    note = sitemaplib.discovery_note(value)
    if for_score:
        scope = recorded_scan_scope(meta)
        if scope is not None and 'technical' not in scope[0]:
            return None
        receipt = sitemaplib.recorded_discovery(value)
        if receipt and receipt['verified_files']:
            return None  # availability of at least one supported root was measured
    return note


def recorded_image_weight_problem(meta, *, for_score=False):
    """Use explicit image-weight coverage; do not infer legacy measurements."""
    scope = recorded_scan_scope(meta) if isinstance(meta, dict) else None
    if for_score and scope is not None and 'technical' not in scope[0]:
        return None
    if not isinstance(meta, dict) or 'images' not in meta:
        return None
    receipt = meta['images']
    if not isinstance(receipt, dict):
        return UNVERIFIED_IMAGE_WEIGHT_ERROR
    if not {'weight_verified', 'weight_unverified'} & receipt.keys():
        return None
    checked, verified, unknown = (receipt.get(key) for key in ('checked', 'weight_verified', 'weight_unverified'))
    if (any(type(value) is not int or value < 0 for value in (checked, verified, unknown))
            or verified + unknown != checked or unknown):
        return UNVERIFIED_IMAGE_WEIGHT_ERROR
    return None


def recorded_llms_problem(meta, *, for_score=False):
    """Interpret explicit root-response uncertainty only for selected GEO checks."""
    scope = recorded_scan_scope(meta) if isinstance(meta, dict) else None
    if for_score and scope is not None and 'geo' not in scope[0]:
        return None
    return llms_resource.problem(meta, for_score=for_score)


def recorded_schema_extraction_problem(meta, *, for_score=False):
    """Keep explicit extractor gaps visible, without inferring old coverage."""
    scope = recorded_scan_scope(meta) if isinstance(meta, dict) else None
    if for_score and scope is not None and 'schema' not in scope[0]:
        return None
    settings = meta.get('scan_settings') if isinstance(meta, dict) else None
    data = meta.get('structured_data') if isinstance(meta, dict) else None
    legacy_warning = isinstance(data, dict) and any(
        isinstance(data.get(key), list) and bool(data[key]) for key in ('microdata_warnings', 'rdfa_warnings'))
    unsupported = ((isinstance(meta, dict) and 'structured_data' in meta and not isinstance(data, dict))
                   or (isinstance(data, dict) and 'extraction_coverage' in data
                       and schema_coverage.recorded(data['extraction_coverage']) is None))
    if (schema_coverage.state(schema_coverage.meta_receipt(meta)) == 'unverified'
            or recorded_response_partial(meta) or recorded_response_truncated(meta)
            or legacy_warning or unsupported or isinstance(settings, dict) and 'schema_extraction_reviewed' in settings
            and settings['schema_extraction_reviewed'] is not True):
        return 'Structured-data extraction needs verification; schema/overall score comparisons are unverified.'
    return None


def _crawler_policy_notes(meta):
    """Read explicit informational notes without reinterpreting legacy metadata."""
    receipt = meta.get("ai_crawler_access") if isinstance(meta, dict) else None
    if (not isinstance(receipt, dict) or type(receipt.get("version")) is not int
            or receipt["version"] != 1 or receipt.get("basis") != "robots_txt_only"
            or receipt.get("checked_path") != "/"):
        return []
    notes = receipt.get("notes")
    if not isinstance(notes, list):
        return []
    result = []
    for note in notes:
        if not isinstance(note, dict) or not all(
                isinstance(note.get(key), str) and note[key] for key in ("agent", "text")):
            continue
        source = note.get("source")
        result.append({"agent": note["agent"], "text": note["text"],
                       "source": source if isinstance(source, str) and source.startswith("https://") else None})
    return result


def _http_robots_notes(meta):
    """Read bounded non-scoring header notes only from the known receipt shape."""
    receipt = meta.get('http_robots') if isinstance(meta, dict) else None
    if (not isinstance(receipt, dict) or type(receipt.get('version')) is not int
            or receipt['version'] != 1 or receipt.get('basis') not in
            ('response_header_fields', 'browser_reported_fields', 'merged_or_unknown')):
        return []
    notes = receipt.get('notes')
    if not isinstance(notes, list):
        return []
    valid = [note for note in notes if isinstance(note, str)]
    result = ['Only noindex/nofollow and the none alias are interpreted. Preview/date rules, '
              'crawler support, actual access and live indexing are not verified.']
    result.extend(note[:600] for note in valid[:20])
    if len(valid) > 20:
        result.append(f'{len(valid) - 20} more observations are retained in meta.http_robots.')
    return result


def _crawler_meta_notes(meta):
    """Render only known, typed named-meta observations; never infer old data."""
    receipt = meta.get('crawler_meta_robots') if isinstance(meta, dict) else None
    if (not isinstance(receipt, dict) or type(receipt.get('version')) is not int
            or receipt['version'] != 1 or receipt.get('basis') != 'active_document_meta'
            or not isinstance(receipt.get('observations'), list)):
        return []
    notes = []
    for item in receipt['observations']:
        if not isinstance(item, dict) or item.get('agent') not in ('googlebot', 'googlebot-news'):
            continue
        directives, positions = item.get('directives'), item.get('tag_positions')
        if (not isinstance(directives, list) or not directives
                or any(value not in ('noindex', 'nofollow') for value in directives)
                or not isinstance(positions, list) or not positions
                or any(type(position) is not int or position < 1 for position in positions)):
            continue
        notes.append(f'{item["agent"]} declares {", ".join(sorted(set(directives)))} '
                     f'in metadata tag position(s) {", ".join(str(n) for n in sorted(set(positions))[:2])}. '
                     'Engine-specific declaration, not an all-crawler restriction.')
    return (['Observed googlebot/googlebot-news meta only; other agents and preview/date rules are not evaluated here. '
             'Review intended policy manually. This is not proof of live crawling or indexing.'] + notes[:2]) if notes else []


def recorded_scan_scope(meta):
    """Validate recorded execution without inferring coverage from findings."""
    scope = meta.get("scan_scope") if isinstance(meta, dict) else None
    if not isinstance(scope, dict):
        return None
    requested, completed = scope.get("requested"), scope.get("completed")
    if not isinstance(requested, list) or not isinstance(completed, list) or not requested:
        return None
    if any(not isinstance(name, str) or name not in CATEGORY_LABELS for name in requested + completed):
        return None
    if len(set(requested)) != len(requested) or len(set(completed)) != len(completed):
        return None
    if not set(completed) <= set(requested):
        return None
    if 'not_selected' in scope:
        skipped = scope['not_selected']
        if (not isinstance(skipped, list) or any(not isinstance(name, str) for name in skipped)
                or len(set(skipped)) != len(skipped)
                or set(skipped) != set(CATEGORY_LABELS) - set(requested)):
            return None
    return requested, completed


@dataclass
class Finding:
    category: str            # technical | content | schema | geo
    severity: str            # one of SEVERITY
    title: str               # short problem statement
    detail: str = ""         # what was observed
    recommendation: str = "" # concrete fix
    evidence: Optional[str] = None  # snippet / value
    rule_id: str = ""          # stable machine identity; title remains presentation
    scope: str = "page"        # page | site | external
    confidence: float = 1.0     # 0..1; heuristic rules may lower this

    def __post_init__(self):
        if self.severity not in SEVERITY:
            raise ValueError(f"bad severity: {self.severity}")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not self.rule_id:
            base = self.title.split(" (")[0].strip().lower()
            slug = re.sub(r"[^a-z0-9]+", ".", base).strip(".")
            self.rule_id = f"{self.category}.{slug}"

    @property
    def reference_url(self):
        """Guide context for a non-passing check, never a validity verdict."""
        return None if self.severity == 'good' else reference_url(self.category, self.rule_id)


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
    hard_fail: bool = False       # unfetchable page -> score is 0, not 100-12

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
        scope = self._scope_info()
        if self.hard_fail or (scope is not None and not scope[1]):
            # A page we couldn't fetch has no measurable health — reporting
            # "88/100" (100 minus one critical) was found misleading in tuning.
            return 0
        return max(0, 100 - self._penalty(self.findings))

    def category_score(self, findings) -> int:
        return max(0, 100 - self._penalty(findings))

    def counts(self) -> dict:
        b = self.by_severity()
        return {s: len(b[s]) for s in SEVERITY}

    def _scope_info(self):
        """Use recorded execution, never infer auditor coverage from findings."""
        return recorded_scan_scope(self.meta)

    def score_label(self) -> str:
        """Name the numerical score's measured scope without changing its value."""
        if self.hard_fail:
            return "Score unavailable"
        scope = self._scope_info()
        if scope is None:
            return "Reported-findings score"
        requested, completed = scope
        if not completed:
            return "Score unavailable"
        if recorded_response_partial(self.meta) or self.fetched_status == 206:
            return 'Reported-findings score'
        if set(completed) != set(requested) or set(requested) != set(CATEGORY_LABELS):
            return "Selected-check score"
        return "Health score"

    def _scope_note(self) -> str:
        scope = self._scope_info()
        discovery = recorded_sitemap_discovery_problem(self.meta)
        llms = recorded_llms_problem(self.meta)
        schema = recorded_schema_extraction_problem(self.meta, for_score=True)
        image_weight = recorded_image_weight_problem(self.meta, for_score=True)
        discovery_suffix = ((' ' + discovery if discovery else '') + (' ' + llms if llms else '')
                            + (' ' + schema if schema else '')
                            + (' ' + image_weight if image_weight else '')
                            + (' ' + canonical.ERROR if canonical.unverified(self.meta) else '')
                            + (' ' + linklib.BASE_ERROR if linklib.unassessed_base(self.meta) else '')
                            + (' ' + hreflanglib.ERROR if hreflanglib.unverified(self.meta, for_score=True) else '')
                            + (' ' + PARTIAL_HTML_ERROR if recorded_response_partial(self.meta) or self.fetched_status == 206 else ''))
        if scope is None:
            if self.hard_fail:
                return "The zero score is a fail-safe, not measured page health; auditor selection was not recorded." + discovery_suffix
            return "Auditor selection was not recorded; do not infer overall page health from this score." + discovery_suffix
        requested, completed = scope
        labels = lambda names: "; ".join(CATEGORY_LABELS[name] for name in names)
        if not completed:
            return f"No auditor groups completed. Requested: {labels(requested)}. The zero score is a fail-safe, not measured page health." + discovery_suffix
        note = f"Checked auditor groups: {labels(completed)}."
        pending = [name for name in requested if name not in completed]
        skipped = [name for name in CATEGORY_LABELS if name not in requested]
        if pending:
            note += f" Not completed: {labels(pending)}."
        if skipped:
            note += f" Not selected: {labels(skipped)}."
        if pending or skipped:
            note += " Score reflects completed selected checks and response-level findings, not overall page health."
        else:
            note += " All four groups ran for this page, not a site-wide or exhaustive validation."
        coverage = self.meta.get("coverage")
        if isinstance(coverage, dict) and coverage.get("response_truncated"):
            note += " Response was truncated; findings use partial HTML coverage."
        js_problem = recorded_js_comparison_problem(self.meta)
        if js_problem:
            note += f" JS-dependence was not measured: {js_problem}."
        settings = self.meta.get("scan_settings")
        if isinstance(settings, dict):
            if settings.get("image_checks") is False and "technical" in requested:
                note += " Image resource checks were disabled."
            if settings.get("rendered") is True:
                note += " Findings use rendered HTML."
            elif settings.get("rendered") is False:
                note += (" Rendering was requested but no rendered DOM was measured; findings use served HTML."
                         if settings.get("render_requested") is True else " Findings use served HTML.")
        return note + discovery_suffix

    def _report_title(self, title):
        if title != "SEO & GEO Audit":
            return title
        label = self.score_label()
        return {"Health score": title, "Selected-check score": "Focused page scan",
                "Score unavailable": "Page scan not completed"}.get(label, "Page findings report")

    # ---- renderers -------------------------------------------------------
    def to_json(self) -> str:
        return json.dumps(
            {
                "schema_version": REPORT_SCHEMA_VERSION,
                "tool_version": TOOL_VERSION,
                "url": self.url,
                "final_url": self.final_url,
                "status": self.fetched_status,
                "rendered": self.rendered,
                "score": self.score(),
                "counts": self.counts(),
                "meta": self.meta,
                "findings": [_finding_dict(f) for f in self.findings],
            },
            indent=2,
            ensure_ascii=False,
        )

    def to_markdown(self, title: str = "SEO & GEO Audit") -> str:
        score = self.score()
        grade = "not measured" if self.score_label() == "Score unavailable" else _grade(score)
        band = grade if self.score_label() == "Score unavailable" else f"score band: {grade}"
        counts = self.counts()
        buckets = self.by_severity()
        lines = [
            f"# {self._report_title(title)} — {self.final_url or self.url}",
            "",
            f"**{self.score_label()}: {score}/100 ({band})**  ·  "
            f"status {self.fetched_status}"
            + ("  ·  JS-rendered" if self.rendered else ""),
            "",
            self._scope_note(),
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
        cats = {} if self.score_label() == "Score unavailable" else self.by_category()
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
                if f.reference_url:
                    lines.append(f"- [Learn more]({f.reference_url})")
                lines.append("")

        # --- Quick wins (low severity) -------------------------------------
        if buckets["low"]:
            lines.append("## Quick wins")
            lines.append("")
            quick = [(f, _quick_win_previews(f)) for f in buckets["low"]]
            if any(previews for _, previews in quick):
                lines += [_QUICK_PREVIEW_NOTE, '']
            for f, previews in quick:
                fix = f" — {f.recommendation}" if f.recommendation else ""
                guide = f" · [Learn more]({f.reference_url})" if f.reference_url else ""
                observations = ''.join(
                    f' · **{label} (preview):** {_literal_preview_code(text)}'
                    + (' (truncated; full value in JSON)' if clipped else '')
                    for label, text, clipped in previews)
                lines.append(f"- 🔵 **{f.title}**{fix}{guide}{observations}")
            lines.append("")

        base_note = linklib.base_note(self.meta)
        if base_note:
            lines += ['## Declared anchor-base observations (not scored)', '', base_note, '']
        hreflang_note = hreflanglib.note(self.meta)
        if hreflang_note:
            lines += ['## HTML hreflang source coverage', '', hreflang_note, '']
        notes = _crawler_policy_notes(self.meta)
        if notes:
            lines += ["## Crawler policy notes (not scored)", "",
                      "Matching disallow directives at / are policy observations, not search-score penalties "
                      "or endorsements. This is not a live access or whole-site check.", ""]
            for note in notes:
                source = f" [Policy source]({note['source']})" if note["source"] else ""
                lines.append(f"- **{note['agent']}** — {note['text']}{source}")
            lines.append("")

        header_notes = _http_robots_notes(self.meta)
        if header_notes:
            lines += ['## HTTP robots observations (not scored)', '']
            lines += ['- ' + note for note in header_notes]
            lines.append('')

        llms_note = llms_resource.note(self.meta)
        if llms_note:
            lines += ['## Root llms.txt response evidence', '', llms_note, '']

        named_meta_notes = _crawler_meta_notes(self.meta)
        if named_meta_notes:
            lines += ['## Crawler-specific meta observations (not scored)', '']
            lines += ['- ' + note for note in named_meta_notes]
            lines.append('')

        length_note = content_length.note(self.meta)
        if length_note:
            lines += ['## Text-length observation (not content quality)', '', length_note, '']

        reading_note = readability_observation.note(self.meta)
        if reading_note:
            lines += ['## Readability formula observation (not comprehension)', '', reading_note, '']

        attribution = authorship.evidence_lines(self.meta)
        if attribution:
            lines += ['## Attribution cue evidence (not identity verification)', '',
                      authorship.LIMITS_NOTE, '', '```text', *attribution, '```', '']
        dates = date_cues.evidence_lines(self.meta)
        if dates:
            lines += ['## Date-cue evidence (not freshness verification)', '',
                      date_cues.LIMITS, '', '```text', *dates, '```', '']

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
        label = self.score_label()
        if label == "Score unavailable":
            return "The scan did not complete; no page health was measured. Check execution scope and any response failure below."
        subject = "This page scores" if label == "Health score" else ("Selected checks score" if label == "Selected-check score" else "Reported findings score")
        score_text = f"{subject} **{score}/100 (score band: {grade})**"
        checked = "in the reported findings" if label == "Reported-findings score" else "in the completed checks"
        if prio == 0 and med == 0:
            lead = (f"{score_text} — no critical, high, or medium issues found {checked}.")
        else:
            bits = []
            if crit:
                bits.append(f"{crit} critical")
            if high:
                bits.append(f"{high} high")
            if med:
                bits.append(f"{med} medium")
            lead = (f"**{', '.join(bits)} issue(s) need attention {checked}"
                    + (f", plus {low} quick win(s).** " if low else ".** ")
                    + score_text + ".")
        return lead


    # ---- HTML renderer ---------------------------------------------------
    def to_html(self, title: str = "SEO & GEO Audit") -> str:
        """A self-contained, styled HTML report (inline CSS, score gauge,
        severity-coloured finding cards). Reuses the same findings model as the
        Markdown/JSON renderers — no logic is duplicated, only presentation."""
        score = self.score()
        grade = "not measured" if self.score_label() == "Score unavailable" else _grade(score)
        counts = self.counts()
        target = self.final_url or self.url
        header = _score_header(score, grade, counts, self.fetched_status, self.rendered,
                               score_label=self.score_label())
        return html_document(self._report_title(title), target, header + "\n".join(self._html_sections()))

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
        body.append(f"<p>{_esc(self._scope_note())}</p>")
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
        cats = {} if self.score_label() == "Score unavailable" else self.by_category()
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
                '<p class="muted">Scroll horizontally if needed to view all scores and severity counts.</p>'
                '<div class="score-table-scroll" tabindex="0" role="region" '
                'aria-label="Score breakdown by area; scroll horizontally if needed">'
                '<table class="areas"><thead><tr><th scope="col">Area</th><th scope="col">Score</th>'
                '<th scope="col" aria-label="Critical">🔴</th><th scope="col" aria-label="High">🟠</th>'
                '<th scope="col" aria-label="Medium">🟡</th><th scope="col" aria-label="Low">🔵</th>'
                '<th scope="col" aria-label="Passed">🟢</th></tr></thead>'
                f'<tbody>{"".join(rows)}</tbody></table></div></section>')

        # Priority fixes
        priority = buckets["critical"] + buckets["high"] + buckets["medium"]
        if priority:
            body.append('<section class="card"><h2>Priority fixes</h2>')
            for n, f in enumerate(priority, 1):
                body.append(_finding_card(n, f))
            body.append("</section>")

        # Quick wins
        if buckets["low"]:
            quick = [(f, _quick_win_previews(f)) for f in buckets["low"]]
            items = []
            for f, previews in quick:
                observations = ''.join(
                    f'<span class="quick-preview"><strong>{label} (preview):</strong> '
                    f'<code>{_esc(text)}</code>'
                    + (' <span class="muted">(truncated; full value in JSON)</span>' if clipped else '')
                    + '</span>' for label, text, clipped in previews)
                items.append(f'<li>{_dot("low")} <strong>{_esc(f.title)}</strong>'
                             + (f' — {_esc(f.recommendation)}' if f.recommendation else '')
                             + (f' · <a class="reference-link" href="{_esc(f.reference_url)}">Learn more</a>' if f.reference_url else '')
                             + observations + '</li>')
            note = (f'<p class="muted">{_QUICK_PREVIEW_NOTE}</p>'
                    if any(previews for _, previews in quick) else '')
            body.append(f'<section class="card"><h2>Quick wins</h2>'
                        + note + f'<ul class="clean">{"".join(items)}</ul></section>')

        base_note = linklib.base_note(self.meta)
        if base_note:
            body.append('<section class="card"><h2>Declared anchor-base observations (not scored)</h2><p>'
                        + _esc(base_note) + '</p></section>')
        hreflang_note = hreflanglib.note(self.meta)
        if hreflang_note:
            body.append('<section class="card"><h2>HTML hreflang source coverage</h2><p>'
                        + _esc(hreflang_note) + '</p></section>')
        notes = _crawler_policy_notes(self.meta)
        if notes:
            items = []
            for note in notes:
                source = (f' <a href="{_esc(note["source"])}">Policy source</a>'
                          if note["source"] else "")
                items.append(f'<li><strong>{_esc(note["agent"])}</strong> — {_esc(note["text"])}{source}</li>')
            body.append('<section class="card"><h2>Crawler policy notes (not scored)</h2>'
                        '<p>Matching disallow directives at / are policy observations, not search-score penalties '
                        'or endorsements. This is not a live access or whole-site check.</p>'
                        f'<ul>{"".join(items)}</ul></section>')

        header_notes = _http_robots_notes(self.meta)
        if header_notes:
            body.append('<section class="card"><h2>HTTP robots observations (not scored)</h2>'
                        + '<ul>' + ''.join('<li>' + _esc(note) + '</li>' for note in header_notes)
                        + '</ul></section>')

        llms_note = llms_resource.note(self.meta)
        if llms_note:
            body.append('<section class="card"><h2>Root llms.txt response evidence</h2><p>'
                        + _esc(llms_note) + '</p></section>')

        named_meta_notes = _crawler_meta_notes(self.meta)
        if named_meta_notes:
            body.append('<section class="card"><h2>Crawler-specific meta observations (not scored)</h2>'
                        + '<ul>' + ''.join('<li>' + _esc(note) + '</li>' for note in named_meta_notes)
                        + '</ul></section>')

        measurement = _measurement_evidence(self.meta)
        if measurement:
            body.append(measurement)

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

def _measurement_evidence(meta):
    """Compact native overview; literal details expand on screen and print once.

    A print-only copy is intentional: closed native details do not reliably
    print their contents, and PDF engines need not execute JavaScript.
    """
    summaries, sections = [], []
    length_note = content_length.note(meta)
    if length_note:
        value = meta['content_length']
        state = ('threshold review not applied (language/text scope)' if value['threshold_status'] == 'uninterpreted'
                 else 'configured threshold review applied')
        summaries.append(f"Text length: {value['ascii_pattern_matches']} ASCII-pattern matches; {state}. Not content quality.")
        sections.append('<section class="card"><h2>Text-length observation (not content quality)</h2><p>'
                        + _esc(length_note) + '</p></section>')
    reading_note = readability_observation.note(meta)
    if reading_note:
        value = meta['readability']
        state = (f"Flesch estimate {value['flesch_reading_ease']}, FK estimate {value['flesch_kincaid_grade']}"
                 if value['formula_status'] == 'computed' else 'unassessed (language/text, page-role or input scope)')
        summaries.append(f'Readability formula: {state}. Not reader comprehension.')
        sections.append('<section class="card"><h2>Readability formula observation (not comprehension)</h2><p>'
                        + _esc(reading_note) + '</p></section>')
    attribution = authorship.evidence_lines(meta)
    if attribution:
        count = sum(line.startswith(tuple(label + ': ' for label in authorship.LABELS.values())) for line in attribution)
        limited = any(line.startswith('A source/depth/') for line in attribution)
        summaries.append(f'Attribution: {count} captured candidate witness(es); identity is unverified.'
                         + (' Capture limits reached; unchecked evidence remains unknown.' if limited else ''))
        sections.append('<section class="card"><h2>Attribution cue evidence (not identity verification)</h2>'
                        + '<p>' + _esc(authorship.LIMITS_NOTE) + '</p><pre><code>'
                        + _esc('\n'.join(attribution)) + '</code></pre></section>')
    dates = date_cues.evidence_lines(meta)
    if dates:
        value = meta['date_cues']
        summaries.append(f"Date cues: {value['candidate_count']} captured candidate(s); publication dates and freshness are unverified."
                         + (' Capture limits reached; unchecked evidence remains unknown.' if any(value['coverage'].values()) else ''))
        sections.append('<section class="card"><h2>Date-cue evidence (not freshness verification)</h2>'
                        + '<p>' + _esc(date_cues.LIMITS) + '</p><pre><code>'
                        + _esc('\n'.join(dates)) + '</code></pre></section>')
    if not sections:
        return ''
    details = ''.join(sections)
    return ('<section class="card measurement-overview"><h2>Measurement overview</h2>'
            '<p class="muted">Reported counts/candidates, not verified page quality. Expand for detailed evidence and limits; '
            'print/PDF includes all details.</p><ul class="clean">'
            + ''.join('<li>' + _esc(line) + '</li>' for line in summaries)
            + '</ul><details class="measurement-details"><summary>Inspect detailed evidence and limits</summary>'
            + details + '</details><div class="measurement-print">' + details + '</div></section>')

def _quick_win_previews(finding):
    """Return bounded display copies; original reported fields remain untouched."""
    previews = []
    for label, value in (('Observed', finding.detail), ('Evidence', finding.evidence)):
        if value is None:
            continue
        text = ' '.join(str(value).split())
        if text:
            clipped = len(text) > _QUICK_PREVIEW_LIMIT
            previews.append((label, text[:_QUICK_PREVIEW_LIMIT] + ('…' if clipped else ''), clipped))
    return previews


def _literal_preview_code(text):
    """Protect a single-line preview from Markdown/link/fence interpretation."""
    longest = max((len(run) for run in re.findall(r'`+', text)), default=0)
    marker = '`' * (longest + 1)
    # Padding separates boundary backticks from the enclosing delimiter. It is
    # layout only; the normalized preview and full source remain distinct.
    padding = ' ' if text.startswith('`') or text.endswith('`') else ''
    return marker + padding + text + padding + marker


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


def score_gauge(score: int, label: str = "Health score") -> str:
    """An SVG donut gauge coloured by grade, score centred."""
    r, cx = 54, 64
    import math
    circ = 2 * math.pi * r
    dash = circ * max(0, min(100, score)) / 100
    color = _grade_color(score)
    return (
        f'<svg viewBox="0 0 128 128" width="128" height="128" class="gauge" '
        f'role="img" aria-label="{_esc(label)} {score} of 100">'
        f'<circle cx="{cx}" cy="{cx}" r="{r}" fill="none" stroke="#e5e7eb" stroke-width="12"/>'
        f'<circle cx="{cx}" cy="{cx}" r="{r}" fill="none" stroke="{color}" stroke-width="12" '
        f'stroke-linecap="round" stroke-dasharray="{dash:.1f} {circ:.1f}" '
        f'transform="rotate(-90 {cx} {cx})"/>'
        f'<text x="{cx}" y="{cx - 2}" text-anchor="middle" class="g-num">{score}</text>'
        f'<text x="{cx}" y="{cx + 18}" text-anchor="middle" class="g-den">/ 100</text>'
        f'</svg>')


def _score_header(score, grade, counts, status, rendered, score_label="Health score") -> str:
    """Lead with reported findings; a numeric band is not a quality verdict."""
    chips = "".join(
        f'<span class="chip s-{s}">{counts[s]} {_SEV_LABEL[s]}</span>'
        for s in SEVERITY if counts[s])
    meta = f"status {status}" + ("  ·  JS-rendered" if rendered else "")
    if score_label == "Score unavailable":
        headline, color = "Not Measured", _grade_color(score)
    elif counts["critical"]:
        headline, color = "Critical findings first", _SEV_COLOR["critical"]
    elif counts["high"]:
        headline, color = "High-priority findings", _SEV_COLOR["high"]
    elif counts["medium"]:
        headline, color = "Medium-priority findings", _SEV_COLOR["medium"]
    elif counts["low"]:
        headline, color = "Low-priority findings", _SEV_COLOR["low"]
    else:
        headline, color = "No flagged findings", _SEV_COLOR["good"]
    band = ("" if score_label == "Score unavailable" else
            f'<div class="muted">Score band: {_esc(grade)} '
            '(reported findings, not page quality)</div>')
    return (
        '<header class="hero">'
        f'{score_gauge(score, label=score_label)}'
        '<div class="hero-txt">'
        f'<div class="muted">{_esc(score_label)}</div>'
        f'<div class="grade" style="color:{color}">{_esc(headline)}</div>'
        f'{band}'
        f'<div class="chips">{chips}</div>'
        f'<div class="muted">{_esc(meta)}</div>'
        '</div></header>')


def _finding_dict(f):
    """Preserve measured fields; reference navigation is additive JSON metadata."""
    data = asdict(f)
    if f.reference_url:
        data['reference_url'] = f.reference_url
    return data


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
    if f.reference_url:
        parts.append(f'<p><a class="reference-link" href="{_esc(f.reference_url)}">Learn more</a></p>')
    parts.append("</div>")
    return "".join(parts)


_HTML_CSS = """
:root{--fg:#1f2933;--muted:#6b7280;--bg:#f7f8fa;--card:#fff;--border:#e5e7eb;
--brand:#14b8a6;--radius:12px}
*{box-sizing:border-box}
body{margin:0;padding:32px 20px;background:var(--bg);color:var(--fg);
font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:820px;margin:0 auto}
h1{font-size:22px;margin:0 0 2px;overflow-wrap:anywhere}
h2{font-size:16px;margin:0 0 14px;padding-bottom:8px;border-bottom:1px solid var(--border)}
.sub{color:var(--muted);margin:0 0 24px;word-break:break-all}
.brand{display:flex;align-items:center;gap:16px;margin:0 0 24px}
.brand-logo{display:block;width:auto;flex:0 0 auto}
.brand>.brand-logo{height:46px}
.brand-txt h1{margin:0}
.brand-txt .sub{margin:2px 0 0}
.foot>.brand-logo{display:inline-block;height:16px;vertical-align:middle;margin-right:6px}
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
.score-table-scroll{max-width:100%;overflow-x:auto;border:1px solid var(--border);border-radius:8px}
.score-table-scroll:focus-visible{outline:2px solid #0f766e;outline-offset:3px}
.score-table-scroll table.areas th:first-child,.score-table-scroll table.areas td:first-child{min-width:10rem}
.score-table-scroll .score-cell{min-width:8rem}
.table-scroll{max-width:100%;overflow-x:auto;margin:14px 0 24px;border:1px solid var(--border);border-radius:8px;background:var(--card)}
.table-scroll:focus-visible{outline:2px solid #0f766e;outline-offset:3px}
table.markdown th,table.markdown td{min-width:8rem;padding:10px 12px;text-align:left;vertical-align:top;border-bottom:1px solid var(--border);overflow-wrap:anywhere}
table.markdown th{background:#f0f1f3;font-weight:600}
table.markdown tbody tr:last-child td{border-bottom:0}
table.markdown .align-center{text-align:center}
table.markdown .align-right{text-align:right}
.score-cell{white-space:nowrap}
.score-cell span{margin-left:8px;font-weight:600}
.bar{display:inline-block;width:70px;height:8px;background:#eef0f2;border-radius:4px;overflow:hidden;vertical-align:middle}
.bar .fill{display:block;height:100%}
.finding{background:#fbfcfd;border:1px solid var(--border);border-left-width:4px;
border-radius:8px;padding:14px 16px;margin:0 0 12px}
.f-head{display:flex;align-items:center;gap:10px}
.f-num{font-weight:700;color:var(--muted)}
.f-title{font-weight:600;flex:1}
.finding p,li{overflow-wrap:anywhere}
.tag{color:#fff;font-size:11px;font-weight:600;padding:2px 8px;border-radius:6px;text-transform:uppercase;letter-spacing:.02em}
.f-cat{margin:2px 0 8px 24px}
.finding p{margin:6px 0}
.reference-link{color:#0f766e;text-underline-offset:2px}
.reference-link:focus-visible{outline:2px solid #0f766e;outline-offset:3px;border-radius:2px}
.quick-preview{display:block;margin:6px 0 0;overflow-wrap:anywhere}
.measurement-details{margin-top:14px}
.measurement-details>summary{cursor:pointer;padding:8px 10px;border:1px solid var(--border);border-radius:6px;color:#0f766e}
.measurement-details>summary:focus-visible{outline:2px solid #0f766e;outline-offset:3px}
.measurement-details .card,.measurement-print .card{border:0;border-radius:0;padding:18px 0 0;margin:0}
.measurement-print{display:none}
.k{display:inline-block;min-width:70px;font-weight:600;color:var(--muted);font-size:12px;
text-transform:uppercase;letter-spacing:.03em}
code{background:#f0f1f3;padding:1px 5px;border-radius:4px;font-size:12.5px;word-break:break-all}
pre{background:#f0f1f3;border:1px solid var(--border);border-radius:8px;padding:14px 16px;overflow-x:auto;white-space:pre}
pre code{display:block;padding:0;background:transparent;border-radius:0;word-break:normal;overflow-wrap:normal;white-space:inherit}
.section{font-size:18px;margin:28px 0 14px;border:0;padding:0}
.metrics{display:flex;flex-wrap:wrap;gap:18px 26px;margin-top:6px}
.metric{display:flex;flex-direction:column}
.m-num{font-size:20px;font-weight:700}
.m-lab{font-size:12px;color:var(--muted)}
.foot{color:var(--muted);font-size:12px;text-align:center;margin:24px 0 0}
.foot a{color:var(--brand);text-decoration:none}
@media print{body{background:#fff;padding:0}.card,.hero,.finding{break-inside:avoid}pre{white-space:pre-wrap;overflow:visible}pre code{overflow-wrap:break-word}.table-scroll{overflow:visible;border:0;border-radius:0}.table-scroll:focus-visible{outline:0}table.markdown{table-layout:fixed;font-size:11px}table.markdown th,table.markdown td{min-width:0;padding:6px 8px}}
@media print{.score-table-scroll{overflow:visible;border:0;border-radius:0}.score-table-scroll:focus-visible{outline:0}.score-table-scroll table.areas th:first-child,.score-table-scroll table.areas td:first-child,.score-table-scroll .score-cell{min-width:0}}
@media print{.measurement-details{display:none}.measurement-print{display:block}.measurement-overview{break-inside:auto}}
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


def _inline_emphasis(text: str) -> str:
    """Format escaped display text, never an HTML attribute or code body."""
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    # Only at word boundaries so snake_case / paths aren't matched.
    return re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"<em>\1</em>", out)


def _inline_md(text: str, unescape=False) -> str:
    """Render our limited inline Markdown, keeping code spans escaped/literal.

    Equal-length backtick runs delimit code on one input line. Protect spans
    before links/emphasis, then restore them without reinterpreting their body.
    Only explicitly marked generated tables opt in to punctuation unescaping;
    ordinary text, legacy tables and fenced/code-span contents stay unchanged.
    This is not a general Markdown parser (e.g. no multiline code spans).
    """
    out = _esc(text)
    runs = list(re.finditer(r'`+', out))
    following, last = {}, {}
    for index in range(len(runs) - 1, -1, -1):
        length = runs[index].end() - runs[index].start()
        if length in last:
            following[index] = last[length]
        last[length] = index
    chunks, code = [], []
    cursor = index = 0
    while index < len(runs):
        preceding = runs[index].start()
        while preceding and out[preceding - 1] == '\\':
            preceding -= 1
        if unescape and (runs[index].start() - preceding) % 2:
            index += 1
            continue  # escaped opening backtick; backslashes inside code stay literal
        end_index = following.get(index)
        if end_index is None:
            index += 1
            continue
        opening, closing = runs[index], runs[end_index]
        chunks.append(out[cursor:opening.start()])
        # Raw '<' cannot occur in escaped user input. These private structural
        # tokens therefore cannot collide with user text or escaped lookalikes.
        chunks.append(f'<narwhal-code-{len(code)}>')
        code.append('<code>' + out[opening.end():closing.start()] + '</code>')
        cursor = closing.end()
        index = end_index + 1
    chunks.append(out[cursor:])
    out = ''.join(chunks)
    escapes = []

    def protect_escape(match):
        """Protect escaped punctuation from links/emphasis outside code spans."""
        token = f'<narwhal-escape-{len(escapes)}>'
        escapes.append(match.group(1))
        return token

    if unescape:
        out = re.sub(r'\\([' + re.escape(string.punctuation) + '])', protect_escape, out)
    links = []

    def protect_link(match):
        """Format a label but keep the already-escaped destination opaque."""
        label, destination = match.groups()
        token = f'<narwhal-link-{len(links)}>'
        links.append(f'<a href="{destination}">{_inline_emphasis(label)}</a>')
        return token

    # Protect full links before emphasis. Like code tokens, raw-angle link
    # tokens cannot occur in escaped user input. Code may be a label, not an href.
    out = re.sub(r"\[([^\]]+)\]\((https?://(?:<narwhal-escape-\d+>|[^)\s<>])+)\)",
                 protect_link, out)
    out = _inline_emphasis(out)
    out = re.sub(r'<narwhal-link-(\d+)>',
                 lambda match: links[int(match.group(1))], out)
    out = re.sub(r'<narwhal-code-(\d+)>', lambda match: code[int(match.group(1))], out)
    return re.sub(r'<narwhal-escape-(\d+)>', lambda match: escapes[int(match.group(1))], out)


def _table_cells(line: str) -> list:
    """Split a table row, honoring escaped pipes and one outer pipe per edge.

    Only the backslash escaping a literal pipe is removed; other backslashes
    remain data. Even backslash runs leave the following pipe as a delimiter.
    """
    row = line.strip()
    cells, cell = [], []
    slashes = 0
    trailing_delimiter = False
    for char in row:
        trailing_delimiter = False
        if char == '|' and not slashes % 2:
            cells.append(''.join(cell).strip())
            cell = []
            trailing_delimiter = True
        else:
            if char == '|':
                cell.pop()  # remove only the backslash that escapes this pipe
            cell.append(char)
        slashes = slashes + 1 if char == '\\' else 0
    cells.append(''.join(cell).strip())
    if row.startswith('|'):
        cells.pop(0)
    if trailing_delimiter:
        cells.pop()
    return cells or ['']


def _table_alignment_classes(separator: str) -> list:
    """Return only static classes from valid marker cells; left is the default."""
    classes = []
    for marker in _table_cells(separator):
        if not re.fullmatch(r':?-+:?', marker) or not marker.endswith(':'):
            classes.append('')
        elif marker.startswith(':'):
            classes.append(' class="align-center"')
        else:
            classes.append(' class="align-right"')
    return classes


def md_to_html(md: str) -> str:
    """Convert the limited Markdown our sub-reports emit (headings, tables,
    lists, blockquotes, root code fences, `---`, bold/code) into styled HTML. This is not a
    general Markdown engine. Shared by sub-reports and the branded render CLI;
    fenced content bypasses inline/block interpretation and stays escaped."""
    lines = markdown_lines(md)
    out, i, n = [], 0, len(lines)

    def close_list(stack):
        while stack:
            out.append(f"</{stack.pop()}>")

    list_stack = []
    while i < n:
        line = lines[i]
        stripped = line.strip()

        fence = opening_fence(line)
        if fence:
            close_list(list_stack)
            code = []
            i += 1
            while i < n and not closes_fence(lines[i], fence):
                content = lines[i]
                indent = min(fence.indent, len(content) - len(content.lstrip(' ')))
                code.append(content[indent:])
                i += 1
            literal = '\n'.join(code) + ('\n' if code else '')
            language = f' class="language-{_esc(fence.language)}"' if fence.language else ''
            out.append(f'<pre><code{language}>{_esc(literal)}</code></pre>')
            i += 1  # consume a closing fence, or finish an unclosed block at EOF
            continue

        # Table: a header row followed by a |:--| separator row
        if (stripped == TABLE_TEXT_MARKER and i + 2 < n
                and lines[i + 1].strip().startswith('|')
                and set(lines[i + 2].strip()) <= set('|:- ')
                and '-' in lines[i + 2]):
            i += 1  # opt-in applies only to the immediately following table
            continue
        if (stripped.startswith("|") and i + 1 < n
                and set(lines[i + 1].strip()) <= set("|:- ")
                and "-" in lines[i + 1]):
            close_list(list_stack)
            headers = _table_cells(line)
            alignments = _table_alignment_classes(lines[i + 1])
            unescape = i > 0 and lines[i - 1].strip() == TABLE_TEXT_MARKER

            def column_class(column):
                """Use only a parsed static class; extra cells stay default left."""
                return alignments[column] if column < len(alignments) else ''

            out.append('<div class="table-scroll" tabindex="0" role="region" aria-label="Scrollable report table"><table class="markdown"><thead><tr>'
                       + "".join(f'<th scope="col"{column_class(column)}>{_inline_md(h, unescape=unescape)}</th>'
                                 for column, h in enumerate(headers))
                       + "</tr></thead><tbody>")
            i += 2
            while i < n and lines[i].strip().startswith("|"):
                cells = _table_cells(lines[i])
                out.append("<tr>" + "".join(f'<td{column_class(column)}>{_inline_md(c, unescape=unescape)}</td>'
                                             for column, c in enumerate(cells))
                           + "</tr>")
                i += 1
            out.append("</tbody></table></div>")
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


def _pdf_via_weasyprint(html: str, path: str) -> bool:
    try:
        from weasyprint import HTML  # type: ignore  # noqa: PLC0415
    except (ImportError, OSError):
        # ImportError: package absent. OSError: present but its native libs
        # (pango/cairo/…) aren't — treat both as "not available here".
        return False
    HTML(string=html).write_pdf(path)
    return True


def _pdf_via_chromium(html: str, path: str) -> bool:
    """Print the HTML to PDF with headless Chromium (Playwright). Renders our exact
    CSS, so the PDF matches the browser; the report is self-contained (inline CSS +
    base64 logo), so no network is touched."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True,
                                        args=["--disable-dev-shm-usage"])
            try:
                page = browser.new_page()
                page.set_content(html, wait_until="load")
                page.pdf(path=path, print_background=True, format="A4",
                         margin={"top": "12mm", "bottom": "14mm",
                                 "left": "10mm", "right": "10mm"})
            finally:
                browser.close()
        return True
    except Exception:  # noqa: BLE001 — missing browser binary etc.; fall back
        return False


def pdf_from_html(html: str, path: str) -> bool:
    """Render ``html`` to a PDF at ``path``. Tries WeasyPrint, then headless
    Chromium (Playwright). Returns True on success, or False if neither engine is
    available (the caller then falls back to writing HTML — see ``deliver``)."""
    return _pdf_via_weasyprint(html, path) or _pdf_via_chromium(html, path)


def deliver(fmt: str, output, content: str, *, label: str = "report",
            score=None, input_stats=None) -> int:
    """Deliver a report; return 2 for expected output/encoding failures.

    All file outputs use the regular-file writer, with optional read-input
    identities to preserve. PDF engines stage their bytes before the final write;
    without an engine, only the actual fallback HTML destination is written.
    Separate final writes remain non-atomic. Analysis/rendering errors before
    this boundary are not caught here.
    """
    import sys
    import tempfile
    from pathlib import Path
    from .report_output import write_output

    score_txt = f" (score {score}/100)" if score is not None else ""
    if fmt == "pdf" and not output:
        print("--format pdf requires -o/--output (PDF is binary).", file=sys.stderr)
        return 2
    try:
        if fmt == "pdf":
            # Engines write paths directly; stage bytes before the guarded final write.
            with tempfile.TemporaryDirectory(prefix='narwhal-report-') as tmp:
                staged = str(Path(tmp) / 'report.pdf')
                made_pdf = pdf_from_html(content, staged)
                if made_pdf:
                    write_output(output, Path(staged).read_bytes(), input_stats or [])
            if made_pdf:
                print(f"Wrote PDF {label} to {output}{score_txt}")
                return 0
            html_path = (output[:-4] + ".html"
                         if output.lower().endswith(".pdf") else output + ".html")
            write_output(html_path, content, input_stats or [])
            print(f"No PDF engine available - wrote HTML {label} to {html_path}"
                  f"{score_txt} instead.\nFor PDF, install either:\n"
                  f"  - WeasyPrint:  pip install weasyprint\n"
                  f"  - or Chromium: pip install playwright && python -m playwright "
                  f"install chromium\n"
                  f"(the HTML is self-contained, so you can also open it and Print to "
                  f"PDF from your browser).", file=sys.stderr)
            return 0
        if output:
            write_output(output, content, input_stats or [])
            print(f"Wrote {fmt} {label} to {output}{score_txt}")
        else:
            print(content)
    except (OSError, ValueError) as exc:
        print(f"Error: {label} output: {exc}", file=sys.stderr)
        return 2
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
