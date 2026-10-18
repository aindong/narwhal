#!/usr/bin/env python3
"""Build a structured, read-only remediation plan from a Narwhal report.

The planner connects deterministic audit findings to likely source owners.  It
does not edit files: its output is a bounded hand-off contract for a coding
agent (or a human) to inspect, implement, and verify.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import links as linkslib, sitemap as sitemaplib  # noqa: E402
from lib.report import recorded_llms_problem, recorded_schema_extraction_problem  # noqa: E402

PLAN_SCHEMA_VERSION = "1.0"
MAX_REPO_FILES = 5000
MAX_FILE_BYTES = 2_000_000
MAX_FINDINGS = 1000
MEMORY_BASELINE_INSTRUCTION = (
    'Save the original input report JSON, keeping all fields, to a fresh before.json '
    'before edits or reruns. If using an existing saved report, point the diff at that '
    'baseline and choose distinct fresh verification output paths. '
    'Do not overwrite files or substitute a new scan. This read-only plan has not saved a baseline.'
)
SKIP_DIRS = {
    ".git", ".hg", ".svn", ".next", ".nuxt", ".output", ".cache",
    "node_modules", "vendor", "dist", "build", "coverage", "__pycache__",
}
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "good": 4}
SCHEMA_ABSENCE_RULES = frozenset(('schema.no.structured.data',
    'schema.no.structured.data.json.ld',
    'schema.article.like.page.without.article.schema', 'schema.no.organization.website.entity',
    'schema.ecommerce.product.missing'))
SCHEMA_EXTRACTION_RULES = frozenset(('schema.microdata.extraction', 'schema.rdfa.extraction',
    'schema.ecommerce.source.extraction', 'schema.invalid.json.ld', 'schema.extraction.unverified',
    'schema.jsonld.processing.unverified'))
SCHEMA_VERIFICATION_RULES = SCHEMA_EXTRACTION_RULES - {'schema.invalid.json.ld'}
RENDER_VERIFICATION_RULES = frozenset((
    'technical.most.content.requires.javascript', 'technical.significant.content.requires.javascript',
    'technical.rendered.text.changed', 'technical.rendered.text.comparison.unverified',
    'technical.rendered.text.unobserved',
    'technical.head.metadata.injected.by.javascript', 'technical.json.ld.injected.by.javascript',
    'geo.ai.answer.engines.may.not.see.this.content'))


def _schema_uncertain(meta, findings):
    """Explicit metadata or known extraction-error IDs, never supplied prose."""
    return bool(recorded_schema_extraction_problem(meta, for_score=True) or any(
        finding['rule_id'] in SCHEMA_EXTRACTION_RULES for finding in findings))


def _legacy_rule_id(finding: dict) -> str:
    """Derive the same compatibility ID used by Report for pre-v2 reports."""
    if finding.get("rule_id"):
        return str(finding["rule_id"])
    title = str(finding.get("title", "")).split(" (")[0].strip().lower()
    slug = re.sub(r"[^a-z0-9]+", ".", title).strip(".")
    return f"{finding.get('category', 'unknown')}.{slug}"


def _sitemap_note_findings(sitemap, schema_version):
    """Separate recorded execution gaps from source invalidity; never parse note text."""
    notes = sitemap.get('errors') or []
    count = len(notes) if isinstance(notes, list) else 1
    attempted, fetched, failed = (sitemap.get(key) for key in
                                  ('sitemaps_attempted', 'sitemaps_fetched', 'fetch_failures'))
    cap = sitemap.get('truncated', 0)
    cap_valid = type(cap) is int and cap >= 0
    known = (schema_version == '2.0' and isinstance(notes, list) and cap_valid
             and all(type(value) is int and value >= 0 for value in (attempted, fetched, failed))
             and attempted == fetched + failed and failed + bool(cap) <= count)
    out = []

    def add(suffix, title, detail, occurrences):
        out.append({'category': 'technical', 'severity': 'low', 'scope': 'site',
                    'rule_id': 'technical.sitemap.' + suffix, 'title': title,
                    'detail': detail, 'occurrences': occurrences,
                    'recommendation': 'Verify the recorded execution gap before making source changes.'})

    classified = 0
    if known and failed:
        add('fetch.unverified', 'Sitemap fetching is unverified',
            f'{failed} failed file fetch(es) in {attempted} recorded attempts; '
            f'{fetched} returned complete bodies. This does not establish missing or invalid sitemap content.', failed)
        classified += failed
    if known and cap:
        add('traversal.incomplete', 'Sitemap traversal is incomplete',
            f'{cap} distinct sitemap file(s) remained outside the recorded attempt budget; URL totals are partial.', cap)
        classified += 1
    hint = any(type(value) is int and value > 0 for value in (failed, cap))
    if count > classified or (hint and not out):
        add('validation.unverified', 'Sitemap validation notes need manual verification',
            'Sitemap notes are unclassified or execution counters are inconsistent/unrecorded. '
            'Review the original report and endpoint; source invalidity is not established.',
            max(1, count - classified))
    return out


def _sitemap_sample_evidence(sitemap):
    """Keep actual failing HTTP responses distinct from uncertain/no-response probes."""
    samples = sitemap.get('sample')
    observed = list(samples) if isinstance(samples, list) else []
    broken = sitemap.get('broken_sample') or []
    for item in broken if isinstance(broken, list) else [broken]:
        if item not in observed:
            observed.append(item)
    failures, unverified = [], 0
    for item in observed:
        status = item.get('status') if isinstance(item, dict) else None
        error = item.get('error') if isinstance(item, dict) else None
        if type(status) is int and not error and status > 0 and linkslib.is_broken(status):
            failures.append(item)
        elif type(status) is int and not error and 200 <= status < 300:
            continue
        else:
            unverified += 1
    return failures, unverified


def normalize_report(data: dict) -> dict:
    """Accept scan or audit JSON and return its actionable page findings."""
    if not isinstance(data, dict):
        raise ValueError("Report JSON must be an object.")
    if isinstance(data.get("findings"), list):
        page = data
        target = data.get("final_url") or data.get("url") or ""
        kind = "scan"
    elif isinstance(data.get("homepage"), dict):
        page = data["homepage"]
        target = data.get("site") or page.get("final_url") or page.get("url") or ""
        kind = "audit"
    else:
        raise ValueError(
            "Unrecognized report JSON: expected `narwhal scan --format json` or "
            "`narwhal audit --format json` output.")
    findings = []
    for raw in page.get("findings", []):
        if not isinstance(raw, dict) or raw.get("severity") == "good":
            continue
        finding = dict(raw)
        finding["rule_id"] = _legacy_rule_id(finding)
        finding.setdefault("scope", "page")
        findings.append(finding)
    page_meta = page.get('meta')
    schema_page_uncertain = _schema_uncertain(page_meta, findings)
    schema_page_verification = any(f['rule_id'] in SCHEMA_VERIFICATION_RULES for f in findings)
    if schema_page_uncertain:
        findings = [f for f in findings if f['rule_id'] not in SCHEMA_ABSENCE_RULES]
    schema_crawl_uncertain = False
    schema_crawl_verification = False
    llms_metadata = [page_meta]
    if kind == 'audit':
        llms_metadata.append(data.get('crawl'))
    llms_uncertain = False
    for meta in llms_metadata:
        detail = recorded_llms_problem(meta, for_score=True)
        if detail:
            llms_uncertain = True
            findings.append({'category': 'geo', 'severity': 'low', 'scope': 'site',
                             'rule_id': 'geo.llms.txt.availability.unverified',
                             'title': 'Root llms.txt needs manual verification', 'detail': detail})
    discovery_receipts = [page_meta.get('sitemap_discovery') if isinstance(page_meta, dict) else None]
    if kind == 'audit':
        discovery_receipts.append(data.get('crawl', {}).get('sitemap_discovery'))
    for receipt in discovery_receipts:
        detail = sitemaplib.discovery_note(receipt)
        if detail:
            recorded = sitemaplib.recorded_discovery(receipt)
            findings.append({'category': 'technical', 'severity': 'low', 'scope': 'site',
                             'rule_id': 'technical.sitemap.discovery.unverified',
                             'title': 'Sitemap discovery needs manual verification', 'detail': detail,
                             'occurrences': max(1, recorded['unverified_files']) if recorded else 1})
    if kind == "audit":
        crawl = data.get('crawl', {})
        schema_crawl_uncertain = any(isinstance(item, dict) and (
            item.get('schema_extraction_unverified') is True
            or recorded_schema_extraction_problem({'scan_settings': item.get('scan_settings')}, for_score=True))
            for item in crawl.get('pages', []))
        schema_crawl_uncertain = schema_crawl_uncertain or any(
            isinstance(item, dict) and item.get('severity') != 'good'
            and _legacy_rule_id(item) in SCHEMA_EXTRACTION_RULES for item in crawl.get('recurring', []))
        seen = {f["rule_id"]: f for f in findings}
        for raw in data.get("crawl", {}).get("recurring", []):
            if not isinstance(raw, dict) or raw.get("severity") == "good":
                continue
            finding = dict(raw)
            finding["rule_id"] = _legacy_rule_id(finding)
            if finding['rule_id'] in SCHEMA_VERIFICATION_RULES:
                schema_crawl_verification = True
            if schema_crawl_uncertain and finding['rule_id'] in SCHEMA_ABSENCE_RULES:
                continue  # aggregate occurrences cannot locate an absence in the verified portion
            finding["scope"] = "site"
            finding["occurrences"] = int(finding.get("count", 1))
            if finding["rule_id"] in seen:
                seen[finding["rule_id"]]["occurrences"] = finding["occurrences"]
                if finding['rule_id'] in SCHEMA_VERIFICATION_RULES:
                    seen[finding['rule_id']]['scope'] = 'site'
            else:
                findings.append(finding)
                seen[finding["rule_id"]] = finding
        sitemap = data.get("sitemap", {})
        findings.extend(_sitemap_note_findings(sitemap, data.get('schema_version')))
        failed_samples, unverified_samples = _sitemap_sample_evidence(sitemap)
        sitemap_issues = ([f'{len(failed_samples)} recorded failing sampled HTTP response(s)']
                          if failed_samples else [])
        if sitemap.get("problems") or sitemap.get("invalid_lastmod"):
            sitemap_issues.append("invalid sitemap entries or lastmod values")
        if sitemap_issues and "technical.sitemap.validation.issues" not in seen:
            findings.append({
                "category": "technical", "severity": "medium",
                "title": "Sitemap validation issues",
                "rule_id": "technical.sitemap.validation.issues",
                "scope": "site", "detail": "; ".join(map(str, sitemap_issues[:5])),
                "recommendation": "Fix the reported sitemap entries and validate again.",
            })
        if unverified_samples:
            findings.append({
                'category': 'technical', 'severity': 'low', 'scope': 'site',
                'rule_id': 'technical.sitemap.sample.unverified',
                'title': 'Sampled sitemap URL reachability is unverified',
                'detail': f'{unverified_samples} recorded sample(s) lack a confirmed successful or failing HTTP response. '
                          'Gated/no-response probes do not establish a dead URL.',
                'recommendation': 'Verify endpoint access and request outcomes before editing sitemap locations.',
                'occurrences': unverified_samples,
            })
        parse_coverage = sitemaplib.recorded_parse_coverage(sitemap.get('parse_coverage'),
                                                           sitemap.get('sitemaps_fetched'))
        if parse_coverage and parse_coverage['unverified_files']:
            findings.append({
                'category': 'technical', 'severity': 'low',
                'title': 'Sitemap XML extraction is unverified',
                'rule_id': 'technical.sitemap.extraction.unverified', 'scope': 'site',
                'detail': sitemaplib.parse_coverage_note(parse_coverage),
                'recommendation': 'Verify source format and parser coverage before trusting URL totals. '
                                  'Unsupported formats are not necessarily invalid.',
                'occurrences': parse_coverage['unverified_files'],
            })
    schema_page_pending = schema_page_uncertain and not schema_page_verification
    schema_crawl_pending = schema_crawl_uncertain and not schema_crawl_verification
    if schema_page_pending or schema_crawl_pending:
        pending_scope = ('page report and crawl sample/rollup' if schema_page_pending and schema_crawl_pending else
                         'crawl sample/rollup' if schema_crawl_pending else 'page report')
        findings.append({'category': 'schema', 'severity': 'low',
                         'scope': 'site' if schema_crawl_pending else 'page',
                         'rule_id': 'schema.extraction.unverified',
                         'title': 'Structured-data extraction needs manual verification',
                         'detail': 'Known structured-data extraction uncertainty was recorded in the '
                                   + pending_scope
                                   + '; non-observed types are not evidence of missing markup. '
                                   'Existing syntax/property findings remain reviewable.'})
    if llms_uncertain:
        # Older/contradictory missing-file findings cannot authorize generation
        # when recorded HTTP evidence explicitly leaves root availability open.
        findings = [finding for finding in findings if finding['rule_id'] != 'geo.no.llms.txt']
    # Stable action IDs require one action per rule. Multiple page nodes can
    # produce the same rule; retain the worst severity and occurrence evidence.
    coalesced = {}
    for finding in findings:
        rid = finding["rule_id"]
        count = _positive_int(finding.get("occurrences", finding.get("count", 1)))
        if rid not in coalesced:
            finding["occurrences"] = count
            coalesced[rid] = finding
            continue
        current = coalesced[rid]
        current["occurrences"] = max(_positive_int(current.get("occurrences", 1)), count)
        if SEVERITY_RANK.get(finding.get("severity"), 9) < SEVERITY_RANK.get(current.get("severity"), 9):
            current["severity"] = finding.get("severity")
    normalized_findings = sorted(
        coalesced.values(),
        key=lambda finding: (SEVERITY_RANK.get(finding.get("severity"), 9),
                             finding["rule_id"]))
    total_findings = len(normalized_findings)
    return {
        "kind": kind,
        "target": str(target),
        "score": data.get("overall_score", page.get("score")),
        "report_schema_version": data.get("schema_version", "legacy"),
        "tool_version": data.get("tool_version", "unknown"),
        "findings": normalized_findings[:MAX_FINDINGS],
        "findings_total": total_findings,
        "findings_capped": total_findings > MAX_FINDINGS,
    }


def _positive_int(value, default=1) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def safe_repo_root(path: str) -> Path:
    root = Path(path).expanduser().resolve()
    if not root.exists():
        raise ValueError(f"Repository path does not exist: {path}")
    if not root.is_dir():
        raise ValueError(f"Repository path is not a directory: {path}")
    return root


def inventory(root: Path, max_files=MAX_REPO_FILES) -> dict:
    """Build a bounded, symlink-safe repository inventory."""
    files, warnings, capped = [], [], False
    for current, dirs, names in os.walk(str(root), followlinks=False):
        current_path = Path(current)
        kept_dirs = []
        for name in sorted(dirs):
            candidate = current_path / name
            if name in SKIP_DIRS or candidate.is_symlink():
                continue
            kept_dirs.append(name)
        dirs[:] = kept_dirs
        for name in sorted(names):
            candidate = current_path / name
            if candidate.is_symlink() or not candidate.is_file():
                continue
            try:
                resolved = candidate.resolve()
                resolved.relative_to(root)
            except (OSError, ValueError):
                warnings.append(f"Skipped path outside repository: {candidate}")
                continue
            files.append(candidate.relative_to(root).as_posix())
            if len(files) >= max_files:
                capped = True
                break
        if capped:
            break
    if capped:
        warnings.append(f"Repository inventory capped at {max_files} files.")
    return {"files": sorted(files), "warnings": warnings, "capped": capped}


def _read_small(root: Path, rel: str) -> str:
    path = root / rel
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return ""


def detect_framework(root: Path, files: list) -> dict:
    """Identify one primary framework from concrete repository signals."""
    file_set = set(files)
    scores = {name: 0 for name in ("nextjs", "astro", "nuxt", "hugo", "jekyll", "plain_html")}
    evidence = {name: [] for name in scores}

    def mark(name, points, message):
        scores[name] += points
        evidence[name].append(message)

    package = {}
    if "package.json" in file_set:
        try:
            package = json.loads(_read_small(root, "package.json"))
        except json.JSONDecodeError:
            package = {}
    deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    if "next" in deps:
        mark("nextjs", 8, "package.json depends on next")
    if any(f.startswith("next.config.") for f in files):
        mark("nextjs", 5, "next.config.* present")
    if "astro" in deps:
        mark("astro", 8, "package.json depends on astro")
    if any(f.startswith("astro.config.") for f in files):
        mark("astro", 5, "astro.config.* present")
    if "nuxt" in deps:
        mark("nuxt", 8, "package.json depends on nuxt")
    if any(f.startswith("nuxt.config.") for f in files):
        mark("nuxt", 5, "nuxt.config.* present")
    if any(f in file_set for f in ("hugo.toml", "hugo.yaml", "hugo.yml", "config.toml",
                                   "config.yaml", "config.yml")) \
            and any(f.startswith("layouts/") for f in files):
        mark("hugo", 10, "Hugo configuration and layouts/ present")
    if "_config.yml" in file_set or "_config.yaml" in file_set:
        mark("jekyll", 8, "Jekyll _config file present")
    if any(f.startswith("_layouts/") for f in files):
        mark("jekyll", 4, "Jekyll _layouts/ present")
    html_count = sum(f.lower().endswith((".html", ".htm")) for f in files)
    if html_count:
        mark("plain_html", min(6, 1 + html_count), f"{html_count} HTML file(s) present")

    winner = max(scores, key=lambda name: scores[name])
    top = scores[winner]
    if top == 0:
        return {"name": "unknown", "confidence": 0.0, "evidence": []}
    second = sorted(scores.values(), reverse=True)[1]
    confidence = min(0.95, 0.5 + min(top, 10) * 0.03
                     + min(max(0, top - second), 8) * 0.015)
    # Framework evidence outranks incidental built/static HTML.
    if winner == "plain_html" and max(scores[n] for n in scores if n != "plain_html") >= 5:
        winner = max((n for n in scores if n != "plain_html"), key=lambda n: scores[n])
        top = scores[winner]
        confidence = min(0.95, 0.5 + min(top, 10) * 0.03)
    if winner == "plain_html":
        confidence = max(confidence, 0.7)
    return {"name": winner, "confidence": round(confidence, 2),
            "evidence": evidence[winner]}


ARTIFACT_RULES = (
    ("title", ("missing.title", "title.is.very.short", "homepage.title", "title.may.be.truncated")),
    ("meta_description", ("meta.description",)),
    ("canonical", ("canonical",)),
    ("robots_meta", ("noindex", "nofollow")),
    ("viewport", ("viewport",)),
    ("language", ("lang.attribute",)),
    ("hreflang", ("hreflang",)),
    ("image_alt", ("images.missing.alt",)),
    ("headings", ("h1", "heading.levels", "question.based.headings", "title.and.h1")),
    ("open_graph", ("open.graph", "twitter.x.card", "og.image")),
    ("product_schema", ("schema.ecommerce.", "product page has no product")),
    ("json_ld", ("json.ld", "structured.data", "schema", "rich.result", "organization.website.entity")),
    ("robots_txt", ("robots.txt", "ai.crawlers.are.blocked", "technical.sitemap.invalid.references")),
    ("sitemap", ("xml.sitemap", "sitemap.directive", "sitemap.validation")),
    ("llms_txt", ("llms.txt",)),
    ("content", ("thin.content", "content.is.on.the.short.side", "read", "filler", "generic",
                 "repetitive", "author.byline", "date.signal", "citable", "evidence.signals",
                 "direct.answer")),
    ("server_rendering", ("requires.javascript", "metadata.injected.by.javascript",
                          "json.ld.injected.by.javascript", "noscript.fallback")),
    ("server_config", ("https", "redirect.chain", "content.type", "compression.header",
                       "page.could.not.be.fetched", "response.non.html")),
)


def classify_artifact(finding: dict) -> str:
    rid = finding["rule_id"].lower()
    if rid.startswith('technical.http.robots.'):
        return 'server_config'  # header owner, never an HTML robots-meta edit
    title = str(finding.get("title", "")).lower()
    haystack = rid + " " + title
    for artifact, needles in ARTIFACT_RULES:
        if any(needle in haystack for needle in needles):
            return artifact
    return "content" if finding.get("category") in ("content", "geo") else "unknown"


FRAMEWORK_CANDIDATES = {
    "nextjs": {
        "head": ["src/app/layout.tsx", "src/app/layout.jsx", "app/layout.tsx", "app/layout.jsx",
                 "src/pages/_document.tsx", "pages/_document.tsx", "src/pages/_app.tsx", "pages/_app.tsx"],
        "content": ["src/app/page.tsx", "app/page.tsx", "src/pages/index.tsx", "pages/index.tsx"],
        "static": ["public"],
        "robots_txt": ["src/app/robots.ts", "app/robots.ts", "public/robots.txt"],
        "sitemap": ["src/app/sitemap.ts", "app/sitemap.ts", "public/sitemap.xml"],
    },
    "astro": {
        "head": ["src/layouts/Layout.astro", "src/layouts/BaseLayout.astro"],
        "content": ["src/pages/index.astro"], "static": ["public"],
        "robots_txt": ["public/robots.txt"], "sitemap": ["public/sitemap.xml", "astro.config.mjs"],
    },
    "nuxt": {
        "head": ["nuxt.config.ts", "nuxt.config.js", "app.vue", "layouts/default.vue"],
        "content": ["pages/index.vue", "app.vue"], "static": ["public"],
        "robots_txt": ["public/robots.txt", "server/routes/robots.txt.ts"],
        "sitemap": ["public/sitemap.xml", "nuxt.config.ts"],
    },
    "hugo": {
        "head": ["layouts/partials/head.html", "layouts/_default/baseof.html"],
        "content": ["content/_index.md", "content/index.md"], "static": ["static"],
        "robots_txt": ["layouts/robots.txt", "static/robots.txt"],
        "sitemap": ["layouts/sitemap.xml", "static/sitemap.xml", "hugo.toml"],
    },
    "jekyll": {
        "head": ["_includes/head.html", "_layouts/default.html"],
        "content": ["index.md", "index.html"], "static": ["."],
        "robots_txt": ["robots.txt"], "sitemap": ["sitemap.xml", "_config.yml"],
    },
    "plain_html": {
        "head": ["index.html"], "content": ["index.html"], "static": ["."],
        "robots_txt": ["robots.txt"], "sitemap": ["sitemap.xml"],
    },
    "unknown": {"head": [], "content": [], "static": [], "robots_txt": ["robots.txt"],
                "sitemap": ["sitemap.xml"]},
}


HEAD_ARTIFACTS = {"title", "meta_description", "canonical", "robots_meta", "viewport",
                  "language", "hreflang", "open_graph", "json_ld", "product_schema",
                  "server_rendering"}


def _route_candidates(target: str, framework: str) -> list:
    path = urlparse(target).path.strip("/")
    if not path:
        return []
    slug = path.split("/")[-1]
    if framework == "plain_html":
        return [f"{path}.html", f"{path}/index.html"]
    if framework == "nextjs":
        return [f"src/app/{path}/page.tsx", f"app/{path}/page.tsx",
                f"src/pages/{path}.tsx", f"pages/{path}.tsx"]
    if framework == "astro":
        return [f"src/pages/{path}.astro", f"src/pages/{path}/index.astro"]
    if framework == "nuxt":
        return [f"pages/{path}.vue", f"pages/{path}/index.vue"]
    if framework in ("hugo", "jekyll"):
        prefix = "content" if framework == "hugo" else ""
        base = f"{prefix}/{path}".strip("/")
        return [f"{base}.md", f"{base}/index.md", f"{slug}.md"]
    return []


def likely_files(root: Path, files: list, framework: str, artifact: str,
                 target: str) -> list:
    if artifact in ("server_config", "unknown"):
        return []
    file_set = set(files)
    config = FRAMEWORK_CANDIDATES.get(framework, FRAMEWORK_CANDIDATES["unknown"])
    if artifact in ("robots_txt", "sitemap"):
        candidates = list(config.get(artifact, []))
    elif artifact == "llms_txt":
        base = config.get("static", ["."])[0]
        candidates = [("llms.txt" if base == "." else f"{base}/llms.txt")]
    elif artifact in HEAD_ARTIFACTS:
        candidates = list(config.get("head", [])) + _route_candidates(target, framework)
    else:
        candidates = _route_candidates(target, framework) + list(config.get("content", []))

    # Include existing convention-matching files, not just canonical names.
    if artifact in HEAD_ARTIFACTS:
        candidates += [f for f in files if any(part in f.lower() for part in
                       ("layout", "head.", "_document", "app.vue"))][:12]
    if artifact in ("content", "headings", "image_alt"):
        candidates += [f for f in files if f.lower().endswith(
            (".html", ".md", ".mdx", ".tsx", ".jsx", ".vue", ".astro"))][:15]

    out, seen = [], set()
    for rel in candidates:
        rel = rel.lstrip("./") if rel != "." else rel
        if not rel or rel in seen:
            continue
        seen.add(rel)
        exists = rel in file_set
        out.append({
            "path": rel,
            "exists": exists,
            "confidence": 0.9 if exists and rel in candidates[:4] else (0.72 if exists else 0.42),
            "reason": ("Existing framework convention" if exists else
                       "Framework convention; create or confirm generated owner"),
        })
    out.sort(key=lambda item: (not item["exists"], -item["confidence"], item["path"]))
    return out[:8]


CHANGE_GUIDANCE = {
    "title": "Define a unique, descriptive page title in the framework's metadata/head API.",
    "meta_description": "Add or revise the page meta description in its metadata/head owner.",
    "canonical": "Define the intended absolute canonical URL in the page or shared head owner.",
    "robots_meta": "Review the page robots directive and remove noindex/nofollow only if indexing is intended.",
    "viewport": "Add a responsive viewport declaration in the shared document head.",
    "language": "Set the document language on the root html element from the site's real locale.",
    "hreflang": "Correct the locale alternate set in the shared/page head and verify reciprocal targets.",
    "image_alt": "Add meaningful alt text to informative images; use empty alt for decorative images.",
    "headings": "Edit the owning page/template to provide one descriptive H1 and a logical heading hierarchy.",
    "open_graph": "Complete Open Graph and Twitter metadata using real page title, description, URL, and image.",
    "json_ld": "Add or repair structured data for the page's real entity; preserve valid Microdata, RDFa or JSON-LD and validate all values before publishing.",
    "product_schema": "Update Product/Offer structured data from the same current product data used by the rendered page; preserve valid Microdata, RDFa or JSON-LD, variants, and merchant values.",
    "robots_txt": "Create or revise robots.txt deliberately, preserving intentional crawler policies.",
    "sitemap": "Create/configure the sitemap and reference it from robots.txt using the canonical deployed URL.",
    "llms_txt": "Generate a starter llms.txt in the public/static root, then curate every entry and TODO.",
    "content": "Revise the owning page content using the finding evidence and recommendation; preserve factual accuracy.",
    "server_rendering": "Move essential content and metadata into server-rendered output using the framework's SSR/static APIs.",
    "server_config": "Change hosting, CDN, redirect, TLS, compression, or response-header configuration outside page source.",
    "unknown": "Inspect the finding evidence and locate the owning source or external system before changing anything.",
}


PHRASE_REVIEW_GUIDANCE = dict.fromkeys(
    ('content.reads.as.ai.generated.generic', 'content.some.generic.ai.sounding.phrasing'),
    'Review the matched wording in context with the page owner. Keep useful wording; '
    'edit only confirmed vague or unnecessary phrasing for the intended audience. '
    'Phrase matches do not determine authorship, originality, helpfulness or ranking impact.')


READABILITY_REVIEW_RULES = {'content.content.is.very.hard.to.read', 'content.content.is.fairly.hard.to.read'}
READABILITY_REVIEW_GUIDANCE = (
    'Review actual audience, language and captured prose. Simplify only where useful; preserve necessary '
    'technical terms, factual precision and useful concise text. Do not pad or rewrite solely to reach '
    'a formula target. Formula estimates do not establish reader comprehension or ranking/citation impact.')


EDITORIAL_REVIEW_GUIDANCE = {
    'technical.canonical.points.elsewhere':
        'Review the original canonical, document base, final fetched URL and actual variants in context. '
        'Preserve intended consolidation; edit only a verified wrong target. Do not force self-reference, '
        'remove query parameters or merge distinct pages solely because component keys differ. '
        'A local comparison does not establish target access/content or search-engine selection.',
    **dict.fromkeys(('content.filler.padding.language', 'content.some.filler.phrasing',
                     'content.repetitive.vocabulary'),
        'Review actual wording, quoted examples and audience needs in context. Keep useful phrasing and '
        'consistent technical terms; edit only confirmed unnecessary repetition or vague wording. '
        'Do not add filler or substitute synonyms solely to change a count or ratio. Pattern counts '
        'do not establish padding, thin/spun content, authorship or ranking/AI-citation impact.'),
    'content.body.may.not.reinforce.the.title.topic':
        'Review actual page purpose and wording, including synonyms, the top-8 lexical cutoff and extraction. '
        'Edit only confirmed misleading labels or missing useful content; keep accurate wording. Do not stuff '
        'keywords or rewrite solely to force literal overlap. Frequency does not establish semantic relevance '
        'or ranking/AI-citation impact.',
    **dict.fromkeys(READABILITY_REVIEW_RULES, READABILITY_REVIEW_GUIDANCE),
    'content.no.visible.date.signal':
        'Review actual page purpose and original publication/update evidence. Add accurate date information '
        'only when useful and known; preserve valid existing dates. Do not invent dates, relabel events '
        'as publication or refresh a date without substantive change. Cue non-observation is not proof '
        'of missing dates, stale content or ranking/citation impact.',
    'schema.invalid.json.ld':
        'Inspect the original JSON-LD block and repair verified JSON syntax errors only. '
        'An old unclassified processing failure is not proof of syntax invalidity; verify tool/parser '
        'limits before rewriting source. Preserve valid semantic data and do not promise engine behavior.',
    'schema.ecommerce.product.missing':
        'Review existing Product markup and actual visible product facts before adding applicable semantic data. '
        'Preserve valid JSON-LD, Microdata or RDFa; do not duplicate entities or infer Google merchant eligibility '
        'or rich-result benefits solely from page signals.',
    **dict.fromkeys(('schema.no.structured.data', 'schema.no.structured.data.json.ld'),
        'Review existing supported markup and the actual page entity; add semantic data only when applicable. '
        'Do not duplicate entities or invent visible content. Non-observation does not prove a markup requirement '
        'or establish rich-result eligibility, ranking or AI citation gains.'),
    'schema.article.like.page.without.article.schema':
        'Review actual page purpose and existing Article-family markup before adding applicable known facts. '
        'Preserve valid JSON-LD, Microdata or RDFa; do not invent authors/dates or promise rich results or AI attribution.',
    'schema.no.organization.website.entity':
        'Review publisher/site identity and existing markup for the intended consumer before adding applicable data. '
        'A single-page non-observation is not whole-site absence; do not duplicate entities or add both types automatically.',
    **PHRASE_REVIEW_GUIDANCE,
    **dict.fromkeys(('content.thin.content', 'content.content.is.on.the.short.side',
                     'content.link.hub.page.with.little.prose'),
        'Review actual extracted text, language/tokenizer coverage and reader intent before proposing edits. '
        'A low ASCII-pattern count does not establish thinness or missing useful content. '
        'Keep useful concise text; do not pad content to meet a configured count. '
        'Edit only confirmed coverage gaps; ranking and citation impact are not measured.'),
    'content.no.visible.author.byline':
        'Review the actual article attribution and editorial ownership before proposing edits. '
        'A missing bounded cue does not prove anonymity. Identify real creators/reviewers only '
        'when appropriate; do not invent people or credentials.',
    'geo.few.question.based.headings':
        'Review heading clarity for the intended audience and language. Keep useful headings; '
        'question phrasing is optional, not a required rewrite or measured citation benefit.',
    'geo.few.self.contained.citable.passages':
        'Review readability and completeness in context. Keep useful text; do not pad or '
        'split it solely to fit the configured word range. Synthetic group counts do not measure citability.',
    'geo.no.statistics.or.citations':
        'Review factual claims and actual references in context. Cue absence does not prove '
        'missing evidence. Keep useful text and do not invent statistics or citations to satisfy this check.',
    'geo.no.direct.answer.up.top':
        'Review whether the opening serves the intended audience and language. Keep useful text; '
        'add a direct answer only when appropriate. English cue absence does not prove a missing answer '
        'or measure citation impact.',
}


SITEMAP_VERIFICATION = {
    'technical.sitemap.discovery.unverified': (
        'Verify declared/common sitemap candidates, supported XML format and discovery limits manually. '
        'Do not publish or rewrite a sitemap solely because discovery was unverified.',
        ('Review the recorded candidate scope and original endpoint/fetch evidence.',
         'Recheck bounded sitemap discovery on the deployed site; preserve host and request-budget guards.')),
    'technical.sitemap.extraction.unverified': (
        'Verify the fetched format and XML extraction coverage manually. '
        'Do not rewrite a valid unsupported format merely to clear this note.',
        ('Validate the source with a trusted XML/sitemap validator.',
         'Re-run narwhal sitemap and confirm complete supported extraction before using URL totals.')),
    'technical.sitemap.fetch.unverified': (
        'Verify sitemap transport, HTTP status, response completeness and scan limits manually. '
        'Do not create or rewrite a sitemap solely because fetching was unverified.',
        ('Review the original fetch notes and intended endpoint/access policy.',
         'Recheck the deployed endpoint with Narwhal sitemap/audit after resolving the verified fetch cause; '
         'reverify after any deployment. Do not automatically grant private access or remove budgets.')),
    'technical.sitemap.traversal.incomplete': (
        'Review the scan budget and remaining-file count; rerun within a deliberate trusted limit. '
        'Do not change sitemap source to clear a scan cap.',
        ('Confirm the intended scan scope and a bounded file-attempt budget.',
         'Rerun Narwhal sitemap/audit and review the remaining-file count before using site URL totals.')),
    'technical.sitemap.validation.unverified': (
        'Inspect unclassified sitemap notes and execution evidence manually. '
        'Confirm what was measured before proposing source edits.',
        ('Review the original report, endpoint and tool/version coverage.',
         'Rerun supported sitemap verification on the deployed endpoint; verify source ownership only if a defect is established.')),
    'technical.sitemap.sample.unverified': (
        'Verify sampled endpoint access, HTTP/HEAD support and request outcomes manually. '
        'Do not remove sitemap URLs solely on gated, incomplete or no-response probes.',
        ('Review sampled status/error evidence and intended access policy.',
         'Recheck sampled endpoints and deployed sitemap reachability after any confirmed fix; '
         'do not equate gated/no-response results with dead URLs.')),
}


RESOURCE_VERIFICATION = dict(SITEMAP_VERIFICATION)
RESOURCE_VERIFICATION['technical.canonical.comparison.unverified'] = (
    'Inspect the original HTML canonical, document base and fetched URL before proposing edits. '
    'Repair only confirmed defects; do not add duplicate markup or assume a selected canonical.',
    ('Review the original declaration and supported local URL comparison scope; no target was fetched.',
     'Re-scan after a verified correction; verify any deployed target and search-engine selection separately.'))
RESOURCE_VERIFICATION['geo.llms.txt.availability.unverified'] = (
    'Verify the root endpoint response and intended file before proposing changes. '
    'Do not create or rewrite llms.txt solely because this observation was unverified.',
    ('Review the recorded HTTP status, media type and completeness; retain access/SSRF/body limits.',
     'Re-scan the deployed root endpoint after resolving a verified cause; subpath files and engine behavior remain separate checks.'))
for _rule in sorted(SCHEMA_VERIFICATION_RULES):
    RESOURCE_VERIFICATION[_rule] = (
        'Verify the original structured data and supported extraction scope before proposing source changes. '
        'Do not add or duplicate markup, rewrite valid unsupported data, or increase limits automatically to clear this note.',
        ('Review original HTML, retained extraction warnings and intended entity/consumer; preserve SSRF and body/parser limits.',
         'Validate supported/unsupported markup with an appropriate validator and re-scan before treating missing findings as fixes. '
         'Syntax/property defects actually observed may still be repaired after confirming their source.'))
for _rule in sorted(RENDER_VERIFICATION_RULES):
    RESOURCE_VERIFICATION[_rule] = (
        'Inspect paired served HTML/rendered DOM, extraction scope and intended page state before proposing source edits. '
        'Counts and legacy JS-only labels do not establish causation, SSR requirements or crawler/citation impact. '
        'Preserve useful client behavior and valid metadata/markup; change delivery only after verifying a real need.',
        ('Review both original snapshots and any missing/partial baseline; equal counts do not establish equal text.',
         'Re-scan with --render after a verified fix, retaining existing private-host/body/render guards. '
         'Do not treat a count/score change alone as an SEO improvement.'))


def safety_for(artifact: str) -> tuple:
    if artifact == "server_config":
        return "manual_external", True
    if artifact in ("robots_txt", "sitemap", "llms_txt"):
        return "deploy_verification", True
    if artifact in ("title", "meta_description", "canonical", "language", "open_graph",
                    "content", "headings", "image_alt", "json_ld", "product_schema", "robots_meta", "hreflang",
                    "server_rendering"):
        return "review_required", False
    if artifact == "unknown":
        return "manual_external", False
    # Structural declarations such as a missing viewport can be inserted
    # deterministically; content-bearing values still require review above.
    return "safely_automatable", False


def _verification_outputs(report_source):
    """Avoid known baseline basename collisions without inspecting the filesystem.

    Treat case and either path separator conservatively for portable templates;
    callers must still choose fresh paths and check symlink/hardlink aliases.
    """
    baseline = report_source.replace('\\', '/').rsplit('/', 1)[-1].casefold()
    page = 'page-after-2.json' if baseline == 'page-after.json' else 'page-after.json'
    comparison = 'after-2.json' if baseline == 'after.json' else 'after.json'
    return page, comparison


def verification_for(artifact: str, target: str, report_source: str,
                     report_kind: str = "scan") -> list:
    """Human POSIX-shell templates; quote data and stop option interpretation."""
    memory_source = report_source.startswith("<")
    prerequisites = [MEMORY_BASELINE_INSTRUCTION] if memory_source else []
    before = ("before.json" if memory_source else
              shlex.quote(report_source))
    page_output, comparison_output = _verification_outputs(report_source)
    if report_kind == 'audit':
        commands = []
        if artifact not in ("robots_txt", "sitemap", "llms_txt", "server_config"):
            commands += [
                f"narwhal scan --allow-private --format json -o {page_output} -- '<local-preview-url>'",
                'The local scan verifies page-level changes only; do not compare '
                f'{page_output} with the audit baseline or treat it as deployed site verification.',
            ]
        commands += [
            'Restore the original audit configuration, rendering, access settings and '
            'crawl/link/sitemap limits before running this template; the report does '
            'not record the complete invocation. A matching report kind alone does '
            'not establish comparable coverage.',
            f'narwhal audit --format json -o {comparison_output} -- {shlex.quote(target)}  # run after deploy',
            f'narwhal diff -- {before} {comparison_output}',
        ]
        if artifact in ("json_ld", "product_schema"):
            commands.insert(0, "Validate the rendered structured data and replace every TODO placeholder.")
        return prerequisites + commands
    if artifact in ("robots_txt", "sitemap", "llms_txt", "server_config"):
        scan_target = shlex.quote(target)
        scan_command = f"narwhal scan --format json -o {comparison_output} -- {scan_target}  # run after deploy"
    else:
        scan_command = f"narwhal scan --allow-private --format json -o {comparison_output} -- '<local-preview-url>'"
    commands = [scan_command,
                f"narwhal diff -- {before} {comparison_output}"]
    if artifact in ("json_ld", "product_schema"):
        commands.insert(0, "Validate the rendered structured data and replace every TODO placeholder.")
    return prerequisites + commands


def build_plan(report: dict, repo: str, *, report_source="<memory>",
               max_files=MAX_REPO_FILES) -> dict:
    normalized = normalize_report(report)
    root = safe_repo_root(repo)
    inv = inventory(root, max_files=max(1, min(int(max_files), MAX_REPO_FILES)))
    framework = detect_framework(root, inv["files"])
    warnings = list(inv["warnings"])
    if normalized["report_schema_version"] == "legacy":
        warnings.append("Legacy report has no schema_version; rule IDs were derived from titles.")
    if framework["name"] == "unknown":
        warnings.append("Framework could not be identified; file suggestions have lower confidence.")
    if normalized["findings_capped"]:
        warnings.append(
            f"Action generation capped at {MAX_FINDINGS} of "
            f"{normalized['findings_total']} actionable findings (severity-first).")

    actions = []
    mapped_named = 0
    for finding in normalized["findings"]:
        verification = RESOURCE_VERIFICATION.get(finding['rule_id'])
        artifact = classify_artifact(finding)
        if verification:
            artifact = ('canonical' if finding['rule_id'] == 'technical.canonical.comparison.unverified' else
                        'server_rendering' if finding['rule_id'] in RENDER_VERIFICATION_RULES else
                        'json_ld' if finding['rule_id'].startswith('schema.') else
                        'llms_txt' if finding['rule_id'] == 'geo.llms.txt.availability.unverified' else 'sitemap')
        if artifact != "unknown":
            mapped_named += 1
        safety, requires_deploy = safety_for(artifact)
        if verification:
            safety, requires_deploy = 'manual_external', False
        owners = ([] if verification else likely_files(root, inv["files"], framework["name"], artifact,
                                                     normalized["target"]))
        if not owners and safety != "manual_external":
            warnings.append(f"No likely source owner found for {finding['rule_id']}.")
        actions.append({
            "action_id": f"action:{finding['rule_id']}",
            "rule_id": finding["rule_id"],
            "title": finding.get("title", "Untitled finding"),
            "category": finding.get("category", "unknown"),
            "severity": finding.get("severity", "low"),
            "artifact": artifact,
            "safety": safety,
            "requires_deploy": requires_deploy,
            "manual_action": safety == "manual_external",
            "proposed_change": (verification[0] if verification else
                                'Correct the recorded sitemap URL/lastmod problems or failing sampled HTTP targets '
                                'in the actual sitemap owner after verifying intended behavior.'
                                if finding['rule_id'] == 'technical.sitemap.validation.issues'
                                else EDITORIAL_REVIEW_GUIDANCE.get(finding['rule_id'], CHANGE_GUIDANCE[artifact])),
            "likely_files": owners,
            "verification": (list(verification[1]) if verification else
                             verification_for(artifact, normalized["target"], report_source,
                                              normalized["kind"])),
            "evidence": finding.get("evidence") or finding.get("detail") or "",
            "source_recommendation": finding.get("recommendation", ""),
            "confidence": finding.get("confidence", 1.0),
            "scope": finding.get("scope", "page"),
            "occurrences": _positive_int(finding.get("occurrences", finding.get("count", 1))),
            "provenance": {"source": "narwhal_finding", "report": report_source,
                           "report_schema_version": normalized["report_schema_version"]},
        })
    actions.sort(key=lambda action: (SEVERITY_RANK.get(action["severity"], 9),
                                     action["rule_id"], action["action_id"]))
    groups = _groups(actions)
    conflicts = _conflicts(actions)
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "kind": "narwhal_remediation_plan",
        "target": normalized["target"],
        "source_score": normalized["score"],
        "repository": str(root),
        "framework": framework,
        "actions": actions,
        "groups": groups,
        "conflicts": conflicts,
        "coverage": {
            "actionable_findings": normalized["findings_total"],
            "actions_emitted": len(actions),
            "action_generation_capped": normalized["findings_capped"],
            "named_mappings": mapped_named,
            "mapping_ratio": round(mapped_named / len(actions), 3) if actions else 1.0,
            "files_scanned": len(inv["files"]),
            "file_inventory_capped": inv["capped"],
        },
        "warnings": sorted(set(warnings)),
        "provenance": {
            "report": report_source,
            "report_kind": normalized["kind"],
            "report_schema_version": normalized["report_schema_version"],
            "report_tool_version": normalized["tool_version"],
            "planner": "narwhal.plan",
        },
    }


def _groups(actions: list) -> list:
    buckets = {}
    for action in actions:
        if action['rule_id'] in RESOURCE_VERIFICATION:
            continue  # verification tasks are not shared source/template edits
        key = action["artifact"]
        if key in HEAD_ARTIFACTS:
            key = "shared_head_metadata"
        elif key in ("robots_txt", "sitemap", "llms_txt"):
            key = "public_discovery_files"
        buckets.setdefault(key, []).append(action)
    out = []
    for key, members in sorted(buckets.items()):
        if len(members) < 2:
            continue
        paths = sorted({f["path"] for action in members for f in action["likely_files"]
                        if f["exists"]})
        out.append({"group_id": f"group:{key}", "artifact": key,
                    "rule_ids": sorted(a["rule_id"] for a in members),
                    "likely_shared_files": paths,
                    "reason": "Implement together to avoid repeated or conflicting template edits."})
    return out


def _conflicts(actions: list) -> list:
    """Flag action pairs that need an owner decision before automation."""
    conflicts = []
    by_artifact = {}
    for action in actions:
        by_artifact.setdefault(action["artifact"], []).append(action)
    for artifact, members in sorted(by_artifact.items()):
        if artifact not in ("canonical", "robots_meta", "robots_txt", "hreflang"):
            continue
        titles = " ".join(a["title"].lower() for a in members)
        if len(members) > 1 and any(word in titles for word in ("elsewhere", "blocked", "noindex")):
            conflicts.append({
                "conflict_id": f"conflict:{artifact}",
                "rule_ids": sorted(a["rule_id"] for a in members),
                "reason": "These directives encode owner intent; resolve the intended index/canonical policy before editing.",
            })
    return conflicts


def render_json(plan: dict) -> str:
    return json.dumps(plan, indent=2, ensure_ascii=False)


def render_markdown(plan: dict) -> str:
    f = plan["framework"]
    c = plan["coverage"]
    lines = [
        f"# Narwhal Remediation Plan — {plan['target']}", "",
        f"**Framework:** {f['name']} ({round(100 * f['confidence'])}% confidence)  ·  "
        f"**Actions:** {len(plan['actions'])}  ·  **Mapping coverage:** {round(100 * c['mapping_ratio'])}%",
        "", "_Read-only plan: inspect proposed owners and values before applying edits._", "",
        'Command templates use POSIX shell quoting; adapt for PowerShell/cmd. '
        'Replace placeholders and add original options before `--`; do not execute '
        'instruction text as commands.', '',
    ]
    if any(MEMORY_BASELINE_INSTRUCTION in action['verification'] for action in plan['actions']):
        lines += ['> ' + MEMORY_BASELINE_INSTRUCTION, '']
    if (plan.get('provenance', {}).get('report_kind') == 'audit'
            and any(step.startswith('narwhal audit ') for action in plan['actions']
                    for step in action['verification'])):
        page_output, _ = _verification_outputs(plan['provenance']['report'])
        lines += ['## Audit verification', '',
                  'A local page scan can verify page-level changes only. Keep its '
                  f'`{page_output}` separate; do not diff it against the audit baseline. '
                  'Site-level signals remain pending deployment.', '']
        steps = verification_for('server_config', plan['target'], plan['provenance']['report'], 'audit')[-3:]
        lines += [steps[0], '', '```sh', steps[1], steps[2], '```', '']
    for safety, label in (("manual_external", "Manual / external"),
                          ("review_required", "Review required"),
                          ("deploy_verification", "Apply, then verify after deploy"),
                          ("safely_automatable", "Safe candidates for automation")):
        members = [a for a in plan["actions"] if a["safety"] == safety]
        if not members:
            continue
        lines += [f"## {label}", ""]
        for action in members:
            owners = ", ".join(f"`{x['path']}`" for x in action["likely_files"][:3]) or "owner not located"
            if action['rule_id'] in RESOURCE_VERIFICATION:
                owners = 'not assigned (verification only)'
            scope_lines = []
            display_title = action['title']
            if action['rule_id'] in ('content.filler.padding.language', 'content.some.filler.phrasing',
                                     'content.repetitive.vocabulary'):
                display_title = 'Review recorded style-pattern observation'
                scope_lines.append('- **Observation scope:** Original label/priority retained in JSON, '
                                   'not verified padding, thinness or originality risk. Review actual text.')
            if action['rule_id'] in READABILITY_REVIEW_RULES:
                display_title = 'Review recorded readability formula finding'
                scope_lines.append('- **Priority scope:** Input report priority retained, not verified readability risk. '
                                   'Original title and priority remain in JSON; review actual readers and text.')
            if action['rule_id'] == 'content.body.may.not.reinforce.the.title.topic':
                display_title = 'Review recorded lexical-focus observation'
                scope_lines.append('- **Observation scope:** Input label/priority retained in JSON, not a verified '
                                   'semantic gap. Review actual page purpose and wording.')
            if action['rule_id'] in SCHEMA_VERIFICATION_RULES:
                scope_label = ('Page report' if action.get('scope') == 'page' else
                               'Site sample/rollup' if action.get('scope') == 'site' else 'Unrecorded scope')
                scope_lines = [f'- **Verification scope:** {scope_label}']
            lines += [f"### {action['severity'].upper()} — {display_title}", "",
                      f"- **Rule:** `{action['rule_id']}`",
                      *scope_lines,
                      f"- **Likely owner:** {owners}",
                      f"- **Change:** {action['proposed_change']}",
                      f"- **Verify:** `{action['verification'][-1]}`", ""]
    if plan["groups"]:
        lines += ["## Grouped template fixes", ""]
        for group in plan["groups"]:
            lines.append(f"- **{group['artifact']}** — {len(group['rule_ids'])} findings; "
                         f"owners: {', '.join(group['likely_shared_files']) or 'confirm owner'}")
        lines.append("")
    if plan["conflicts"]:
        lines += ["## Conflicts requiring a decision", ""]
        for conflict in plan["conflicts"]:
            lines.append(f"- **{conflict['conflict_id']}** — {conflict['reason']}")
        lines.append("")
    if plan["warnings"]:
        lines += ["## Coverage warnings", ""] + [f"- {w}" for w in plan["warnings"]] + [""]
    return "\n".join(lines).rstrip() + "\n"


def _load_json(path: str) -> dict:
    candidate = Path(path).expanduser()
    if not candidate.is_file():
        raise ValueError(f"Report file not found: {path}")
    if candidate.stat().st_size > 50_000_000:
        raise ValueError("Report file exceeds the 50 MB safety limit.")
    try:
        return json.loads(candidate.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid report JSON: {exc}") from exc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Map Narwhal findings to likely repository owners and verification steps")
    ap.add_argument("report", help="scan/audit JSON report")
    ap.add_argument("--repo", default=".", help="site source repository (default: current directory)")
    ap.add_argument("--format", choices=("markdown", "json"), default="markdown")
    ap.add_argument("-o", "--output")
    ap.add_argument("--max-files", type=int, default=MAX_REPO_FILES,
                    help=f"repository inventory cap (maximum {MAX_REPO_FILES})")
    args = ap.parse_args(argv)
    try:
        report = _load_json(args.report)
        plan = build_plan(report, args.repo, report_source=str(Path(args.report).resolve()),
                          max_files=args.max_files)
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    output = render_json(plan) if args.format == "json" else render_markdown(plan)
    if args.output:
        try:
            Path(args.output).write_text(output, encoding="utf-8")
        except OSError as exc:
            print(f"Error: could not write {args.output}: {exc}", file=sys.stderr)
            return 2
        print(f"Wrote remediation plan to {args.output} ({len(plan['actions'])} actions)")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
