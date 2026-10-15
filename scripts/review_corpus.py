#!/usr/bin/env python3
"""Offline reported-finding review packets; not a scanner accuracy benchmark.

No network, imports of scanner code, source edits, remediation or score changes.
Snapshots and reviewer identities remain caller-controlled, not attestations.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import sys

MAX_CASES = 100
MAX_FINDINGS = 10_000
MAX_REPORT_BYTES = 2_000_000
MAX_EVIDENCE_BYTES = 5_000_000
MAX_INPUT_BYTES = 32_000_000
MAX_PACKET_BYTES = 32_000_000
DIMENSIONS = ('observation', 'priority', 'recommendation')
VERDICTS = ('pending', 'supported', 'unsupported', 'uncertain', 'not_applicable')
SEVERITIES = ('critical', 'high', 'medium', 'low', 'good')
BASIS = ('Review of reported actionable findings only. Good findings are excluded; '
         'missed issues, recall, ranking outcomes and reviewer independence are not measured. '
         'Hashes bind local file versions, not origin, capture accuracy or reviewer identity.')


def _object(pairs):
    """Reject duplicate JSON keys instead of letting a later value hide data."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def _json(raw):
    def invalid_constant(value):
        raise ValueError('Nonfinite JSON number: ' + value)
    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('Nonfinite JSON number')
        return result
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_object,
                      parse_constant=invalid_constant, parse_float=finite_float)


def _same(left, right):
    """Compare JSON values without equating booleans with numeric scalars."""
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def _read(path, limit):
    if limit < 0:
        raise ValueError('Input byte limit exceeded')
    if not path.is_file():
        raise ValueError('Expected a regular file: ' + str(path))
    with path.open('rb') as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Input byte limit exceeded: ' + str(path))
    return raw


def _file(root, name, limit, budget):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError('Snapshot paths must be nonempty relative paths')
    path = (root / name).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise ValueError('Snapshot path escapes manifest directory') from None
    raw = _read(path, min(limit, MAX_INPUT_BYTES - budget[0]))
    budget[0] += len(raw)
    return raw


def _timestamp(value):
    if not isinstance(value, str) or not value:
        raise ValueError('A timezone-aware timestamp is required')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.utcoffset() is None:
        raise ValueError('A timezone-aware timestamp is required')


def _text(value, label, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise ValueError(label + ' must be a string' + ('' if empty else ' with content'))
    return value


def prepare(manifest_path):
    """Build pending reviews from exact local snapshots with explicit limits."""
    manifest_path = Path(manifest_path).resolve()
    raw_manifest = _read(manifest_path, 1_000_000)
    manifest = _json(raw_manifest)
    if (not isinstance(manifest, dict) or type(manifest.get('schema_version')) is not int
            or manifest['schema_version'] != 1 or set(manifest) != {'schema_version', 'name', 'cases'}):
        raise ValueError('Expected manifest schema version 1 with name and cases')
    _text(manifest['name'], 'Corpus name')
    entries = manifest['cases']
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_CASES:
        raise ValueError('Manifest requires 1–100 cases')
    root, budget, cases, ids, digests, finding_count = manifest_path.parent, [len(raw_manifest)], [], set(), set(), 0
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) - {'id', 'report', 'evidence'}:
            raise ValueError('Invalid case fields')
        case_id = entry.get('id')
        if not isinstance(case_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', case_id) or case_id in ids:
            raise ValueError('Case IDs must be unique simple identifiers')
        ids.add(case_id)
        raw = _file(root, entry.get('report'), MAX_REPORT_BYTES, budget)
        digest = sha256(raw).hexdigest()
        if digest in digests:
            raise ValueError('Duplicate report bytes cannot count as another case')
        digests.add(digest)
        report = _json(raw)
        if (not isinstance(report, dict) or not isinstance(report.get('findings'), list)
                or not isinstance(report.get('url'), str)):
            raise ValueError('Expected a single-page report with URL and findings')
        attached, evidence_ids = [], set()
        evidence = entry.get('evidence', [])
        if not isinstance(evidence, list) or len(evidence) > 4:
            raise ValueError('At most four evidence files per case')
        for item in evidence:
            if not isinstance(item, dict) or set(item) != {'id', 'path', 'kind', 'captured_at'}:
                raise ValueError('Evidence needs id, path, kind and captured_at')
            evidence_id = _text(item['id'], 'Evidence ID')
            if evidence_id in evidence_ids:
                raise ValueError('Duplicate evidence ID')
            evidence_ids.add(evidence_id)
            _text(item['kind'], 'Declared evidence kind')
            _timestamp(item['captured_at'])
            content = _file(root, item['path'], MAX_EVIDENCE_BYTES, budget)
            if sha256(content).hexdigest() == digest:
                raise ValueError('A report cannot corroborate itself as attached evidence')
            attached.append({**item, 'sha256': sha256(content).hexdigest(), 'bytes': len(content)})
        rows, excluded = [], 0
        for ordinal, finding in enumerate(report['findings']):
            finding_count += 1
            if finding_count > MAX_FINDINGS:
                raise ValueError('Finding limit exceeded')
            if not isinstance(finding, dict) or finding.get('severity') not in SEVERITIES:
                raise ValueError('Finding severity must be recognized')
            for key in ('category', 'title'):
                _text(finding.get(key), 'Finding ' + key)
            for key in ('detail', 'recommendation'):
                _text(finding.get(key, ''), 'Finding ' + key, empty=True)
            if finding['severity'] == 'good':
                excluded += 1
                continue
            rows.append({'id': case_id + ':' + str(ordinal), 'source_ordinal': ordinal,
                         'finding': finding,
                         'review': {**{key: 'pending' for key in DIMENSIONS}, 'reviewer': '',
                                    'reviewed_at': '', 'rationale': '', 'evidence': []}})
        meta = report.get('meta') if isinstance(report.get('meta'), dict) else {}
        cases.append({'id': case_id, 'report': entry['report'], 'report_sha256': digest,
                      'provenance': {key: report.get(key) for key in
                                     ('schema_version', 'tool_version', 'url', 'final_url', 'status', 'rendered')},
                      'recorded_extraction': meta.get('extraction'), 'recorded_scan_scope': meta.get('scan_scope'),
                      'evidence': attached, 'evidence_status': 'files_attached' if attached else 'report_only',
                      'excluded_good_findings': excluded, 'findings': rows})
    return {'schema_version': 1, 'name': manifest['name'], 'manifest_sha256': sha256(raw_manifest).hexdigest(),
            'basis': BASIS, 'cases': cases}


def summarize(manifest_path, packet):
    """Count labelled reviews; do not turn incomplete or biased review into accuracy."""
    expected = prepare(manifest_path)
    if not isinstance(packet, dict) or set(packet) != set(expected):
        raise ValueError('Invalid packet fields')
    if any(not _same(packet[key], expected[key]) for key in expected if key != 'cases'):
        raise ValueError('Packet manifest/protocol is stale or changed')
    if not isinstance(packet['cases'], list) or len(packet['cases']) != len(expected['cases']):
        raise ValueError('Case inventory changed')
    counts = {key: dict.fromkeys(VERDICTS, 0) for key in DIMENSIONS}
    reviewers, total, labelled, report_only = set(), 0, 0, 0
    for case, original in zip(packet['cases'], expected['cases']):
        if (not isinstance(case, dict) or set(case) != set(original)
                or any(not _same(case[key], original[key]) for key in original if key != 'findings')):
            raise ValueError('Case source or provenance changed')
        if not isinstance(case['findings'], list) or len(case['findings']) != len(original['findings']):
            raise ValueError('Finding inventory changed')
        report_only += case['evidence_status'] == 'report_only'
        evidence_ids = {item['id'] for item in case['evidence']}
        for row, source in zip(case['findings'], original['findings']):
            if (not isinstance(row, dict) or set(row) != set(source)
                    or any(not _same(row[key], source[key]) for key in source if key != 'review')):
                raise ValueError('Finding data changed')
            review = row['review']
            if not isinstance(review, dict) or set(review) != set(source['review']):
                raise ValueError('Invalid review fields')
            for key in DIMENSIONS:
                if review[key] not in VERDICTS:
                    raise ValueError('Unknown review verdict')
            for key in ('reviewer', 'reviewed_at', 'rationale'):
                _text(review[key], 'Review ' + key, empty=True)
            refs = review['evidence']
            if not isinstance(refs, list) or any(not isinstance(ref, str) or ref not in evidence_ids for ref in refs):
                raise ValueError('Review evidence must reference attached file IDs')
            touched = any(review[key] != 'pending' for key in DIMENSIONS)
            if touched:
                _text(review['reviewer'], 'Reviewer')
                _text(review['rationale'], 'Review rationale')
                _timestamp(review['reviewed_at'])
                reviewers.add(review['reviewer'])
            if any(review[key] in ('supported', 'unsupported') for key in DIMENSIONS) and not refs:
                raise ValueError('Supported/unsupported judgements require attached evidence')
            total += 1
            labelled += all(review[key] != 'pending' for key in DIMENSIONS)
            for key in DIMENSIONS:
                counts[key][review[key]] += 1
    if not total:
        status = 'no_actionable_findings'
    elif all(counts[key]['pending'] == total for key in DIMENSIONS):
        status = 'pending'
    elif labelled == total:
        status = 'fully_labelled'
    else:
        status = 'partial'
    return {'schema_version': 1, 'interpretation': 'review_coverage_only',
            'review_status': status, 'case_count': len(expected['cases']),
            'finding_count': total, 'fully_labelled_findings': labelled,
            'report_only_cases': report_only, 'cases_with_attached_files': len(expected['cases']) - report_only,
            'self_reported_reviewer_labels': sorted(reviewers), 'verdict_counts': counts,
            'accuracy_metrics': None, 'recall_metrics': None, 'basis': BASIS}


def markdown(summary):
    """Render fixed labels and counts only, never untrusted finding text as Markdown."""
    lines = ['# Reported-finding review coverage', '', 'Status: ' + summary['review_status'], '',
             f"Cases: {summary['case_count']}; report-only cases: {summary['report_only_cases']}; "
             f"actionable findings: {summary['finding_count']}; fully labelled: {summary['fully_labelled_findings']}.", '',
             '| Dimension | Pending | Supported | Unsupported | Uncertain | Not applicable |',
             '|:--|--:|--:|--:|--:|--:|']
    for key in DIMENSIONS:
        lines.append('| ' + key + ' | ' + ' | '.join(str(summary['verdict_counts'][key][v]) for v in VERDICTS) + ' |')
    return '\n'.join(lines + ['', 'Accuracy and recall: not measured.', '', BASIS, ''])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('prepare', help='Create a new pending packet; never overwrite')
    build.add_argument('manifest')
    build.add_argument('-o', '--output', required=True)
    read = commands.add_parser('summarize', help='Validate against original files and summarize review coverage')
    read.add_argument('manifest')
    read.add_argument('packet')
    read.add_argument('--format', choices=('json', 'markdown'), default='json')
    read.add_argument('-o', '--output')
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            result = prepare(args.manifest)
        else:
            packet = _json(_read(Path(args.packet), MAX_PACKET_BYTES))
            result = summarize(args.manifest, packet)
        rendered = (markdown(result) if getattr(args, 'format', None) == 'markdown'
                    else json.dumps(result, indent=2, ensure_ascii=not bool(args.output), allow_nan=False) + '\n')
        if len(rendered.encode('utf-8')) > MAX_PACKET_BYTES:
            raise ValueError('Output byte limit exceeded; split the corpus')
        if args.output:
            with Path(args.output).open('x', encoding='utf-8') as handle:
                handle.write(rendered)
        else:
            print(rendered, end='')
        return 0
    except (OSError, ValueError, RecursionError) as exc:
        print('Review corpus error: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
