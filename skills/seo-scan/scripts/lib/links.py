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
LEGACY_RESOLUTION_BASIS = 'relative_path_merge_preserve_separators_v1'
RESOLUTION_BASIS = 'first_declared_base_relative_path_merge_v2'
KNOWN_RESOLUTION_BASES = (LEGACY_RESOLUTION_BASIS, RESOLUTION_BASIS)
DOCUMENT_BASE_BASIS = 'first_non_template_base_href_declared_http_v1'
BASE_ERROR = 'Declared anchor-base coverage is unassessed; technical/overall score comparisons are unverified.'
_BASE_URI = re.compile(r'(?:^|[;,])\s*base-uri(?:\s|[;,]|$)', re.I)


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


def document_base(doc, base_url: str, *, csp=''):
    """Resolve a bounded declared base, not a browser/CSP or fetch permission proof.

    Unsupported bases withhold base-dependent targets; do not fabricate a
    document-URL fallback. Receipts contain no source URL or parser exception.
    """
    href = getattr(doc, 'base_href', None)
    if href is None:
        return base_url, None
    value = href.strip()
    receipt = {'basis': DOCUMENT_BASE_BASIS, 'status': 'document_url'}
    if not value or value.startswith('#'):
        return base_url, receipt
    scheme = _SCHEME.match(value)
    if scheme and scheme.group(1).lower() in ('data', 'javascript'):
        receipt['status'] = 'ignored_scheme'
        return base_url, receipt
    policies = [csp] + [(meta.get('content') or '') for meta in getattr(doc, 'meta', [])
                        if (meta.get('http-equiv') or '').strip().lower() == 'content-security-policy']
    if any(_BASE_URI.search(policy or '') for policy in policies):
        return None, dict(receipt, status='unverified', reason='base_uri_policy')
    if any(ord(c) <= 32 or ord(c) == 127 or c.isspace() for c in value) or '\\' in value or value.startswith('///'):
        return None, dict(receipt, status='unverified', reason='unsupported_reference')
    if scheme and scheme.group(1).lower() not in ('http', 'https'):
        return None, dict(receipt, status='non_http')
    try:
        effective = resolve_http_link(value, base_url)
        parts = urlsplit(effective or '')
        if not effective or parts.username is not None:
            return None, dict(receipt, status='unverified', reason='unsupported_reference')
    except ValueError:
        return None, dict(receipt, status='unverified', reason='syntax')
    return effective, dict(receipt, status='declared_http')


def resolve_anchor(href: str, base_url: str, effective_base, *, diagnostics=None):
    """Resolve an anchor with an assessed base, retaining independent absolute URLs."""
    if effective_base is not None:
        return resolve_http_link(href, effective_base)
    value = href.strip()
    scheme = _SCHEME.match(value)
    if not value or value.startswith('#') or (scheme and scheme.group(1).lower() not in ('http', 'https')):
        return None
    parts = urlsplit(value)
    if parts.netloc:
        parts.port  # source syntax can be invalid independently of a base
    if parts.scheme and parts.netloc:
        return resolve_http_link(value, base_url)
    if diagnostics is not None:
        diagnostics['unassessed_base_occurrences'] = diagnostics.get('unassessed_base_occurrences', 0) + 1
    return None


def base_note(meta):
    """Explain only a recognized declared-base receipt, never echo source secrets."""
    receipt = meta.get('anchor_base') if isinstance(meta, dict) else None
    if not isinstance(receipt, dict) or receipt.get('basis') != DOCUMENT_BASE_BASIS:
        return ''
    status = receipt.get('status')
    if status in ('unverified', 'non_http'):
        return ('Declared anchor base is unassessed for HTTP target collection; base-dependent references are omitted, '
                'not reported as dead or as malformed anchor URLs. Inspect the first base, CSP and browser behavior '
                'before source edits or broader crawling. Absolute HTTP(S) anchors remain independently assessable.')
    if status == 'declared_http':
        return ('Anchor targets use the first declared non-template base href. This is local declaration resolution, '
                'not verified browser execution, CSP enforcement or permission to fetch another host.')
    return ''


def unassessed_base(meta):
    """Only an explicit supported receipt establishes this known coverage gap."""
    receipt = meta.get('anchor_base') if isinstance(meta, dict) else None
    return (isinstance(receipt, dict) and receipt.get('basis') == DOCUMENT_BASE_BASIS
            and receipt.get('status') in ('unverified', 'non_http'))


def extract_links(doc, base_url: str, *, diagnostics=None, csp='') -> list:
    """Return unique outbound links from ``doc`` as ``[{url, internal}]``.

    Uses the first declared document base when supported, drops fragments and non-HTTP
    schemes (mailto/tel/…), and marks each link internal or external by host.
    Known malformed hrefs are omitted, not assigned a network-failure status.
    Optional diagnostics counts occurrences without retaining raw URLs/errors.
    """
    host = urlparse(base_url).netloc.lower()
    effective, receipt = document_base(doc, base_url, csp=csp)
    if receipt is not None and diagnostics is not None:
        diagnostics['anchor_base'] = receipt
    seen, out = set(), []
    for a in doc.links:
        try:
            full = resolve_anchor(a.get("href") or "", base_url, effective, diagnostics=diagnostics)
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
