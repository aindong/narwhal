#!/usr/bin/env python3
"""Opt-in local scan snapshots for review, never accuracy or SEO validation.

Writes a new directory only, with decoded source as inert .txt files. Uses the
normal guarded scanner; no added account integrations, metric APIs or publication workflow.
Snapshots may contain sensitive response headers/content: inspect before sharing.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from importlib import metadata as distribution_metadata
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/seo-scan/scripts'))
import scan
from lib import config as configlib
from lib import http
from lib.report import TOOL_VERSION

MAX_REPORT_BYTES = 2_000_000
MAX_EVIDENCE_BYTES = 5_000_000
MAX_CAPTURE_BYTES = 32_000_000
LIMITATIONS = [
    'Decoded response text/serialized DOM, not original HTTP wire bytes or authenticated origin evidence.',
    'Headers are the fetcher mapping plus available robots-field boundaries, not every raw header line.',
    'Site context retains inputs used by this scan, not all sitemap/llms response bodies or linked resources.',
    'Image-probe inputs, browser subresources, redirect response bodies and live indexing are not captured.',
    'Capture timestamps describe this local acquisition window, not content freshness or response authenticity.',
    'Attached files and hashes do not establish completeness, scanner accuracy, reviewer independence or SEO outcomes.',
]


def _json_bytes(value):
    """Emit finite UTF-8 JSON; artifact limits are not total heap/CPU limits."""
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')


def _response_meta(response, source_path):
    """Preserve available fields without reconstructing missing raw boundaries."""
    return {**{key: getattr(response, key) for key in
               ('url', 'final_url', 'status', 'headers', 'elapsed_ms', 'rendered',
                'redirects', 'error', 'robots_header_fields', 'robots_header_basis')},
            'decoded_source': source_path}


def _write_new(path, raw):
    """Exclusive owner-only file creation, not atomic/durable bundle publication."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
    descriptor = os.open(str(path), flags, 0o600)
    with os.fdopen(descriptor, 'wb') as handle:
        handle.write(raw)


def _runtime():
    """Record installed versions, not an inference about the parser actually used."""
    packages = {}
    for name in ('requests', 'beautifulsoup4', 'lxml', 'trafilatura', 'playwright'):
        try:
            packages[name] = distribution_metadata.version(name)
        except (distribution_metadata.PackageNotFoundError, OSError, ValueError):
            packages[name] = None
    return {'python': sys.version, 'implementation': sys.implementation.name,
            'platform': sys.platform, 'optional_distributions': packages,
            'basis': 'installed_version_inventory_not_backend_selection_proof'}


def capture(url, destination, *, case_id, render=False, allow_private=False,
            timeout=20, only=None, check_images=True, max_bytes=5_000_000,
            source_revision=None):
    """Record one normal scan in an exclusive directory; never re-fetch evidence.

    Failures leave partial files for inspection, possibly a partial manifest.
    The manifest is written last, not as an atomic/durable transaction.
    Successful recording can still describe a failed/unmeasured/partial scan.
    No redaction is automatic: record any later redactions and regenerate packets.
    """
    if not isinstance(case_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', case_id):
        raise ValueError('case_id must be a simple 1–80-character identifier')
    if source_revision is not None and (not isinstance(source_revision, str)
                                        or not source_revision.strip() or len(source_revision) > 160):
        raise ValueError('source_revision must be a nonempty declaration of at most 160 characters')
    if type(timeout) is not int or not 1 <= timeout <= 120:
        raise ValueError('timeout must be 1–120 seconds')
    if type(max_bytes) is not int or not 64_000 <= max_bytes <= 20_000_000:
        raise ValueError('max_bytes must be 64KB–20MB')
    if any(type(value) is not bool for value in (render, allow_private, check_images)):
        raise ValueError('render, allow_private and check_images must be booleans')
    selected = list(dict.fromkeys(only or list(scan.AUDITORS)))
    if any(name not in scan.AUDITORS for name in selected):
        raise ValueError('Unknown auditor group')
    normalized = http.normalize_url(url)
    parsed = urlparse(normalized)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError('Capture URLs must not include credentials')
    destination = Path(destination)
    # Reserve before DNS/network activity; existing paths are never reused.
    destination.mkdir(mode=0o700)
    started = datetime.now(timezone.utc).isoformat()
    config = configlib.Config()  # explicit defaults; no ambient narwhal.toml discovery
    report = scan.scan(normalized, render=render, allow_private=allow_private,
                       timeout=timeout, only=selected, config=config,
                       check_images=check_images, max_bytes=max_bytes, retain_evidence=True)
    finished = datetime.now(timezone.utc).isoformat()
    inputs = report._capture_inputs
    primary, served = inputs['primary_response'], inputs['served_response']
    blobs = {'report.json': report.to_json().encode('utf-8') + b'\n',
             'page-source.txt': primary.text.encode('utf-8'),
             'site-context.json': _json_bytes(inputs['site_context'])}
    source_kind = ('declared_error_response_text' if primary.error else
                   'declared_rendered_dom' if primary.rendered else 'declared_decoded_response_text')
    evidence = [{'id': 'page-source', 'path': 'page-source.txt', 'kind': source_kind,
                 'captured_at': finished},
                {'id': 'site-context', 'path': 'site-context.json',
                 'kind': 'declared_scan_context_inputs_not_complete_network_capture', 'captured_at': finished}]
    if served is not None:
        blobs['served-source.txt'] = served.text.encode('utf-8')
        evidence.append({'id': 'served-source', 'path': 'served-source.txt',
                         'kind': 'declared_decoded_comparison_response_text', 'captured_at': finished})
    metadata = {
        'schema_version': 1, 'interpretation': 'captured_inputs_only_pending_review',
        'capture_started_at': started, 'capture_finished_at': finished,
        'scanner_tool_version': TOOL_VERSION,
        'runtime': _runtime(),
        'declared_source_revision': source_revision,
        'revision_basis': 'operator_supplied_unverified' if source_revision is not None else 'not_recorded',
        'settings': {'render_requested': bool(render), 'allow_private': bool(allow_private),
                     'timeout': timeout, 'only': selected, 'check_images': bool(check_images),
                     'max_bytes': max_bytes, 'config_basis': 'explicit_default_config_no_discovery',
                     'weights': config.weights, 'thresholds': config.thresholds},
        'primary_response': _response_meta(primary, 'page-source.txt'),
        'served_comparison_response': _response_meta(served, 'served-source.txt') if served is not None else None,
        'scan_coverage': report.meta.get('coverage'),
        'files': {name: {'bytes': len(raw), 'sha256': sha256(raw).hexdigest()} for name, raw in blobs.items()},
        'limitations': LIMITATIONS,
        'privacy': 'Local files may contain sensitive headers/content. No automatic redaction or publication.',
    }
    blobs['capture.json'] = _json_bytes(metadata)
    evidence.append({'id': 'capture', 'path': 'capture.json', 'kind': 'declared_local_acquisition_metadata',
                     'captured_at': finished})
    manifest = {'schema_version': 1, 'name': 'Captured scan inputs — not validated',
                'cases': [{'id': case_id, 'report': 'report.json', 'evidence': evidence}]}
    blobs['manifest.json'] = _json_bytes(manifest)
    if any(len(raw) > (MAX_REPORT_BYTES if name == 'report.json' else MAX_EVIDENCE_BYTES)
           for name, raw in blobs.items()) or sum(map(len, blobs.values())) > MAX_CAPTURE_BYTES:
        raise ValueError('Capture artifact byte limit exceeded; no completion manifest was written')
    # Manifest last: an interrupted/failed write is not a completed bundle.
    for name, raw in blobs.items():
        _write_new(destination / name, raw)
    return manifest


def main(argv=None):
    """Explicit capture command; never adds a public narwhal subcommand."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--output-dir', required=True, help='new directory; parent must already exist')
    parser.add_argument('--case-id', required=True)
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--allow-private', action='store_true')
    parser.add_argument('--no-image-checks', action='store_true')
    parser.add_argument('--only', help='comma-separated auditor groups')
    parser.add_argument('--timeout', type=int, default=20, help='per-request seconds, not a total capture deadline')
    parser.add_argument('--max-bytes', type=int, default=5_000_000,
                        help='per HTML snapshot budget; review evidence still has a separate 5MB/file limit')
    parser.add_argument('--source-revision', help='optional operator declaration; not authenticated')
    args = parser.parse_args(argv)
    try:
        capture(args.url, args.output_dir, case_id=args.case_id, render=args.render,
                allow_private=args.allow_private, timeout=args.timeout,
                only=args.only.split(',') if args.only is not None else None,
                check_images=not args.no_image_checks, max_bytes=args.max_bytes,
                source_revision=args.source_revision)
    except (OSError, ValueError, RecursionError) as exc:
        print('Capture error: ' + str(exc)
              + '; any partial directory is retained for inspection, not a completed capture.', file=sys.stderr)
        return 2
    print('Recorded local scan inputs in ' + str(args.output_dir)
          + '; inspect sensitive content before sharing. Human review/accuracy remain unmeasured.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
