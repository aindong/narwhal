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
import stat
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import links as linkslib, sitemap as sitemaplib, finding_urls  # noqa: E402
from lib.http import normalize_url, URLInputError  # noqa: E402
from lib.report import (recorded_llms_problem, recorded_schema_extraction_problem,  # noqa: E402
                        recorded_response_partial, recorded_response_truncated, recorded_scan_scope, _http_robots_notes,
                        recorded_image_weight_problem, _literal_preview_code)
from lib.report_output import write_output  # noqa: E402
from crawl_site import _link_coverage  # noqa: E402

PLAN_SCHEMA_VERSION = "1.0"
MAX_REPO_FILES = 5000
INVENTORY_ERROR_WITNESSES = 5
MAX_FILE_BYTES = 2_000_000
MAX_FINDINGS = 1000
REPORTED_TEXT_PREVIEW_CHARS = 600
SITEMAP_SAMPLE_WITNESSES = 5
LINK_TARGET_WITNESSES = 5
LINK_SOURCE_WITNESSES = 3
MEMORY_BASELINE_INSTRUCTION = (
    'Save the original input report JSON, keeping all fields, to a fresh before.json '
    'before edits or reruns. If using an existing saved report, point the diff at that '
    'baseline and choose distinct fresh verification output paths. '
    'Do not overwrite files or substitute a new scan. This read-only plan has not saved a baseline.'
)
SCAN_SETTINGS_INSTRUCTION = (
    'Restore the original scan configuration, access settings and resource limits before '
    'running this template. Recorded auditor selection, rendering, image-check '
    'and HTML byte-budget options are included when known; the report does not record the complete invocation. '
    'Matching known options alone does not establish comparable coverage.'
)
SKIP_DIRS = {
    ".git", ".hg", ".svn", ".next", ".nuxt", ".output", ".cache",
    "node_modules", "vendor", "dist", "build", "coverage", "__pycache__",
}
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "good": 4}
HTTP_ROBOTS_REVIEW_RULES = frozenset((
    'technical.http.robots.noindex', 'technical.http.robots.nofollow',
    'technical.http.x.robots.tag.declares.noindex', 'technical.http.x.robots.tag.declares.nofollow'))
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
    failures, unverified = [], []
    for item in observed:
        status = item.get('status') if isinstance(item, dict) else None
        error = item.get('error') if isinstance(item, dict) else None
        state = linkslib.http_check_state(status, error)
        if state == 'broken':
            failures.append(item)
        elif state == 'successful_2xx':
            continue
        else:
            unverified.append(item)
    return failures, unverified


def _url_witness(value):
    """Keep literal recorded labels, omitting the shared credential-like markers."""
    if not isinstance(value, str):
        return {'url': None}
    if linkslib.has_credential_like_marker(value):
        return {'url': None, 'url_omitted': 'credential_like_marker'}
    return {'url': value}


def _crawl_link_findings(crawl):
    """Carry reported link failures and measurement gaps into manual actions."""
    info = crawl.get('links')
    if info is None:
        return []  # link checking was not recorded/run
    if not isinstance(info, dict):
        raise ValueError('Report.crawl.links must be an object or null.')
    records = info.get('broken', [])
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise ValueError('Report.crawl.links.broken must be a list of objects.')
    for key in ('unique_links', 'checked', 'skipped_over_cap'):
        if key in info and (type(info[key]) is not int or info[key] < 0):
            raise ValueError('Report.crawl.links.' + key + ' must be a nonnegative integer.')
    failures, uncertain = [], []
    for row in records:
        status = row.get('status')
        confirmed = linkslib.http_check_state(status, row.get('error')) == 'broken'
        (failures if confirmed else uncertain).append(row)
    receipt = _link_coverage(dict(info, broken=records))
    if 'unverified' in info:
        rows = info['unverified']
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError('Report.crawl.links.unverified must be a list of objects.')
        if receipt:
            uncertain = list(rows)
        else:
            for row in rows:
                if row not in uncertain:
                    uncertain.append(row)
    if (receipt and (receipt['broken'] != len(failures)
                    or any(type(row.get('status')) is not int for row in records))):
        receipt = None
    budget_known = (all(key in info for key in ('unique_links', 'checked', 'skipped_over_cap'))
                    and info['unique_links'] == info['checked'] + info['skipped_over_cap'])

    def witnesses(rows):
        selected = []
        for row in rows[:LINK_TARGET_WITNESSES]:
            sources = row.get('sources')
            sources = [value for value in sources if isinstance(value, str)] if isinstance(sources, list) else None
            source_witnesses = ([_url_witness(value) for value in sources[:LINK_SOURCE_WITNESSES]]
                                if sources is not None else None)
            witness = {'status': row.get('status') if type(row.get('status')) is int else None,
                       **_url_witness(row.get('url')),
                       'internal': row.get('internal') if type(row.get('internal')) is bool else None,
                       'sources': [item['url'] for item in source_witnesses] if source_witnesses is not None else None,
                       'source_count': len(sources) if sources is not None else None}
            omissions = [{'position': position, 'reason': item['url_omitted']}
                         for position, item in enumerate(source_witnesses or [], 1) if 'url_omitted' in item]
            if omissions:
                witness['source_url_omissions'] = omissions
            selected.append(witness)
        return (f'Reported witnesses (first {len(selected)} of {len(rows)}; up to {LINK_SOURCE_WITNESSES} source URLs each; '
                'not rechecked; null means unavailable or explicitly omitted):\n'
                + json.dumps(selected, indent=2, ensure_ascii=True))

    findings = []
    if failures:
        findings.append({'category': 'technical', 'severity': 'medium', 'scope': 'site',
                         'rule_id': 'technical.links.http.failures',
                         'title': 'Reported failing HTTP link checks',
                         'detail': f'{len(failures)} reported failing HTTP response(s).\n' + witnesses(failures),
                         'occurrences': len(failures)})
    unverified = receipt['unverified'] if receipt else len(uncertain)
    skipped = info['skipped_over_cap'] if budget_known else 0
    if receipt is None or not budget_known or unverified or skipped:
        detail = (f"Recorded checked-target responses: {info['checked']} checked, {unverified} unverified; "
                  if receipt else 'Link-response coverage is unrecorded or inconsistent; ')
        detail += (f'{skipped} target(s) omitted by cap.' if budget_known else
                   'request-budget coverage is unrecorded or inconsistent.')
        detail += ' This does not establish dead destinations; target identities may be absent for legacy or capped checks.'
        if uncertain:
            detail += '\n' + witnesses(uncertain)
        findings.append({'category': 'technical', 'severity': 'low', 'scope': 'site',
                         'rule_id': 'technical.links.coverage.unverified',
                         'title': 'Link-check coverage needs manual verification', 'detail': detail,
                         'occurrences': max(1, unverified + skipped)})
    return findings


def _header_target_evidence(crawl, rule_id):
    """Match supported unprefixed header receipts, never infer affected targets."""
    directive = rule_id.rpartition('.')[2]
    witnesses, matched = [], 0
    for page in crawl.get('pages', []):
        if page.get('hard_fail') or not _http_robots_notes(page):
            continue
        receipt = page['http_robots']
        generic = receipt.get('generic')
        if (type(receipt.get('field_count')) is not int or receipt['field_count'] < 1
                or not isinstance(generic, list)
                or any(value not in ('noindex', 'nofollow') for value in generic)
                or directive not in generic):
            continue
        matched += 1
        if len(witnesses) >= LINK_TARGET_WITNESSES:
            continue
        target = page.get('url')
        row = {'crawl_target_label': target if isinstance(target, str) and target else None,
               'header_basis': receipt['basis']}
        if row['crawl_target_label'] is None:
            row['url_omitted'] = 'unrecorded_or_unsupported'
        elif linkslib.has_credential_like_marker(target):
            row['crawl_target_label'] = None
            row['url_omitted'] = 'credential_like_marker'
        witnesses.append(row)
    if not matched:
        return ''
    return (f'Matching recorded header receipts (first {len(witnesses)} of {matched}; '
            'crawl target labels, not verified response destinations or distinct pages; not re-fetched):\n'
            + json.dumps(witnesses))


def _automation_source_gap(page):
    """Explicitly failed or unusable execution evidence cannot support structural edits."""
    meta = page.get('meta', page)
    if not isinstance(meta, dict):
        meta = {}
    status = page.get('status', 0)
    scope = recorded_scan_scope(meta)
    return (page.get('hard_fail') is True
            or ('hard_fail' in page and type(page['hard_fail']) is not bool)
            or ('status' in page and (type(status) is not int or status == 206 or not 200 <= status < 300))
            or recorded_response_partial(meta) or recorded_response_truncated(meta)
            or ('scan_scope' in meta and scope is None)
            or (scope is not None and 'technical' not in scope[1]))


def _recorded_scan_options(page: dict) -> tuple:
    """Reproduce supported recorded inputs without guessing a full invocation."""
    meta = page.get('meta')
    meta = meta if isinstance(meta, dict) else {}
    options = []
    scope = recorded_scan_scope(meta)
    if scope is not None:
        options += ['--only', ','.join(scope[0])]
    settings = meta.get('scan_settings')
    if isinstance(settings, dict):
        if settings.get('render_requested') is True:
            options.append('--render')
        if settings.get('image_checks') is False:
            options.append('--no-image-checks')
    coverage = meta.get('coverage')
    budget = coverage.get('response_byte_limit') if isinstance(coverage, dict) else None
    if type(budget) is int and 64_000 <= budget <= 20_000_000:
        options += ['--max-bytes', str(budget)]
    return tuple(options)


def _validate_text(value, location, *, nullable=False):
    if nullable and value is None:
        return
    if not isinstance(value, str):
        raise ValueError(location + ' must be a string' + (' or null.' if nullable else '.'))
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise ValueError(location + ' must contain valid UTF-8 text.') from None


def _validate_findings(findings, location):
    """Validate fields consumed as identities, priorities and action evidence."""
    if not isinstance(findings, list):
        raise ValueError(location + ' must be a list.')
    for index, finding in enumerate(findings):
        at = f'{location}[{index}]'
        if not isinstance(finding, dict):
            raise ValueError(at + ' must be an object.')
        for field in ('category', 'title', 'recommendation'):
            if field in finding:
                _validate_text(finding[field], at + '.' + field)
        for field in ('detail', 'evidence'):
            _validate_text(finding.get(field), at + '.' + field, nullable=True)
        if 'severity' in finding and (not isinstance(finding['severity'], str)
                                      or finding['severity'] not in SEVERITY_RANK):
            raise ValueError(at + '.severity must be critical, high, medium, low or good.')
        rule = finding.get('rule_id')
        _validate_text(rule, at + '.rule_id', nullable=True)
        if rule and not rule.strip():
            raise ValueError(at + '.rule_id must be a string or null; whitespace is unsupported.')
        if not rule and not _legacy_rule_id(finding).rsplit('.', 1)[-1]:
            raise ValueError(at + ' needs an explicit rule_id or usable legacy title identity.')
        if 'confidence' in finding and (type(finding['confidence']) not in (int, float)
                                        or not 0 <= finding['confidence'] <= 1):
            raise ValueError(at + '.confidence must be a finite number between 0 and 1.')
        if 'scope' in finding and finding['scope'] not in ('page', 'site', 'external'):
            raise ValueError(at + '.scope must be page, site or external.')
        for field in ('count', 'occurrences'):
            if field in finding and (type(finding[field]) is not int or finding[field] < 1):
                raise ValueError(at + '.' + field + ' must be a positive integer.')


def normalize_report(data: dict) -> dict:
    """Accept scan or audit JSON and return its actionable page findings."""
    if not isinstance(data, dict):
        raise ValueError("Report JSON must be an object.")
    if 'findings' in data and 'homepage' in data:
        raise ValueError('Report has ambiguous scan/audit fields; supply one report kind.')
    if 'findings' in data:
        page = data
        target = data.get("final_url") or data.get("url") or ""
        kind = "scan"
    elif 'homepage' in data:
        page = data['homepage']
        if not isinstance(page, dict):
            raise ValueError('Report.homepage must be an object.')
        target = data.get("site") or page.get("final_url") or page.get("url") or ""
        kind = "audit"
    else:
        raise ValueError(
            "Unrecognized report JSON: expected `narwhal scan --format json` or "
            "`narwhal audit --format json` output.")
    _validate_text(target, 'Report URL label')
    for field in ('schema_version', 'tool_version'):
        if field in data:
            _validate_text(data[field], 'Report.' + field)
    score_field = 'overall_score' if 'overall_score' in data else 'score'
    score = data.get('overall_score', page.get('score'))
    if score is not None and (type(score) not in (int, float) or not 0 <= score <= 100):
        raise ValueError('Report.' + score_field + ' must be a finite number between 0 and 100 or null.')
    _validate_findings(page.get('findings', []), 'Report.homepage.findings' if kind == 'audit' else 'Report.findings')
    if kind == 'audit':
        for field in ('crawl', 'sitemap'):
            if not isinstance(data.get(field, {}), dict):
                raise ValueError('Report.' + field + ' must be an object.')
        crawl = data.get('crawl', {})
        pages = crawl.get('pages', [])
        if not isinstance(pages, list) or any(not isinstance(item, dict) for item in pages):
            raise ValueError('Report.crawl.pages must be a list of objects.')
        _validate_findings(crawl.get('recurring', []), 'Report.crawl.recurring')
    crawl_rule_ids = set()
    crawl_automation_gap = False
    findings = []
    for raw in page.get("findings", []):
        if not isinstance(raw, dict) or raw.get("severity") == "good":
            continue
        finding = dict(raw)
        finding["rule_id"] = _legacy_rule_id(finding)
        finding.setdefault("scope", "page")
        findings.append(finding)
    page_meta = page.get('meta')
    image_problem = recorded_image_weight_problem(page_meta, for_score=True)
    if image_problem:
        findings.append({'category': 'technical', 'severity': 'low', 'scope': 'page',
                         'rule_id': 'technical.images.weight.unverified',
                         'title': 'Image weights need manual verification', 'detail': image_problem})
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
        crawl_automation_gap = any(_automation_source_gap(item) for item in crawl.get('pages', [])
                                   if isinstance(item, dict))
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
            crawl_rule_ids.add(finding["rule_id"])
            if finding['rule_id'] in SCHEMA_VERIFICATION_RULES:
                schema_crawl_verification = True
            if schema_crawl_uncertain and finding['rule_id'] in SCHEMA_ABSENCE_RULES:
                continue  # aggregate occurrences cannot locate an absence in the verified portion
            finding["scope"] = "site"
            finding["occurrences"] = int(finding.get("count", finding.get("occurrences", 1)))
            findings.append(finding)
            seen[finding["rule_id"]] = finding
        findings.extend(_crawl_link_findings(crawl))
        sitemap = data.get("sitemap", {})
        findings.extend(_sitemap_note_findings(sitemap, data.get('schema_version')))
        failed_samples, unverified_samples = _sitemap_sample_evidence(sitemap)
        sitemap_issues = ([f'{len(failed_samples)} recorded failing sampled HTTP response(s)']
                          if failed_samples else [])
        if sitemap.get("problems") or sitemap.get("invalid_lastmod"):
            sitemap_issues.append("invalid sitemap entries or lastmod values")
        if sitemap_issues and "technical.sitemap.validation.issues" not in seen:
            detail = "; ".join(map(str, sitemap_issues[:5]))
            if failed_samples:
                witnesses = [{'status': item['status'],
                              **_url_witness(item.get('url'))}
                             for item in failed_samples[:SITEMAP_SAMPLE_WITNESSES]]
                detail += (f"\nReported HTTP failure witnesses (first {len(witnesses)} of {len(failed_samples)}; "
                           "not rechecked; null URL means unavailable or explicitly omitted):\n"
                           + json.dumps(witnesses, indent=2, ensure_ascii=True))
            findings.append({
                "category": "technical", "severity": "medium",
                "title": "Sitemap validation issues",
                "rule_id": "technical.sitemap.validation.issues",
                "scope": "site", "detail": detail,
                "recommendation": "Fix the reported sitemap entries and validate again.",
            })
        if unverified_samples:
            witnesses = [{'status': item.get('status') if type(item.get('status')) is int else None,
                          **_url_witness(item.get('url'))}
                         if isinstance(item, dict) else {'status': None, 'url': None}
                         for item in unverified_samples[:SITEMAP_SAMPLE_WITNESSES]]
            detail = (f'{len(unverified_samples)} recorded sample(s) lack a confirmed successful or failing HTTP response. '
                      'Gated, unsupported or no-response probes do not establish a dead URL.'
                      f'\nReported unverified witnesses (first {len(witnesses)} of {len(unverified_samples)}; '
                      'not rechecked; null means unavailable or explicitly omitted):\n'
                      + json.dumps(witnesses, indent=2, ensure_ascii=True))
            findings.append({
                'category': 'technical', 'severity': 'low', 'scope': 'site',
                'rule_id': 'technical.sitemap.sample.unverified',
                'title': 'Sampled sitemap URL reachability is unverified',
                'detail': detail,
                'recommendation': 'Verify endpoint access and request outcomes before editing sitemap locations.',
                'occurrences': len(unverified_samples),
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
    # Keep a complete worst-severity observation, never severity from one and evidence from another.
    coalesced = {}
    for finding in findings:
        coalesced.setdefault(finding["rule_id"], []).append(finding)
    representatives = []
    for observations in coalesced.values():
        representative = dict(min(observations, key=lambda finding: (
            SEVERITY_RANK.get(finding.get("severity"), 9), json.dumps(finding, sort_keys=True))))
        representative['occurrences'] = max(
            _positive_int(item.get('occurrences', item.get('count', 1))) for item in observations)
        if any(item.get('scope') == 'site' for item in observations):
            representative['scope'] = 'site'
        representatives.append(representative)
    normalized_findings = sorted(
        representatives,
        key=lambda finding: (SEVERITY_RANK.get(finding.get("severity"), 9),
                             finding["rule_id"]))
    total_findings = len(normalized_findings)
    return {
        "scan_options": _recorded_scan_options(page),
        "page_automation_gap": _automation_source_gap(page),
        "crawl_automation_gap": crawl_automation_gap,
        "crawl_rule_ids": sorted(crawl_rule_ids),
        "kind": kind,
        "target": str(target),
        "score": data.get("overall_score", page.get("score")),
        "report_schema_version": data.get("schema_version", "legacy"),
        "tool_version": data.get("tool_version", "unknown"),
        "finding_observation_counts": {rid: len(rows) for rid, rows in coalesced.items()},
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
    walk_errors = 0

    def on_walk_error(error):
        nonlocal walk_errors
        walk_errors += 1
        if walk_errors <= INVENTORY_ERROR_WITNESSES:
            warnings.append(f"Could not traverse repository directory {error.filename!r} "
                            f"({type(error).__name__}).")

    for current, dirs, names in os.walk(str(root), followlinks=False, onerror=on_walk_error):
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
            if len(files) >= max_files:
                capped = True
                break
            files.append(candidate.relative_to(root).as_posix())
        if capped:
            break
    if capped:
        warnings.append(f"Repository inventory capped at {max_files} files.")
    if walk_errors:
        warnings.append(f"Repository inventory could not traverse {walk_errors} directory/ies; "
                        "source coverage is incomplete. Check read permissions and rerun planning.")
    return {"files": sorted(files), "warnings": warnings, "capped": capped, "walk_errors": walk_errors}


def _read_small(root: Path, rel: str) -> str:
    path = root / rel
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return ""


def detect_framework(root: Path, files: list, warnings=None) -> dict:
    """Identify one primary framework from concrete repository signals."""
    file_set = set(files)
    scores = {name: 0 for name in ("nextjs", "astro", "nuxt", "hugo", "jekyll", "plain_html")}
    evidence = {name: [] for name in scores}

    def mark(name, points, message):
        scores[name] += points
        evidence[name].append(message)

    package = {}
    warnings = [] if warnings is None else warnings
    if "package.json" in file_set:
        try:
            package = json.loads(_read_small(root, "package.json"))
        except (ValueError, RecursionError):
            warnings.append('package.json could not be read as supported JSON within planner limits; '
                            'dependency evidence is unverified. Confirm the framework manually.')
            package = {}
        if not isinstance(package, dict):
            warnings.append('package.json is not a JSON object; dependency evidence is unverified. '
                            'Confirm the framework manually.')
            package = {}
    deps = set()
    for field in ('dependencies', 'devDependencies'):
        values = package.get(field, {})
        if not isinstance(values, dict):
            warnings.append(f'package.json {field} is not an object; this dependency section was skipped. '
                            'Confirm the framework manually.')
            continue
        valid = {name for name, version in values.items() if isinstance(version, str) and version.strip()}
        deps.update(valid)
        if len(valid) != len(values):
            warnings.append(f'package.json {field} contains unsupported dependency values; '
                            'only non-empty string declarations were used. Confirm the framework manually.')
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
    if rid in ('technical.links.with.no.anchor.text', 'technical.generic.anchor.text',
               'technical.links.invalid.url', 'technical.malformed.http.link.urls'):
        return 'content'
    if rid.startswith('technical.http.robots.') or rid in HTTP_ROBOTS_REVIEW_RULES:
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


SOURCE_CANDIDATE_WARNING = (
    'Unsafe or symlinked source candidates omitted; confirm source ownership manually. '
    'No URL path decoding or filesystem alias equivalence was inferred.'
)


def _portable_source_path(rel: str) -> bool:
    """Reject traversal, controls and drive/stream separator spellings."""
    return (bool(rel) and not any(char in rel for char in ('\\', ':'))
            and not any(ord(char) < 32 for char in rel)
            and all(part not in ('', '.', '..') for part in rel.split('/')))


def _safe_source_candidate(root: Path, rel: str) -> bool:
    """Check current containment and every component, including missing owners."""
    if not _portable_source_path(rel):
        return False
    try:
        root = root.resolve()
        path = root
        parts = rel.split('/')
        for index, part in enumerate(parts):
            path = path / part
            try:
                mode = path.lstat().st_mode
            except FileNotFoundError:
                break  # absent descendants are proposed owners, not observed files
            if stat.S_ISLNK(mode) or (index < len(parts) - 1 and not stat.S_ISDIR(mode)):
                return False
            if index == len(parts) - 1 and not stat.S_ISREG(mode):
                return False
        (root / rel).resolve().relative_to(root)
    except (OSError, ValueError, RuntimeError):
        return False
    return True


def _route_candidates(target: str, framework: str, warnings=None, *, files=()) -> list:
    if any(ord(char) < 32 for char in target):
        if warnings is not None:
            warnings.append(SOURCE_CANDIDATE_WARNING)
        return []
    try:
        parsed = urlparse(target)
        url_path = parsed.path
        path = url_path.strip("/")
    except ValueError:
        if warnings is not None:
            warnings.append(SOURCE_CANDIDATE_WARNING)
        return []
    if not path:
        if parsed.scheme in ('http', 'https') and parsed.netloc and url_path in ('', '/'):
            if framework == 'nextjs':
                return [f'{stem}.{extension}' for extension in ('tsx', 'ts', 'jsx', 'js')
                        for stem in ('src/app/page', 'app/page', 'src/pages/index', 'pages/index')
                        if f'{stem}.{extension}' in files]
            if framework == 'astro':
                return [f'src/pages/index.{extension}' for extension in ('astro', 'md', 'mdx', 'html')
                        if f'src/pages/index.{extension}' in files]
            if framework == 'nuxt':
                return [rel for rel in ('app/pages/index.vue', 'pages/index.vue') if rel in files]
            if framework == 'hugo':
                return ['content/_index.md'] if 'content/_index.md' in files else []
        return []
    if not _portable_source_path(path):
        if warnings is not None:
            warnings.append(SOURCE_CANDIDATE_WARNING)
        return []
    slug = path.split("/")[-1]
    if framework == "plain_html":
        direct = [path] if not url_path.endswith('/') and path.lower().endswith(('.html', '.htm')) else []
        return direct + [f"{path}.html", f"{path}/index.html"]
    if framework == "nextjs":
        routes = [f"src/app/{path}/page.tsx", f"app/{path}/page.tsx",
                  f"src/pages/{path}.tsx", f"pages/{path}.tsx"]
        # Additional spellings locate observed owners, not duplicate routes to create.
        routes += [f"{stem}.{extension}" for extension in ('tsx', 'ts', 'jsx', 'js')
                   for stem in (f"src/app/{path}/page", f"app/{path}/page",
                                f"src/pages/{path}", f"pages/{path}",
                                f"src/pages/{path}/index", f"pages/{path}/index")
                   if f"{stem}.{extension}" in files]
        return routes
    if framework == "astro":
        return [f"src/pages/{path}.astro", f"src/pages/{path}/index.astro"] + [
            f'{stem}.{extension}' for extension in ('md', 'mdx', 'html')
            for stem in (f'src/pages/{path}', f'src/pages/{path}/index')
            if f'{stem}.{extension}' in files]
    if framework == "nuxt":
        return [f"pages/{path}.vue", f"pages/{path}/index.vue"] + [
            rel for rel in (f'app/pages/{path}.vue', f'app/pages/{path}/index.vue') if rel in files]
    if framework in ("hugo", "jekyll"):
        prefix = "content" if framework == "hugo" else ""
        base = f"{prefix}/{path}".strip("/")
        routes = [f"{base}.md", f"{base}/index.md", f"{slug}.md"]
        if framework == 'hugo' and f'{base}/_index.md' in files:
            routes.append(f'{base}/_index.md')
        return routes
    return []


def likely_files(root: Path, files: list, framework: str, artifact: str,
                 target: str, warnings=None) -> list:
    if artifact in ("server_config", "unknown"):
        return []
    file_set = set(files)
    config = FRAMEWORK_CANDIDATES.get(framework, FRAMEWORK_CANDIDATES["unknown"])
    routes = ([] if artifact in ('robots_txt', 'sitemap', 'llms_txt') else
              _route_candidates(target, framework, warnings, files=file_set))
    preferred_routes = set(routes) if (artifact in ('content', 'headings', 'image_alt')
                                      or framework == 'plain_html' and artifact in HEAD_ARTIFACTS) else set()
    if artifact in ("robots_txt", "sitemap"):
        candidates = list(config.get(artifact, []))
        if framework == 'nextjs':
            filenames = ('robots.js', 'robots.txt') if artifact == 'robots_txt' else ('sitemap.js', 'sitemap.xml')
            candidates += [f'{base}/{name}' for base in ('src/app', 'app') for name in filenames
                           if f'{base}/{name}' in file_set]
    elif artifact == "llms_txt":
        base = (config.get("static") or ["."])[0]
        candidates = [("llms.txt" if base == "." else f"{base}/llms.txt")]
    elif artifact in HEAD_ARTIFACTS:
        candidates = list(config.get("head", [])) + routes
    else:
        candidates = routes + list(config.get("content", []))

    # Include existing convention-matching files, not just canonical names.
    if artifact in HEAD_ARTIFACTS:
        candidates += [f for f in files if any(part in f.lower() for part in
                       ("layout", "head.", "_document", "app.vue"))][:12]
    if artifact in ("content", "headings", "image_alt"):
        candidates += [f for f in files if f.lower().endswith(
            (".html", ".md", ".mdx", ".tsx", ".jsx", ".vue", ".astro"))][:15]

    out, seen = [], set()
    for rel in candidates:
        if not rel or rel in seen:
            continue
        seen.add(rel)
        if not _safe_source_candidate(root, rel):
            if warnings is not None:
                warnings.append(SOURCE_CANDIDATE_WARNING)
            continue
        exists = rel in file_set
        out.append({
            "path": rel,
            "exists": exists,
            "confidence": 0.9 if exists and (rel in preferred_routes or rel in candidates[:4]) else (0.72 if exists else 0.42),
            "reason": ("Existing route convention; confirm source ownership" if exists and rel in routes else
                       "Existing framework convention" if exists else
                       "Framework convention; create or confirm generated owner"),
        })
    out.sort(key=lambda item: (not item["exists"], -item["confidence"],
                               not (item["exists"] and item["path"] in preferred_routes), item["path"]))
    return out[:8]


CHANGE_GUIDANCE = {
    "title": "Define a unique, descriptive page title in the framework's metadata/head API.",
    "meta_description": "Add or revise the page meta description in its metadata/head owner.",
    "canonical": "Define the intended absolute canonical URL in the page or shared head owner.",
    "robots_meta": "Review the page robots directive and remove noindex/nofollow only if indexing is intended.",
    "viewport": "Inspect complete HTML and the current viewport/source owner. Add a declaration only if confirmed absent; repair an empty declaration in place. Preserve intentional values and avoid duplicate declarations.",
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
    **dict.fromkeys(HTTP_ROBOTS_REVIEW_RULES,
        'Review the observed response headers, their page/crawler scope and the hosting/CDN/middleware response-header owner. '
        'Preserve intentional restrictions; change X-Robots-Tag only if confirmed unintended. '
        'Editing HTML meta tags does not remove a response header. Re-fetch affected headers after deployment; '
        'declarations do not prove live indexing or crawler behavior.'),
    **dict.fromkeys(('technical.links.invalid.url', 'technical.malformed.http.link.urls'),
        'Inspect the recorded href spellings in current source and confirm the intended destinations. '
        'Correct verified host, IPv6 bracket or port syntax without guessing a new destination or '
        'dropping parameters. Syntax rejection is not a failed HTTP request; verify destination behavior separately.'),
    'technical.links.with.no.anchor.text':
        'Review the recorded anchors, intended link labels and destination context. Add useful visible text '
        'or meaningful image alt text where appropriate; preserve valid accessible labeling. '
        'This source check is not a full accessibility audit or proof of destination reachability.',
    'technical.generic.anchor.text':
        'Review surrounding text and destination purpose. Make labels descriptive where useful, preserving '
        'concise navigation and intentional repeated wording. Do not insert keywords or promise ranking '
        'gains solely to change the phrase count.',
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
        'Do not remove sitemap URLs solely on gated, unsupported, incomplete or no-response probes.',
        ('Review sampled status/error evidence and intended access policy.',
         'Recheck sampled endpoints and deployed sitemap reachability after any confirmed fix; '
         'do not equate gated/unsupported/no-response results with dead URLs.')),
}


RESOURCE_VERIFICATION = dict(SITEMAP_VERIFICATION)
RESOURCE_VERIFICATION['technical.links.http.failures'] = (
    'Recheck reported targets and referring anchors, including HEAD/GET support and intended access. '
    'Repair destinations or target behavior only after confirming the defect and actual source ownership.',
    ('Inspect the recorded status, target and referring-page witnesses in the original audit; this plan has not fetched them.',
     'Verify target responses and intended anchor behavior manually. Inspect actual source before any edit; '
     'rerun the bounded crawl/audit link check after a confirmed fix.'))
RESOURCE_VERIFICATION['technical.links.coverage.unverified'] = (
    'Review request coverage, access policy and the deliberate link cap before rerunning. '
    'Gated, no-response or capped links do not establish dead destinations.',
    ('Review the original audit and source anchors; unverified target identities may be absent from the rollup.',
     'Recheck within an intentional request budget and verify HEAD/GET support; do not remove links solely to clear measurement gaps.'))
RESOURCE_VERIFICATION['technical.response.partial'] = (
    'Verify full standalone HTML delivery and server/CDN range handling before proposing source edits. '
    'Do not rewrite metadata, schema or content based on a partial/ranged body.',
    ('Inspect observed HTTP status and bounded coverage evidence without relaxing SSRF or byte limits.',
     'Re-scan the intended full-page URL after verifying complete HTML; do not treat fail-safe score changes as SEO gains.'))
RESOURCE_VERIFICATION['technical.hreflang.urls.review'] = (
    'Confirm intended language-page URLs and original HTML declarations before editing. '
    'Do not invent locale pages, infer HTTP failures or rewrite unrelated anchor links.',
    ('Inspect supported/omitted source counts and verify intended fully-qualified HTTP(S) alternates manually.',
     'Re-scan source annotations and bounded reciprocal snapshots after any confirmed correction; '
     'verify search acceptance separately.'))
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
RESOURCE_VERIFICATION['technical.images.weight.unverified'] = (
    'Verify intended image responses and bounded HEAD weight evidence before proposing optimization edits. '
    'Do not resize, replace or remove an image solely because its weight was unverified.',
    ('Review HTTP status, media type and complete Content-Length evidence with existing access/budget guards.',
     'Re-scan after verifying the response; unknown weights cannot establish resolved optimization findings or score gains.'))
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


def safety_for(artifact: str, rule_id: str = "") -> tuple:
    if artifact == "server_config":
        return "manual_external", True
    if artifact in ("robots_txt", "sitemap", "llms_txt"):
        return "deploy_verification", True
    if artifact in ("title", "meta_description", "canonical", "language", "open_graph",
                    "content", "headings", "image_alt", "json_ld", "product_schema", "robots_meta", "hreflang",
                    "server_rendering"):
        return "review_required", False
    if artifact == "viewport":
        return ("safely_automatable" if rule_id == "technical.no.responsive.viewport.tag"
                else "review_required"), False
    return "manual_external", False


def _verification_output(report_source, name):
    """Avoid known baseline basename collisions without inspecting the filesystem.

    Treat case and either path separator conservatively for portable templates;
    callers must still choose fresh paths and check symlink/hardlink aliases.
    """
    baseline = report_source.replace('\\', '/').rsplit('/', 1)[-1].casefold()
    return name.replace('.json', '-2.json') if baseline == name else name


def _verification_outputs(report_source):
    return (_verification_output(report_source, 'page-after.json'),
            _verification_output(report_source, 'after.json'))


def verification_for(artifact: str, target: str, report_source: str,
                     report_kind: str = "scan", *, scan_options: tuple = ()) -> list:
    """Human POSIX-shell templates; quote data and stop option interpretation."""
    memory_source = report_source.startswith("<")
    prerequisites = [MEMORY_BASELINE_INSTRUCTION] if memory_source else []
    before = ("before.json" if memory_source else
              shlex.quote(report_source))
    page_output, comparison_output = _verification_outputs(report_source)
    options = ''.join(' ' + shlex.quote(option) for option in scan_options)
    local = []
    if artifact not in ("robots_txt", "sitemap", "llms_txt", "server_config"):
        page_before = _verification_output(report_source, 'page-before.json')
        local = [SCAN_SETTINGS_INSTRUCTION,
                 'Before editing, when a preview is available, confirm its route maps to the affected source. '
                 'Capture this local baseline with fresh paths; use distinct snapshots for each affected page.',
                 f"narwhal scan --allow-private --format json -o {page_before}{options} -- '<local-preview-url>'",
                 'After applying the reviewed source edits, scan the same local route with matching options.',
                 f"narwhal scan --allow-private --format json -o {page_output}{options} -- '<local-preview-url>'",
                 f'narwhal diff --fail-on-regression --require-comparable -- {page_before} {page_output}',
                 'The local pair verifies page-level changes only; do not compare '
                 f'{page_output} with the original baseline or treat it as deployed site verification. '
                 'Without a pre-edit local scan, the preview is a current-state check, not measured improvement. '
                 'If no preview is available, mark local proof pending and use the original baseline checks after deployment.']
        if artifact in ("json_ld", "product_schema"):
            local.insert(4, "Validate the rendered structured data and replace every TODO placeholder.")
    if report_kind == 'audit':
        commands = local
        commands += [
            'Restore the original audit configuration, rendering, access settings and '
            'crawl/link/sitemap limits before running this template; the report does '
            'not record the complete invocation. A matching report kind alone does '
            'not establish comparable coverage.',
            f'narwhal audit --format json -o {comparison_output} -- {shlex.quote(target)}  # run after deploy',
            f'narwhal diff --fail-on-regression --require-comparable -- {before} {comparison_output}',
        ]
        return prerequisites + commands
    scan_target = shlex.quote(target)
    scan_command = f"narwhal scan --format json -o {comparison_output}{options} -- {scan_target}  # run after deploy"
    if not local:
        prerequisites.append(SCAN_SETTINGS_INSTRUCTION)
    commands = local + [scan_command,
                f"narwhal diff --fail-on-regression --require-comparable -- {before} {comparison_output}"]
    return prerequisites + commands


def _rule_page_witnesses(report, target):
    """Index bounded per-rule labels, without inferring page severity or completeness."""
    # Audit retains bare-host input; normalize context, never imported URL labels.
    try:
        target = normalize_url(target)
    except URLInputError:
        return {}
    samples = {}
    crawl_rules = set()
    for row in report.get('crawl', {}).get('recurring', []):
        rule = _legacy_rule_id(row)
        crawl_rules.add(rule)
        sample = finding_urls.read(row, target)
        if sample is not None:
            for url in sample['urls']:
                finding_urls.record(samples, rule, url)
    page = report.get('homepage', {})
    page_url = page.get('final_url') or page.get('url') or target
    if not _automation_source_gap(page) and finding_urls.same_origin_label(page_url, target):
        for row in page.get('findings', []):
            rule = _legacy_rule_id(row)
            if row.get('severity') != 'good' and rule in crawl_rules:
                finding_urls.record(samples, rule, page_url)
    return {rule: sample['urls'] for rule, sample in samples.items()}


def _witness_owners(root, files, framework, artifact, targets, warnings, unlocated=None):
    """Keep observed candidates for witnessed pages, never an unrelated home fallback."""
    local = artifact in ('content', 'headings', 'image_alt') or framework == 'plain_html'
    matches, candidates = set(), {}
    file_set = set(files)
    for target in targets:
        routes = set(_route_candidates(target, framework, warnings, files=file_set))
        if urlparse(target).path in ('', '/'):
            routes.update(FRAMEWORK_CANDIDATES.get(framework, {}).get('content', []))
        matches.update(routes)
        located = False
        for owner in likely_files(root, files, framework, artifact, target, warnings):
            if not owner['exists'] or (local and owner['path'] not in routes):
                continue
            located = True
            previous = candidates.get(owner['path'])
            if previous is None or owner['confidence'] > previous['confidence']:
                candidates[owner['path']] = owner
        if not located:
            if unlocated is not None:
                unlocated.append(target)
            warnings.append('A recorded recurring-rule URL has no inventoried source candidate; '
                            'locate it manually before claiming site-wide remediation.')
    return sorted(candidates.values(), key=lambda owner: (
        -owner['confidence'], not (local and owner['path'] in matches), owner['path']))[:8]


def build_plan(report: dict, repo: str, *, report_source="<memory>",
               max_files=MAX_REPO_FILES) -> dict:
    normalized = normalize_report(report)
    root = safe_repo_root(repo)
    inv = inventory(root, max_files=max(1, min(int(max_files), MAX_REPO_FILES)))
    warnings = list(inv["warnings"])
    framework = detect_framework(root, inv["files"], warnings)
    page_witnesses = (_rule_page_witnesses(report, normalized['target'])
                      if normalized['kind'] == 'audit' else {})
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
            artifact = ('links' if finding['rule_id'].startswith('technical.links.') else
                        'static' if finding['rule_id'] == 'technical.images.weight.unverified' else
                        'server_config' if finding['rule_id'] == 'technical.response.partial' else
                        'canonical' if finding['rule_id'] == 'technical.canonical.comparison.unverified' else
                        'hreflang' if finding['rule_id'] == 'technical.hreflang.urls.review' else
                        'server_rendering' if finding['rule_id'] in RENDER_VERIFICATION_RULES else
                        'json_ld' if finding['rule_id'].startswith('schema.') else
                        'llms_txt' if finding['rule_id'] == 'geo.llms.txt.availability.unverified' else 'sitemap')
        if artifact != "unknown":
            mapped_named += 1
        safety, requires_deploy = safety_for(artifact, finding["rule_id"])
        if verification:
            safety, requires_deploy = 'manual_external', False
        site_page = (finding['rule_id'] in normalized['crawl_rule_ids'] and not verification
                     and artifact in HEAD_ARTIFACTS | {'content', 'headings', 'image_alt'})
        targets = page_witnesses.get(finding['rule_id'], [])
        unlocated = []
        if verification:
            owners = []
        elif site_page:
            owners = _witness_owners(root, inv['files'], framework['name'], artifact, targets, warnings, unlocated)
        else:
            owners = likely_files(root, inv['files'], framework['name'], artifact, normalized['target'], warnings)
        eligibility = None
        if artifact == 'viewport':
            blockers = []
            if finding['rule_id'] != 'technical.no.responsive.viewport.tag':
                blockers.append('unrecognized_structural_rule')
            if inv['capped'] or inv['walk_errors']:
                blockers.append('incomplete_repository_inventory')
            if unlocated:
                blockers.append('unlocated_page_witness')
            if not any(owner.get('exists') is True for owner in owners):
                blockers.append('no_existing_owner_candidate')
            if ((finding.get('scope', 'page') != 'site' and normalized['page_automation_gap'])
                    or (finding['rule_id'] in normalized['crawl_rule_ids'] and normalized['crawl_automation_gap'])):
                blockers.append('known_incomplete_source_evidence')
            eligibility = {
                'basis': 'explicit_structural_rule_and_existing_candidate_v1',
                'eligible': not blockers, 'blockers': blockers,
                'scope': 'Planning classification only, not edit authorization or proof of source ownership/completeness; inspect current source before editing.',
            }
            if blockers:
                safety = 'review_required'
        if not owners and safety != "manual_external":
            warnings.append(f"No likely source owner found for {finding['rule_id']}.")
            safety = 'manual_external'
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
                                              normalized["kind"], scan_options=normalized["scan_options"])),
            "evidence": finding.get("evidence") or finding.get("detail") or "",
            "source_recommendation": finding.get("recommendation", ""),
            "confidence": finding.get("confidence", 1.0),
            "scope": finding.get("scope", "page"),
            "occurrences": _positive_int(finding.get("occurrences", finding.get("count", 1))),
            "provenance": {"source": "narwhal_finding", "report": report_source,
                           "report_schema_version": normalized["report_schema_version"]},
        })
        if site_page:
            note = ('Recorded URL label witnesses for this rule across audit page/crawl observations; '
                    'not a complete affected-page list, per-page severity or proof of ownership. '
                    'Confirm current source and URL behavior before editing.\n' + json.dumps(targets, ensure_ascii=False)
                    if targets else
                    'Recurring rule page locations are unverified. Re-run the audit or confirm affected URLs '
                    'before selecting source files; aggregate counts do not locate a page owner.')
            actions[-1]['evidence'] += ('\n\n' if actions[-1]['evidence'] else '') + note
        if normalized['kind'] == 'audit' and finding['rule_id'] in HTTP_ROBOTS_REVIEW_RULES:
            targets = _header_target_evidence(report.get('crawl', {}), finding['rule_id'])
            if targets:
                actions[-1]['evidence'] += ('\n\n' if actions[-1]['evidence'] else '') + targets
        if eligibility is not None:
            actions[-1]['automation_eligibility'] = eligibility
        observation_count = normalized['finding_observation_counts'][finding['rule_id']]
        if observation_count > 1:
            actions[-1]['observation_selection'] = {
                'basis': 'worst_severity_then_sorted_json_v1',
                'normalized_observations': observation_count,
                'occurrences_basis': 'maximum_recorded_count',
                'scope': 'One representative from normalized findings/rollups; not matched or distinct page instances. '
                         'Consult the original report for other observations. Site scope is retained when recorded.',
            }
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
            "file_inventory_walk_errors": inv["walk_errors"],
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
    """Coordinate source candidates without promoting manual verification to edits."""
    buckets = {}
    for action in actions:
        if (action['rule_id'] in RESOURCE_VERIFICATION
                or action['safety'] == 'manual_external' or not action['likely_files']):
            continue  # keep manual/ownerless work in the action list, not edit groups
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
        usage = {}
        for action in members:
            for candidate in action['likely_files']:
                if candidate['exists']:
                    usage.setdefault(candidate['path'], set()).add(action['rule_id'])
        out.append({"group_id": f"group:{key}", "artifact": key,
                    "rule_ids": sorted(a["rule_id"] for a in members),
                    "likely_shared_files": sorted(usage),
                    "candidate_file_basis": "Legacy likely_shared_files is the union of existing candidates, not proven shared ownership.",
                    "candidate_file_overlaps": [
                        {'path': path, 'rule_ids': sorted(rules)} for path, rules in sorted(usage.items())
                        if len(rules) > 1],
                    "reason": "Review related actions together; confirm source owners before coordinating edits."})
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


def _code_block(text: str, language: str) -> list:
    """Keep literal backtick runs inside data or command blocks."""
    longest_run = max((len(run) for run in re.findall(r'`+', text)), default=0)
    fence = '`' * max(3, longest_run + 1)
    return [f'{fence}{language}', text, fence, '']


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
    for instruction in (MEMORY_BASELINE_INSTRUCTION, SCAN_SETTINGS_INSTRUCTION):
        if any(instruction in action['verification'] for action in plan['actions']):
            lines += ['> ' + instruction, '']
    if (plan.get('provenance', {}).get('report_kind') == 'audit'
            and any(step.startswith('narwhal audit ') for action in plan['actions']
                    for step in action['verification'])):
        page_output, _ = _verification_outputs(plan['provenance']['report'])
        lines += ['## Audit verification', '',
                  'A local page scan can verify page-level changes only. Keep its '
                  f'`{page_output}` separate; do not diff it against the audit baseline. '
                  'Site-level signals remain pending deployment.', '']
        steps = verification_for('server_config', plan['target'], plan['provenance']['report'], 'audit')[-3:]
        lines += [steps[0], ''] + _code_block(steps[1] + '\n' + steps[2], 'sh')
    for safety, label in (("manual_external", "Manual / external"),
                          ("review_required", "Review required"),
                          ("deploy_verification", "Apply, then verify after deploy"),
                          ("safely_automatable", "Safe candidates for automation")):
        members = [a for a in plan["actions"] if a["safety"] == safety]
        if not members:
            continue
        lines += [f"## {label}", ""]
        for action in members:
            owners = ", ".join(
                f"{_literal_preview_code(x['path'])} ({'in file inventory' if x['exists'] else 'not in file inventory'})"
                for x in action["likely_files"][:3]) or "owner not located"
            if len(action['likely_files']) > 3:
                owners += f"; additional candidates in JSON: {len(action['likely_files']) - 3}"
            if action['rule_id'] in RESOURCE_VERIFICATION:
                owners = 'not assigned (verification only)'
            scope_lines = []
            if 'automation_eligibility' in action:
                receipt = action['automation_eligibility']
                result = 'candidate' if receipt['eligible'] else 'withheld: ' + ', '.join(receipt['blockers'])
                scope_lines.append(f"- **Automation eligibility:** {result}. {receipt['scope']}")
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
            if 'observation_selection' in action:
                receipt = action['observation_selection']
                scope_lines.append(f"- **Observation selection:** One complete worst-severity representative from "
                                   f"{receipt['normalized_observations']} normalized observations; equal-severity ties use "
                                   "sorted-key JSON order. Occurrences retain the maximum recorded count, not a sum or "
                                   "matched page instances. Consult the original report for other observations.")
            lines += [f"### {action['severity'].upper()} — {display_title}", "",
                      f"- **Rule:** `{action['rule_id']}`",
                      *scope_lines,
                      f"- **Likely owner:** {owners}",
                      f"- **Change:** {action['proposed_change']}", ""]
            for field, label, full_label in (
                    ('evidence', 'Reported evidence (preview, not reverified)', 'evidence'),
                    ('source_recommendation', 'Reported recommendation (preview, review required)', 'source_recommendation')):
                text = action.get(field)
                if text:
                    if field == 'source_recommendation' and (
                            action['rule_id'] in EDITORIAL_REVIEW_GUIDANCE or action['rule_id'] in RESOURCE_VERIFICATION):
                        lines += ['_Original recommendation remains in plan JSON; use the contextual '
                                  'review/verification guidance above._', '']
                        continue
                    lines += [f'**{label}:**', '']
                    lines += _code_block(text[:REPORTED_TEXT_PREVIEW_CHARS], 'text')
                    if len(text) > REPORTED_TEXT_PREVIEW_CHARS:
                        lines += [f'_Preview truncated at {REPORTED_TEXT_PREVIEW_CHARS} characters; '
                                  f'full action {full_label} remains in plan JSON._', '']
            lines += ["**Verification, in order:**", ""]
            for step in action['verification']:
                if step in (MEMORY_BASELINE_INSTRUCTION, SCAN_SETTINGS_INSTRUCTION):
                    continue  # the shared prerequisite is already visible above all actions
                if step.startswith('narwhal '):
                    lines += _code_block(step, 'sh')
                else:
                    lines += [step, '']
    if plan["groups"]:
        lines += ["## Related actions to review", ""]
        for group in plan["groups"]:
            overlaps = group.get('candidate_file_overlaps')
            overlap_paths = ', '.join(_literal_preview_code(item['path']) for item in overlaps) if overlaps is not None else 'unrecorded'
            lines.append(f"- **{group['artifact']}** — {len(group['rule_ids'])} findings; "
                         f"existing candidate union: {', '.join(_literal_preview_code(path) for path in group['likely_shared_files']) or 'none recorded'}; "
                         f"candidates in multiple actions: {overlap_paths or 'none recorded'}. "
                         "Confirm actual owners before coordinating edits.")
        lines.append("")
    if plan["conflicts"]:
        lines += ["## Conflicts requiring a decision", ""]
        for conflict in plan["conflicts"]:
            lines.append(f"- **{conflict['conflict_id']}** — {conflict['reason']}")
        lines.append("")
    if plan["warnings"]:
        lines += ["## Coverage warnings", ""] + [f"- {w}" for w in plan["warnings"]] + [""]
    return "\n".join(lines).rstrip() + "\n"


def _load_json(path: str, input_stats=None) -> dict:
    candidate = Path(path).expanduser()
    if not candidate.is_file():
        raise ValueError(f"Report file not found: {path}")
    if candidate.stat().st_size > 50_000_000:
        raise ValueError("Report file exceeds the 50 MB safety limit.")
    try:
        with candidate.open('r', encoding='utf-8') as source:
            if input_stats is not None:
                input_stats.append(os.fstat(source.fileno()))
            text = source.read()
    except UnicodeError:
        raise ValueError('Report file must contain UTF-8 JSON.') from None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f'Invalid report JSON at line {exc.lineno}, column {exc.colno}.') from None
    except (ValueError, RecursionError):
        raise ValueError('Report JSON could not be decoded within supported parser limits.') from None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Map Narwhal findings to likely repository owners and verification steps")
    ap.add_argument("report", help="scan/audit JSON report")
    ap.add_argument("--repo", default=".", help="site source repository (default: current directory)")
    ap.add_argument("--format", choices=("markdown", "json"), default="markdown")
    ap.add_argument("-o", "--output", help='save to a regular file distinct from the input report')
    ap.add_argument("--max-files", type=int, default=MAX_REPO_FILES,
                    help=f"repository inventory cap (maximum {MAX_REPO_FILES})")
    args = ap.parse_args(argv)
    input_stats = [] if args.output else None
    try:
        report = _load_json(args.report, input_stats)
        plan = build_plan(report, args.repo, report_source=str(Path(args.report).expanduser().resolve()),
                          max_files=args.max_files)
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    output = render_json(plan) if args.format == "json" else render_markdown(plan)
    if args.output:
        try:
            write_output(args.output, output, input_stats, label='Remediation plan output')
        except ValueError as exc:
            print(f'Error: {exc}', file=sys.stderr)
            return 2
        except OSError as exc:
            print(f'Error: Could not write remediation plan output ({type(exc).__name__}); '
                  'check target path and permissions.', file=sys.stderr)
            return 2
        print(f"Wrote remediation plan to {args.output} ({len(plan['actions'])} actions)")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
