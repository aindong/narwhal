"""XML sitemap parsing and validation (pure helpers, no network).

Handles both ``<urlset>`` (page lists) and ``<sitemapindex>`` (nested sitemaps),
gzip-decodes ``.gz`` payloads, and validates ``<loc>`` and ``<lastmod>`` values.
The orchestration (fetching, recursion, 404 sampling) lives in
``validate_sitemap.py`` and uses these helpers.
"""

from __future__ import annotations

import gzip
import re
from urllib.parse import urlparse

_LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.I | re.S)
_LASTMOD = re.compile(r"<lastmod>\s*(.*?)\s*</lastmod>", re.I | re.S)
# W3C Datetime (sitemaps.org): date or dateTime with optional time/zone.
_LASTMOD_FMT = re.compile(
    r"^\d{4}(-\d{2}(-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?)?)?)?$"
)


def decode(raw: bytes) -> str:
    """Decode sitemap bytes to text, transparently gunzipping ``.gz`` payloads."""
    if raw[:2] == b"\x1f\x8b":  # gzip magic number
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
    return raw.decode("utf-8", "replace")


def kind_of(text: str) -> str:
    low = text.lower()
    if "<sitemapindex" in low:
        return "index"
    if "<urlset" in low:
        return "urlset"
    return "unknown"


def parse(text: str):
    """Return ``(kind, entries)`` where each entry is ``{loc, lastmod}``.

    ``kind`` is ``"index"``, ``"urlset"``, or ``"unknown"``.
    """
    kind = kind_of(text)
    tag = "sitemap" if kind == "index" else "url"
    entries = []
    for block in re.findall(rf"<{tag}\b[^>]*>(.*?)</{tag}>", text, re.I | re.S):
        loc = _LOC.search(block)
        if not loc:
            continue
        lm = _LASTMOD.search(block)
        entries.append({"loc": loc.group(1).strip(),
                        "lastmod": lm.group(1).strip() if lm else None})
    if not entries:  # fallback: a bare list of <loc> with no wrapping tags
        entries = [{"loc": l.strip(), "lastmod": None} for l in _LOC.findall(text)]
    return kind, entries


def valid_lastmod(value) -> bool:
    """True if ``value`` is a valid W3C Datetime (sitemaps.org lastmod format)."""
    return bool(value) and bool(_LASTMOD_FMT.match(value.strip()))


def loc_problem(loc: str, host: str = None):
    """Return a problem label for a ``<loc>`` value, or None if it's fine."""
    try:
        p = urlparse(loc)
        p.port  # urllib validates numeric/range constraints lazily
        hostname = p.hostname
    except ValueError:
        return "invalid-url"
    if p.scheme not in ("http", "https") or not p.netloc:
        return "not-absolute"
    if not hostname:
        return "invalid-url"
    if host and p.netloc.lower() != host.lower():
        return "cross-host"
    return None


REFERENCE_KINDS = ('robots_directives', 'index_locations', 'page_locations')


def usable_locations(values, *, diagnostics=None, source='page_locations'):
    """Keep absolute HTTP source references; count rejections without I/O."""
    usable = []
    for value in values:
        value = value.strip()
        if loc_problem(value):
            if diagnostics is not None:
                diagnostics[source] = diagnostics.get(source, 0) + 1
        else:
            usable.append(value)
    return usable


def robots_sitemaps(text, *, diagnostics=None):
    """Read Sitemap directives without trusting their values as fetch inputs."""
    values = []
    for raw in (text or '').splitlines():
        field, separator, value = raw.split('#', 1)[0].partition(':')
        if separator and field.strip().lower() == 'sitemap':
            values.append(value.strip())
    return usable_locations(values, diagnostics=diagnostics, source='robots_directives')


def reference_diagnostics(counts):
    """Own at most three positive scalar source counts, never URLs or errors."""
    if not isinstance(counts, dict):
        return None
    rejected = {key: counts[key] for key in REFERENCE_KINDS
                if type(counts.get(key)) is int and counts[key] > 0}
    return {'basis': 'absolute_http_url_syntax', 'rejected': rejected} if rejected else None


def recorded_reference_diagnostics(value):
    """Read only a recognized receipt; missing legacy data stays unverified."""
    if not isinstance(value, dict) or value.get('basis') != 'absolute_http_url_syntax':
        return None
    return reference_diagnostics(value.get('rejected'))


def reference_note(value):
    """Describe rejected source references separately from HTTP failures."""
    receipt = recorded_reference_diagnostics(value)
    if receipt is None:
        return None
    labels = {'robots_directives': 'robots.txt directive(s)',
              'index_locations': 'index location(s)', 'page_locations': 'page location(s)'}
    counts = ', '.join(f'{n} {labels[key]}' for key, n in receipt['rejected'].items())
    return (f'Rejected sitemap URL references ({counts}): not absolute HTTP(S) URLs or '
            'parser-invalid hosts/ports. Omitted before fetching or sampling; not HTTP failures. '
            'Counts cover examined references, not complete site validation.')
