"""robots.txt parsing and path matching (RFC 9309 / Google semantics).

Implements the rules that matter for correctness:
- **User-agent groups**: the most specific matching agent wins; ``*`` is the
  fallback. Multiple user-agent lines can share one rule block.
- **Wildcards**: ``*`` matches any run of characters, ``$`` anchors the URL end.
- **Longest-match precedence**: among matching rules, the one with the longest
  pattern applies; on an equal-length tie, ``Allow`` beats ``Disallow``.
- An empty ``Disallow:`` means "allow everything".
- URI comparison normalizes unreserved escapes and UTF-8, preserving encoded
  reserved characters and literal encoded wildcard/end-marker characters.

Used by the GEO auditor (AI-crawler access) and the polite site crawler.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse


_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_HEX = frozenset("0123456789abcdefABCDEF")


def _comparison_path(value: str, *, pattern=False) -> str:
    """Canonicalize comparison octets, not URI structure or repeated escapes."""
    out, i = [], 0
    while i < len(value):
        char = value[i]
        if (char == "%" and i + 2 < len(value)
                and value[i + 1] in _HEX and value[i + 2] in _HEX):
            octet = int(value[i + 1:i + 3], 16)
            decoded = chr(octet)
            out.append(decoded if decoded in _UNRESERVED else f"%{octet:02X}")
            i += 3
            continue
        operator = pattern and (char == "*" or (char == "$" and i == len(value) - 1))
        if ord(char) > 127 or (char in "*$" and not operator):
            out.extend(f"%{octet:02X}" for octet in char.encode("utf-8"))
        else:
            out.append(char)
        i += 1
    return "".join(out)


class RobotsTxt:
    def __init__(self):
        # user-agent (lowercased) -> list of (kind, pattern)
        self._groups: dict = {}
        self.sitemaps: list = []

    # ---- parsing ---------------------------------------------------------
    @classmethod
    def parse(cls, text: str) -> "RobotsTxt":
        rt = cls()
        if not text:
            return rt
        current_agents: list = []
        last_was_rule = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            field, _, value = line.partition(":")
            field = field.strip().lower()
            value = value.strip()

            if field == "user-agent":
                if last_was_rule:
                    current_agents = []
                    last_was_rule = False
                ua = value.lower()
                current_agents.append(ua)
                rt._groups.setdefault(ua, [])
            elif field in ("allow", "disallow"):
                for ua in current_agents:
                    rt._groups[ua].append((field, value))
                last_was_rule = True
            elif field == "sitemap":
                rt.sitemaps.append(value)
        return rt

    # ---- querying --------------------------------------------------------
    def allowed(self, url_or_path: str, user_agent: str) -> bool:
        """Is ``user_agent`` allowed to fetch ``url_or_path``?"""
        path = _comparison_path(self._path(url_or_path))
        rules = self._rules_for(user_agent)
        if not rules:
            return True  # no applicable group => allowed

        best_len = -1
        best_allow = True
        for kind, pattern in rules:
            if pattern == "":
                continue  # empty Disallow/Allow matches nothing
            length = _match_len(pattern, path)
            if length < 0:
                continue
            if length > best_len:
                best_len, best_allow = length, (kind == "allow")
            elif length == best_len and kind == "allow":
                best_allow = True  # Allow wins an equal-length tie
        if best_len < 0:
            return True
        return best_allow

    def disallowed(self, url_or_path: str, user_agent: str) -> bool:
        return not self.allowed(url_or_path, user_agent)

    def _rules_for(self, user_agent: str) -> list:
        """Return the rule list for the most specific matching group.

        A robots user-agent token matches when it is a case-insensitive prefix of
        the crawler's product token (so ``googlebot`` matches ``Googlebot`` and
        ``Googlebot-News``, but ``adsbot-google`` does not match a bare ``Bot``).
        The longest matching token wins; ``*`` is the fallback.
        """
        ua = user_agent.lower()
        best_key = None
        for key in self._groups:
            if key == "*" or not key:
                continue
            if ua.startswith(key):
                if best_key is None or len(key) > len(best_key):
                    best_key = key
        if best_key is not None:
            return self._groups[best_key]
        return self._groups.get("*", [])

    @staticmethod
    def _path(url_or_path: str) -> str:
        if "://" in url_or_path or url_or_path.startswith("//"):
            parts = urlparse(url_or_path)
            path = parts.path or "/"
            if parts.query:
                path += "?" + parts.query
        else:
            path = url_or_path or "/"
        if not path.startswith("/"):
            path = "/" + path
        return path


def _match_len(pattern: str, path: str) -> int:
    """Match a rule to a canonical target; measure normalized rule specificity."""
    pattern = _comparison_path(pattern, pattern=True)
    end_anchor = ""
    p = pattern
    if p.endswith("$"):
        end_anchor = "$"
        p = p[:-1]
    regex = "^" + "".join(".*" if ch == "*" else re.escape(ch) for ch in p) + end_anchor
    return len(pattern) if re.search(regex, path) else -1
