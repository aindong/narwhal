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
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PLAN_SCHEMA_VERSION = "1.0"
MAX_REPO_FILES = 5000
MAX_FILE_BYTES = 2_000_000
MAX_FINDINGS = 1000
SKIP_DIRS = {
    ".git", ".hg", ".svn", ".next", ".nuxt", ".output", ".cache",
    "node_modules", "vendor", "dist", "build", "coverage", "__pycache__",
}
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "good": 4}


def _legacy_rule_id(finding: dict) -> str:
    """Derive the same compatibility ID used by Report for pre-v2 reports."""
    if finding.get("rule_id"):
        return str(finding["rule_id"])
    title = str(finding.get("title", "")).split(" (")[0].strip().lower()
    slug = re.sub(r"[^a-z0-9]+", ".", title).strip(".")
    return f"{finding.get('category', 'unknown')}.{slug}"


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
    if kind == "audit":
        seen = {f["rule_id"]: f for f in findings}
        for raw in data.get("crawl", {}).get("recurring", []):
            if not isinstance(raw, dict) or raw.get("severity") == "good":
                continue
            finding = dict(raw)
            finding["rule_id"] = _legacy_rule_id(finding)
            finding["scope"] = "site"
            finding["occurrences"] = int(finding.get("count", 1))
            if finding["rule_id"] in seen:
                seen[finding["rule_id"]]["occurrences"] = finding["occurrences"]
            else:
                findings.append(finding)
                seen[finding["rule_id"]] = finding
        sitemap = data.get("sitemap", {})
        sitemap_issues = (list(sitemap.get("errors", []))
                          + list(sitemap.get("broken_sample", [])))
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
    ("json_ld", ("json.ld", "structured.data", "schema", "rich.result", "organization.website.entity")),
    ("robots_txt", ("robots.txt", "ai.crawlers.are.blocked")),
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
                  "language", "hreflang", "open_graph", "json_ld", "server_rendering"}


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
    "json_ld": "Add or repair JSON-LD for the page's real entity; validate all values before publishing.",
    "robots_txt": "Create or revise robots.txt deliberately, preserving intentional crawler policies.",
    "sitemap": "Create/configure the sitemap and reference it from robots.txt using the canonical deployed URL.",
    "llms_txt": "Generate a starter llms.txt in the public/static root, then curate every entry and TODO.",
    "content": "Revise the owning page content using the finding evidence and recommendation; preserve factual accuracy.",
    "server_rendering": "Move essential content and metadata into server-rendered output using the framework's SSR/static APIs.",
    "server_config": "Change hosting, CDN, redirect, TLS, compression, or response-header configuration outside page source.",
    "unknown": "Inspect the finding evidence and locate the owning source or external system before changing anything.",
}


def safety_for(artifact: str) -> tuple:
    if artifact == "server_config":
        return "manual_external", True
    if artifact in ("robots_txt", "sitemap", "llms_txt"):
        return "deploy_verification", True
    if artifact in ("title", "meta_description", "canonical", "language", "open_graph",
                    "content", "headings", "image_alt", "json_ld", "robots_meta", "hreflang",
                    "server_rendering"):
        return "review_required", False
    if artifact == "unknown":
        return "manual_external", False
    # Structural declarations such as a missing viewport can be inserted
    # deterministically; content-bearing values still require review above.
    return "safely_automatable", False


def verification_for(artifact: str, target: str, report_source: str) -> list:
    before = ("before.json" if report_source.startswith("<") else
              json.dumps(report_source))
    if artifact in ("robots_txt", "sitemap", "llms_txt", "server_config"):
        scan_target = json.dumps(target)
        scan_command = f"narwhal scan {scan_target} --format json -o after.json  # run after deploy"
    else:
        scan_command = ('narwhal scan "<local-preview-url>" --allow-private '
                        '--format json -o after.json')
    commands = [scan_command,
                f"narwhal diff {before} after.json"]
    if artifact == "json_ld":
        commands.insert(0, "Validate the rendered JSON-LD and replace every TODO placeholder.")
    return commands


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
        artifact = classify_artifact(finding)
        if artifact != "unknown":
            mapped_named += 1
        safety, requires_deploy = safety_for(artifact)
        owners = likely_files(root, inv["files"], framework["name"], artifact,
                              normalized["target"])
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
            "proposed_change": CHANGE_GUIDANCE[artifact],
            "likely_files": owners,
            "verification": verification_for(artifact, normalized["target"],
                                               report_source),
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
    ]
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
            lines += [f"### {action['severity'].upper()} — {action['title']}", "",
                      f"- **Rule:** `{action['rule_id']}`",
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
