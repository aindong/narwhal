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
    p = urlparse(loc)
    if p.scheme not in ("http", "https") or not p.netloc:
        return "not-absolute"
    if host and p.netloc.lower() != host.lower():
        return "cross-host"
    return None
