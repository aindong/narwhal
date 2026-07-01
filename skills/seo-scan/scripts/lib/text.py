"""Lightweight text analysis: readability + keyword/entity extraction.

Pure, dependency-free heuristics used by the content auditor. Nothing here is
exact linguistics — the goal is directional signals: is this hard to read, and
what is it actually about?
"""

from __future__ import annotations

import re
from collections import Counter

_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
_SENT = re.compile(r"[.!?]+")
# Multi-word Capitalized runs — naive proper-noun / entity candidates.
_PROPER = re.compile(r"\b[A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)+\b")
_VOWELS = "aeiouy"

STOPWORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "any", "can", "her",
    "was", "one", "our", "out", "day", "get", "has", "him", "his", "how", "man",
    "new", "now", "old", "see", "two", "way", "who", "boy", "did", "its", "let",
    "put", "say", "she", "too", "use", "that", "this", "with", "from", "they",
    "will", "would", "there", "their", "what", "about", "which", "when", "your",
    "have", "more", "some", "than", "them", "then", "into", "just", "over",
    "also", "such", "only", "very", "were", "been", "being", "these", "those",
    "here", "each", "other", "http", "https", "www", "com", "org",
}


def words(text: str) -> list:
    return _WORD.findall(text or "")


def sentences(text: str) -> list:
    return [s for s in _SENT.split(text or "") if s.strip()]


def syllables(word: str) -> int:
    """Heuristic syllable count (vowel groups, minus a common silent 'e')."""
    w = word.lower().strip("'-")
    if not w:
        return 0
    count, prev_vowel = 0, False
    for ch in w:
        is_vowel = ch in _VOWELS
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    # Subtract a trailing silent 'e' (code, make) — but NOT a consonant+'le'
    # ending, where the 'le' is its own syllable (apple, table, little).
    if w.endswith("e") and not w.endswith("le") and count > 1:
        count -= 1
    return max(1, count)


def flesch_reading_ease(text: str):
    w, s = words(text), sentences(text)
    if not w or not s:
        return None
    syl = sum(syllables(x) for x in w)
    return round(206.835 - 1.015 * (len(w) / len(s)) - 84.6 * (syl / len(w)), 1)


def flesch_kincaid_grade(text: str):
    w, s = words(text), sentences(text)
    if not w or not s:
        return None
    syl = sum(syllables(x) for x in w)
    return round(0.39 * (len(w) / len(s)) + 11.8 * (syl / len(w)) - 15.59, 1)


def reading_ease_label(score) -> str:
    if score is None:
        return "unknown"
    if score >= 70:
        return "easy"
    if score >= 50:
        return "moderate"
    if score >= 30:
        return "difficult"
    return "very difficult"


def top_keywords(text: str, n: int = 10) -> list:
    """Most frequent meaningful unigrams as ``[(term, count)]``."""
    toks = [w.lower() for w in words(text)
            if len(w) >= 3 and w.lower() not in STOPWORDS]
    return Counter(toks).most_common(n)


def top_bigrams(text: str, n: int = 5) -> list:
    """Most frequent two-word phrases (skipping stopwords) as ``[(phrase, count)]``."""
    counts, prev = Counter(), None
    for w in (x.lower() for x in words(text)):
        if len(w) < 3 or w in STOPWORDS:
            prev = None
            continue
        if prev:
            counts[f"{prev} {w}"] += 1
        prev = w
    return counts.most_common(n)


def candidate_entities(text: str, n: int = 8) -> list:
    """Repeated multi-word Capitalized phrases — naive named-entity candidates."""
    counts = Counter(m.strip() for m in _PROPER.findall(text or ""))
    ranked = [(k, c) for k, c in counts.items() if c >= 2]
    ranked.sort(key=lambda kv: -kv[1])
    return ranked[:n]
