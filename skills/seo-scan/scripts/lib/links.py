"""Link extraction and broken-link classification.

Pure helpers (no network) used by the crawler's broken-link checker: pull the
resolvable outbound links from a parsed page, classify internal vs external, and
decide which HTTP results count as broken.
"""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

# Non-navigational hrefs we should never HTTP-check.
SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:", "sms:", "callto:")


def extract_links(doc, base_url: str) -> list:
    """Return unique outbound links from ``doc`` as ``[{url, internal}]``.

    Resolves relative hrefs against ``base_url``, drops fragments and non-HTTP
    schemes (mailto/tel/…), and marks each link internal or external by host.
    """
    host = urlparse(base_url).netloc.lower()
    seen, out = set(), []
    for a in doc.links:
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#"):
            continue
        if href.lower().startswith(SKIP_SCHEMES):
            continue
        full = urljoin(base_url, href).split("#")[0]
        parts = urlparse(full)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            continue
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
