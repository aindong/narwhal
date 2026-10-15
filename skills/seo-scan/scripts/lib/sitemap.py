"""XML sitemap parsing and validation (pure helpers, no network).

Handles both ``<urlset>`` (page lists) and ``<sitemapindex>`` (nested sitemaps),
gzip-decodes ``.gz`` payloads, and validates ``<loc>`` and ``<lastmod>`` values.
The orchestration (fetching, recursion, 404 sampling) lives in
``validate_sitemap.py`` and uses these helpers.
"""

from __future__ import annotations

import gzip
import io
import re
import zlib
from urllib.parse import urlparse
from xml.parsers import expat

_LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.I | re.S)
_LASTMOD = re.compile(r"<lastmod>\s*(.*?)\s*</lastmod>", re.I | re.S)
# W3C Datetime (sitemaps.org): date or dateTime with optional time/zone.
_LASTMOD_FMT = re.compile(
    r"^\d{4}(-\d{2}(-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?)?)?)?$"
)


# Uncompressed per-file ceiling from https://www.sitemaps.org/protocol.html.
MAX_DECODED_BYTES = 52_428_800


def decode_checked(raw: bytes, *, max_bytes=None):
    """Return (text, reason), withholding text on decode failure or byte limit.

    Sized reads bound retained gzip output before UTF-8 conversion. This is a
    per-file decoded-byte budget, not a total memory, CPU or transport budget.
    Concatenated members share the budget; no decoded prefix is returned.
    """
    max_bytes = MAX_DECODED_BYTES if max_bytes is None else max_bytes
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError('Decoded sitemap byte budget must be a positive integer.')
    if raw[:2] == b"\x1f\x8b":
        decoded = bytearray()
        try:
            with io.BytesIO(raw) as source, gzip.GzipFile(fileobj=source, mode='rb') as stream:
                while True:
                    chunk = stream.read(min(65_536, max_bytes + 1 - len(decoded)))
                    if not chunk:
                        break
                    decoded.extend(chunk)
                    if len(decoded) > max_bytes:
                        return '', 'decoded_byte_limit'
        except (OSError, EOFError, zlib.error):
            return '', 'gzip_decode_failed'
    else:
        if len(raw) > max_bytes:
            return '', 'decoded_byte_limit'
        decoded = raw
    return decoded.decode('utf-8', 'replace'), None


def decode(raw: bytes) -> str:
    """Decode within the per-file budget; failed/unverified inputs yield no text."""
    return decode_checked(raw)[0]


def kind_of(text: str) -> str:
    """Legacy marker hint, not proof of complete XML extraction."""
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


MAX_XML_DEPTH = 128
MAX_XML_ELEMENTS = 500_000
MAX_XML_ENTRIES = 50_000
_SITEMAP_NS = 'http://www.sitemaps.org/schemas/sitemap/0.9'
XML_PARSE_REASONS = {
    'decoded_byte_limit': 'decoded sitemap byte limit reached',
    'gzip_decode_failed': 'gzip decoding could not be completed or integrity checked',
    'unparseable_xml': 'content could not be parsed as complete XML',
    'unrecognized_root': 'root/namespace is outside supported XML sitemap formats',
    'unsupported_dtd': 'DTD/entity declarations are outside the supported XML scope',
    'unsupported_entry_shape': 'entry location shape is missing, ambiguous or unsupported',
    'xml_depth_limit': 'XML nesting limit reached',
    'xml_element_limit': 'XML element limit reached',
    'entry_limit': 'sitemap entry limit reached',
}


class _XMLUnverified(Exception):
    """A bounded parser cannot establish complete supported extraction."""


def parse_checked(text: str):
    """Return (kind, entries, reason); withhold all entries on a coverage gap.

    This streaming parser does not build a DOM, fetch resources or validate an
    XSD. DTDs are declined before declarations/expansion; namespaces and direct
    URL fields are interpreted, including normal XML character escaping.
    """
    parser = expat.ParserCreate(namespace_separator='}')
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    path, entries = [], []
    kind, namespace, entry_name = 'unknown', '', ''
    current, value_buffer, value_key = None, None, None
    elements = 0

    def start(name, attrs):
        nonlocal kind, namespace, entry_name, current, value_buffer, value_key, elements
        elements += 1
        if elements > MAX_XML_ELEMENTS:
            raise _XMLUnverified('xml_element_limit')
        uri, _, local = name.rpartition('}')
        path.append((uri, local))
        if len(path) > MAX_XML_DEPTH:
            raise _XMLUnverified('xml_depth_limit')
        if len(path) == 1:
            if uri not in ('', _SITEMAP_NS) or local not in ('urlset', 'sitemapindex'):
                raise _XMLUnverified('unrecognized_root')
            namespace = uri
            kind = 'index' if local == 'sitemapindex' else 'urlset'
            entry_name = 'sitemap' if kind == 'index' else 'url'
        elif len(path) == 2 and path[-1] == (namespace, entry_name):
            current = {'loc': None, 'lastmod': None}
        elif (len(path) == 3 and current is not None
              and uri == namespace and local in ('loc', 'lastmod')):
            if local == 'loc' and current['loc'] is not None:
                raise _XMLUnverified('unsupported_entry_shape')
            value_key, value_buffer = local, []
        elif len(path) > 3 and value_buffer is not None:
            raise _XMLUnverified('unsupported_entry_shape')

    def end(name):
        nonlocal current, value_buffer, value_key
        if len(path) == 3 and value_buffer is not None:
            if current[value_key] is None:
                current[value_key] = ''.join(value_buffer).strip()
            value_buffer, value_key = None, None
        if len(path) == 2 and current is not None and path[-1] == (namespace, entry_name):
            if current['loc'] is None:
                raise _XMLUnverified('unsupported_entry_shape')
            if len(entries) >= MAX_XML_ENTRIES:
                raise _XMLUnverified('entry_limit')
            entries.append(current)
            current = None
        path.pop()

    def data(value):
        if value_buffer is not None:
            value_buffer.append(value)

    def decline_dtd(*args):
        raise _XMLUnverified('unsupported_dtd')

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = data
    parser.StartDoctypeDeclHandler = decline_dtd
    parser.EntityDeclHandler = decline_dtd
    parser.ExternalEntityRefHandler = decline_dtd
    try:
        parser.Parse(text, True)
    except _XMLUnverified as exc:
        return kind, [], exc.args[0]
    except expat.ExpatError:
        return kind, [], 'unparseable_xml'
    return kind, entries, None


def recorded_parse_coverage(value, fetched=None):
    """Recognize explicit fetched-file coverage without guessing legacy state."""
    if (not isinstance(value, dict) or value.get('basis') != 'bounded_xml_parse'
            or value.get('scope') != 'fetched_files'):
        return None
    if any(type(value.get(key)) is not int or value[key] < 0
           for key in ('verified_files', 'unverified_files')):
        return None
    reasons = value.get('reasons')
    if (not isinstance(reasons, dict) or any(key not in XML_PARSE_REASONS or type(n) is not int or n <= 0
                                           for key, n in reasons.items())
            or sum(reasons.values()) != value['unverified_files']):
        return None
    if fetched is not None and (type(fetched) is not int or fetched < 0
                               or value['verified_files'] + value['unverified_files'] != fetched):
        return None
    return {**value, 'reasons': dict(reasons)}


def parse_coverage_note(value, fetched=None):
    """Explain withheld measurements without declaring unsupported data invalid."""
    coverage = recorded_parse_coverage(value, fetched)
    if coverage is None:
        return 'XML extraction coverage was not recorded; verify source formats before trusting URL totals or a health verdict.'
    if not coverage['unverified_files']:
        return None
    reasons = '; '.join(f'{XML_PARSE_REASONS[key]} ({n})' for key, n in coverage['reasons'].items())
    limit = coverage.get('decoded_byte_limit')
    budget = (f'Decoded-byte budget: {limit:,} bytes per file. '
              if 'decoded_byte_limit' in coverage['reasons'] and type(limit) is int and limit > 0 else '')
    return (f"XML extraction unverified for {coverage['unverified_files']} fetched file(s): {reasons}. "
            + budget +
            'URL totals cover verified files only, not all sitemap content. '
            'Unsupported formats are not necessarily invalid; verify them separately.')


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
