"""Link extraction and broken-link classification.

Pure helpers (no network) used by the crawler's broken-link checker: pull the
resolvable outbound links from a parsed page, classify internal vs external, and
decide which HTTP results count as broken.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit

from .urlpaths import remove_dot_segments

# Non-navigational hrefs we should never HTTP-check.
SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:", "sms:", "callto:")
_SCHEME = re.compile(r'^([a-zA-Z][a-zA-Z0-9+.-]*):')
RESOLUTION_BASIS = 'relative_path_merge_preserve_separators_v1'


def resolve_http_link(href: str, base_url: str):
    """Resolve a source href without I/O; malformed HTTP syntax raises ValueError.

    Empty, fragment-only and non-HTTP references return None. This is not host
    authorization or complete URI validation: every fetch still needs HTTP guards.
    """
    href = href.strip()
    scheme = _SCHEME.match(href)
    if (not href or href.startswith('#') or href.lower().startswith(SKIP_SCHEMES)
            or (scheme and scheme.group(1).lower() not in ('http', 'https'))):
        return None
    full = urljoin(base_url, href).split('#')[0]
    reference = urlsplit(href)
    if reference.path and not reference.scheme and not reference.netloc and not reference.path.startswith('/'):
        # urllib.urljoin drops empty segments when merging relative paths.
        # Preserve their literal separators, including ones in the base path;
        # keep its existing scheme/authority/query handling outside this merge.
        origin = urlsplit(base_url)
        merged = (origin.path.rpartition('/')[0] + '/' if origin.path else '/') + reference.path
        parts = urlsplit(full)
        full = urlunsplit((parts.scheme, parts.netloc, remove_dot_segments(merged), parts.query, ''))
    parts = urlparse(full)
    if parts.scheme not in ('http', 'https'):
        return None
    if not parts.hostname:
        raise ValueError('HTTP link has no hostname')
    parts.port  # lazy numeric/range validation, also used at the fetch boundary
    return full


def extract_links(doc, base_url: str, *, diagnostics=None) -> list:
    """Return unique outbound links from ``doc`` as ``[{url, internal}]``.

    Resolves relative hrefs against ``base_url``, drops fragments and non-HTTP
    schemes (mailto/tel/…), and marks each link internal or external by host.
    Known malformed hrefs are omitted, not assigned a network-failure status.
    Optional diagnostics counts occurrences without retaining raw URLs/errors.
    """
    host = urlparse(base_url).netloc.lower()
    seen, out = set(), []
    for a in doc.links:
        try:
            full = resolve_http_link(a.get("href") or "", base_url)
        except ValueError:
            if diagnostics is not None:
                diagnostics['invalid_url_occurrences'] = diagnostics.get('invalid_url_occurrences', 0) + 1
            continue
        if full is None:
            continue
        parts = urlparse(full)
        if full in seen:
            continue
        seen.add(full)
        out.append({"url": full, "internal": parts.netloc.lower() == host})
    return out


# Codes that mean "exists but gated/throttled", not "dead". Treating these as
# broken produces false positives (bot-blocking, rate-limiting, login walls).
UNDETERMINED = {401, 403, 429, 451, 999}


def is_broken(status: int) -> bool:
    """A link is broken when unreachable (0) or the server returns a real 4xx/5xx.

    Access-restricted / rate-limited codes (401/403/429/451/999) are treated as
    *not* broken — they indicate gating, not a dead link, and flagging them would
    be noise.
    """
    if status == 0:
        return True
    if status in UNDETERMINED:
        return False
    return status >= 400
