"""SimHash near-duplicate detection (pure, deterministic, no deps).

Fingerprints text into a 64-bit SimHash over word-shingles. Two near-identical
pages produce fingerprints a small Hamming distance apart, so duplicate content
can be detected across a crawl without comparing every page word-for-word.

Deterministic across processes (uses md5, not the salted built-in ``hash``), so
results are reproducible and testable.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter

_WORD = re.compile(r"[a-z0-9]+")
BITS = 64


def _tokens(text: str) -> list:
    return _WORD.findall((text or "").lower())


def shingle_counts(text: str, k: int = 4) -> Counter:
    """Frequency-weighted overlapping k-word shingles (tokens for short text).

    Weighting by frequency is what makes SimHash robust: on a long document a
    small edit changes only a few low-frequency shingles, so the fingerprint —
    dominated by the many repeated ones — barely moves.
    """
    toks = _tokens(text)
    if len(toks) < k:
        return Counter(toks)
    return Counter(" ".join(toks[i:i + k]) for i in range(len(toks) - k + 1))


def shingles(text: str, k: int = 4) -> set:
    """Distinct k-word shingles (set view of :func:`shingle_counts`)."""
    return set(shingle_counts(text, k))


def _hash64(feature: str) -> int:
    return int.from_bytes(hashlib.md5(feature.encode("utf-8")).digest()[:8], "big")


def simhash(text: str, k: int = 4) -> int:
    """64-bit SimHash of ``text`` (frequency-weighted). Returns 0 for empty input."""
    feats = shingle_counts(text, k)
    if not feats:
        return 0
    vector = [0] * BITS
    for feature, weight in feats.items():
        h = _hash64(feature)
        for i in range(BITS):
            vector[i] += weight if (h >> i) & 1 else -weight
    out = 0
    for i in range(BITS):
        if vector[i] > 0:
            out |= (1 << i)
    return out


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def similarity(a: int, b: int) -> float:
    """Percentage similarity (0–100) between two fingerprints."""
    return round((1 - hamming(a, b) / BITS) * 100, 1)


def distance_for(threshold_pct: float) -> int:
    """Max Hamming distance corresponding to a similarity-percent threshold."""
    return int(round(BITS * (1 - threshold_pct / 100.0)))


def cluster(items: list, threshold_pct: float = 90.0) -> list:
    """Group near-duplicate items.

    ``items`` is a list of ``(key, fingerprint)``. Returns a list of clusters
    (lists of keys) where every member is within the similarity threshold of at
    least one other member (transitive). Singletons are omitted.
    """
    max_dist = distance_for(threshold_pct)
    n = len(items)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    for i in range(n):
        for j in range(i + 1, n):
            if hamming(items[i][1], items[j][1]) <= max_dist:
                union(i, j)

    groups: dict = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(items[i][0])
    return [g for g in groups.values() if len(g) > 1]
